from __future__ import annotations

from strategy.evening_final_gate import evaluate_evening_final_gate


def _write_sources(tmp_path, captured_at: str):
    official = tmp_path / "official.csv"
    official.write_text(
        "match_number,updated_at\n001," + captured_at + "\n002," + captured_at + "\n",
        encoding="utf-8",
    )
    plays = tmp_path / "plays.csv"
    plays.write_text(
        "match_number,play_type,captured_at\n"
        f"001,total_goals,{captured_at}\n"
        f"001,correct_score,{captured_at}\n"
        f"001,half_full_time,{captured_at}\n"
        f"002,total_goals,{captured_at}\n"
        f"002,correct_score,{captured_at}\n"
        f"002,half_full_time,{captured_at}\n",
        encoding="utf-8",
    )
    return official, plays


def _write_early_sources(tmp_path, captured_at: str):
    official, plays = _write_sources(tmp_path, captured_at)
    official.write_text(
        "match_number,kickoff_time,updated_at\n"
        f"001,2026-08-25 18:30,{captured_at}\n"
        f"002,2026-08-25 18:30,{captured_at}\n",
        encoding="utf-8",
    )
    return official, plays


def test_gate_allows_fresh_complete_sources_during_weekday_final_window(tmp_path):
    official, plays = _write_sources(tmp_path, "2026-08-03T21:05:00+08:00")

    gate = evaluate_evening_final_gate(
        as_of="2026-08-03T21:20:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"001", "002"},
    )

    assert gate["phase"] == "READY_FOR_FINAL_ANALYSIS"
    assert gate["may_create_plan"] is True
    assert gate["failures"] == []


def test_gate_blocks_stale_sources_and_never_reopens_after_lock(tmp_path):
    official, plays = _write_sources(tmp_path, "2026-08-03T13:30:00+08:00")

    stale = evaluate_evening_final_gate(
        as_of="2026-08-03T21:20:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"001", "002"},
    )
    late = evaluate_evening_final_gate(
        as_of="2026-08-03T21:50:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"001", "002"},
    )

    assert stale["phase"] == "BLOCKED_DATA_GATE"
    assert "official_snapshot_not_refreshed_in_final_window" in stale["failures"]
    assert late["phase"] == "VERIFY_AND_ARCHIVE_ONLY"
    assert late["may_create_plan"] is False


def test_gate_derives_early_match_window_instead_of_waiting_for_evening(tmp_path):
    official, plays = _write_early_sources(tmp_path, "2026-08-25T17:05:00+08:00")

    gate = evaluate_evening_final_gate(
        as_of="2026-08-25T17:10:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"001", "002"},
    )

    assert gate["deadline_source"] == "expected_match_kickoff"
    assert gate["deadlines"]["decision_start"] == "2026-08-25T17:00:00+08:00"
    assert gate["deadlines"]["decision_lock"] == "2026-08-25T18:15:00+08:00"
    assert gate["deadlines"]["sales_cutoff"] == "2026-08-25T18:30:00+08:00"
    assert gate["phase"] == "READY_FOR_FINAL_ANALYSIS"
    assert gate["may_create_plan"] is True


def test_explicit_task_window_can_start_before_automatic_ninety_minute_window(tmp_path):
    official, plays = _write_early_sources(tmp_path, "2026-08-25T16:02:00+08:00")

    gate = evaluate_evening_final_gate(
        as_of="2026-08-25T16:10:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"001", "002"},
        decision_start="2026-08-25T16:00:00+08:00",
        decision_lock="2026-08-25T18:15:00+08:00",
        sales_cutoff="2026-08-25T18:30:00+08:00",
    )

    assert gate["deadline_source"] == "task_override"
    assert gate["phase"] == "READY_FOR_FINAL_ANALYSIS"
    assert gate["may_create_plan"] is True


def test_overnight_match_keeps_sales_day_evening_fallback(tmp_path):
    official, plays = _write_sources(tmp_path, "2026-08-25T21:05:00+08:00")
    official.write_text(
        "match_number,kickoff_time,updated_at\n"
        "001,2026-08-26 02:00,2026-08-25T21:05:00+08:00\n"
        "002,2026-08-26 03:00,2026-08-25T21:05:00+08:00\n",
        encoding="utf-8",
    )

    gate = evaluate_evening_final_gate(
        as_of="2026-08-25T21:10:00+08:00",
        official_markets_path=official,
        play_odds_path=plays,
        expected_match_numbers={"001", "002"},
    )

    assert gate["deadline_source"] == "sales_day_default"
    assert gate["deadlines"]["decision_start"] == "2026-08-25T21:00:00+08:00"
    assert gate["deadlines"]["decision_lock"] == "2026-08-25T21:45:00+08:00"
    assert gate["deadlines"]["sales_cutoff"] == "2026-08-25T22:00:00+08:00"
    assert gate["may_create_plan"] is True
