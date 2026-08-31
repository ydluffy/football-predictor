from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pandas as pd


INDEX_COLUMNS = [
    "snapshot_id",
    "sales_day",
    "stage",
    "captured_at",
    "source_type",
    "source_path",
    "archive_path",
    "sha256",
    "rows",
    "match_numbers",
    "fixture_count",
    "fixtures_before_kickoff_count",
    "safe_match_numbers",
    "unsafe_match_numbers",
    "all_fixtures_before_kickoff",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_rows(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        return pd.read_csv(path, low_memory=False, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        # A UTF-8 BOM-only file has a non-zero size but no CSV columns.  It is
        # still worth archiving as evidence of a failed source response; the
        # caller's source status decides whether the scan can proceed.
        return pd.DataFrame()


def archive_sporttery_scan_inputs(
    *,
    official_markets_path: str | Path,
    play_odds_path: str | Path,
    scan: dict[str, Any],
    archive_root: str | Path,
    index_path: str | Path,
) -> dict[str, Any]:
    captured = pd.Timestamp(scan["scanned_at"])
    if captured.tzinfo is None:
        raise ValueError("scan scanned_at must be timezone-aware")
    stage = str(scan["stage"])
    sales_day = str(scan["sales_day"])
    stamp = captured.strftime("%Y%m%dT%H%M%S%z")
    snapshot_id = f"{sales_day}_{stamp}_{stage}"
    target_dir = Path(archive_root) / sales_day / snapshot_id
    target_dir.mkdir(parents=True, exist_ok=True)
    fixtures = scan.get("fixtures", [])
    safe_match_numbers = sorted(
        str(item.get("match_number"))
        for item in fixtures
        if item.get("match_number") and item.get("kickoff") and captured < pd.Timestamp(item["kickoff"])
    )
    unsafe_match_numbers = sorted(
        str(item.get("match_number"))
        for item in fixtures
        if item.get("match_number") and (
            not item.get("kickoff") or captured >= pd.Timestamp(item["kickoff"])
        )
    )
    all_before = bool(fixtures) and not unsafe_match_numbers
    match_numbers = sorted({str(item.get("match_number", "")) for item in fixtures if item.get("match_number")})

    records: list[dict[str, Any]] = []
    files = {
        "official_markets": Path(official_markets_path),
        "play_odds": Path(play_odds_path),
    }
    for source_type, source in files.items():
        if not source.exists():
            raise FileNotFoundError(f"missing sporttery snapshot input: {source}")
        digest = _sha256(source)
        archive = target_dir / f"{source_type}{source.suffix.lower()}"
        if archive.exists() and _sha256(archive) != digest:
            archive = target_dir / f"{source_type}_{digest[:12]}{source.suffix.lower()}"
        if not archive.exists():
            shutil.copy2(source, archive)
        frame = _read_rows(source)
        records.append(
            {
                "snapshot_id": snapshot_id,
                "sales_day": sales_day,
                "stage": stage,
                "captured_at": captured.isoformat(),
                "source_type": source_type,
                "source_path": str(source.resolve()),
                "archive_path": str(archive.resolve()),
                "sha256": digest,
                "rows": int(len(frame)),
                "match_numbers": ",".join(match_numbers),
                "fixture_count": int(len(fixtures)),
                "fixtures_before_kickoff_count": int(len(safe_match_numbers)),
                "safe_match_numbers": ",".join(safe_match_numbers),
                "unsafe_match_numbers": ",".join(unsafe_match_numbers),
                "all_fixtures_before_kickoff": all_before,
            }
        )

    index = Path(index_path)
    if index.exists() and index.stat().st_size:
        history = pd.read_csv(index, low_memory=False)
    else:
        history = pd.DataFrame(columns=INDEX_COLUMNS)
    combined = pd.concat([history, pd.DataFrame(records)], ignore_index=True, sort=False)
    combined = combined.drop_duplicates(["snapshot_id", "source_type", "sha256"], keep="last")
    combined = combined[INDEX_COLUMNS].sort_values(["captured_at", "source_type"], kind="mergesort")
    index.parent.mkdir(parents=True, exist_ok=True)
    part = index.with_suffix(index.suffix + ".part")
    combined.to_csv(part, index=False)
    part.replace(index)

    metadata = {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "sales_day": sales_day,
        "stage": stage,
        "captured_at": captured.isoformat(),
        "fixture_count": int(len(fixtures)),
        "fixtures_before_kickoff_count": int(len(safe_match_numbers)),
        "safe_match_numbers": safe_match_numbers,
        "unsafe_match_numbers": unsafe_match_numbers,
        "match_numbers": match_numbers,
        "all_fixtures_before_kickoff": all_before,
        "files": records,
        "index_path": str(index.resolve()),
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata
