from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

import pandas as pd


DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "east_asia_data_sources.json"
SOURCE_KEY = "openfootball_japan_j1"

_DATE_RE = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+"
    r"(?P<day>\d{1,2})(?:\s+(?P<year>\d{4}))?$"
)
_MATCHDAY_RE = re.compile(r"^.+Matchday\s+(?P<matchday>\d+)\s*$", re.IGNORECASE)
_MATCH_RE = re.compile(
    r"^(?:(?P<time>\d{1,2}:\d{2})\s+)?"
    r"(?P<home>.+?)\s+v\s+(?P<away>.+?)"
    r"(?:\s+(?P<hg>\d+)-(?P<ag>\d+)"
    r"(?:\s+\((?P<hthg>\d+)-(?P<htag>\d+)\))?)?$"
)

OUTPUT_COLUMNS = [
    "match_id",
    "competition_id",
    "league",
    "season",
    "date",
    "kickoff_local",
    "matchday",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "halftime_home_goals",
    "halftime_away_goals",
    "actual_result",
    "status",
    "source",
    "source_url",
    "odds_available",
    "model_training_eligible",
]


def load_east_asia_source_policy(
    source_key: str = SOURCE_KEY,
    *,
    policy_path: str | Path = DEFAULT_POLICY_PATH,
) -> dict[str, object]:
    payload = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported east Asia data source schema_version")
    sources = payload.get("sources", {})
    if source_key not in sources:
        raise ValueError(f"unknown east Asia data source: {source_key}")
    return dict(sources[source_key])


def _match_id(date: str, home_team: str, away_team: str) -> str:
    key = f"J1|{date}|{home_team}|{away_team}".encode("utf-8")
    return f"J1-{hashlib.sha1(key).hexdigest()[:16]}"


def parse_openfootball_japan_j1(
    text: str,
    *,
    season: int,
    source_url: str,
) -> pd.DataFrame:
    if not re.search(r"Japan\s*\|\s*J1 League", text, re.IGNORECASE):
        raise ValueError("input is not an OpenFootball Japan J1 file")

    current_date: str | None = None
    matchday: int | None = None
    rows: list[dict[str, object]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue
        matchday_match = _MATCHDAY_RE.match(line)
        if matchday_match:
            matchday = int(matchday_match.group("matchday"))
            continue
        date_match = _DATE_RE.match(line)
        if date_match:
            year = int(date_match.group("year") or season)
            current_date = datetime.strptime(
                f"{year} {date_match.group('month')} {date_match.group('day')}", "%Y %b %d"
            ).date().isoformat()
            continue
        if current_date is None or matchday is None or " v " not in line:
            continue
        match = _MATCH_RE.match(line)
        if not match:
            continue
        home_team = match.group("home").strip()
        away_team = match.group("away").strip()
        home_goals = int(match.group("hg")) if match.group("hg") is not None else pd.NA
        away_goals = int(match.group("ag")) if match.group("ag") is not None else pd.NA
        settled = not pd.isna(home_goals) and not pd.isna(away_goals)
        actual_result = (
            "H" if settled and home_goals > away_goals else "A" if settled and home_goals < away_goals else "D"
        ) if settled else pd.NA
        rows.append(
            {
                "match_id": _match_id(current_date, home_team, away_team),
                "competition_id": "J1",
                "league": "J1",
                "season": str(season),
                "date": current_date,
                "kickoff_local": match.group("time") or pd.NA,
                "matchday": matchday,
                "home_team": home_team,
                "away_team": away_team,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "halftime_home_goals": int(match.group("hthg")) if match.group("hthg") else pd.NA,
                "halftime_away_goals": int(match.group("htag")) if match.group("htag") else pd.NA,
                "actual_result": actual_result,
                "status": "finished" if settled else "scheduled",
                "source": "OpenFootball",
                "source_url": source_url,
                "odds_available": False,
                "model_training_eligible": False,
            }
        )
    frame = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if frame.empty:
        raise ValueError("no J1 fixtures parsed from OpenFootball input")
    if frame["match_id"].duplicated().any():
        raise ValueError("duplicate J1 match_id parsed from OpenFootball input")
    return frame


def download_openfootball_japan_j1(
    *,
    output_dir: str | Path,
    years: Iterable[int],
    policy_path: str | Path = DEFAULT_POLICY_PATH,
    timeout: float = 30.0,
) -> tuple[list[Path], list[dict[str, object]]]:
    policy = load_east_asia_source_policy(policy_path=policy_path)
    if not policy.get("automatic_download_allowed") or not policy.get("storage_allowed"):
        raise PermissionError("source policy does not allow automatic download and storage")
    allowed = {int(year) for year in policy.get("available_years", [])}
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    downloaded: list[Path] = []
    failures: list[dict[str, object]] = []
    template = str(policy["raw_url_template"])
    for year_value in years:
        year = int(year_value)
        url = template.format(year=year)
        if year not in allowed:
            failures.append({"year": year, "url": url, "error": "year_not_allowed_by_policy"})
            continue
        target = root / f"{year}_jp1.txt"
        part = target.with_suffix(target.suffix + ".part")
        try:
            request = Request(url, headers={"User-Agent": "football-predictor/0.1"})
            with urlopen(request, timeout=float(timeout)) as response:
                content = response.read()
            text = content.decode("utf-8-sig")
            parse_openfootball_japan_j1(text, season=year, source_url=url)
            part.write_bytes(content)
            part.replace(target)
            downloaded.append(target)
        except Exception as exc:  # the audit must retain each per-season failure
            if part.exists():
                part.unlink()
            failures.append({"year": year, "url": url, "error": f"{type(exc).__name__}: {exc}"})
    return downloaded, failures


def build_openfootball_japan_context_dataset(
    *,
    input_dir: str | Path,
    output_path: str | Path,
    audit_path: str | Path,
    policy_path: str | Path = DEFAULT_POLICY_PATH,
    download_failures: list[dict[str, object]] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    policy = load_east_asia_source_policy(policy_path=policy_path)
    root = Path(input_dir)
    frames: list[pd.DataFrame] = []
    files = sorted(root.glob("*_jp1.txt"))
    for path in files:
        year = int(path.stem.split("_", 1)[0])
        source_url = str(policy["raw_url_template"]).format(year=year)
        frames.append(
            parse_openfootball_japan_j1(path.read_text(encoding="utf-8-sig"), season=year, source_url=source_url)
        )
    if not frames:
        raise FileNotFoundError(f"no OpenFootball Japan J1 files found: {root}")
    combined = pd.concat(frames, ignore_index=True).sort_values(["date", "match_id"], kind="mergesort")
    combined = combined.drop_duplicates("match_id", keep="last").reset_index(drop=True)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    combined.to_csv(part, index=False)
    part.replace(output)
    season_quality: dict[str, dict[str, object]] = {}
    for season, group in combined.groupby("season", sort=True):
        finished = int((group["status"] == "finished").sum())
        scheduled = int((group["status"] == "scheduled").sum())
        season_quality[str(season)] = {
            "rows": int(len(group)),
            "finished_rows": finished,
            "unresolved_schedule_rows": scheduled,
            "result_completeness": round(finished / len(group), 6) if len(group) else 0.0,
            "complete_results": scheduled == 0,
        }
    incomplete_result_seasons = [
        season for season, quality in season_quality.items() if not quality["complete_results"]
    ]
    audit: dict[str, object] = {
        "competition_id": "J1",
        "source": "OpenFootball",
        "license": policy.get("license"),
        "input_files": [str(path) for path in files],
        "rows": int(len(combined)),
        "finished_rows": int((combined["status"] == "finished").sum()),
        "scheduled_rows": int((combined["status"] == "scheduled").sum()),
        "seasons": combined["season"].value_counts().sort_index().to_dict(),
        "season_quality": season_quality,
        "incomplete_result_seasons": incomplete_result_seasons,
        "date_min": str(combined["date"].min()),
        "date_max": str(combined["date"].max()),
        "odds_available": False,
        "model_training_eligible": False,
        "training_gate": "blocked_missing_pre_match_odds",
        "schedule_usage_gate": "historical_context_only_not_current_schedule",
        "download_failures": download_failures or [],
        "output_path": str(output.resolve()),
    }
    audit_file = Path(audit_path)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return combined, audit
