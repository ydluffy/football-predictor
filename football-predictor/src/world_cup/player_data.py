from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from world_cup.data import normalize_national_team


SQUAD_ROLES = {"starter", "substitute", "squad"}
AVAILABILITY_STATUSES = {
    "unknown",
    "available",
    "doubtful",
    "injured",
    "suspended",
    "unavailable",
}


@dataclass(frozen=True)
class PlayerDataBundle:
    players: pd.DataFrame
    aliases: pd.DataFrame
    squads: pd.DataFrame
    availability: pd.DataFrame
    club_appearances: pd.DataFrame
    national_appearances: pd.DataFrame


def _read_csv(path: str | Path, required: set[str], name: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")
    return frame


def _parse_dates(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> pd.DataFrame:
    out = frame.copy()
    for column in columns:
        out[column] = pd.to_datetime(out[column], errors="coerce")
        if out[column].isna().any():
            raise ValueError(f"{name}.{column} contains invalid dates")
    return out


def _parse_boolean(series: pd.Series, name: str) -> pd.Series:
    mapping = {
        "true": True,
        "1": True,
        "yes": True,
        "false": False,
        "0": False,
        "no": False,
    }
    normalized = series.astype(str).str.lower().str.strip()
    invalid = sorted(set(normalized) - set(mapping))
    if invalid:
        raise ValueError(f"{name} contains invalid booleans: {invalid}")
    return normalized.map(mapping).astype(bool)


def load_player_registry(path: str | Path) -> pd.DataFrame:
    frame = _read_csv(
        path,
        {"player_id", "canonical_name", "national_team", "date_of_birth"},
        "players",
    )
    frame["player_id"] = frame["player_id"].astype(str).str.strip()
    frame["canonical_name"] = frame["canonical_name"].astype(str).str.strip()
    frame["national_team"] = frame["national_team"].map(normalize_national_team)
    frame["date_of_birth"] = pd.to_datetime(
        frame["date_of_birth"],
        errors="coerce",
    )
    if frame["player_id"].eq("").any() or frame["canonical_name"].eq("").any():
        raise ValueError("players contains blank identifiers or names")
    if frame["player_id"].duplicated().any():
        raise ValueError("players.player_id must be unique")
    return frame


def load_player_aliases(path: str | Path, players: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(
        path,
        {"source", "source_player_id", "source_name", "player_id"},
        "player_aliases",
    )
    for column in ("source", "source_player_id", "source_name", "player_id"):
        frame[column] = frame[column].astype(str).str.strip()
    if frame[["source", "source_player_id"]].duplicated().any():
        raise ValueError("player aliases contain duplicate source identities")
    if not set(frame["player_id"]) <= set(players["player_id"]):
        unknown = sorted(set(frame["player_id"]) - set(players["player_id"]))
        raise ValueError(f"player aliases reference unknown players: {unknown}")
    return frame


def resolve_player_id(
    aliases: pd.DataFrame,
    *,
    source: str,
    source_player_id: str | None = None,
    source_name: str | None = None,
) -> str:
    candidates = aliases[aliases["source"].eq(str(source).strip())]
    if source_player_id is not None:
        candidates = candidates[
            candidates["source_player_id"].eq(str(source_player_id).strip())
        ]
    elif source_name is not None:
        candidates = candidates[
            candidates["source_name"].str.casefold().eq(str(source_name).strip().casefold())
        ]
    else:
        raise ValueError("source_player_id or source_name is required")
    player_ids = candidates["player_id"].unique()
    if len(player_ids) != 1:
        raise ValueError(
            f"player identity is not uniquely resolved: source={source}, "
            f"source_player_id={source_player_id}, source_name={source_name}"
        )
    return str(player_ids[0])


def load_squad_snapshots(path: str | Path, players: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(
        path,
        {
            "snapshot_date",
            "team",
            "player_id",
            "role",
            "position",
            "club",
        },
        "squads",
    )
    frame = _parse_dates(frame, ("snapshot_date",), "squads")
    frame["team"] = frame["team"].map(normalize_national_team)
    frame["player_id"] = frame["player_id"].astype(str).str.strip()
    frame["role"] = frame["role"].astype(str).str.lower().str.strip()
    if not set(frame["role"]) <= SQUAD_ROLES:
        invalid = sorted(set(frame["role"]) - SQUAD_ROLES)
        raise ValueError(f"squads contains invalid roles: {invalid}")
    if frame[["snapshot_date", "team", "player_id"]].duplicated().any():
        raise ValueError("squads contains duplicate players in a team snapshot")
    _validate_player_references(frame, players, "squads")
    return frame


def load_availability(path: str | Path, players: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(
        path,
        {"as_of_date", "team", "player_id", "status", "reason"},
        "availability",
    )
    frame = _parse_dates(frame, ("as_of_date",), "availability")
    frame["team"] = frame["team"].map(normalize_national_team)
    frame["player_id"] = frame["player_id"].astype(str).str.strip()
    frame["status"] = frame["status"].astype(str).str.lower().str.strip()
    if not set(frame["status"]) <= AVAILABILITY_STATUSES:
        invalid = sorted(set(frame["status"]) - AVAILABILITY_STATUSES)
        raise ValueError(f"availability contains invalid statuses: {invalid}")
    if frame[["as_of_date", "team", "player_id"]].duplicated().any():
        raise ValueError("availability contains duplicate player status rows")
    _validate_player_references(frame, players, "availability")
    return frame


def load_club_appearances(path: str | Path, players: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(
        path,
        {
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
        },
        "club_appearances",
    )
    frame = _parse_dates(frame, ("match_date",), "club_appearances")
    frame["player_id"] = frame["player_id"].astype(str).str.strip()
    _validate_player_references(frame, players, "club_appearances")
    for column in ("minutes", "goals", "assists", "xg", "xa"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise ValueError(f"club_appearances.{column} contains invalid numbers")
    if ((frame["minutes"] < 0) | (frame["minutes"] > 130)).any():
        raise ValueError("club_appearances.minutes must be between 0 and 130")
    if not frame.empty:
        frame["started"] = _parse_boolean(
            frame["started"],
            "club_appearances.started",
        )
    else:
        frame["started"] = frame["started"].astype(bool)
    return frame


def load_national_appearances(path: str | Path, players: pd.DataFrame) -> pd.DataFrame:
    frame = _read_csv(
        path,
        {"match_date", "team", "opponent", "player_id", "started", "minutes"},
        "national_appearances",
    )
    frame = _parse_dates(frame, ("match_date",), "national_appearances")
    frame["team"] = frame["team"].map(normalize_national_team)
    frame["opponent"] = frame["opponent"].map(normalize_national_team)
    frame["player_id"] = frame["player_id"].astype(str).str.strip()
    _validate_player_references(frame, players, "national_appearances")
    frame["minutes"] = pd.to_numeric(frame["minutes"], errors="coerce")
    if frame["minutes"].isna().any():
        raise ValueError("national_appearances.minutes contains invalid numbers")
    if ((frame["minutes"] < 0) | (frame["minutes"] > 130)).any():
        raise ValueError("national_appearances.minutes must be between 0 and 130")
    if not frame.empty:
        frame["started"] = _parse_boolean(
            frame["started"],
            "national_appearances.started",
        )
    else:
        frame["started"] = frame["started"].astype(bool)
    if frame[["match_date", "team", "opponent", "player_id"]].duplicated().any():
        raise ValueError("national_appearances contains duplicate player-match rows")
    return frame


def _validate_player_references(
    frame: pd.DataFrame,
    players: pd.DataFrame,
    name: str,
) -> None:
    unknown = sorted(set(frame["player_id"]) - set(players["player_id"]))
    if unknown:
        raise ValueError(f"{name} references unknown players: {unknown}")


def load_player_data_bundle(root: str | Path) -> PlayerDataBundle:
    base = Path(root)
    players = load_player_registry(base / "players.csv")
    return PlayerDataBundle(
        players=players,
        aliases=load_player_aliases(base / "player_aliases.csv", players),
        squads=load_squad_snapshots(base / "squads.csv", players),
        availability=load_availability(base / "availability.csv", players),
        club_appearances=load_club_appearances(
            base / "club_appearances.csv",
            players,
        ),
        national_appearances=load_national_appearances(
            base / "national_appearances.csv",
            players,
        ),
    )
