from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE = "api_football"
ASIAN_HANDICAP_MARKET = "Asian Handicap"
SNAPSHOT_COLUMNS = [
    "record_id",
    "snapshot_id",
    "captured_at",
    "source",
    "source_fixture_id",
    "match_id",
    "competition_id",
    "league_id",
    "league_name",
    "kickoff_at",
    "home_team",
    "away_team",
    "bookmaker_id",
    "bookmaker_name",
    "bet_id",
    "bet_name",
    "home_handicap",
    "away_handicap",
    "home_odds",
    "away_odds",
    "raw_home_value",
    "raw_away_value",
    "provider_updated_at",
    "raw_sha256",
    "raw_archive_path",
    "mapping_status",
    "before_kickoff",
    "quarter_line",
    "price_balance_score",
    "is_bookmaker_main_line",
    "primary_line_price_balanced",
    "eligible_for_research",
    "eligible_for_primary_research",
    "reject_reason",
]


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != value:
            raise RuntimeError(f"immutable archive collision: {path}")
        return
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(value)
    part.replace(path)


def _timestamp(value: str | pd.Timestamp) -> pd.Timestamp:
    parsed = pd.Timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError("captured_at must be timezone-aware")
    return parsed


def _parse_asian_value(value: object) -> tuple[str, float] | None:
    match = re.fullmatch(
        r"\s*(Home|Away)\s*([+-]?\d+(?:\.\d+)?)\s*",
        str(value or ""),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return match.group(1).lower(), float(match.group(2))


def _mapping_for_fixture(
    mapping: pd.DataFrame,
    fixture_id: str,
) -> tuple[dict[str, Any], str]:
    if mapping.empty or "source_fixture_id" not in mapping.columns:
        return {}, "unmapped"
    candidates = mapping[mapping["source_fixture_id"].astype(str).eq(fixture_id)].copy()
    if candidates.empty:
        return {}, "unmapped"
    match_ids = {
        str(value).strip()
        for value in candidates.get("match_id", pd.Series(dtype=object)).tolist()
        if str(value).strip()
    }
    if len(candidates) != 1 or len(match_ids) != 1:
        return candidates.iloc[0].to_dict(), "ambiguous"
    return candidates.iloc[0].to_dict(), "mapped"


def normalize_api_football_asian_handicap(
    payload: dict[str, Any],
    *,
    mapping: pd.DataFrame,
    captured_at: str | pd.Timestamp,
    snapshot_id: str,
    raw_sha256: str,
    raw_archive_path: str | Path,
) -> pd.DataFrame:
    captured = _timestamp(captured_at)
    rows: list[dict[str, Any]] = []
    for event in payload.get("response") or []:
        fixture = event.get("fixture") or {}
        league = event.get("league") or {}
        fixture_id = str(fixture.get("id", "")).strip()
        if not fixture_id:
            continue
        mapped, mapping_status = _mapping_for_fixture(mapping, fixture_id)
        kickoff_raw = mapped.get("kickoff_at") or fixture.get("date") or ""
        kickoff = pd.to_datetime(kickoff_raw, errors="coerce", utc=True)
        before_kickoff = bool(pd.notna(kickoff) and captured.tz_convert("UTC") < kickoff)

        for bookmaker in event.get("bookmakers") or []:
            for bet in bookmaker.get("bets") or []:
                if str(bet.get("name", "")).strip().casefold() != ASIAN_HANDICAP_MARKET.casefold():
                    continue
                paired: dict[float, dict[str, Any]] = {}
                for value in bet.get("values") or []:
                    parsed = _parse_asian_value(value.get("value"))
                    if parsed is None:
                        continue
                    side, home_handicap = parsed
                    try:
                        decimal_odds = float(value.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if decimal_odds <= 1.0:
                        continue
                    item = paired.setdefault(home_handicap, {})
                    item[side] = decimal_odds
                    item[f"raw_{side}_value"] = str(value.get("value", ""))

                for home_handicap, pair in sorted(paired.items()):
                    if "home" not in pair or "away" not in pair:
                        continue
                    quarter_line = abs(home_handicap * 4 - round(home_handicap * 4)) <= 1e-8
                    reject_reasons: list[str] = []
                    if mapping_status != "mapped":
                        reject_reasons.append(f"fixture_mapping_{mapping_status}")
                    if pd.isna(kickoff):
                        reject_reasons.append("kickoff_missing")
                    elif not before_kickoff:
                        reject_reasons.append("captured_at_not_before_kickoff")
                    if not quarter_line:
                        reject_reasons.append("non_quarter_handicap")
                    record_key = "|".join(
                        [
                            snapshot_id,
                            fixture_id,
                            str(bookmaker.get("id", "")),
                            str(bet.get("id", "")),
                            f"{home_handicap:.4f}",
                        ]
                    )
                    rows.append(
                        {
                            "record_id": _sha256_bytes(record_key.encode("utf-8"))[:24],
                            "snapshot_id": snapshot_id,
                            "captured_at": captured.isoformat(),
                            "source": SOURCE,
                            "source_fixture_id": fixture_id,
                            "match_id": str(mapped.get("match_id", "")),
                            "competition_id": str(mapped.get("competition_id", "")),
                            "league_id": str(league.get("id", "")),
                            "league_name": str(league.get("name", "")),
                            "kickoff_at": pd.Timestamp(kickoff).isoformat() if pd.notna(kickoff) else "",
                            "home_team": str(mapped.get("home_team", "")),
                            "away_team": str(mapped.get("away_team", "")),
                            "bookmaker_id": str(bookmaker.get("id", "")),
                            "bookmaker_name": str(bookmaker.get("name", "")),
                            "bet_id": str(bet.get("id", "")),
                            "bet_name": str(bet.get("name", "")),
                            "home_handicap": float(home_handicap),
                            "away_handicap": float(-home_handicap),
                            "home_odds": float(pair["home"]),
                            "away_odds": float(pair["away"]),
                            "raw_home_value": pair.get("raw_home_value", ""),
                            "raw_away_value": pair.get("raw_away_value", ""),
                            "provider_updated_at": str(event.get("update", "")),
                            "raw_sha256": raw_sha256,
                            "raw_archive_path": str(Path(raw_archive_path).resolve()),
                            "mapping_status": mapping_status,
                            "before_kickoff": before_kickoff,
                            "quarter_line": quarter_line,
                            "price_balance_score": abs(math.log(float(pair["home"]) / float(pair["away"]))),
                            "is_bookmaker_main_line": False,
                            "primary_line_price_balanced": False,
                            "eligible_for_research": not reject_reasons,
                            "eligible_for_primary_research": False,
                            "reject_reason": ";".join(reject_reasons),
                        }
                    )
    frame = pd.DataFrame(rows, columns=SNAPSHOT_COLUMNS)
    if frame.empty:
        return frame
    group_columns = ["source_fixture_id", "bookmaker_id", "bet_id"]
    main_indices = frame.groupby(group_columns, dropna=False)["price_balance_score"].idxmin()
    frame.loc[main_indices, "is_bookmaker_main_line"] = True
    frame["primary_line_price_balanced"] = frame["price_balance_score"].le(0.5)
    frame["eligible_for_primary_research"] = (
        frame["eligible_for_research"].astype(bool)
        & frame["is_bookmaker_main_line"].astype(bool)
        & frame["primary_line_price_balanced"].astype(bool)
    )
    return frame


def archive_api_football_odds_snapshots(
    *,
    client: Any,
    mapping: pd.DataFrame,
    captured_at: str | pd.Timestamp,
    raw_root: str | Path,
    snapshot_root: str | Path,
    history_path: str | Path,
    continue_on_error: bool = True,
) -> dict[str, Any]:
    captured = _timestamp(captured_at)
    required = {"source_fixture_id", "match_id", "competition_id", "kickoff_at", "home_team", "away_team"}
    missing = required - set(mapping.columns)
    if missing:
        raise ValueError(f"API-Football odds mapping missing columns: {sorted(missing)}")

    fixture_ids = sorted({str(value).strip() for value in mapping["source_fixture_id"] if str(value).strip()})
    stamp = captured.tz_convert("UTC").strftime("%Y%m%dT%H%M%SZ")
    sales_day = captured.tz_convert("Asia/Shanghai").strftime("%Y-%m-%d")
    raw_records: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    quota: dict[str, str] = {}

    for fixture_id in fixture_ids:
        try:
            payload = client.get("odds", {"fixture": fixture_id})
            errors = payload.get("errors") if isinstance(payload, dict) else None
            if errors:
                raise RuntimeError("API-Football odds payload contains errors")
            encoded = _canonical_json(payload)
            digest = _sha256_bytes(encoded)
            raw_path = Path(raw_root) / sales_day / fixture_id / f"{stamp}_{digest[:12]}.json"
            _atomic_write_bytes(raw_path, encoded)
            raw_records.append(
                {
                    "fixture_id": fixture_id,
                    "payload": payload,
                    "sha256": digest,
                    "path": raw_path,
                }
            )
            quota = {
                "daily_limit": str(getattr(client, "last_headers", {}).get("x-ratelimit-requests-limit", "")),
                "daily_remaining": str(getattr(client, "last_headers", {}).get("x-ratelimit-requests-remaining", "")),
                "minute_limit": str(getattr(client, "last_headers", {}).get("x-ratelimit-limit", "")),
                "minute_remaining": str(getattr(client, "last_headers", {}).get("x-ratelimit-remaining", "")),
            }
        except Exception as exc:
            failed.append({"fixture_id": fixture_id, "error": str(exc)})
            if not continue_on_error:
                raise

    run_material = "|".join(f"{item['fixture_id']}:{item['sha256']}" for item in raw_records)
    run_digest = _sha256_bytes(f"{captured.isoformat()}|{run_material}".encode("utf-8"))
    snapshot_id = f"api_football_odds_{stamp}_{run_digest[:12]}"
    frames = [
        normalize_api_football_asian_handicap(
            item["payload"],
            mapping=mapping,
            captured_at=captured,
            snapshot_id=snapshot_id,
            raw_sha256=item["sha256"],
            raw_archive_path=item["path"],
        )
        for item in raw_records
    ]
    snapshot = pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    snapshot = snapshot[SNAPSHOT_COLUMNS]
    snapshot_path = Path(snapshot_root) / sales_day / f"{snapshot_id}.csv"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if not snapshot_path.exists():
        part = snapshot_path.with_suffix(".csv.part")
        snapshot.to_csv(part, index=False, encoding="utf-8-sig")
        part.replace(snapshot_path)
    primary_snapshot = snapshot[
        snapshot["eligible_for_primary_research"].astype(bool)
    ].copy()
    primary_snapshot_path = snapshot_path.with_name(f"{snapshot_path.stem}_primary.csv")
    if not primary_snapshot_path.exists():
        part = primary_snapshot_path.with_suffix(".csv.part")
        primary_snapshot.to_csv(part, index=False, encoding="utf-8-sig")
        part.replace(primary_snapshot_path)

    history_file = Path(history_path)
    if history_file.exists() and history_file.stat().st_size:
        history = pd.read_csv(history_file, low_memory=False)
    else:
        history = pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    combined = pd.concat([history, snapshot], ignore_index=True, sort=False)
    combined = combined.drop_duplicates("record_id", keep="last")
    home_prices = pd.to_numeric(combined["home_odds"], errors="coerce")
    away_prices = pd.to_numeric(combined["away_odds"], errors="coerce")
    combined["price_balance_score"] = (home_prices / away_prices).map(
        lambda value: abs(math.log(value)) if pd.notna(value) and value > 0 else float("nan")
    )
    combined["is_bookmaker_main_line"] = False
    valid_balance = combined[combined["price_balance_score"].notna()]
    if not valid_balance.empty:
        history_group_columns = ["snapshot_id", "source_fixture_id", "bookmaker_id", "bet_id"]
        main_indices = valid_balance.groupby(history_group_columns, dropna=False)["price_balance_score"].idxmin()
        combined.loc[main_indices, "is_bookmaker_main_line"] = True
    combined["primary_line_price_balanced"] = combined["price_balance_score"].le(0.5)
    eligible = combined["eligible_for_research"].map(
        lambda value: value is True or str(value).strip().lower() in {"true", "1", "yes"}
    )
    combined["eligible_for_primary_research"] = (
        eligible
        & combined["is_bookmaker_main_line"]
        & combined["primary_line_price_balanced"]
    )
    combined = combined[SNAPSHOT_COLUMNS].sort_values(
        ["captured_at", "source_fixture_id", "bookmaker_id", "home_handicap"],
        kind="mergesort",
    )
    history_file.parent.mkdir(parents=True, exist_ok=True)
    part = history_file.with_suffix(history_file.suffix + ".part")
    combined.to_csv(part, index=False, encoding="utf-8-sig")
    part.replace(history_file)

    return {
        "schema_version": 1,
        "source": SOURCE,
        "status": "ok" if not failed else "partial",
        "snapshot_id": snapshot_id,
        "captured_at": captured.isoformat(),
        "requested_fixtures": len(fixture_ids),
        "archived_fixtures": len(raw_records),
        "failed": failed,
        "asian_handicap_rows": int(len(snapshot)),
        "eligible_rows": int(snapshot["eligible_for_research"].astype(bool).sum()) if not snapshot.empty else 0,
        "bookmaker_main_line_rows": int(snapshot["is_bookmaker_main_line"].astype(bool).sum()) if not snapshot.empty else 0,
        "primary_line_rows": int(snapshot["eligible_for_primary_research"].astype(bool).sum()) if not snapshot.empty else 0,
        "unsafe_rows": int((~snapshot["before_kickoff"].astype(bool)).sum()) if not snapshot.empty else 0,
        "unmapped_rows": int((snapshot["mapping_status"] != "mapped").sum()) if not snapshot.empty else 0,
        "bookmakers": sorted(snapshot["bookmaker_name"].dropna().astype(str).unique().tolist()) if not snapshot.empty else [],
        "quota": quota,
        "raw_files": [str(Path(item["path"]).resolve()) for item in raw_records],
        "snapshot_path": str(snapshot_path.resolve()),
        "primary_snapshot_path": str(primary_snapshot_path.resolve()),
        "history_path": str(history_file.resolve()),
        "history_rows": int(len(combined)),
    }
