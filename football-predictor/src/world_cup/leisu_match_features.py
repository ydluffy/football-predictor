from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from world_cup.data import normalize_national_team


LEISU_TEAM_ZH_TO_EN = {
    "阿尔及利亚": "Algeria",
    "阿根廷": "Argentina",
    "澳大利亚": "Australia",
    "奥地利": "Austria",
    "比利时": "Belgium",
    "波黑": "Bosnia-Herzegovina",
    "巴西": "Brazil",
    "加拿大": "Canada",
    "佛得角": "Cape Verde",
    "哥斯达黎加": "Costa Rica",
    "库拉索": "Curaçao",
    "捷克": "Czechia",
    "厄瓜多尔": "Ecuador",
    "埃及": "Egypt",
    "法国": "France",
    "德国": "Germany",
    "海地": "Haiti",
    "洪都拉斯": "Honduras",
    "伊朗": "Iran",
    "伊拉克": "Iraq",
    "科特迪瓦": "Ivory Coast",
    "日本": "Japan",
    "约旦": "Jordan",
    "韩国": "South Korea",
    "墨西哥": "Mexico",
    "摩洛哥": "Morocco",
    "荷兰": "Netherlands",
    "新西兰": "New Zealand",
    "挪威": "Norway",
    "巴拉圭": "Paraguay",
    "卡塔尔": "Qatar",
    "沙特阿拉伯": "Saudi Arabia",
    "苏格兰": "Scotland",
    "塞内加尔": "Senegal",
    "南非": "South Africa",
    "西班牙": "Spain",
    "瑞典": "Sweden",
    "瑞士": "Switzerland",
    "突尼斯": "Tunisia",
    "土耳其": "Türkiye",
    "乌拉圭": "Uruguay",
    "美国": "USA",
}


def normalize_leisu_team(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    return normalize_national_team(LEISU_TEAM_ZH_TO_EN.get(text, text))


def _parse_leisu_date(value: object, *, year: int) -> pd.Timestamp | pd.NaT:
    text = str(value or "").strip()
    match = re.search(r"(?P<month>\d{1,2})-(?P<day>\d{1,2})", text)
    if not match:
        return pd.NaT
    return pd.Timestamp(year=year, month=int(match.group("month")), day=int(match.group("day")))


def prepare_leisu_world_cup_matches(
    leisu_matches: pd.DataFrame,
    *,
    year: int = 2026,
) -> pd.DataFrame:
    required = {
        "leisu_match_id",
        "competition",
        "date_text",
        "home_team_zh",
        "away_team_zh",
        "intelligence_count",
    }
    missing = required - set(leisu_matches.columns)
    if missing:
        raise ValueError(f"missing Leisu public match columns: {sorted(missing)}")

    out = leisu_matches.copy()
    out = out[out["competition"].astype(str).str.contains("世界杯", na=False)].copy()
    out["leisu_date"] = out["date_text"].map(lambda x: _parse_leisu_date(x, year=year))
    out["leisu_home_team"] = out["home_team_zh"].map(normalize_leisu_team)
    out["leisu_away_team"] = out["away_team_zh"].map(normalize_leisu_team)
    out["intelligence_count"] = pd.to_numeric(
        out["intelligence_count"],
        errors="coerce",
    ).fillna(0).astype(int)
    return out.reset_index(drop=True)


def attach_leisu_features_to_fixtures(
    fixtures: pd.DataFrame,
    leisu_matches: pd.DataFrame,
    *,
    year: int = 2026,
    max_date_delta_days: int = 1,
) -> pd.DataFrame:
    required = {"match_id", "date", "home_team", "away_team"}
    missing = required - set(fixtures.columns)
    if missing:
        raise ValueError(f"missing fixture columns: {sorted(missing)}")

    leisu = prepare_leisu_world_cup_matches(leisu_matches, year=year)
    fixture_rows: list[dict[str, object]] = []
    for fixture in fixtures.copy().itertuples(index=False):
        fixture_date = pd.Timestamp(fixture.date).normalize()
        home = normalize_national_team(fixture.home_team)
        away = normalize_national_team(fixture.away_team)
        candidates: list[tuple[int, str, pd.Series]] = []
        for _, item in leisu.iterrows():
            if pd.isna(item["leisu_date"]):
                continue
            same_order = item["leisu_home_team"] == home and item["leisu_away_team"] == away
            reversed_order = item["leisu_home_team"] == away and item["leisu_away_team"] == home
            if not same_order and not reversed_order:
                continue
            delta = abs((pd.Timestamp(item["leisu_date"]) - fixture_date).days)
            if delta <= max_date_delta_days:
                candidates.append((delta, "same" if same_order else "reversed", item))

        candidates.sort(key=lambda entry: (entry[0], entry[1] != "same"))
        base = {
            "match_id": getattr(fixture, "match_id"),
            "date": str(fixture_date.date()),
            "home_team": home,
            "away_team": away,
            "leisu_public_match_linked": 0,
            "leisu_match_id": "",
            "leisu_team_order": "",
            "leisu_date_delta_days": pd.NA,
            "leisu_competition_zh": "",
            "leisu_date_text": "",
            "leisu_time_text": "",
            "leisu_home_team_zh": "",
            "leisu_away_team_zh": "",
            "leisu_intelligence_count": 0,
            "leisu_has_intelligence": 0,
            "leisu_detail_url": "",
            "leisu_analysis_url": "",
            "leisu_intelligence_url": "",
        }
        if candidates:
            delta, order, item = candidates[0]
            base.update(
                {
                    "leisu_public_match_linked": 1,
                    "leisu_match_id": str(item.get("leisu_match_id", "")),
                    "leisu_team_order": order,
                    "leisu_date_delta_days": int(delta),
                    "leisu_competition_zh": str(item.get("competition", "")),
                    "leisu_date_text": str(item.get("date_text", "")),
                    "leisu_time_text": str(item.get("time_text", "")),
                    "leisu_home_team_zh": str(item.get("home_team_zh", "")),
                    "leisu_away_team_zh": str(item.get("away_team_zh", "")),
                    "leisu_intelligence_count": int(item.get("intelligence_count", 0)),
                    "leisu_has_intelligence": int(item.get("intelligence_count", 0) > 0),
                    "leisu_detail_url": str(item.get("detail_url", "")),
                    "leisu_analysis_url": str(item.get("analysis_url", "")),
                    "leisu_intelligence_url": str(item.get("intelligence_url", "")),
                }
            )
        fixture_rows.append(base)
    return pd.DataFrame(fixture_rows)


def export_leisu_fixture_features(
    *,
    fixtures_path: str | Path,
    leisu_matches_path: str | Path,
    output_path: str | Path,
    audit_output_path: str | Path | None = None,
    year: int = 2026,
    max_date_delta_days: int = 1,
) -> dict[str, object]:
    fixtures = pd.read_csv(fixtures_path)
    leisu_matches = pd.read_csv(leisu_matches_path, dtype={"leisu_match_id": str})
    features = attach_leisu_features_to_fixtures(
        fixtures,
        leisu_matches,
        year=year,
        max_date_delta_days=max_date_delta_days,
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output, index=False)
    audit = {
        "source": "leisu_public_html",
        "fixtures": int(len(features)),
        "linked_fixtures": int(features["leisu_public_match_linked"].sum()),
        "unlinked_fixtures": int((features["leisu_public_match_linked"] == 0).sum()),
        "linked_with_intelligence": int(features["leisu_has_intelligence"].sum()),
        "max_date_delta_days": int(max_date_delta_days),
        "output": str(output),
        "method": "team-name match with Chinese-to-English national-team aliases; date may differ by configured tolerance for timezone display.",
    }
    if audit_output_path is not None:
        audit_path = Path(audit_output_path)
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit
