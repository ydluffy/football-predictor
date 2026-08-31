from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from world_cup.data import normalize_national_team
from world_cup.markets import implied_probabilities_from_decimal_odds


PLAY_TYPES = {
    "spf",
    "handicap_spf",
    "correct_score",
    "total_goals",
    "half_full_time",
}

SNAPSHOT_TYPES = {
    "opening",
    "t_minus_12h",
    "t_minus_2h",
    "latest",
    "closing",
}

SPORTTERY_PLAY_ODDS_COLUMNS = [
    "date",
    "match_id",
    "match_number",
    "home_team",
    "away_team",
    "play_type",
    "selection",
    "odds",
    "source",
    "snapshot_type",
    "captured_at",
    "notes",
]


def normalize_total_goals_selection(value: object) -> str:
    text = str(value).strip().lower()
    text = text.replace("球", "").replace("及以上", "+").replace("以上", "+")
    text = text.replace("7+", "7_plus").replace("7_plus", "7_plus")
    if text in {"7", "7_plus", "7+"}:
        return "7_plus"
    if text.endswith("+"):
        return f"{text[:-1]}_plus"
    if text.endswith(".0"):
        text = text[:-2]
    if text.isdigit():
        return text
    raise ValueError(f"unsupported total goals selection: {value!r}")


def normalize_play_selection(play_type: object, selection: object) -> str:
    play = str(play_type).strip()
    if play == "total_goals":
        return normalize_total_goals_selection(selection)
    if play == "correct_score":
        return normalize_correct_score_selection(selection)
    return str(selection).strip()


def normalize_correct_score_selection(value: object) -> str:
    text = str(value).strip()
    aliases = {
        "home_other": "home_other",
        "draw_other": "draw_other",
        "away_other": "away_other",
        "胜其它": "home_other",
        "胜其他": "home_other",
        "平其它": "draw_other",
        "平其他": "draw_other",
        "负其它": "away_other",
        "负其他": "away_other",
    }
    if text in aliases:
        return aliases[text]
    if re.fullmatch(r"\d+:\d+", text):
        return text
    raise ValueError(f"unsupported correct score selection: {value!r}")


def load_sporttery_play_odds(path: str | Path) -> pd.DataFrame:
    odds_path = Path(path)
    if not odds_path.exists():
        raise FileNotFoundError(odds_path)
    frame = pd.read_csv(odds_path).fillna("")
    missing = sorted(set(SPORTTERY_PLAY_ODDS_COLUMNS[:8]) - set(frame.columns))
    if missing:
        raise ValueError(f"sporttery play odds file missing columns: {missing}")

    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="raise").dt.date.astype(str)
    out["play_type"] = out["play_type"].astype(str).str.strip()
    unknown_plays = sorted(set(out["play_type"]) - PLAY_TYPES)
    if unknown_plays:
        raise ValueError(f"unsupported sporttery play types: {unknown_plays}")
    out["selection"] = [
        normalize_play_selection(play_type, selection)
        for play_type, selection in zip(out["play_type"], out["selection"])
    ]
    out["odds"] = pd.to_numeric(out["odds"], errors="coerce")
    out = out[out["odds"].gt(1.0)].copy()
    out["home_team_norm"] = out["home_team"].map(normalize_national_team)
    out["away_team_norm"] = out["away_team"].map(normalize_national_team)
    if "source" not in out.columns:
        out["source"] = "sporttery_manual"
    if "snapshot_type" not in out.columns:
        out["snapshot_type"] = "latest"
    out["snapshot_type"] = out["snapshot_type"].replace("", "latest")
    unknown_snapshots = sorted(set(out["snapshot_type"]) - SNAPSHOT_TYPES)
    if unknown_snapshots:
        raise ValueError(f"unsupported snapshot types: {unknown_snapshots}")
    for column in SPORTTERY_PLAY_ODDS_COLUMNS:
        if column not in out.columns:
            out[column] = ""
    return out


def latest_sporttery_play_odds(odds: pd.DataFrame) -> pd.DataFrame:
    if odds.empty:
        return odds.copy()
    frame = odds.copy()
    frame["captured_at_sort"] = pd.to_datetime(
        frame.get("captured_at", ""),
        errors="coerce",
        utc=True,
    )
    frame = frame.sort_values(
        [
            "date",
            "home_team_norm",
            "away_team_norm",
            "play_type",
            "selection",
            "captured_at_sort",
        ],
        kind="mergesort",
    )
    return (
        frame.groupby(
            ["date", "home_team_norm", "away_team_norm", "play_type", "selection"],
            as_index=False,
        )
        .tail(1)
        .drop(columns=["captured_at_sort"], errors="ignore")
        .reset_index(drop=True)
    )


def find_play_odds(
    odds: pd.DataFrame,
    *,
    date: object,
    home_team: object,
    away_team: object,
    play_type: str,
    date_tolerance_days: int = 1,
) -> dict[str, float]:
    if odds.empty:
        return {}
    target_date = str(pd.Timestamp(date).date())
    home_norm = normalize_national_team(home_team)
    away_norm = normalize_national_team(away_team)
    frame = latest_sporttery_play_odds(odds)
    matched = frame[
        frame["date"].eq(target_date)
        & frame["home_team_norm"].eq(home_norm)
        & frame["away_team_norm"].eq(away_norm)
        & frame["play_type"].eq(play_type)
    ]
    if matched.empty and date_tolerance_days > 0:
        candidates = frame[
            frame["home_team_norm"].eq(home_norm)
            & frame["away_team_norm"].eq(away_norm)
            & frame["play_type"].eq(play_type)
        ].copy()
        if not candidates.empty:
            candidates["date_gap"] = (
                pd.to_datetime(candidates["date"], errors="coerce")
                - pd.Timestamp(target_date)
            ).abs().dt.days
            candidates = candidates[candidates["date_gap"].le(date_tolerance_days)]
            if not candidates.empty:
                matched = candidates[candidates["date_gap"].eq(candidates["date_gap"].min())]
    return {
        str(row["selection"]): float(row["odds"])
        for _, row in matched.iterrows()
    }


def play_market_value(
    model_probabilities: dict[str, float],
    decimal_odds: dict[str, float],
) -> dict[str, object]:
    market_probabilities = implied_probabilities_from_decimal_odds(decimal_odds)
    rows = []
    for selection, model_probability in model_probabilities.items():
        odd = decimal_odds.get(selection)
        market_probability = market_probabilities.get(selection)
        if odd is None or market_probability is None:
            continue
        rows.append(
            {
                "selection": selection,
                "model_probability": float(model_probability),
                "market_probability": float(market_probability),
                "edge": float(model_probability) - float(market_probability),
                "expected_value": float(model_probability) * float(odd) - 1.0,
                "odds": float(odd),
            }
        )
    rows.sort(key=lambda row: (row["expected_value"], row["edge"]), reverse=True)
    return {
        "rows": rows,
        "best_selection": rows[0]["selection"] if rows else "",
        "best_expected_value": rows[0]["expected_value"] if rows else None,
        "best_edge": rows[0]["edge"] if rows else None,
    }


def _parse_decimal_sequence(value: str, *, expected: int) -> list[float]:
    odds = [float(item) for item in re.findall(r"\d+\.\d{2}", str(value))]
    return odds[:expected] if len(odds) >= expected else []


def _split_cells(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\t|\\t", str(value)) if part.strip()]


def _strip_team_rank(value: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", str(value)).strip()


def _split_fixture(value: str) -> tuple[str, str] | None:
    clean = _strip_team_rank(value)
    if " VS " in clean:
        home, away = clean.split(" VS ", 1)
    elif "VS" in clean:
        home, away = clean.split("VS", 1)
    elif " vs " in clean:
        home, away = clean.split(" vs ", 1)
    else:
        return None
    return home.strip(), away.strip()


def _append_play_odds_rows(
    rows: list[dict[str, object]],
    *,
    date: str,
    match_number: str,
    competition: str,
    kickoff_time: str,
    home_team: str,
    away_team: str,
    play_type: str,
    selections: list[str],
    odds: list[float],
    source: str,
    snapshot_type: str,
    captured_at: str,
) -> None:
    for selection, odd in zip(selections, odds):
        rows.append(
            {
                "date": date,
                "match_id": "",
                "match_number": match_number,
                "home_team": home_team,
                "away_team": away_team,
                "play_type": play_type,
                "selection": selection,
                "odds": odd,
                "source": source,
                "snapshot_type": snapshot_type,
                "captured_at": captured_at,
                "notes": f"{competition}; kickoff={kickoff_time}",
            }
        )


def parse_lottery_gov_total_goals_text(
    text: str,
    *,
    snapshot_type: str = "latest",
    captured_at: str = "",
) -> pd.DataFrame:
    selections = ["0", "1", "2", "3", "4", "5", "6", "7_plus"]
    rows: list[dict[str, object]] = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    index = 0
    while index < len(lines) - 1:
        header_cells = _split_cells(lines[index])
        detail_cells = _split_cells(lines[index + 1])
        if len(header_cells) < 3 or len(detail_cells) < 3:
            index += 1
            continue
        if not re.fullmatch(r"\d{3}", header_cells[0]) or not re.fullmatch(
            r"\d{2}-\d{2}",
            header_cells[2],
        ):
            index += 1
            continue
        fixture = _split_fixture(detail_cells[1])
        odds = _parse_decimal_sequence(detail_cells[2], expected=8)
        if fixture and len(odds) == 8:
            kickoff = f"2026-{header_cells[2]} {detail_cells[0]}"
            _append_play_odds_rows(
                rows,
                date=str(pd.Timestamp(kickoff).date()),
                match_number=header_cells[0],
                competition=header_cells[1],
                kickoff_time=kickoff,
                home_team=fixture[0],
                away_team=fixture[1],
                play_type="total_goals",
                selections=selections,
                odds=odds,
                source="lottery.gov.cn:zqzjq",
                snapshot_type=snapshot_type,
                captured_at=captured_at,
            )
            index += 2
            continue
        index += 1
    return pd.DataFrame(rows, columns=SPORTTERY_PLAY_ODDS_COLUMNS)


def parse_lottery_gov_half_full_time_text(
    text: str,
    *,
    snapshot_type: str = "latest",
    captured_at: str = "",
) -> pd.DataFrame:
    selections = ["H-H", "H-D", "H-A", "D-H", "D-D", "D-A", "A-H", "A-D", "A-A"]
    rows: list[dict[str, object]] = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    index = 0
    while index < len(lines) - 2:
        header_cells = _split_cells(lines[index + 1])
        detail_cells = _split_cells(lines[index + 2])
        if len(header_cells) < 3 or len(detail_cells) < 3:
            index += 1
            continue
        if not re.fullmatch(r"\d{3}", header_cells[0]) or not re.fullmatch(
            r"\d{2}-\d{2}",
            header_cells[2],
        ):
            index += 1
            continue
        fixture = _split_fixture(detail_cells[1])
        odds = _parse_decimal_sequence(detail_cells[2], expected=9)
        if fixture and len(odds) == 9:
            kickoff = f"2026-{header_cells[2]} {detail_cells[0]}"
            _append_play_odds_rows(
                rows,
                date=str(pd.Timestamp(kickoff).date()),
                match_number=header_cells[0],
                competition=header_cells[1],
                kickoff_time=kickoff,
                home_team=fixture[0],
                away_team=fixture[1],
                play_type="half_full_time",
                selections=selections,
                odds=odds,
                source="lottery.gov.cn:zqbqc",
                snapshot_type=snapshot_type,
                captured_at=captured_at,
            )
            index += 3
            continue
        index += 1
    return pd.DataFrame(rows, columns=SPORTTERY_PLAY_ODDS_COLUMNS)


def _parse_match_header_line(line: str) -> dict[str, str] | None:
    cells = _split_cells(line)
    if len(cells) < 5:
        return None
    match_id = re.search(r"(\d{3})", cells[0])
    kickoff = re.fullmatch(r"(\d{2}-\d{2})\s+(\d{2}:\d{2})", cells[2])
    fixture = _split_fixture(cells[3])
    if not match_id or not kickoff or not fixture:
        return None
    kickoff_time = f"2026-{kickoff.group(1)} {kickoff.group(2)}"
    return {
        "date": str(pd.Timestamp(kickoff_time).date()),
        "match_number": match_id.group(1),
        "competition": cells[1],
        "kickoff_time": kickoff_time,
        "home_team": fixture[0],
        "away_team": fixture[1],
    }


def parse_lottery_gov_correct_score_text(
    text: str,
    *,
    snapshot_type: str = "latest",
    captured_at: str = "",
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    index = 0
    while index < len(lines):
        header = _parse_match_header_line(lines[index])
        if header is None:
            index += 1
            continue
        block_end = index + 1
        while block_end < len(lines) and _parse_match_header_line(lines[block_end]) is None:
            block_end += 1
        block = lines[index + 1 : block_end]
        pair_index = 0
        while pair_index < len(block) - 1:
            selection_raw = block[pair_index].strip()
            odds_raw = block[pair_index + 1].strip()
            try:
                selection = normalize_correct_score_selection(selection_raw)
                odd = float(odds_raw)
            except ValueError:
                pair_index += 1
                continue
            _append_play_odds_rows(
                rows,
                date=header["date"],
                match_number=header["match_number"],
                competition=header["competition"],
                kickoff_time=header["kickoff_time"],
                home_team=header["home_team"],
                away_team=header["away_team"],
                play_type="correct_score",
                selections=[selection],
                odds=[odd],
                source="lottery.gov.cn:zqbf",
                snapshot_type=snapshot_type,
                captured_at=captured_at,
            )
            pair_index += 2
        index = block_end
    return pd.DataFrame(rows, columns=SPORTTERY_PLAY_ODDS_COLUMNS)


def total_goals_model_probabilities(total_goals: dict[str, object]) -> dict[str, float]:
    raw = total_goals.get("sporttery_total_goal_probabilities", {})
    if not isinstance(raw, dict):
        return {}
    probabilities: dict[str, float] = {}
    prefix = "total_goals_"
    suffix = "_probability"
    for key, value in raw.items():
        text = str(key)
        if not text.startswith(prefix) or not text.endswith(suffix):
            continue
        selection = text[len(prefix) : -len(suffix)]
        probabilities[selection] = float(value)
    return probabilities


def flatten_play_market_value(
    value: dict[str, object],
    *,
    prefix: str,
    selections: list[str],
) -> dict[str, object]:
    rows = {
        str(row["selection"]): row
        for row in value.get("rows", [])
        if isinstance(row, dict) and row.get("selection") is not None
    }
    out: dict[str, object] = {
        f"{prefix}_best_selection": value.get("best_selection", ""),
        f"{prefix}_best_expected_value": value.get("best_expected_value"),
        f"{prefix}_best_edge": value.get("best_edge"),
        f"{prefix}_value_signal": "no_market",
    }
    if rows:
        best_ev = value.get("best_expected_value")
        out[f"{prefix}_value_signal"] = (
            "positive" if best_ev is not None and float(best_ev) > 0 else "watch"
        )
    for selection in selections:
        row = rows.get(selection, {})
        safe_selection = selection.replace("+", "plus")
        out[f"{prefix}_{safe_selection}_odds"] = row.get("odds", "")
        out[f"{prefix}_{safe_selection}_market_probability"] = row.get(
            "market_probability",
            "",
        )
        out[f"{prefix}_{safe_selection}_edge"] = row.get("edge", "")
        out[f"{prefix}_{safe_selection}_expected_value"] = row.get(
            "expected_value",
            "",
        )
    return out
