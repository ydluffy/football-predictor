from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import ensure_project_dirs, get_settings


@dataclass(frozen=True)
class ScheduledJob:
    job_id: str
    workflow_name: str
    interval_seconds: int
    context: dict[str, Any]


class LocalScheduler:
    def __init__(self, *, jobs: list[ScheduledJob] | None = None) -> None:
        ensure_project_dirs()
        self._jobs = list(jobs or [])

    def add_job(self, job: ScheduledJob) -> None:
        self._jobs.append(job)

    def _load_state(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"schema_version": "scheduler_state_v1", "jobs": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": "scheduler_state_v1", "jobs": {}}

    def _save_state(self, path: Path, state: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_history(self, record: dict[str, Any]) -> None:
        s = get_settings()
        s.research_scheduler_history_path.parent.mkdir(parents=True, exist_ok=True)
        with s.research_scheduler_history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run_pending(self, *, director: Any, now: datetime | None = None) -> list[dict[str, Any]]:
        ensure_project_dirs()
        s = get_settings()
        now_dt = now or datetime.now(timezone.utc)
        state = self._load_state(s.research_scheduler_state_path)
        jobs_state: dict[str, Any] = state.get("jobs") if isinstance(state.get("jobs"), dict) else {}

        results: list[dict[str, Any]] = []
        for job in self._jobs:
            js = jobs_state.get(job.job_id) if isinstance(jobs_state.get(job.job_id), dict) else {}
            last_run_at = js.get("last_run_at")
            due = True
            if last_run_at:
                try:
                    last_dt = datetime.fromisoformat(str(last_run_at))
                except Exception:
                    last_dt = None
                if last_dt is not None:
                    elapsed = (now_dt - last_dt).total_seconds()
                    due = elapsed >= float(job.interval_seconds)

            if not due:
                continue

            result = director.run(job.workflow_name, context=dict(job.context))
            results.append(result)
            jobs_state[job.job_id] = {
                "last_run_at": now_dt.isoformat(),
                "last_run_id": str(result.get("run_id") or ""),
                "last_status": str(result.get("status") or ""),
            }
            self._append_history(
                {
                    "job_id": job.job_id,
                    "workflow_name": job.workflow_name,
                    "run_time": now_dt.isoformat(),
                    "run_id": str(result.get("run_id") or ""),
                    "status": str(result.get("status") or ""),
                }
            )

        state["jobs"] = jobs_state
        state["updated_at"] = now_dt.isoformat()
        self._save_state(s.research_scheduler_state_path, state)
        return results


def _parse_int_set(expr: str, *, min_v: int, max_v: int) -> set[int] | None:
    s = str(expr).strip()
    if s == "*":
        return None
    out: set[int] = set()
    for part in s.split(","):
        p = part.strip()
        if not p:
            continue
        if p.isdigit():
            v = int(p)
            if v < min_v or v > max_v:
                raise ValueError(f"cron 字段越界: {expr}")
            out.add(v)
            continue
        raise ValueError(f"不支持的 cron 字段: {expr}")
    return out


@dataclass(frozen=True)
class CronSpec:
    minute: set[int] | None
    hour: set[int] | None
    day: set[int] | None
    month: set[int] | None
    weekday: set[int] | None

    @staticmethod
    def parse(expr: str) -> "CronSpec":
        parts = str(expr).strip().split()
        if len(parts) != 5:
            raise ValueError("cron 仅支持 5 字段: minute hour day month weekday")
        minute = _parse_int_set(parts[0], min_v=0, max_v=59)
        hour = _parse_int_set(parts[1], min_v=0, max_v=23)
        day = _parse_int_set(parts[2], min_v=1, max_v=31)
        month = _parse_int_set(parts[3], min_v=1, max_v=12)
        weekday = _parse_int_set(parts[4], min_v=0, max_v=6)
        return CronSpec(minute=minute, hour=hour, day=day, month=month, weekday=weekday)

    def matches(self, dt: datetime) -> bool:
        d = dt.astimezone(timezone.utc)
        if self.minute is not None and d.minute not in self.minute:
            return False
        if self.hour is not None and d.hour not in self.hour:
            return False
        if self.day is not None and d.day not in self.day:
            return False
        if self.month is not None and d.month not in self.month:
            return False
        if self.weekday is not None and d.weekday() not in self.weekday:
            return False
        return True


@dataclass(frozen=True)
class ResearchJob:
    job_id: str
    workflow: str
    trigger_type: str
    interval_seconds: int | None
    cron: CronSpec | None
    context: dict[str, Any]


class ResearchScheduler:
    def __init__(self, *, jobs: list[ResearchJob]) -> None:
        ensure_project_dirs()
        self._jobs = list(jobs)

    @staticmethod
    def load_from_config(path: str | Path | None = None) -> "ResearchScheduler":
        ensure_project_dirs()
        s = get_settings()
        cfg_path = Path(path) if path is not None else s.research_scheduler_config_path
        if not cfg_path.is_absolute():
            cfg_path = (s.project_root / cfg_path).resolve()
        if not cfg_path.exists():
            payload = {"schema_version": "research_scheduler_config_v1", "jobs": []}
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return ResearchScheduler(jobs=[])

        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        jobs_raw = raw.get("jobs") if isinstance(raw, dict) else []
        jobs: list[ResearchJob] = []
        for j in jobs_raw if isinstance(jobs_raw, list) else []:
            if not isinstance(j, dict):
                continue
            job_id = str(j.get("job_id") or "")
            workflow = str(j.get("workflow") or "")
            trigger = j.get("trigger") if isinstance(j.get("trigger"), dict) else {}
            trigger_type = str(trigger.get("type") or "interval")
            interval_seconds = None
            cron = None
            if trigger_type == "interval":
                interval_seconds = int(trigger.get("seconds") or 0)
            elif trigger_type == "cron":
                cron = CronSpec.parse(str(trigger.get("cron") or "* * * * *"))
            else:
                raise ValueError(f"不支持的 trigger.type: {trigger_type}")

            ctx = {
                "workflow": workflow,
                "model_type": j.get("model_type"),
                "feature_version": j.get("feature_version"),
                "calibration": j.get("calibration"),
                "use_verifier": bool(j.get("use_verifier", False)),
                "data_mode": j.get("data_mode") or "mock",
            }
            jobs.append(ResearchJob(job_id=job_id, workflow=workflow, trigger_type=trigger_type, interval_seconds=interval_seconds, cron=cron, context=ctx))
        return ResearchScheduler(jobs=jobs)

    def list_jobs(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for j in self._jobs:
            out.append(
                {
                    "job_id": j.job_id,
                    "workflow": j.workflow,
                    "trigger_type": j.trigger_type,
                    "interval_seconds": j.interval_seconds,
                    "cron": None if j.cron is None else "cron",
                    "context": j.context,
                }
            )
        return out

    def _load_state(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"schema_version": "research_scheduler_state_v1", "jobs": {}}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": "research_scheduler_state_v1", "jobs": {}}

    def _save_state(self, path: Path, state: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_history(self, record: dict[str, Any]) -> None:
        s = get_settings()
        s.research_scheduler_history_path.parent.mkdir(parents=True, exist_ok=True)
        with s.research_scheduler_history_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def run_pending(self, *, director: Any, now: datetime | None = None) -> list[dict[str, Any]]:
        ensure_project_dirs()
        s = get_settings()
        now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(second=0, microsecond=0)
        state = self._load_state(s.research_scheduler_state_path)
        jobs_state: dict[str, Any] = state.get("jobs") if isinstance(state.get("jobs"), dict) else {}

        results: list[dict[str, Any]] = []
        for job in self._jobs:
            js = jobs_state.get(job.job_id) if isinstance(jobs_state.get(job.job_id), dict) else {}

            due = False
            if job.trigger_type == "interval":
                last_run_at = js.get("last_run_at")
                if not last_run_at:
                    due = True
                else:
                    try:
                        last_dt = datetime.fromisoformat(str(last_run_at)).astimezone(timezone.utc)
                    except Exception:
                        last_dt = None
                    if last_dt is None:
                        due = True
                    else:
                        elapsed = (now_dt - last_dt).total_seconds()
                        due = elapsed >= float(job.interval_seconds or 0)
            else:
                cron_slot = now_dt.strftime("%Y%m%d%H%M")
                last_slot = str(js.get("last_cron_slot") or "")
                if job.cron is not None and job.cron.matches(now_dt) and cron_slot != last_slot:
                    due = True

            if not due:
                continue

            result = director.run(job.workflow, context=dict(job.context))
            results.append(result)
            jobs_state[job.job_id] = {
                "last_run_at": now_dt.isoformat(),
                "last_run_id": str(result.get("run_id") or ""),
                "last_status": str(result.get("status") or ""),
                "last_cron_slot": now_dt.strftime("%Y%m%d%H%M") if job.trigger_type == "cron" else "",
            }
            self._append_history(
                {
                    "job_id": job.job_id,
                    "workflow_name": job.workflow,
                    "run_time": now_dt.isoformat(),
                    "run_id": str(result.get("run_id") or ""),
                    "status": str(result.get("status") or ""),
                }
            )

        state["schema_version"] = "research_scheduler_state_v1"
        state["jobs"] = jobs_state
        state["updated_at"] = now_dt.isoformat()
        self._save_state(s.research_scheduler_state_path, state)
        return results
