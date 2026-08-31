from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from world_cup.data import normalize_national_team


HEADER_ALIASES = {
    "date": ["date", "match_date", "比赛日期", "日期", "æ¯”èµ›æ—¥æœŸ", "æ—¥æœŸ"],
    "match_id": ["match_id", "fixture_id", "赛事id", "比赛id", "æ¯”èµ›id", "èµ›äº‹id"],
    "match_number": [
        "match_number",
        "lottery_match_number",
        "场次",
        "竞彩编号",
        "åœºæ¬¡",
        "ç«žå½©ç¼–å·",
    ],
    "home_team": ["home_team", "home", "主队", "ä¸»é˜Ÿ"],
    "away_team": ["away_team", "away", "客队", "å®¢é˜Ÿ"],
    "home_handicap": [
        "home_handicap",
        "handicap_line",
        "official_home_handicap",
        "让球",
        "让球数",
        "让球盘",
        "è®©çƒ",
        "è®©çƒæ•°",
        "è®©çƒç›˜",
    ],
    "source": ["source", "来源", "æ¥æº"],
    "updated_at": ["updated_at", "更新时间", "æ›´æ–°æ—¶é—´"],
}


MARKET_HISTORY_COLUMNS = [
    "date",
    "match_id",
    "match_number",
    "home_team",
    "away_team",
    "snapshot_type",
    "home_handicap_raw",
    "home_handicap",
    "source",
    "captured_at",
    "updated_at",
    "notes",
]

LINE_MOVEMENT_COLUMNS = [
    "date",
    "match_id",
    "home_team",
    "away_team",
    "opening_home_handicap",
    "latest_home_handicap",
    "handicap_line_delta",
    "handicap_movement_direction",
    "favorite_movement",
    "opening_snapshot_type",
    "latest_snapshot_type",
    "opening_captured_at",
    "latest_captured_at",
    "snapshots",
]

LOTTERY_GOV_SPF_COLUMNS = [
    "date",
    "match_id",
    "match_number",
    "competition",
    "kickoff_time",
    "home_team",
    "away_team",
    "home_handicap",
    "spf_odds_home",
    "spf_odds_draw",
    "spf_odds_away",
    "rqspf_odds_home",
    "rqspf_odds_draw",
    "rqspf_odds_away",
    "support_home_pct",
    "support_draw_pct",
    "support_away_pct",
    "source",
    "updated_at",
    "notes",
]


def _canonical_columns(frame: pd.DataFrame) -> pd.DataFrame:
    aliases = {
        alias.lower(): canonical
        for canonical, names in HEADER_ALIASES.items()
        for alias in names
    }
    renamed = {}
    for column in frame.columns:
        key = str(column).strip().lower()
        renamed[column] = aliases.get(key, str(column).strip())
    return frame.rename(columns=renamed)


def _normalize_match_number(value: object) -> str:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    return text.zfill(3) if text.isdigit() else text


def parse_home_handicap(value: object) -> float:
    """Return the handicap in our convention: negative means home gives goals."""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        raise ValueError("empty handicap value")

    normalized = (
        text.replace("ï¼ˆ", "(")
        .replace("ï¼‰", ")")
        .replace("ï¼‹", "+")
        .replace("ï¼", "-")
        .replace("ä¸»è®©", "ä¸»é˜Ÿè®©")
        .replace("ä¸»å—è®©", "ä¸»é˜Ÿå—è®©")
        .replace("主让", "主队让")
        .replace("主受让", "主队受让")
    )
    if "å¹³æ‰‹" in normalized or "平手" in normalized:
        return 0.0

    number_match = re.search(r"[-+]?\d+(?:\.\d+)?", normalized)
    if not number_match:
        raise ValueError(f"cannot parse handicap value: {value!r}")
    number = float(number_match.group(0))

    if "å—è®©" in normalized or "受让" in normalized:
        return abs(number)
    if ("è®©" in normalized or "让" in normalized) and not normalized.lstrip().startswith(("+", "-")):
        return -abs(number)
    return number


def parse_sporttery_paste_text(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"\t|,|\s{2,}", line) if part.strip()]
        if len(parts) < 4:
            continue
        handicap_index = None
        for index in range(len(parts) - 1, -1, -1):
            part = parts[index]
            try:
                parse_home_handicap(part)
            except ValueError:
                continue
            handicap_index = index
            break
        if handicap_index is None:
            continue

        match_number = ""
        match_number_index = None
        for index, part in enumerate(parts[:handicap_index]):
            if re.search(r"\d", part) and (
                re.search(r"[A-Za-z]", part) or re.search(r"[\u4e00-\u9fff]", part)
            ):
                match_number = part
                match_number_index = index
                break

        team_candidates = [
            part
            for index, part in enumerate(parts[:handicap_index])
            if index != match_number_index
        ]
        if len(team_candidates) < 2:
            continue
        rows.append(
            {
                "match_number": match_number,
                "home_team": team_candidates[-2],
                "away_team": team_candidates[-1],
                "home_handicap": parts[handicap_index],
            }
        )
    return rows


def _parse_float_token(value: str) -> float | None:
    token = str(value).strip()
    if not token or token in {"--", "-"}:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _split_triplet(value: str) -> tuple[float | None, float | None, float | None]:
    raw = str(value).strip()
    if "/" in raw:
        parts = [part.strip() for part in raw.split("/") if part.strip()]
    else:
        parts = re.findall(r"\d+\.\d{2}|--", raw)
    parts = (parts + ["", "", ""])[:3]
    return tuple(_parse_float_token(part) for part in parts)  # type: ignore[return-value]


def _split_support_triplet(value: str) -> tuple[float | None, float | None, float | None]:
    parts = [part.strip().rstrip("%") for part in str(value).split("/") if part.strip()]
    parts = (parts + ["", "", ""])[:3]
    return tuple(_parse_float_token(part) for part in parts)  # type: ignore[return-value]


def _extract_home_handicap_from_lottery_cell(value: str) -> str:
    text = re.sub(r"[（(].*?[）)]", "", str(value)).strip()
    parts = [part.strip() for part in text.split("/") if part.strip()]
    if not parts:
        return ""
    for part in reversed(parts):
        if part not in {"0", "+0", "-0"}:
            return part
    return parts[-1]


def _strip_lottery_team_rank(value: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", str(value)).strip()


def _append_lottery_gov_spf_row(
    rows: list[dict[str, object]],
    *,
    year: int | None,
    match_number: str,
    competition: str,
    kickoff: str,
    fixture: str,
    handicap_cell: str,
    spf_odds: str,
    rqspf_odds: str,
    support: str = "",
    updated_at: str = "",
) -> None:
    fixture_clean = _strip_lottery_team_rank(fixture)
    if " VS " in fixture_clean:
        home_team, away_team = [part.strip() for part in fixture_clean.split(" VS ", 1)]
    elif " vs " in fixture_clean:
        home_team, away_team = [part.strip() for part in fixture_clean.split(" vs ", 1)]
    else:
        return
    kickoff_date = pd.Timestamp(
        f"{year or pd.Timestamp.now(tz='Asia/Shanghai').year}-{kickoff}"
    )
    spf_home, spf_draw, spf_away = _split_triplet(spf_odds)
    rqspf_home, rqspf_draw, rqspf_away = _split_triplet(rqspf_odds)
    support_home, support_draw, support_away = _split_support_triplet(support)
    rows.append(
        {
            "date": str(kickoff_date.date()),
            "match_id": "",
            "match_number": match_number,
            "competition": competition,
            "kickoff_time": kickoff_date.strftime("%Y-%m-%d %H:%M"),
            "home_team": home_team,
            "away_team": away_team,
            "home_handicap": _extract_home_handicap_from_lottery_cell(handicap_cell),
            "spf_odds_home": spf_home,
            "spf_odds_draw": spf_draw,
            "spf_odds_away": spf_away,
            "rqspf_odds_home": rqspf_home,
            "rqspf_odds_draw": rqspf_draw,
            "rqspf_odds_away": rqspf_away,
            "support_home_pct": support_home,
            "support_draw_pct": support_draw,
            "support_away_pct": support_away,
            "source": "lottery.gov.cn:zqspf",
            "updated_at": updated_at,
            "notes": "Parsed from rendered China Sports Lottery SPF calculator.",
        }
    )


def parse_lottery_gov_spf_text(
    text: str,
    *,
    updated_at: str = "",
) -> pd.DataFrame:
    """Parse rendered lottery.gov.cn football SPF calculator table text.

    The official page is client-rendered, so this parser intentionally accepts
    text copied from a browser/agent-browser table instead of depending on a
    brittle unauthenticated JSON endpoint.
    """
    current_year: int | None = None
    rows: list[dict[str, object]] = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    index = 0
    while index < len(lines):
        line = lines[index]
        day_match = re.search(r"(20\d{2})-\d{2}-\d{2}", line)
        if day_match:
            current_year = int(day_match.group(1))
            index += 1
            continue

        block_match = re.fullmatch(r"(\d{3})\t([^\t]+)\t(\d{2}-\d{2})", line)
        if block_match and index + 5 < len(lines):
            fixture_match = re.fullmatch(r"(\d{2}:\d{2})\t(.+?)(?:\t)?", lines[index + 1])
            if fixture_match:
                handicap_first = lines[index + 2]
                handicap_second = lines[index + 3]
                spf_odds = lines[index + 4]
                rqspf_odds = lines[index + 5]
                handicap_cell = f"{handicap_first} / {handicap_second}"
                _append_lottery_gov_spf_row(
                    rows,
                    year=current_year,
                    match_number=block_match.group(1),
                    competition=block_match.group(2),
                    kickoff=f"{block_match.group(3)} {fixture_match.group(1)}",
                    fixture=fixture_match.group(2),
                    handicap_cell=handicap_cell,
                    spf_odds=spf_odds,
                    rqspf_odds=rqspf_odds,
                    updated_at=updated_at,
                )
                index += 6
                continue

        # Also accept normalized tabular text exported by browser automation.
        parts = [part.strip() for part in re.split(r"\t|\s{2,}", line) if part.strip()]
        if len(parts) < 8 or not re.fullmatch(r"\d{3}", parts[0]):
            index += 1
            continue

        match_number, competition, kickoff, fixture, handicap_cell = parts[:5]
        _append_lottery_gov_spf_row(
            rows,
            year=current_year,
            match_number=match_number,
            competition=competition,
            kickoff=kickoff,
            fixture=fixture,
            handicap_cell=handicap_cell,
            spf_odds=parts[5],
            rqspf_odds=parts[6],
            support=parts[7],
            updated_at=updated_at,
        )
        index += 1
    return pd.DataFrame(rows, columns=LOTTERY_GOV_SPF_COLUMNS)


def load_sporttery_handicap_markets(path: str | Path) -> pd.DataFrame:
    market_path = Path(path)
    if not market_path.exists():
        raise FileNotFoundError(market_path)
    frame = pd.read_csv(market_path)
    frame = _canonical_columns(frame)
    required = {"date", "home_team", "away_team", "home_handicap"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"sporttery market file missing columns: {missing}")

    out = frame.copy().fillna("")
    out["date"] = pd.to_datetime(out["date"], errors="raise").dt.date.astype(str)
    out = out[out["home_handicap"].astype(str).str.strip().ne("")].copy()
    out["home_team_norm"] = out["home_team"].map(normalize_national_team)
    out["away_team_norm"] = out["away_team"].map(normalize_national_team)
    out["home_handicap"] = out["home_handicap"].map(parse_home_handicap)
    if "match_id" in out.columns:
        out["match_id"] = out["match_id"].fillna("").astype(str)
    else:
        out["match_id"] = ""
    if "match_number" not in out.columns:
        out["match_number"] = ""
    out["match_number"] = out["match_number"].map(_normalize_match_number)
    if "source" not in out.columns:
        out["source"] = "sporttery_manual"
    if "updated_at" not in out.columns:
        out["updated_at"] = ""
    return out


def append_sporttery_market_history(
    history_path: str | Path,
    rows: pd.DataFrame,
    *,
    snapshot_type: str = "latest",
    captured_at: str = "",
) -> pd.DataFrame:
    history_file = Path(history_path)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    captured = captured_at or pd.Timestamp.now(tz="Asia/Shanghai").isoformat()
    records = []
    for _, row in rows.fillna("").iterrows():
        raw_handicap = str(row.get("home_handicap", "") or "").strip()
        if not raw_handicap:
            continue
        records.append(
            {
                "date": str(pd.Timestamp(row["date"]).date()),
                "match_id": str(row.get("match_id", "") or ""),
                "match_number": str(row.get("match_number", "") or ""),
                "home_team": str(row.get("home_team", "") or ""),
                "away_team": str(row.get("away_team", "") or ""),
                "snapshot_type": snapshot_type,
                "home_handicap_raw": raw_handicap,
                "home_handicap": parse_home_handicap(raw_handicap),
                "source": str(row.get("source", "") or "sporttery_manual"),
                "captured_at": captured,
                "updated_at": str(row.get("updated_at", "") or ""),
                "notes": str(row.get("notes", "") or ""),
            }
        )
    new_rows = pd.DataFrame(records, columns=MARKET_HISTORY_COLUMNS)
    if history_file.exists():
        existing = pd.read_csv(history_file).fillna("")
    else:
        existing = pd.DataFrame(columns=MARKET_HISTORY_COLUMNS)
    output = pd.concat([existing, new_rows], ignore_index=True)
    output.to_csv(history_file, index=False, encoding="utf-8-sig")
    return output


def latest_sporttery_markets_from_history(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    frame = history.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
    frame["captured_at_sort"] = pd.to_datetime(
        frame.get("captured_at", ""),
        errors="coerce",
        utc=True,
    )
    frame = frame.sort_values(
        ["date", "home_team", "away_team", "captured_at_sort"],
        kind="mergesort",
    )
    latest = frame.groupby(["date", "home_team", "away_team"], as_index=False).tail(1)
    latest = latest.copy()
    latest["home_handicap"] = latest["home_handicap_raw"]
    return latest.drop(columns=["captured_at_sort"], errors="ignore").reset_index(drop=True)


def build_sporttery_line_movement_features(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=LINE_MOVEMENT_COLUMNS)
    frame = history.copy().fillna("")
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
    frame["home_handicap"] = pd.to_numeric(frame["home_handicap"], errors="coerce")
    frame["captured_at_sort"] = pd.to_datetime(
        frame.get("captured_at", ""),
        errors="coerce",
        utc=True,
    )
    frame = frame.sort_values(
        ["date", "home_team", "away_team", "captured_at_sort"],
        kind="mergesort",
    )
    rows: list[dict[str, object]] = []
    for key, group in frame.groupby(["date", "home_team", "away_team"], sort=False):
        valid = group.dropna(subset=["home_handicap"])
        if valid.empty:
            continue
        opening = valid.iloc[0]
        latest = valid.iloc[-1]
        delta = float(latest["home_handicap"] - opening["home_handicap"])
        if abs(delta) < 1e-12:
            direction = "stable"
        elif delta < 0:
            direction = "toward_home"
        else:
            direction = "toward_away"
        opening_line = float(opening["home_handicap"])
        latest_line = float(latest["home_handicap"])
        opening_abs = abs(opening_line)
        latest_abs = abs(latest_line)
        if latest_abs > opening_abs:
            favorite_movement = "deeper"
        elif latest_abs < opening_abs:
            favorite_movement = "shallower"
        else:
            favorite_movement = "stable"
        rows.append(
            {
                "date": key[0],
                "match_id": str(latest.get("match_id", "") or opening.get("match_id", "")),
                "home_team": key[1],
                "away_team": key[2],
                "opening_home_handicap": opening_line,
                "latest_home_handicap": latest_line,
                "handicap_line_delta": delta,
                "handicap_movement_direction": direction,
                "favorite_movement": favorite_movement,
                "opening_snapshot_type": str(opening.get("snapshot_type", "")),
                "latest_snapshot_type": str(latest.get("snapshot_type", "")),
                "opening_captured_at": str(opening.get("captured_at", "")),
                "latest_captured_at": str(latest.get("captured_at", "")),
                "snapshots": int(len(valid)),
            }
        )
    return pd.DataFrame(rows, columns=LINE_MOVEMENT_COLUMNS)


def build_sporttery_template_from_fixtures(
    fixtures: pd.DataFrame,
    *,
    as_of_date: str,
) -> pd.DataFrame:
    required = {"date", "home_team", "away_team"}
    missing = sorted(required - set(fixtures.columns))
    if missing:
        raise ValueError(f"fixtures missing columns: {missing}")

    target_date = str(pd.Timestamp(as_of_date).date())
    frame = fixtures.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.date.astype(str)
    frame = frame[frame["date"] == target_date].copy()
    columns = [
        "date",
        "match_id",
        "match_number",
        "home_team",
        "away_team",
        "home_handicap",
        "source",
        "updated_at",
        "notes",
    ]
    if "match_id" not in frame.columns:
        frame["match_id"] = ""
    frame["match_number"] = ""
    frame["home_handicap"] = ""
    frame["source"] = "sporttery_manual"
    frame["updated_at"] = ""
    frame["notes"] = "Fill from verified China Sports Lottery handicap market."
    return frame[columns].reset_index(drop=True)


def index_sporttery_markets(markets: pd.DataFrame) -> dict[tuple[str, str, str], dict[str, object]]:
    indexed = {}
    for _, row in markets.iterrows():
        key = (str(row["date"]), str(row["home_team_norm"]), str(row["away_team_norm"]))
        indexed[key] = row.to_dict()
    return indexed


def find_sporttery_market(
    markets_by_fixture: dict[tuple[str, str, str], dict[str, object]],
    *,
    date: object,
    home_team: object,
    away_team: object,
    date_tolerance_days: int = 1,
) -> dict[str, object] | None:
    target_date = pd.Timestamp(date).normalize()
    home_norm = normalize_national_team(home_team)
    away_norm = normalize_national_team(away_team)
    key = (str(target_date.date()), home_norm, away_norm)
    exact = markets_by_fixture.get(key)
    if exact is not None or date_tolerance_days <= 0:
        return exact
    candidates: list[tuple[int, dict[str, object]]] = []
    for market_date, market_home, market_away in markets_by_fixture:
        if market_home != home_norm or market_away != away_norm:
            continue
        day_gap = abs((pd.Timestamp(market_date).normalize() - target_date).days)
        if day_gap <= date_tolerance_days:
            candidates.append((day_gap, markets_by_fixture[(market_date, market_home, market_away)]))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]
