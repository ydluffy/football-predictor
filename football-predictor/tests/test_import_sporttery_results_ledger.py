from __future__ import annotations

import pandas as pd

from scripts import import_sporttery_results as importer


def test_review_ledger_settles_waiting_row_but_preserves_superseded_row(monkeypatch, tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    ledger_path.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-08-03,21:20,WAITING,稳健,A胜,100,2.0,,待赛,,,,\n"
        "2026-08-03,20:00,ARCHIVED,稳健,A胜,100,1.9,,已替代,,,,终版已覆盖\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(importer, "evaluate_selection", lambda selection, results: (True, "命中"))

    reviewed = importer.review_ledger(ledger_path, pd.DataFrame())

    waiting = reviewed.loc[reviewed["plan_id"] == "WAITING"].iloc[0]
    archived = reviewed.loc[reviewed["plan_id"] == "ARCHIVED"].iloc[0]
    assert waiting["result"] == "命中"
    assert waiting["payout"] == "200.00"
    assert archived["result"] == "已替代"
    assert archived["payout"] == ""


def test_evaluate_selection_supports_numbered_compact_ledger_format():
    results = pd.DataFrame(
        [
            {
                "match_number": "周日022",
                "home_team": "摩雷伦斯",
                "away_team": "布拉加",
                "all_home_team": "摩雷伦斯",
                "all_away_team": "布拉加",
                "handicap": 1,
                "full_time_score": "2:2",
                "spf_result": "平",
                "rqspf_result": "让胜",
            }
        ]
    )

    hit, _ = importer.evaluate_selection(
        "022 摩雷伦斯vs布拉加 让球胜平负(+1):让平@2.96", results
    )

    assert hit is False


def test_evaluate_selection_supports_inline_home_handicap_ledger_format():
    results = pd.DataFrame(
        [
            {
                "match_number": "周二007",
                "home_team": "诺丁汉",
                "away_team": "利兹联",
                "all_home_team": "诺丁汉森林",
                "all_away_team": "利兹联",
                "handicap": -1,
                "full_time_score": "0:2",
                "spf_result": "负",
                "rqspf_result": "让负",
            }
        ]
    )

    hit, _ = importer.evaluate_selection(
        "007 诺丁汉(-1)vs利兹联 让球胜平负:让胜@4.20", results
    )

    assert hit is False


def test_parse_odds_value_supports_display_formula():
    assert importer.parse_odds_value("1.15*1.60=1.8400") == 1.84
