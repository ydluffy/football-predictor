from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


_TITLE_RE = re.compile(r"^=\s*World Cup\s+(?P<year>\d{4})")
_MATCH_RE = re.compile(
    r"^\s*(?P<home>.+?)\s+v\s+(?P<away>.+?)\s{2,}"
    r"(?P<home_goals>\d+)-(?P<away_goals>\d+)"
)

TEAM_ALIASES = {
    "cote d ivoire": "Ivory Coast",
    "curacao": "Curaçao",
    "dr congo": "Congo DR",
    "democratic republic of congo": "Congo DR",
    "congo dr": "Congo DR",
    "ir iran": "Iran",
    "korea republic": "South Korea",
    "korea dpr": "North Korea",
    "turkiye": "Türkiye",
    "united states": "USA",
}

CN_TEAM_ALIASES = {
    "厄瓜多尔": "Ecuador",
    "德国": "Germany",
    "库拉索": "Curaçao",
    "科特迪瓦": "Ivory Coast",
    "突尼斯": "Tunisia",
    "荷兰": "Netherlands",
    "日本": "Japan",
    "瑞典": "Sweden",
    "巴西": "Brazil",
    "摩洛哥": "Morocco",
    "巴拉圭": "Paraguay",
    "澳大利亚": "Australia",
    "土耳其": "Türkiye",
    "葡萄牙": "Portugal",
    "乌拉圭": "Uruguay",
    "挪威": "Norway",
    "法国": "France",
    "伊拉克": "Iraq",
    "佛得角": "Cape Verde",
    "沙特": "Saudi Arabia",
    "西班牙": "Spain",
    "埃及": "Egypt",
    "伊朗": "Iran",
    "比利时": "Belgium",
    "克罗地亚": "Croatia",
    "加纳": "Ghana",
    "捷克": "Czechia",
    "美国": "USA",
    "波兰": "Poland",
    "新西兰": "New Zealand",
    "塞内加尔": "Senegal",
    "墨西哥": "Mexico",
    "巴拿马": "Panama",
    "英格兰": "England",
    "哥伦比亚": "Colombia",
    "刚果金": "Congo DR",
    "乌兹别克": "Uzbekistan",
    "阿尔及利": "Algeria",
    "阿尔及利亚": "Algeria",
    "奥地利": "Austria",
    "约旦": "Jordan",
    "阿根廷": "Argentina",
    "加拿大": "Canada",
}

TOURNAMENT_IMPORTANCE = {
    "FIFA World Cup": 1.5,
    "FIFA World Cup qualification": 1.2,
    "UEFA Euro": 1.3,
    "UEFA Euro qualification": 1.1,
    "Copa América": 1.3,
    "African Cup of Nations": 1.3,
    "AFC Asian Cup": 1.3,
    "CONCACAF Gold Cup": 1.2,
    "UEFA Nations League": 1.0,
    "Friendly": 0.55,
}


def normalize_national_team(value: object) -> str:
    raw = str(value).strip()
    if raw in CN_TEAM_ALIASES:
        return CN_TEAM_ALIASES[raw]
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    key = re.sub(r"\s+", " ", text).strip()
    return TEAM_ALIASES.get(key, raw)


def parse_world_cup_min_text(text: str, *, source: str = "") -> pd.DataFrame:
    tournament_year: int | None = None
    stage = ""
    rows: list[dict[str, object]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        title = _TITLE_RE.match(line)
        if title:
            tournament_year = int(title.group("year"))
            continue
        if line.strip().startswith("▪"):
            stage = line.strip().lstrip("▪").strip()
            continue

        match = _MATCH_RE.match(line)
        if not match or tournament_year is None:
            continue
        home_goals = int(match.group("home_goals"))
        away_goals = int(match.group("away_goals"))
        rows.append(
            {
                "tournament_year": tournament_year,
                "match_order": len(rows),
                "stage": stage,
                "home_team": normalize_national_team(match.group("home")),
                "away_team": normalize_national_team(match.group("away")),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "actual_result": "H" if home_goals > away_goals else "A" if away_goals > home_goals else "D",
                "source": source,
                "source_line": line_number,
            }
        )
    return pd.DataFrame(rows)


def load_world_cup_min_directory(path: str | Path) -> pd.DataFrame:
    root = Path(path)
    frames = [
        parse_world_cup_min_text(file.read_text(encoding="utf-8"), source=str(file.name))
        for file in sorted(root.glob("*.txt"))
    ]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        raise FileNotFoundError(f"no World Cup text files found under {root}")
    out = pd.concat(frames, ignore_index=True)
    return out.sort_values(["tournament_year", "match_order"], kind="mergesort").reset_index(drop=True)


def tournament_importance(name: object) -> float:
    text = str(name).strip()
    if text in TOURNAMENT_IMPORTANCE:
        return float(TOURNAMENT_IMPORTANCE[text])
    if "qualification" in text.lower():
        return 1.1
    return 0.85


def load_international_results(
    path: str | Path,
    *,
    start_date: str = "2000-01-01",
    end_date: str | None = None,
    completed_only: bool = True,
) -> pd.DataFrame:
    raw = pd.read_csv(path)
    required = {
        "date",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "tournament",
        "neutral",
    }
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"missing international results columns: {sorted(missing)}")

    out = raw.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["home_score"] = pd.to_numeric(out["home_score"], errors="coerce")
    out["away_score"] = pd.to_numeric(out["away_score"], errors="coerce")
    out = out[out["date"].notna()]
    out = out[out["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        out = out[out["date"] <= pd.Timestamp(end_date)]
    if completed_only:
        out = out[out["home_score"].notna() & out["away_score"].notna()]

    out["home_team"] = out["home_team"].map(normalize_national_team)
    out["away_team"] = out["away_team"].map(normalize_national_team)
    out["home_goals"] = out["home_score"].astype("Int64")
    out["away_goals"] = out["away_score"].astype("Int64")
    out["neutral"] = out["neutral"].astype("boolean")
    out["importance"] = out["tournament"].map(tournament_importance)
    completed = out["home_goals"].notna() & out["away_goals"].notna()
    out["actual_result"] = pd.Series(pd.NA, index=out.index, dtype="string")
    out.loc[completed & (out["home_goals"] > out["away_goals"]), "actual_result"] = "H"
    out.loc[completed & (out["home_goals"] < out["away_goals"]), "actual_result"] = "A"
    out.loc[completed & (out["home_goals"] == out["away_goals"]), "actual_result"] = "D"
    return out.sort_values(["date"], kind="mergesort").reset_index(drop=True)
