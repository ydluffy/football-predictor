from __future__ import annotations

from pathlib import Path

import pandas as pd

from world_cup.player_data import PlayerDataBundle, load_player_data_bundle


REQUIRED_INPUT_COLUMNS = {
    "match_date",
    "club",
    "competition",
    "minutes",
    "started",
    "goals",
    "assists",
    "xg",
    "xa",
}

OUTPUT_COLUMNS = [
    "match_date",
    "player_id",
    "club",
    "competition",
    "minutes",
    "started",
    "goals",
    "assists",
    "xg",
    "xa",
]


def _resolve_input_players(frame: pd.DataFrame, bundle: PlayerDataBundle) -> pd.Series:
    direct = (
        frame["player_id"].fillna("").astype(str).str.strip()
        if "player_id" in frame.columns
        else pd.Series("", index=frame.index)
    )
    if direct.ne("").all():
        return direct
    required = {"source", "source_player_id"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(
            "club form input must include player_id or source/source_player_id"
        )
    aliases = bundle.aliases.copy()
    aliases["source"] = aliases["source"].astype(str).str.strip()
    aliases["source_player_id"] = aliases["source_player_id"].astype(str).str.strip()
    lookup = aliases.set_index(["source", "source_player_id"])["player_id"].to_dict()
    resolved = []
    missing_keys = []
    for index, row in enumerate(frame.itertuples(index=False)):
        if direct.iloc[index]:
            resolved.append(direct.iloc[index])
            continue
        key = (str(getattr(row, "source")).strip(), str(getattr(row, "source_player_id")).strip())
        player_id = lookup.get(key)
        if player_id is None:
            missing_keys.append(key)
            resolved.append("")
        else:
            resolved.append(player_id)
    if missing_keys:
        raise ValueError(f"unresolved club form player aliases: {missing_keys[:10]}")
    return pd.Series(resolved, index=frame.index)


def normalize_club_form_input(
    input_path: str | Path,
    bundle: PlayerDataBundle,
) -> pd.DataFrame:
    frame = pd.read_csv(input_path)
    missing = REQUIRED_INPUT_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"club form input missing columns: {sorted(missing)}")
    out = frame.copy()
    out["player_id"] = _resolve_input_players(out, bundle)
    out = out[OUTPUT_COLUMNS].copy()
    out["match_date"] = pd.to_datetime(out["match_date"], errors="coerce")
    if out["match_date"].isna().any():
        raise ValueError("club form input contains invalid match_date values")
    for column in ("minutes", "goals", "assists", "xg", "xa"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
        if out[column].isna().any():
            raise ValueError(f"club form input contains invalid {column} values")
    if ((out["minutes"] < 0) | (out["minutes"] > 130)).any():
        raise ValueError("club form minutes must be between 0 and 130")
    out["started"] = out["started"].astype(str).str.lower().str.strip().map(
        {
            "true": True,
            "1": True,
            "yes": True,
            "false": False,
            "0": False,
            "no": False,
        }
    )
    if out["started"].isna().any():
        raise ValueError("club form input contains invalid started values")
    return out


def import_club_form_csv(
    *,
    player_data_dir: str | Path,
    input_path: str | Path,
    as_of_date: str | pd.Timestamp,
    window_days: int = 90,
) -> dict[str, object]:
    root = Path(player_data_dir)
    bundle = load_player_data_bundle(root)
    incoming = normalize_club_form_input(input_path, bundle)
    existing = bundle.club_appearances.copy()
    combined = pd.concat([existing, incoming], ignore_index=True)
    combined = combined.drop_duplicates(
        ["match_date", "player_id", "club", "competition"],
        keep="last",
    ).sort_values(["match_date", "player_id"], kind="mergesort")
    combined.to_csv(root / "club_appearances.csv", index=False)

    cutoff = pd.Timestamp(as_of_date).normalize()
    start = cutoff - pd.Timedelta(days=window_days)
    recent = combined[
        combined["match_date"].lt(cutoff)
        & combined["match_date"].ge(start)
    ]
    players = set(bundle.players["player_id"])
    covered_players = set(recent["player_id"])
    starter_ids = set(
        bundle.squads[
            bundle.squads["snapshot_date"].le(cutoff)
            & bundle.squads["role"].eq("starter")
        ]["player_id"]
    )
    return {
        "input_rows": int(len(incoming)),
        "club_appearance_rows": int(len(combined)),
        "recent_window_days": int(window_days),
        "recent_rows": int(len(recent)),
        "recent_player_coverage": len(covered_players & players) / len(players)
        if players
        else 0.0,
        "recent_confirmed_starter_coverage": (
            len(covered_players & starter_ids) / len(starter_ids)
            if starter_ids
            else 0.0
        ),
        "output": str(root / "club_appearances.csv"),
    }
