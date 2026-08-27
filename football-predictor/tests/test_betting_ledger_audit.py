from __future__ import annotations

from strategy.betting_ledger_audit import audit_betting_ledger, render_audit_markdown


def test_audit_detects_superseded_pending_and_keeps_financial_scopes_separate(tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-07-17,19:01,OLD,稳健,A胜 + B胜,100,2.0,,待赛,,,,旧方案\n"
        "2026-07-17,21:07,NEW,稳健,A胜+B胜,100,2.1,,命中,210,110,1.1,终版\n"
        "2026-07-18,20:00,PARTIAL,组合,C胜,50,3.0,,部分命中,25,-25,-0.5,部分结算\n",
        encoding="utf-8",
    )

    audit = audit_betting_ledger(ledger)

    assert audit["rows"] == 3
    assert audit["issue_counts"] == {"errors": 0, "warnings": 2}
    assert audit["pending_plan_ids"] == ["OLD"]
    assert audit["financials"]["all_settled"]["stake"] == 150
    assert audit["financials"]["binary_only"]["stake"] == 100
    assert "pending_superseded_by_settled" in {issue["code"] for issue in audit["issues"]}
    assert "建议人工确认后归档前者" in render_audit_markdown(audit)


def test_audit_detects_duplicate_id_and_settlement_arithmetic_errors(tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-07-19,20:00,SAME,稳健,A胜,100,2.0,,命中,200,90,1.0,错误净收益\n"
        "2026-07-20,20:00,SAME,稳健,B胜,100,2.0,,未中,0,-100,-0.9,错误ROI\n",
        encoding="utf-8",
    )

    audit = audit_betting_ledger(ledger)
    codes = {issue["code"] for issue in audit["issues"]}

    assert {"duplicate_plan_id", "net_profit_mismatch", "roi_mismatch"} <= codes
    assert audit["issue_counts"]["errors"] == 3


def test_superseded_row_is_archived_without_remaining_duplicate_warning(tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-07-17,19:01,OLD,稳健,A胜,100,2.0,,已替代,,,,由终版替代\n"
        "2026-07-17,21:07,NEW,稳健,A胜,100,2.1,,命中,210,110,1.1,终版\n",
        encoding="utf-8",
    )

    audit = audit_betting_ledger(ledger)

    assert audit["issue_counts"] == {"errors": 0, "warnings": 0}
    assert audit["pending_plan_ids"] == []
    assert audit["archived_plan_ids"] == ["OLD"]
    assert len(audit["archived_duplicate_groups"]) == 1


def test_official_result_pending_status_remains_retryable(tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text(
        "date,time_window,plan_id,plan_type,selections,stake,estimated_odds,actual_odds,result,payout,net_profit,roi,review_note\n"
        "2026-08-03,21:05,WAITING,稳健,A胜,100,2.0,,待官方赛果,,,,官方接口暂不可用\n",
        encoding="utf-8",
    )

    audit = audit_betting_ledger(ledger)

    assert audit["issue_counts"] == {"errors": 0, "warnings": 0}
    assert audit["pending_plan_ids"] == ["WAITING"]
    assert audit["financials"]["all_settled"]["rows"] == 0
