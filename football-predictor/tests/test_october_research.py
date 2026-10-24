import importlib.util
from pathlib import Path

import pytest

from strategy.october_research import build_experiments, settle, summarize

spec = importlib.util.spec_from_file_location("october_runner", Path(__file__).resolve().parents[1] / "scripts/run_october_research.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

CONFIG = {"mode": "simulation_only", "real_money_allowed": False, "effective_from": "2026-10-02", "max_pairs_per_family": 12, "max_structure_matches": 4, "unit_stake": 2}


def rows(count=4):
    return [{"match_number": f"{i:03d}", "home_team": f"H{i}", "away_team": f"A{i}",
        "kickoff_time": "2026-10-05 20:00", "home_handicap": -1, "captured_at": "2026-10-05 18:30",
        "spf_odds_home": 2.6, "spf_odds_draw": 3.1, "spf_odds_away": 2.9,
        "rqspf_odds_home": 4.5, "rqspf_odds_draw": 3.4, "rqspf_odds_away": 1.7} for i in range(1, count + 1)]


def gate(count=4):
    return {"phase": "READY_FOR_FINAL_ANALYSIS", "may_create_plan": True, "failures": [],
        "as_of": "2026-10-05 18:31", "freshness": {"official_captured_at": "2026-10-05 18:30"},
        "deadlines": {"decision_start": "2026-10-05 18:30", "decision_lock": "2026-10-05 19:45", "sales_cutoff": "2026-10-05 20:00"},
        "expected_match_numbers": [f"{i:03d}" for i in range(1, count + 1)]}


def test_relaxed_candidates_include_low_confidence_and_multiple_structures():
    experiments, skips = build_experiments(rows(), CONFIG)
    assert len(experiments) > 2
    assert not skips
    assert all(exp["is_shadow"] and not exp["real_money_allowed"] for exp in experiments)
    assert len([exp for exp in experiments if exp["family"] == "structure_four_all_doubles"]) == 6
    assert any(exp["family"] == "anchor_double_cover" for exp in experiments)
    assert all(leg["probability_source"] == "market_implied_only" for exp in experiments for leg in exp["legs"])


def test_single_match_retains_theoretical_observations_without_fake_double():
    experiments, _ = build_experiments(rows(1), CONFIG)
    assert len(experiments) == 4
    assert all(exp["ticket_eligibility"] == "unverified_theoretical" for exp in experiments)


@pytest.mark.parametrize("when", ["2026-10-05 19:45", "2026-10-05 20:01", "2026-10-05 18:42"])
def test_gate_prevents_postlock_and_stale_freeze(when):
    with pytest.raises(ValueError):
        runner.freeze(rows(), gate(), runner.timestamp(when), CONFIG)


def test_wrong_snapshot_or_missing_batch_is_rejected():
    for markets in (rows()[:3], rows() + rows()[:1]):
        with pytest.raises(ValueError):
            runner.freeze(markets, gate(), runner.timestamp("2026-10-05 18:32"), CONFIG)
    markets = rows()
    markets[0]["captured_at"] = "2026-10-04 18:30"
    with pytest.raises(ValueError):
        runner.freeze(markets, gate(), runner.timestamp("2026-10-05 18:32"), CONFIG)


def test_exact_margin_settlement_and_ambiguous_results_stay_pending():
    experiments, _ = build_experiments(rows(1), CONFIG)
    snapshot = {"protocol_version": "test", "experiments": experiments}
    result = {"date": "2026-10-05", "match_number": "周一001", "home_team": "H1", "away_team": "A1", "status": "已完成", "full_time_score": "2:1"}
    review = settle(snapshot, [result])
    exact = next(row for row in review["settled"] if row["family"] == "rqspf_exact_margin")
    assert exact["payout"] == 6.8
    assert exact["net"] == 4.8
    assert not review["pending"]
    assert len(settle(snapshot, [result, result])["pending"]) == 4
    result["date"] = "2026-10-06"
    assert len(settle(snapshot, [result])["pending"]) == 4


def test_official_void_refunds_singles_without_counting_prediction_hit():
    experiments, _ = build_experiments(rows(1), CONFIG)
    snapshot = {'protocol_version':'void_test','experiments':experiments,'matches':rows(1)}
    result = {'date':'2026-10-05','match_number':'001','home_team':'H1','away_team':'A1','status':'已完成','full_time_score':'无效场次'}
    review = settle(snapshot,[result])
    assert not review['pending'] and not review['prediction_scores']
    assert all(r['payout']==r['stake'] and r['net']==0 and r['refund_only'] and not r['hit'] for r in review['settled'])
    result['full_time_score']=''
    assert len(settle(snapshot,[result])['pending'])==4
    result['full_time_score']='无效场次';result['status']='postponed'
    assert len(settle(snapshot,[result])['pending'])==4


def test_void_leg_removed_from_combo_and_other_leg_must_still_win():
    experiments,_=build_experiments(rows(2),CONFIG)
    experiment=next(e for e in experiments if e['family']=='spf_direction' and len(e['legs'])==2)
    snapshot={'protocol_version':'void_test','experiments':[experiment]}
    result=[{'date':'2026-10-05','match_number':f'{i:03}','home_team':f'H{i}','away_team':f'A{i}','status':'已完成','full_time_score':score} for i,score in [(1,'无效场次'),(2,'2:0')]]
    row=settle(snapshot,result)['settled'][0]
    assert row['payout']==pytest.approx(2*2.6) and row['void_match_numbers']==['001']
    result[1]['full_time_score']='0:1'
    assert settle(snapshot,result)['settled'][0]['payout']==0


def test_market_missing_prices_are_skipped_not_invented():
    markets = rows(1)
    markets[0]["rqspf_odds_draw"] = ""
    experiments, skips = build_experiments(markets, CONFIG)
    assert all(exp["family"].startswith("spf") for exp in experiments)
    assert len(skips) >= 2


def test_immutable_batch_file(tmp_path):
    path = tmp_path / "batch.json"
    runner.write_new(path, {"first": True})
    with pytest.raises(FileExistsError):
        runner.write_new(path, {"first": False})
    assert 'true' in path.read_text()


def test_native_updated_at_snapshot_and_summary_pending_separation():
    markets = rows(1)
    markets[0]["updated_at"] = markets[0].pop("captured_at")
    assert runner.freeze(markets, gate(1), runner.timestamp("2026-10-05 18:32"), CONFIG)
    experiments, _ = build_experiments(markets, CONFIG)
    snapshot = {"frozen_at": "2026-10-05T18:32:00+08:00", "sales_day": "2026-10-05", "batch_id": "one", "protocol_version": "test", "experiments": experiments}
    result = {"date": "2026-10-05", "match_number": "001", "home_team": "H1", "away_team": "A1", "status": "已完成", "full_time_score": "2:1"}
    pending = summarize([(snapshot, None)])
    assert pending["families"]["spf_direction"]["roi"] is None
    assert pending["families"]["spf_direction"]["pending_plans"] == 1
    complete = summarize([(snapshot, settle(snapshot, [result]))])
    assert complete["families"]["rqspf_exact_margin"]["independent_events"] == 1
    assert complete["families"]["rqspf_exact_margin"]["common_batch_normalized_12_roi"] == pytest.approx(2.4)
    assert complete["production_promotion_allowed"] is False


def test_margin_scoring_counts_same_prediction_once():
    markets = rows(1)
    for name in ("away_4plus", "away_3", "away_2", "away_1", "draw", "home_1", "home_2", "home_3", "home_4plus"):
        markets[0][f"margin_probability_{name}"] = 1.0 if name == "home_1" else 0.0
    markets[0]["handicap_model_id"] = "test_margin"
    experiments, _ = build_experiments(markets, CONFIG)
    snapshot = {"frozen_at": "2026-10-05T18:32:00+08:00", "sales_day": "2026-10-05", "batch_id": "one", "protocol_version": "test", "experiments": experiments, "matches": markets}
    result = {"date": "2026-10-05", "match_number": "001", "home_team": "H1", "away_team": "A1", "status": "已完成", "full_time_score": "2:1"}
    review = settle(snapshot, [result])
    assert review["prediction_scores"][0]["margin_brier"] == 0
    assert review["prediction_scores"][0]["margin_log_loss"] == 0
    assert summarize([(snapshot, review), (snapshot, review)])["model_scores"]["test_margin"]["samples"] == 1


def test_cli_freeze_settle_summary_in_isolated_directory(tmp_path, monkeypatch):
    import json
    import sys

    import pandas as pd

    now = pd.Timestamp.now(tz="Asia/Shanghai")
    captured = now - pd.Timedelta(seconds=30)
    kickoff = now + pd.Timedelta(hours=8)
    sales_day = (kickoff - pd.Timedelta(hours=10)).date().isoformat()
    market = rows(1)[0]
    market.update({"kickoff_time": kickoff.isoformat(), "updated_at": captured.isoformat()})
    current_gate = gate(1)
    current_gate.update({"as_of": captured.isoformat(), "freshness": {"official_captured_at": captured.isoformat()},
        "deadlines": {"decision_start": (now - pd.Timedelta(minutes=1)).isoformat(), "decision_lock": (now + pd.Timedelta(minutes=10)).isoformat(), "sales_cutoff": (now + pd.Timedelta(minutes=20)).isoformat()}})
    config = {**CONFIG, "effective_from": "2000-01-01", "protocol_version": "isolated_test"}
    (tmp_path / "config").mkdir()
    (tmp_path / "config/october_research.json").write_text(json.dumps(config))
    pd.DataFrame([market]).to_csv(tmp_path / "market.csv", index=False)
    (tmp_path / "gate.json").write_text(json.dumps(current_gate))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["research", "freeze", "--market-csv", str(tmp_path / "market.csv"), "--gate-json", str(tmp_path / "gate.json"), "--sales-day", sales_day, "--batch-id", "isolated"])
    runner.main()
    snapshot = tmp_path / f"artifacts/data/october_research/{sales_day}_isolated.json"
    assert snapshot.exists()
    original = snapshot.read_bytes()
    runner.main()
    assert snapshot.read_bytes() == original
    result = {"date": kickoff.date().isoformat(), "match_number": "001", "home_team": "H1", "away_team": "A1", "status": "已完成", "full_time_score": "2:1"}
    pd.DataFrame([result]).to_csv(tmp_path / "results.csv", index=False)
    monkeypatch.setattr(sys, "argv", ["research", "settle", "--snapshot", str(snapshot), "--results-csv", str(tmp_path / "results.csv")])
    runner.main()
    runner.main()
    assert len(list((snapshot.parent / "reviews").glob("*.json"))) == 1
    monkeypatch.setattr(sys, "argv", ["research", "summarize"])
    runner.main()
    summary = json.loads((snapshot.parent / "summary.json").read_text())
    assert summary["families"]["spf_direction"]["settled_plans"] == 1
