from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


_DATE_RE = re.compile(
    r"^\s*(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+"
    r"(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})(?:\s+(?P<year>\d{4}))?\s*$"
)
_MATCH_RE = re.compile(
    r"^\s*(?:(?:\d{1,2}:\d{2})\s+)?(?P<home>.+?)\s+v\s+"
    r"(?P<away>.+?)\s+(?P<home_goals>\d+)-(?P<away_goals>\d+)"
)
_COUNTRY_SUFFIX_RE = re.compile(r"\s+\([A-Z]{3}\)\s*$")

TEAM_ALIASES = {
    "afc bournemouth": "Bournemouth",
    "arsenal fc": "Arsenal",
    "aston villa fc": "Aston Villa",
    "barrow afc": "Barrow",
    "birmingham city": "Birmingham",
    "blackburn rovers": "Blackburn",
    "bolton wanderers": "Bolton",
    "brighton and hove albion": "Brighton",
    "bristol rovers": "Bristol Rvs",
    "burton albion": "Burton",
    "cambridge united": "Cambridge",
    "cardiff city": "Cardiff",
    "charlton athletic": "Charlton",
    "chelsea fc": "Chelsea",
    "colchester united": "Colchester",
    "coventry city": "Coventry",
    "crewe alexandra": "Crewe",
    "dagenham and redbridge": "Dag and Red",
    "derby county": "Derby",
    "doncaster rovers": "Doncaster",
    "everton fc": "Everton",
    "exeter city": "Exeter",
    "forest green rovers": "Forest Green",
    "fulham fc": "Fulham",
    "halifax town": "Halifax",
    "harrogate town": "Harrogate",
    "hull city": "Hull",
    "ipswich town": "Ipswich",
    "leeds united": "Leeds",
    "leicester city": "Leicester",
    "lincoln city": "Lincoln",
    "liverpool fc": "Liverpool",
    "luton town": "Luton",
    "manchester city": "Man City",
    "manchester city fc": "Man City",
    "manchester united": "Man United",
    "mansfield town": "Mansfield",
    "milton keynes dons": "Milton Keynes Dons",
    "newcastle united": "Newcastle",
    "northampton town": "Northampton",
    "norwich city": "Norwich",
    "nottingham forest": "Nott'm Forest",
    "nottingham forest fc": "Nott'm Forest",
    "oxford united": "Oxford",
    "peterborough united": "Peterboro",
    "plymouth argyle": "Plymouth",
    "port vale fc": "Port Vale",
    "preston north end": "Preston",
    "queens park rangers": "QPR",
    "reading fc": "Reading",
    "rotherham united": "Rotherham",
    "sheffield wednesday": "Sheffield Weds",
    "southampton fc": "Southampton",
    "stockport county": "Stockport",
    "stoke city": "Stoke",
    "sunderland afc": "Sunderland",
    "sutton united": "Sutton",
    "swansea city": "Swansea",
    "swindon town": "Swindon",
    "tottenham hotspur": "Tottenham",
    "tranmere rovers": "Tranmere",
    "walsall fc": "Walsall",
    "west bromwich albion": "West Brom",
    "west ham united": "West Ham",
    "wigan athletic": "Wigan",
    "wolverhampton wanderers": "Wolves",
    "wrexham afc": "Wrexham",
    "wycombe wanderers": "Wycombe",
    "york city": "York",
}


def normalize_team_name(value: object) -> str:
    text = _COUNTRY_SUFFIX_RE.sub("", str(value)).strip()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_team_lookup(teams: set[str]) -> dict[str, str]:
    lookup = {normalize_team_name(team): team for team in teams}
    for alias, canonical in TEAM_ALIASES.items():
        if canonical in teams:
            lookup[alias] = canonical
    return lookup


def parse_football_txt(
    text: str,
    *,
    season: str,
    competition: str,
    source: str = "",
) -> pd.DataFrame:
    start_year = int(str(season).split("-", 1)[0])
    end_year = start_year + 1
    current_date: pd.Timestamp | None = None
    rows: list[dict[str, object]] = []

    for line_number, line in enumerate(text.splitlines(), start=1):
        date_match = _DATE_RE.match(line)
        if date_match:
            month = date_match.group("month")
            month_number = pd.Timestamp(f"2000-{month}-01").month
            explicit_year = date_match.group("year")
            year = int(explicit_year) if explicit_year else (start_year if month_number >= 7 else end_year)
            current_date = pd.Timestamp(f"{year}-{month}-{int(date_match.group('day'))}")
            continue

        match = _MATCH_RE.match(line)
        if not match or current_date is None:
            continue
        rows.append(
            {
                "date": current_date.date().isoformat(),
                "home_team_source": match.group("home").strip(),
                "away_team_source": match.group("away").strip(),
                "competition": competition,
                "season": season,
                "source": source,
                "source_line": line_number,
            }
        )
    return pd.DataFrame(rows)


def build_external_calendar(
    *,
    input_dir: str | Path,
    league_teams: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(input_dir)
    lookup = build_team_lookup(league_teams)
    frames = []
    for path in sorted(root.rglob("*.txt")):
        relative = path.relative_to(root)
        season = relative.parts[0]
        competition = path.stem
        frames.append(
            parse_football_txt(
                path.read_text(encoding="utf-8"),
                season=season,
                competition=competition,
                source=str(relative),
            )
        )
    if not frames:
        raise FileNotFoundError(f"no Football.TXT files found under {root}")

    calendar = pd.concat(frames, ignore_index=True)
    calendar["home_team"] = calendar["home_team_source"].map(
        lambda value: lookup.get(normalize_team_name(value))
    )
    calendar["away_team"] = calendar["away_team_source"].map(
        lambda value: lookup.get(normalize_team_name(value))
    )
    matched = calendar[calendar["home_team"].notna() | calendar["away_team"].notna()].copy()
    audit = calendar[
        (calendar["home_team"].isna() & calendar["home_team_source"].notna())
        | (calendar["away_team"].isna() & calendar["away_team_source"].notna())
    ][
        [
            "source",
            "source_line",
            "home_team_source",
            "away_team_source",
            "home_team",
            "away_team",
        ]
    ].copy()
    return matched, audit
