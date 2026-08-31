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


def test_sales_window_result_end_includes_next_calendar_day():
    assert importer.sales_window_result_end("2026-08-27") == "2026-08-28"


def test_review_ledger_uses_sales_day_and_next_calendar_day(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    ledger_path.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-08-27,21:00,CROSS_DAY,稳健,008 巴萨vs毕尔巴鄂 胜平负:主胜@1.12,100,1.12,,待赛,,,,\n",
        encoding="utf-8",
    )
    results = pd.DataFrame(
        [
            {
                "date": "2026-08-28",
                "match_number": "周四008",
                "home_team": "巴萨",
                "away_team": "毕尔巴鄂",
                "all_home_team": "巴塞罗那",
                "all_away_team": "毕尔巴鄂竞技",
                "handicap": -1,
                "full_time_score": "2:0",
                "spf_result": "胜",
                "rqspf_result": "让胜",
            }
        ]
    )

    reviewed = importer.review_ledger(ledger_path, results)

    row = reviewed.iloc[0]
    assert row["result"] == "命中"
    assert row["payout"] == "112.00"


def test_review_ledger_rejects_same_identity_outside_sales_window(tmp_path):
    ledger_path = tmp_path / "ledger.csv"
    ledger_path.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-08-27,21:00,OUTSIDE,稳健,008 巴萨vs毕尔巴鄂 胜平负:主胜@1.12,100,1.12,,待赛,,,,\n",
        encoding="utf-8",
    )
    results = pd.DataFrame(
        [
            {
                "date": "2026-08-29",
                "match_number": "周五008",
                "home_team": "巴萨",
                "away_team": "毕尔巴鄂",
                "all_home_team": "巴塞罗那",
                "all_away_team": "毕尔巴鄂竞技",
                "handicap": -1,
                "full_time_score": "2:0",
                "spf_result": "胜",
                "rqspf_result": "让胜",
            }
        ]
    )

    reviewed = importer.review_ledger(ledger_path, results)

    assert reviewed.iloc[0]["result"] == "待赛"
    assert "未匹配比赛" in reviewed.iloc[0]["review_note"]
