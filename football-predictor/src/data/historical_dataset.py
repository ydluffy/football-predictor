from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.request import Request, urlopen

import pandas as pd

from data.field_mapping import apply_field_mapping, load_field_mapping
from data.transform_rules import parse_match_dates, standardize_dataset_values
from data.validate_dataset import ensure_match_id


DEFAULT_DIVISIONS = ("E0", "E1", "E2", "E3", "EC")
DEFAULT_SOURCE_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "historical_data_sources.json"
TRAINING_REQUIRED_FIELDS = (
    "match_id",
    "date",
    "league",
    "home_team",
    "away_team",
    "home_goals",
    "away_goals",
    "odds_home",
    "odds_draw",
    "odds_away",
    "actual_result",
)


def _read_historical_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, low_memory=False, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(path, low_memory=False, encoding="cp1252")


def season_code(season: str) -> str:
    start_text, end_text = str(season).split("-", 1)
    start = int(start_text)
    end = int(end_text)
    if end < 100:
        end += (start // 100) * 100
    if end != start + 1:
        raise ValueError(f"非法赛季: {season}")
    return f"{start % 100:02d}{end % 100:02d}"


def infer_season(dates: pd.Series) -> pd.Series:
    parsed = parse_match_dates(dates)
    start_year = parsed.dt.year.where(parsed.dt.month >= 7, parsed.dt.year - 1)
    return start_year.map(lambda y: f"{int(y):04d}-{(int(y) + 1) % 100:02d}" if pd.notna(y) else pd.NA)


def download_football_data_files(
    *,
    output_dir: str | Path,
    seasons: Iterable[str],
    divisions: Iterable[str] = DEFAULT_DIVISIONS,
    timeout: float = 30.0,
) -> list[Path]:
    root = Path(output_dir)
    downloaded: list[Path] = []
    for season in seasons:
        code = season_code(season)
        season_dir = root / str(season)
        season_dir.mkdir(parents=True, exist_ok=True)
        for division in divisions:
            url = f"https://www.football-data.co.uk/mmz4281/{code}/{division}.csv"
            request = Request(url, headers={"User-Agent": "football-predictor/0.1"})
            with urlopen(request, timeout=float(timeout)) as response:
                content = response.read()
            preview = pd.read_csv(BytesIO(content), nrows=5, low_memory=False)
            required = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}
            missing = required - set(preview.columns)
            if missing:
                raise ValueError(f"downloaded {division} {season} missing columns: {sorted(missing)}")
            found_divisions = set(preview["Div"].dropna().astype(str).str.strip().unique())
            if found_divisions and found_divisions != {str(division)}:
                raise ValueError(
                    f"downloaded {division} {season} contains unexpected Div values: {sorted(found_divisions)}"
                )
            target = season_dir / f"{division}.csv"
            part = target.with_suffix(target.suffix + ".part")
            part.write_bytes(content)
            part.replace(target)
            downloaded.append(target)
    return downloaded


def load_division_profile(
    profile: str,
    *,
    config_path: str | Path = DEFAULT_SOURCE_CONFIG_PATH,
) -> tuple[str, ...]:
    payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported historical data source schema_version")
    profiles = payload.get("football_data_csv", {}).get("profiles", {})
    if profile not in profiles:
        raise ValueError(f"unknown historical data profile: {profile}")
    divisions = tuple(str(item).strip() for item in profiles[profile] if str(item).strip())
    if not divisions:
        raise ValueError(f"historical data profile is empty: {profile}")
    return divisions


def build_historical_dataset(
    *,
    input_dir: str | Path,
    mapping_path: str | Path,
    output_path: str | Path,
    audit_path: str | Path,
    divisions: Iterable[str] | None = None,
) -> tuple[pd.DataFrame, dict[str, object]]:
    root = Path(input_dir)
    paths = sorted(root.rglob("*.csv"))
    selected_divisions = None if divisions is None else {str(item).strip() for item in divisions}
    if selected_divisions is not None:
        paths = [path for path in paths if path.stem in selected_divisions]
    if not paths:
        raise FileNotFoundError(f"未找到历史 CSV: {root}")

    frames: list[pd.DataFrame] = []
    mapping = load_field_mapping(mapping_path)
    source_rows = 0
    for path in paths:
        raw = _read_historical_csv(path)
        if raw.empty:
            continue
        source_rows += int(len(raw))
        mapped = apply_field_mapping(raw, mapping)
        mapped = standardize_dataset_values(mapped)
        if "actual_result" in mapped.columns:
            result = mapped["actual_result"].astype("string").str.lower()
            mapped["actual_result"] = result.map({"home": "H", "draw": "D", "away": "A"}).astype("string")
        mapped, _ = ensure_match_id(mapped)
        mapped["source_file"] = str(path.relative_to(root))
        mapped["season"] = infer_season(mapped["date"])
        frames.append(mapped)

    if not frames:
        raise ValueError("历史 CSV 均为空")

    combined = pd.concat(frames, axis=0, ignore_index=True, sort=False)
    missing_columns = [c for c in TRAINING_REQUIRED_FIELDS if c not in combined.columns]
    if missing_columns:
        raise ValueError(f"历史数据缺少训练字段: {missing_columns}")

    valid_mask = combined[list(TRAINING_REQUIRED_FIELDS)].notna().all(axis=1)
    trainable = combined.loc[valid_mask].copy()
    duplicate_count = int(trainable["match_id"].duplicated().sum())
    if duplicate_count:
        trainable = trainable.drop_duplicates("match_id", keep="last").copy()

    trainable["date"] = parse_match_dates(trainable["date"]).dt.date.astype("string")
    trainable = trainable.sort_values(["date", "league", "match_id"], kind="mergesort").reset_index(drop=True)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    trainable.to_csv(output, index=False)

    audit: dict[str, object] = {
        "input_dir": str(root.resolve()),
        "output_path": str(output.resolve()),
        "source_file_count": len(paths),
        "selected_divisions": sorted(selected_divisions) if selected_divisions is not None else None,
        "source_rows": source_rows,
        "rows_with_missing_required_fields": int((~valid_mask).sum()),
        "duplicate_match_id_count": duplicate_count,
        "trainable_rows": int(len(trainable)),
        "seasons": trainable["season"].value_counts().sort_index().to_dict(),
        "leagues": trainable["league"].value_counts().sort_index().to_dict(),
        "date_min": str(trainable["date"].min()),
        "date_max": str(trainable["date"].max()),
    }
    audit_file = Path(audit_path)
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    audit_file.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return trainable, audit
