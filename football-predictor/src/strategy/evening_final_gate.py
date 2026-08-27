from __future__ import annotations

import csv
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


CHINA_TZ = timezone(timedelta(hours=8))
REQUIRED_PLAY_TYPES = {"total_goals", "correct_score", "half_full_time"}


def parse_china_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


def sales_deadlines(as_of: str | datetime) -> dict[str, datetime]:
    current = parse_china_datetime(as_of)
    cutoff_clock = time(23, 0) if current.weekday() >= 5 else time(22, 0)
    cutoff = datetime.combine(current.date(), cutoff_clock, tzinfo=CHINA_TZ)
    return {
        "decision_start": cutoff - timedelta(hours=1),
        "decision_lock": cutoff - timedelta(minutes=15),
        "sales_cutoff": cutoff,
    }


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _latest_timestamp(rows: list[dict[str, str]], field: str) -> datetime | None:
    values = []
    for row in rows:
        raw = str(row.get(field) or "").strip()
        if raw:
            try:
                values.append(parse_china_datetime(raw))
            except ValueError:
                continue
    return max(values) if values else None


def _match_deadlines_from_official_rows(
    *,
    current: datetime,
    official_rows: list[dict[str, str]],
    expected_match_numbers: set[str],
) -> dict[str, datetime] | None:
    """Derive a safe final window from the earliest expected kickoff.

    The sales-day evening cutoff remains the upper bound for overnight groups.
    Early groups must lock before their own kickoff instead of inheriting the
    later sales-day cutoff.
    """
    kickoffs: list[datetime] = []
    for row in official_rows:
        number = str(row.get("match_number") or "").strip()
        if number not in expected_match_numbers:
            continue
        raw = str(row.get("kickoff_time") or row.get("kickoff") or "").strip()
        if not raw:
            continue
        try:
            kickoffs.append(parse_china_datetime(raw))
        except ValueError:
            continue
    if not kickoffs:
        return None

    daily = sales_deadlines(current)
    earliest_kickoff = min(kickoffs)
    if earliest_kickoff >= daily["sales_cutoff"]:
        return None
    cutoff = earliest_kickoff
    return {
        "decision_start": cutoff - timedelta(minutes=90),
        "decision_lock": cutoff - timedelta(minutes=15),
        "sales_cutoff": cutoff,
    }


def evaluate_evening_final_gate(
    *,
    as_of: str | datetime,
    official_markets_path: str | Path,
    play_odds_path: str | Path,
    expected_match_numbers: set[str],
    decision_start: str | datetime | None = None,
    decision_lock: str | datetime | None = None,
    sales_cutoff: str | datetime | None = None,
) -> dict[str, Any]:
    current = parse_china_datetime(as_of)
    official_rows = _read_rows(official_markets_path)
    play_rows = _read_rows(play_odds_path)
    custom_deadlines = (decision_start, decision_lock, sales_cutoff)
    if any(value is not None for value in custom_deadlines):
        if not all(value is not None for value in custom_deadlines):
            raise ValueError("decision_start, decision_lock, and sales_cutoff must be provided together")
        deadlines = {
            "decision_start": parse_china_datetime(decision_start),
            "decision_lock": parse_china_datetime(decision_lock),
            "sales_cutoff": parse_china_datetime(sales_cutoff),
        }
        if not deadlines["decision_start"] < deadlines["decision_lock"] < deadlines["sales_cutoff"]:
            raise ValueError("task deadlines must satisfy decision_start < decision_lock < sales_cutoff")
    else:
        deadlines = _match_deadlines_from_official_rows(
            current=current,
            official_rows=official_rows,
            expected_match_numbers=expected_match_numbers,
        ) or sales_deadlines(current)
    official_matches = {str(row.get("match_number") or "").strip() for row in official_rows}
    play_matches = {str(row.get("match_number") or "").strip() for row in play_rows}
    play_types = {str(row.get("play_type") or "").strip() for row in play_rows}
    official_captured = _latest_timestamp(official_rows, "updated_at")
    play_captured = _latest_timestamp(play_rows, "captured_at")

    failures: list[str] = []
    missing_official = sorted(expected_match_numbers - official_matches)
    missing_play = sorted(expected_match_numbers - play_matches)
    missing_types = sorted(REQUIRED_PLAY_TYPES - play_types)
    if missing_official:
        failures.append(f"official_missing_matches:{','.join(missing_official)}")
    if missing_play:
        failures.append(f"play_odds_missing_matches:{','.join(missing_play)}")
    if missing_types:
        failures.append(f"missing_play_types:{','.join(missing_types)}")
    if official_captured is None or official_captured < deadlines["decision_start"]:
        failures.append("official_snapshot_not_refreshed_in_final_window")
    if play_captured is None or play_captured < deadlines["decision_start"]:
        failures.append("play_odds_not_refreshed_in_final_window")
    if official_captured and official_captured > current:
        failures.append("official_snapshot_timestamp_is_in_future")
    if play_captured and play_captured > current:
        failures.append("play_odds_timestamp_is_in_future")

    if current < deadlines["decision_start"]:
        phase = "WAIT_FOR_FINAL_WINDOW"
    elif current <= deadlines["decision_lock"]:
        phase = "READY_FOR_FINAL_ANALYSIS" if not failures else "BLOCKED_DATA_GATE"
    elif current < deadlines["sales_cutoff"]:
        phase = "VERIFY_AND_ARCHIVE_ONLY"
    else:
        phase = "SALES_CLOSED"

    may_create_plan = phase == "READY_FOR_FINAL_ANALYSIS"
    return {
        "as_of": current.isoformat(),
        "phase": phase,
        "may_create_plan": may_create_plan,
        "deadlines": {key: value.isoformat() for key, value in deadlines.items()},
        "deadline_source": "task_override" if any(value is not None for value in custom_deadlines) else (
            "expected_match_kickoff" if _match_deadlines_from_official_rows(
                current=current,
                official_rows=official_rows,
                expected_match_numbers=expected_match_numbers,
            ) else "sales_day_default"
        ),
        "expected_match_numbers": sorted(expected_match_numbers),
        "coverage": {
            "official_match_numbers": sorted(value for value in official_matches if value),
            "play_odds_match_numbers": sorted(value for value in play_matches if value),
            "play_types": sorted(value for value in play_types if value),
        },
        "freshness": {
            "official_captured_at": official_captured.isoformat() if official_captured else None,
            "play_odds_captured_at": play_captured.isoformat() if play_captured else None,
        },
        "failures": failures,
        "rules": {
            "after_decision_lock": "不得生成新方案，只能核验既有决定并留档",
            "data_gate": "官方 SPF/RQSPF 与三类多玩法均须在终版窗口内刷新且覆盖预期场次",
        },
    }


def render_gate_markdown(gate: dict[str, Any]) -> str:
    ready = "允许" if gate["may_create_plan"] else "禁止"
    failures = gate["failures"] or ["无"]
    return "\n".join(
        [
            "# 晚间终版分析闸门",
            "",
            f"- 检查时间：{gate['as_of']}",
            f"- 阶段：`{gate['phase']}`",
            f"- 新建方案：{ready}",
            f"- 终版窗口：{gate['deadlines']['decision_start']} 至 {gate['deadlines']['decision_lock']}",
            f"- 销售截止：{gate['deadlines']['sales_cutoff']}",
            "",
            "## 未通过项",
            "",
            *[f"- {failure}" for failure in failures],
            "",
            "闸门只判断是否具备生成方案的资格，不会自动写入投注台账。",
            "",
        ]
    )
