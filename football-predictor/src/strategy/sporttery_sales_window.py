from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from data.competition_registry import load_competition_registry, load_team_alias_registry


CHINA_TZ = timezone(timedelta(hours=8))
PRELISTED = "prelisted"
ON_SALE = "on_sale"
STOPPED = "stopped"
NO_MATCHES = "no_matches"
TASK_STATUSES = {"scheduled", "updated", "completed", "pending_schedule", "failed"}
REQUIRED_PLAY_TYPES = {"total_goals", "correct_score", "half_full_time"}


def parse_china_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHINA_TZ)
    return parsed.astimezone(CHINA_TZ)


def parse_sales_day(value: str | date | None, *, as_of: datetime) -> date:
    if value is None or value == "":
        return as_of.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def confirmation_open_at(sales_day: date) -> datetime:
    return datetime.combine(sales_day, time(11, 5), tzinfo=CHINA_TZ)


def sales_window(sales_day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(sales_day, time(10, 0), tzinfo=CHINA_TZ)
    return start, start + timedelta(days=1)


def sales_deadlines(sales_day: date) -> dict[str, datetime]:
    weekend = sales_day.weekday() >= 5
    cutoff = datetime.combine(
        sales_day,
        time(23, 0) if weekend else time(22, 0),
        tzinfo=CHINA_TZ,
    )
    return {
        "decision_start": cutoff - timedelta(hours=1),
        "decision_lock": cutoff - timedelta(minutes=15),
        "sales_cutoff": cutoff,
    }


def _normalise_match_number(value: object) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    return raw.zfill(3) if raw.isdigit() else raw


def read_csv_rows(path: str | Path | None) -> list[dict[str, str]]:
    if not path:
        return []
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return []
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def file_sha256(path: str | Path) -> str | None:
    source = Path(path)
    if not source.exists():
        return None
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _kickoff_from_row(row: dict[str, Any]) -> datetime | None:
    raw = str(row.get("kickoff_time") or row.get("kickoff") or "").strip()
    if raw:
        try:
            return parse_china_datetime(raw)
        except ValueError:
            pass
    day = str(row.get("date") or "").strip()
    clock = str(row.get("time") or "").strip()
    if day and clock:
        try:
            return parse_china_datetime(f"{day}T{clock}:00")
        except ValueError:
            return None
    return None


def normalise_fixtures(
    official_rows: Iterable[dict[str, Any]],
    play_rows: Iterable[dict[str, Any]],
    *,
    sales_day: date,
    stage: str,
    previous_fixtures: Iterable[dict[str, Any]] = (),
    stopped_match_numbers: set[str] | None = None,
    infer_missing_as_stopped: bool = True,
) -> list[dict[str, Any]]:
    if stage not in {"preopen", "confirm"}:
        raise ValueError("stage must be preopen or confirm")
    stopped = {_normalise_match_number(value) for value in (stopped_match_numbers or set())}
    competition_registry = load_competition_registry()
    team_registry = load_team_alias_registry()
    start, end = sales_window(sales_day)
    coverage: dict[str, set[str]] = {}
    for row in play_rows:
        number = _normalise_match_number(row.get("match_number"))
        play_type = str(row.get("play_type") or "").strip()
        if number and play_type:
            coverage.setdefault(number, set()).add(play_type)

    fixtures: list[dict[str, Any]] = []
    current_numbers: set[str] = set()
    for row in official_rows:
        kickoff = _kickoff_from_row(row)
        if kickoff is None or not (start <= kickoff < end):
            continue
        number = _normalise_match_number(row.get("match_number"))
        if not number:
            continue
        current_numbers.add(number)
        sale_status = PRELISTED if stage == "preopen" else (STOPPED if number in stopped else ON_SALE)
        competition = str(row.get("competition") or "").strip()
        home_team = str(row.get("home_team") or "").strip()
        away_team = str(row.get("away_team") or "").strip()
        competition_metadata = competition_registry.annotate(competition)
        home_metadata = team_registry.annotate(home_team)
        away_metadata = team_registry.annotate(away_team)
        fixtures.append(
            {
                "match_id": f"{sales_day.isoformat()}|{number}",
                "match_number": number,
                "competition": competition,
                **competition_metadata,
                "kickoff": kickoff.isoformat(),
                "home_team": home_team,
                "away_team": away_team,
                "home_team_canonical": home_metadata["canonical_team"],
                "away_team_canonical": away_metadata["canonical_team"],
                "home_team_alias_known": home_metadata["team_alias_known"],
                "away_team_alias_known": away_metadata["team_alias_known"],
                "sale_status": sale_status,
                "play_coverage": sorted(coverage.get(number, set())),
                "official_odds_present": any(
                    str(row.get(field) or "").strip()
                    for field in (
                        "spf_odds_home",
                        "spf_odds_draw",
                        "spf_odds_away",
                        "rqspf_odds_home",
                        "rqspf_odds_draw",
                        "rqspf_odds_away",
                    )
                ),
            }
        )

    if stage == "confirm" and infer_missing_as_stopped:
        for row in previous_fixtures:
            number = _normalise_match_number(row.get("match_number"))
            if not number or number in current_numbers:
                continue
            kickoff_raw = row.get("kickoff")
            if not kickoff_raw:
                continue
            kickoff = parse_china_datetime(str(kickoff_raw))
            if start <= kickoff < end:
                previous = dict(row)
                previous["match_number"] = number
                previous["sale_status"] = STOPPED
                fixtures.append(previous)

    return sorted(fixtures, key=lambda item: (item["kickoff"], item["match_number"]))


@dataclass(frozen=True)
class TimeGroup:
    label: str
    fixtures: tuple[dict[str, Any], ...]
    run_at: datetime
    hard_lock: datetime
    sales_cutoff: datetime


def group_on_sale_fixtures(fixtures: Iterable[dict[str, Any]], *, sales_day: date) -> list[TimeGroup]:
    active = [row for row in fixtures if row.get("sale_status") == ON_SALE]
    active.sort(key=lambda item: parse_china_datetime(item["kickoff"]))
    clusters: list[list[dict[str, Any]]] = []
    for fixture in active:
        kickoff = parse_china_datetime(fixture["kickoff"])
        if not clusters:
            clusters.append([fixture])
            continue
        previous = parse_china_datetime(clusters[-1][-1]["kickoff"])
        if kickoff - previous <= timedelta(minutes=90):
            clusters[-1].append(fixture)
        else:
            clusters.append([fixture])

    deadlines = sales_deadlines(sales_day)
    result: list[TimeGroup] = []
    for cluster in clusters:
        kickoffs = [parse_china_datetime(item["kickoff"]) for item in cluster]
        first, last = min(kickoffs), max(kickoffs)
        label = first.strftime("%H:%M") if first == last else f"{first:%H:%M}-{last:%H:%M}"
        group_cutoff = min(first, deadlines["sales_cutoff"])
        group_lock = group_cutoff - timedelta(minutes=15)
        natural = first - timedelta(minutes=90)
        if first.date() > sales_day or natural >= deadlines["sales_cutoff"]:
            run_at = deadlines["decision_start"]
        else:
            run_at = natural
        result.append(
            TimeGroup(
                label=label,
                fixtures=tuple(cluster),
                run_at=run_at,
                hard_lock=group_lock,
                sales_cutoff=group_cutoff,
            )
        )
    return result


def task_key(sales_day: date, time_group: str, purpose: str = "终版分析") -> str:
    return f"{sales_day.isoformat()}|{time_group}|{purpose}"


def build_task_records(groups: Iterable[TimeGroup], *, sales_day: date) -> list[dict[str, Any]]:
    records = []
    for group in groups:
        key = task_key(sales_day, group.label)
        records.append(
            {
                "key": key,
                "sales_day": sales_day.isoformat(),
                "time_group": group.label,
                "purpose": "终版分析",
                "task_name": f"{sales_day.isoformat()}|{group.label}|终版分析",
                "run_at": group.run_at.isoformat(),
                "hard_lock": group.hard_lock.isoformat(),
                "sales_cutoff": group.sales_cutoff.isoformat(),
                "match_numbers": [item["match_number"] for item in group.fixtures],
                "matches": [
                    f"{item['match_number']} {item['home_team']} vs {item['away_team']}"
                    for item in group.fixtures
                ],
            }
        )
    return records


def load_registry(path: str | Path, *, sales_day: date) -> dict[str, Any]:
    registry_path = Path(path)
    if registry_path.exists():
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        payload.setdefault("tasks", [])
        return payload
    return {"version": 1, "sales_day": sales_day.isoformat(), "tasks": []}


def _task_signature(record: dict[str, Any]) -> str:
    fields = {key: record.get(key) for key in ("run_at", "hard_lock", "match_numbers", "purpose")}
    return json.dumps(fields, ensure_ascii=False, sort_keys=True)


def upsert_registry_tasks(
    registry: dict[str, Any],
    planned_tasks: Iterable[dict[str, Any]],
    *,
    as_of: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    existing = {str(item["key"]): dict(item) for item in registry.get("tasks", [])}
    queue: list[dict[str, Any]] = []
    for planned in planned_tasks:
        key = planned["key"]
        current = existing.get(key)
        if current is None:
            current = {
                **planned,
                "status": "pending_schedule",
                "revision": 1,
                "scheduling_attempts": 0,
                "automation_id": None,
                "last_error": None,
                "created_at": as_of.isoformat(),
            }
            existing[key] = current
        elif _task_signature(current) != _task_signature(planned):
            old_status = current.get("status")
            current.update(planned)
            current["revision"] = int(current.get("revision", 1)) + 1
            current["status"] = "updated" if old_status in {"scheduled", "updated", "completed"} else "pending_schedule"
        current["updated_at"] = as_of.isoformat()
        if current.get("status") in {"pending_schedule", "failed", "updated"}:
            queue.append(dict(current))
    registry["updated_at"] = as_of.isoformat()
    registry["tasks"] = sorted(existing.values(), key=lambda item: item["key"])
    return registry, queue


def apply_task_status(
    registry: dict[str, Any],
    *,
    key: str,
    status: str,
    as_of: datetime,
    automation_id: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if status not in TASK_STATUSES:
        raise ValueError(f"unsupported task status: {status}")
    for task in registry.get("tasks", []):
        if task.get("key") != key:
            continue
        task["status"] = status
        task["updated_at"] = as_of.isoformat()
        if status in {"scheduled", "updated", "failed"}:
            task["scheduling_attempts"] = int(task.get("scheduling_attempts", 0)) + 1
            task["last_attempt_at"] = as_of.isoformat()
        if automation_id:
            task["automation_id"] = automation_id
        task["last_error"] = error
        registry["updated_at"] = as_of.isoformat()
        return registry
    raise KeyError(key)


def save_registry(path: str | Path, registry: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")


def build_scan_result(
    *,
    stage: str,
    as_of: str | datetime,
    sales_day: str | date | None,
    official_rows: Iterable[dict[str, Any]],
    play_rows: Iterable[dict[str, Any]],
    previous_scan: dict[str, Any] | None = None,
    stopped_match_numbers: set[str] | None = None,
    ledger_path: str | Path | None = None,
    source_ok: bool = True,
) -> dict[str, Any]:
    current = parse_china_datetime(as_of)
    day = parse_sales_day(sales_day, as_of=current)
    if stage == "confirm" and current < confirmation_open_at(day):
        raise ValueError(
            f"confirm stage opens at {confirmation_open_at(day).isoformat()}; "
            f"received {current.isoformat()}"
        )
    previous_fixtures = (previous_scan or {}).get("fixtures", [])
    fixtures = normalise_fixtures(
        official_rows,
        play_rows,
        sales_day=day,
        stage=stage,
        previous_fixtures=previous_fixtures,
        stopped_match_numbers=stopped_match_numbers,
        infer_missing_as_stopped=source_ok,
    )
    if stage == "confirm" and not source_ok and not fixtures:
        fixtures = [dict(item) for item in previous_fixtures]
        for fixture in fixtures:
            fixture["sale_status"] = PRELISTED
    active = [item for item in fixtures if item["sale_status"] == ON_SALE]
    groups = group_on_sale_fixtures(fixtures, sales_day=day)
    if stage == "preopen":
        batch_status = PRELISTED
        message = "开售前已取得官网预列数据，须在 11:05 重新确认。" if fixtures else "开售前尚未发布。"
    elif not source_ok:
        batch_status = "source_failed"
        message = "11:05 官方数据抓取失败，不能据此判断无比赛，已保留待重试状态。"
    elif active:
        batch_status = ON_SALE
        message = f"开售确认完成：{len(active)} 场确认在售。"
    else:
        batch_status = NO_MATCHES
        message = "11:05 开售确认仍为空，本销售窗口无确认在售比赛。"
    start, end = sales_window(day)
    deadlines = sales_deadlines(day)
    return {
        "schema_version": 1,
        "stage": stage,
        "sales_day": day.isoformat(),
        "scanned_at": current.isoformat(),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "batch_status": batch_status,
        "message": message,
        "fixtures": fixtures,
        "summary": {
            PRELISTED: sum(item["sale_status"] == PRELISTED for item in fixtures),
            ON_SALE: sum(item["sale_status"] == ON_SALE for item in fixtures),
            STOPPED: sum(item["sale_status"] == STOPPED for item in fixtures),
            "time_groups": len(groups),
            "competition_known": sum(bool(item.get("competition_known")) for item in fixtures),
            "competition_unknown": sum(not bool(item.get("competition_known")) for item in fixtures),
            "historical_model_covered": sum(bool(item.get("historical_model_coverage")) for item in fixtures),
            "model_fallback_required": sum(
                item.get("recommended_model_route") == "market_anchor_fallback" for item in fixtures
            ),
        },
        "time_groups": [
            {
                "label": group.label,
                "match_numbers": [item["match_number"] for item in group.fixtures],
                "run_at": group.run_at.isoformat(),
                "hard_lock": group.hard_lock.isoformat(),
                "sales_cutoff": group.sales_cutoff.isoformat(),
            }
            for group in groups
        ],
        "planned_tasks": build_task_records(groups, sales_day=day),
        "deadlines": {key: value.isoformat() for key, value in deadlines.items()},
        "ledger_gate": {
            "write_performed": False,
            "may_write": False,
            "reason": (
                "prelisted odds are never eligible for ledger writes"
                if stage == "preopen"
                else "confirmation scan only registers final-analysis tasks; the final gate must run separately"
            ),
            "ledger_sha256": file_sha256(ledger_path) if ledger_path else None,
        },
    }


def render_scan_markdown(scan: dict[str, Any], queue: Iterable[dict[str, Any]] = ()) -> str:
    fixtures = scan["fixtures"]
    tasks = list(queue)
    lines = [
        f"# 体彩销售窗口扫描：{scan['sales_day']} {scan['stage']}",
        "",
        f"- 扫描时间：{scan['scanned_at']}",
        f"- 批次状态：`{scan['batch_status']}`",
        f"- 结论：{scan['message']}",
        f"- 预列：{scan['summary']['prelisted']} 场",
        f"- 在售：{scan['summary']['on_sale']} 场",
        f"- 停售：{scan['summary']['stopped']} 场",
        f"- 台账写入：禁止（{scan['ledger_gate']['reason']}）",
        "",
        "## 比赛",
        "",
    ]
    if fixtures:
        lines.extend(
            f"- {item['match_number']} {item['home_team']} vs {item['away_team']}｜{item['kickoff']}｜`{item['sale_status']}`"
            for item in fixtures
        )
    else:
        lines.append(f"- {scan['message']}")
    external = scan.get("external_odds")
    if external:
        lines.extend(
            [
                "",
                "## 外盘快照",
                "",
                f"- 数据源：`{external['source']}`",
                f"- 状态：`{external['status']}`",
                f"- 同场匹配：{external['mapped_fixtures']}/{external['on_sale_fixtures']}",
                f"- 未匹配：{external['unmatched_fixtures']} 场",
                f"- 快照目录：`{external['snapshot_dir']}`",
                "- 定位：只作外盘特征与复核，不具备体彩在售或台账授权。",
                "- 终版要求：赛前再次刷新，不能复用确认快照冒充终版赔率。",
            ]
        )
    lines.extend(["", "## 待调度或待更新任务", ""])
    if tasks:
        lines.extend(f"- `{item['key']}`｜{item['run_at']}｜`{item['status']}`" for item in tasks)
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)
