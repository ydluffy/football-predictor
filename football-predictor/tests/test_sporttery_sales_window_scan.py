from __future__ import annotations

from datetime import date

import pytest

from strategy.evening_final_gate import evaluate_evening_final_gate
from strategy.sporttery_sales_window import (
    apply_task_status,
    build_scan_result,
    group_on_sale_fixtures,
    parse_china_datetime,
    retryable_tasks,
    upsert_registry_tasks,
)


def _official(number: str = "002", kickoff: str = "2026-08-06 00:30") -> dict[str, str]:
    return {
        "match_number": number,
        "competition": "欧冠",
        "kickoff_time": kickoff,
        "home_team": "主队",
        "away_team": "客队",
        "spf_odds_home": "1.80",
        "spf_odds_draw": "3.30",
        "spf_odds_away": "4.20",
        "rqspf_odds_home": "2.80",
    }


def _plays(number: str = "002") -> list[dict[str, str]]:
    return [
        {"match_number": number, "play_type": play_type}
        for play_type in ("total_goals", "correct_score", "half_full_time")
    ]


def test_1000_empty_batch_is_prelisted_and_never_claims_no_matches(tmp_path):
    scan = build_scan_result(
        stage="preopen",
        as_of="2026-08-05T10:00:00+08:00",
        sales_day="2026-08-05",
        official_rows=[],
        play_rows=[],
        ledger_path=tmp_path / "ledger.csv",
    )

    assert scan["batch_status"] == "prelisted"
    assert scan["message"] == "开售前尚未发布。"
    assert "无确认在售比赛" not in scan["message"]


def test_1105_empty_batch_is_no_matches():
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-05T11:05:00+08:00",
        sales_day="2026-08-05",
        official_rows=[],
        play_rows=[],
    )

    assert scan["batch_status"] == "no_matches"
    assert scan["summary"]["on_sale"] == 0


def test_confirm_before_1105_is_rejected():
    with pytest.raises(ValueError, match="confirm stage opens"):
        build_scan_result(
            stage="confirm",
            as_of="2026-08-05T10:59:00+08:00",
            sales_day="2026-08-05",
            official_rows=[_official()],
            play_rows=_plays(),
        )


def test_1105_source_failure_does_not_claim_no_matches():
    previous = build_scan_result(
        stage="preopen",
        as_of="2026-08-05T10:00:00+08:00",
        sales_day="2026-08-05",
        official_rows=[_official()],
        play_rows=_plays(),
    )
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-05T11:05:00+08:00",
        sales_day="2026-08-05",
        official_rows=[],
        play_rows=[],
        previous_scan=previous,
        source_ok=False,
    )

    assert scan["batch_status"] == "source_failed"
    assert "不能据此判断无比赛" in scan["message"]
    assert scan["fixtures"][0]["sale_status"] == "prelisted"
    assert scan["fixtures"][0]["match_id"] == "2026-08-05|002"


def test_prelisted_odds_never_write_or_enable_ledger(tmp_path):
    ledger = tmp_path / "ledger.csv"
    ledger.write_text("plan_id,stake\nexisting,100\n", encoding="utf-8")
    before = ledger.read_bytes()

    scan = build_scan_result(
        stage="preopen",
        as_of="2026-08-05T10:00:00+08:00",
        sales_day="2026-08-05",
        official_rows=[_official()],
        play_rows=_plays(),
        ledger_path=ledger,
    )

    assert scan["fixtures"][0]["sale_status"] == "prelisted"
    assert scan["ledger_gate"]["may_write"] is False
    assert scan["ledger_gate"]["write_performed"] is False
    assert ledger.read_bytes() == before


def test_repeated_confirmation_of_same_group_does_not_duplicate_task():
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-05T11:05:00+08:00",
        sales_day="2026-08-05",
        official_rows=[_official()],
        play_rows=_plays(),
    )
    registry = {"version": 1, "sales_day": "2026-08-05", "tasks": []}
    as_of = parse_china_datetime("2026-08-05T11:05:00+08:00")

    registry, first_queue = upsert_registry_tasks(registry, scan["planned_tasks"], as_of=as_of)
    registry, second_queue = upsert_registry_tasks(registry, scan["planned_tasks"], as_of=as_of)

    assert len(registry["tasks"]) == 1
    assert registry["tasks"][0]["key"] == "2026-08-05|00:30|终版分析"
    assert first_queue[0]["status"] == "pending_schedule"
    assert second_queue[0]["key"] == first_queue[0]["key"]


def test_scheduler_failure_stays_in_retry_queue():
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-05T11:05:00+08:00",
        sales_day="2026-08-05",
        official_rows=[_official()],
        play_rows=_plays(),
    )
    as_of = parse_china_datetime("2026-08-05T11:05:00+08:00")
    registry, _ = upsert_registry_tasks(
        {"version": 1, "sales_day": "2026-08-05", "tasks": []},
        scan["planned_tasks"],
        as_of=as_of,
    )
    key = registry["tasks"][0]["key"]
    registry = apply_task_status(
        registry,
        key=key,
        status="failed",
        as_of=as_of,
        error="scheduler unavailable",
    )
    registry, retry_queue = upsert_registry_tasks(registry, scan["planned_tasks"], as_of=as_of)

    assert registry["tasks"][0]["status"] == "failed"
    assert retry_queue[0]["key"] == key
    assert retry_queue[0]["last_error"] == "scheduler unavailable"


def test_retry_queue_excludes_task_after_hard_lock():
    registry = {
        "tasks": [
            {
                "key": "expired",
                "status": "failed",
                "run_at": "2026-08-28T21:00:00+08:00",
                "hard_lock": "2026-08-28T21:45:00+08:00",
                "sales_cutoff": "2026-08-28T22:00:00+08:00",
            },
            {
                "key": "still-safe",
                "status": "pending_schedule",
                "run_at": "2026-08-29T10:00:00+08:00",
                "hard_lock": "2026-08-29T10:45:00+08:00",
            },
        ]
    }

    queue = retryable_tasks(
        registry,
        as_of=parse_china_datetime("2026-08-29T01:30:00+08:00"),
    )

    assert [task["key"] for task in queue] == ["still-safe"]


def test_overnight_group_is_moved_before_weekday_sales_cutoff():
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-05T11:05:00+08:00",
        sales_day="2026-08-05",
        official_rows=[_official("002", "2026-08-06 00:30"), _official("003", "2026-08-06 02:00")],
        play_rows=_plays("002") + _plays("003"),
    )

    assert scan["time_groups"][0]["label"] == "00:30-02:00"
    assert scan["time_groups"][0]["run_at"] == "2026-08-05T21:00:00+08:00"
    assert scan["time_groups"][0]["hard_lock"] == "2026-08-05T21:45:00+08:00"


def test_early_group_locks_before_its_own_kickoff():
    scan = build_scan_result(
        stage="confirm",
        as_of="2026-08-25T11:05:00+08:00",
        sales_day="2026-08-25",
        official_rows=[_official("001", "2026-08-25 18:30"), _official("002", "2026-08-25 18:30")],
        play_rows=_plays("001") + _plays("002"),
    )

    assert scan["time_groups"][0]["run_at"] == "2026-08-25T17:00:00+08:00"
    assert scan["time_groups"][0]["hard_lock"] == "2026-08-25T18:15:00+08:00"
    assert scan["time_groups"][0]["sales_cutoff"] == "2026-08-25T18:30:00+08:00"


def test_weekday_gate_forbids_new_plan_after_2145(tmp_path):
    official = tmp_path / "official.csv"
    official.write_text("match_number,updated_at\n002,2026-08-05T21:30:00+08:00\n", encoding="utf-8")
    plays = tmp_path / "plays.csv"
    plays.write_text(
        "match_number,play_type,captured_at\n"
        "002,total_goals,2026-08-05T21:30:00+08:00\n"
        "002,correct_score,2026-08-05T21:30:00+08:00\n"
        "002,half_full_time,2026-08-05T21:30:00+08:00\n",
        encoding="utf-8",
    )

    gate = evaluate_evening_final_gate(
        as_of="2026-08-05T21:46:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"002"},
    )

    assert gate["phase"] == "VERIFY_AND_ARCHIVE_ONLY"
    assert gate["may_create_plan"] is False
