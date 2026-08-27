from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pandas as pd
import requests


INTERNATIONAL_RESULTS_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)
REQUIRED_COLUMNS = {
    "date",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
    "tournament",
    "neutral",
}


def validate_international_results_file(
    path: str | Path,
    *,
    min_rows: int = 40_000,
    min_latest_date: str = "2022-01-01",
) -> dict[str, object]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    frame = pd.read_csv(source)
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"missing international results columns: {sorted(missing)}")
    if len(frame) < min_rows:
        raise ValueError(f"international results file has only {len(frame)} rows")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    if dates.notna().sum() != len(frame):
        raise ValueError("international results file contains invalid dates")
    latest_date = dates.max()
    if latest_date < pd.Timestamp(min_latest_date):
        raise ValueError(
            f"international results latest date {latest_date.date()} is older than "
            f"{pd.Timestamp(min_latest_date).date()}"
        )

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "path": str(source),
        "rows": int(len(frame)),
        "earliest_date": str(dates.min().date()),
        "latest_date": str(latest_date.date()),
        "sha256": digest,
        "bytes": int(source.stat().st_size),
    }


def refresh_international_results(
    destination: str | Path,
    *,
    url: str = INTERNATIONAL_RESULTS_URL,
    timeout: int = 90,
    min_rows: int = 40_000,
    min_latest_date: str = "2022-01-01",
) -> dict[str, object]:
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")

    try:
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        metadata = validate_international_results_file(
            temporary,
            min_rows=min_rows,
            min_latest_date=min_latest_date,
        )
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    metadata["path"] = str(target)
    return metadata
