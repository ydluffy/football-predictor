from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPETITION_REGISTRY_PATH = PROJECT_ROOT / "config" / "competitions.json"
DEFAULT_TEAM_ALIASES_PATH = PROJECT_ROOT / "data" / "mappings" / "team_aliases.json"


def normalize_alias(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = text.replace("&", " and ")
    return re.sub(r"[^0-9a-z\u3400-\u9fff]+", "", text)


@dataclass(frozen=True)
class CompetitionDefinition:
    competition_id: str
    display_name: str
    country: str
    competition_type: str
    tier: int | None
    season_format: str
    total_rounds: int | None
    model_group: str
    historical_model_coverage: bool
    aliases: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["aliases"] = list(self.aliases)
        return payload


class CompetitionRegistry:
    def __init__(self, definitions: Iterable[CompetitionDefinition]) -> None:
        self.definitions = tuple(definitions)
        self._by_id = {item.competition_id: item for item in self.definitions}
        self._by_alias: dict[str, CompetitionDefinition] = {}
        for item in self.definitions:
            for alias in (item.competition_id, item.display_name, *item.aliases):
                key = normalize_alias(alias)
                previous = self._by_alias.get(key)
                if previous is not None and previous.competition_id != item.competition_id:
                    raise ValueError(
                        f"duplicate competition alias {alias!r}: "
                        f"{previous.competition_id} vs {item.competition_id}"
                    )
                self._by_alias[key] = item

    def resolve(self, value: object) -> CompetitionDefinition | None:
        if value is None:
            return None
        return self._by_alias.get(normalize_alias(value))

    def get(self, competition_id: str) -> CompetitionDefinition | None:
        return self._by_id.get(str(competition_id))

    def annotate(self, value: object) -> dict[str, Any]:
        item = self.resolve(value)
        if item is None:
            return {
                "competition_id": "UNKNOWN",
                "competition_known": False,
                "competition_display_name": str(value or "").strip(),
                "competition_country": "",
                "competition_type": "unknown",
                "competition_tier": None,
                "season_format": "unknown",
                "total_rounds": None,
                "model_group": "unknown",
                "historical_model_coverage": False,
                "recommended_model_route": "market_anchor_fallback",
                "model_route_status": "fallback_required",
            }
        if item.competition_id == "FIFA_WORLD_CUP":
            route, status = "world_cup_specialist", "available"
        elif item.competition_id == "UEFA_EURO":
            route, status = "national_team_backbone", "competition_calibration_required"
        elif item.model_group.startswith("national_team_"):
            route, status = "national_team_backbone", "competition_calibration_required"
        elif item.historical_model_coverage:
            route, status = "club_history_candidate", "competition_calibration_required"
        else:
            route, status = "market_anchor_fallback", "historical_training_data_required"
        return {
            "competition_id": item.competition_id,
            "competition_known": True,
            "competition_display_name": item.display_name,
            "competition_country": item.country,
            "competition_type": item.competition_type,
            "competition_tier": item.tier,
            "season_format": item.season_format,
            "total_rounds": item.total_rounds,
            "model_group": item.model_group,
            "historical_model_coverage": item.historical_model_coverage,
            "recommended_model_route": route,
            "model_route_status": status,
        }


class TeamAliasRegistry:
    def __init__(self, records: Iterable[dict[str, Any]]) -> None:
        self._aliases: dict[str, str] = {}
        for record in records:
            canonical = str(record.get("canonical") or "").strip()
            if not canonical:
                raise ValueError("team alias record requires canonical")
            for alias in (canonical, *(record.get("aliases") or [])):
                key = normalize_alias(alias)
                previous = self._aliases.get(key)
                if previous is not None and previous != canonical:
                    raise ValueError(f"duplicate team alias {alias!r}: {previous!r} vs {canonical!r}")
                self._aliases[key] = canonical

    def resolve(self, value: object) -> str | None:
        return self._aliases.get(normalize_alias(value))

    def annotate(self, value: object) -> dict[str, Any]:
        raw = str(value or "").strip()
        canonical = self.resolve(value)
        return {
            "canonical_team": canonical or raw,
            "team_alias_known": canonical is not None,
        }


def load_competition_registry(
    path: str | Path = DEFAULT_COMPETITION_REGISTRY_PATH,
) -> CompetitionRegistry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported competition registry schema_version")
    definitions = [
        CompetitionDefinition(
            competition_id=str(item["competition_id"]),
            display_name=str(item["display_name"]),
            country=str(item["country"]),
            competition_type=str(item["competition_type"]),
            tier=None if item.get("tier") is None else int(item["tier"]),
            season_format=str(item["season_format"]),
            total_rounds=None if item.get("total_rounds") is None else int(item["total_rounds"]),
            model_group=str(item["model_group"]),
            historical_model_coverage=bool(item.get("historical_model_coverage", False)),
            aliases=tuple(str(value) for value in item.get("aliases", [])),
        )
        for item in payload.get("competitions", [])
    ]
    return CompetitionRegistry(definitions)


def load_team_alias_registry(
    path: str | Path = DEFAULT_TEAM_ALIASES_PATH,
) -> TeamAliasRegistry:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("unsupported team alias schema_version")
    return TeamAliasRegistry(payload.get("teams", []))
