from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backtest_market_movement_value import build_external_movement
from research_inner_outer_market_patterns import normalize_team
from world_cup.sporttery_markets import build_sporttery_line_movement_features


TEAM_ALIASES = {
    "法国": "france",
    "英格兰": "england",
    "西班牙": "spain",
    "阿根廷": "argentina",
    "瑞士": "switzerland",
    "哥伦比亚": "colombia",
}


def team_key(value: object) -> str:
    text = str(value or "").strip()
    return TEAM_ALIASES.get(text, normalize_team(text))


def to_float(value: object) -> float | None:
    parsed = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(parsed):
        return None
    return float(parsed)


def text_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text


def favorite_from_home_line(line: float | None) -> str:
    if line is None:
        return ""
    if line < 0:
        return "home"
    if line > 0:
        return "away"
    return ""


def favorite_from_spf(row: pd.Series) -> str:
    odds = {
        "home": to_float(row.get("spf_odds_home")),
        "draw": to_float(row.get("spf_odds_draw")),
        "away": to_float(row.get("spf_odds_away")),
    }
    available = {key: value for key, value in odds.items() if value and value > 1}
    if not available:
        return ""
    return min(available, key=available.get)


def line_relation(sporttery_line: float | None, external_line: float | None) -> str:
    if sporttery_line is None or external_line is None:
        return "missing_external" if external_line is None else "missing_sporttery"
    diff = external_line - sporttery_line
    if abs(diff) <= 0.25:
        return "aligned"
    if diff > 0.25:
        return "sporttery_deeper_home"
    return "external_deeper_home"


def build_risk_flags(row: pd.Series) -> list[str]:
    flags: list[str] = []
    relation = text_value(row.get("inner_outer_line_relation", ""))
    sporttery_fav = text_value(row.get("sporttery_handicap_favorite", ""))
    external_fav = text_value(row.get("external_latest_favorite", ""))
    external_spread_fav = text_value(row.get("external_latest_spread_favorite", ""))
    total_signal = text_value(row.get("external_latest_total_signal", ""))
    sporttery_line = to_float(row.get("sporttery_home_handicap"))
    external_line = to_float(row.get("external_latest_home_spread_point"))
    prob_delta = to_float(row.get("external_favorite_probability_delta"))
    line_delta = to_float(row.get("external_home_spread_point_delta"))

    if relation == "missing_external":
        flags.append("no_external_market")
    if relation == "sporttery_deeper_home":
        flags.append("sporttery_deeper_than_external")
    if relation == "external_deeper_home":
        flags.append("external_deeper_than_sporttery")
    if external_fav and sporttery_fav and external_fav != sporttery_fav:
        flags.append("inner_outer_favorite_conflict")
    if external_spread_fav and external_fav and external_spread_fav != external_fav:
        flags.append("external_h2h_spread_conflict")
    if sporttery_line is not None and abs(sporttery_line) >= 1 and total_signal == "under":
        flags.append("deep_line_but_under_signal")
    if external_line is not None and abs(external_line) <= 0.5 and sporttery_line is not None and abs(sporttery_line) >= 1:
        flags.append("external_shallow_vs_sporttery_deep")
    if prob_delta is not None and prob_delta > 0.03 and (line_delta is None or abs(line_delta) <= 0.01):
        flags.append("favorite_hot_without_line_move")
    if prob_delta is not None and prob_delta < -0.03:
        flags.append("favorite_cooling")
    return flags


def signal_strength(flags: list[str]) -> str:
    hard_risk = {
        "inner_outer_favorite_conflict",
        "external_h2h_spread_conflict",
        "deep_line_but_under_signal",
        "external_shallow_vs_sporttery_deep",
        "sporttery_deeper_than_external",
    }
    if any(flag in hard_risk for flag in flags):
        return "high_risk"
    if "no_external_market" in flags:
        return "medium_unknown"
    if flags:
        return "watch"
    return "clean"


def build_market_signal_features(
    markets: pd.DataFrame,
    sporttery_history: pd.DataFrame,
    external_history: pd.DataFrame,
) -> pd.DataFrame:
    current = markets.copy().fillna("")
    current["date"] = pd.to_datetime(current["date"], errors="coerce").dt.date.astype(str)
    current["home_key"] = current["home_team"].map(team_key)
    current["away_key"] = current["away_team"].map(team_key)
    current["sporttery_home_handicap"] = pd.to_numeric(current["home_handicap"], errors="coerce")
    current["sporttery_handicap_favorite"] = current["sporttery_home_handicap"].map(favorite_from_home_line)
    current["sporttery_spf_favorite"] = current.apply(favorite_from_spf, axis=1)

    sporttery_movement = build_sporttery_line_movement_features(sporttery_history) if not sporttery_history.empty else pd.DataFrame()
    if not sporttery_movement.empty:
        sporttery_movement["date"] = pd.to_datetime(sporttery_movement["date"], errors="coerce").dt.date.astype(str)
        sporttery_movement["home_key"] = sporttery_movement["home_team"].map(team_key)
        sporttery_movement["away_key"] = sporttery_movement["away_team"].map(team_key)

    external_movement = build_external_movement(external_history) if not external_history.empty else pd.DataFrame()
    if not external_movement.empty:
        external_movement = external_movement.rename(
            columns={
                "external_latest_home_spread_point": "external_latest_home_spread_point",
            }
        )
        latest_fields = []
        for _, group in external_history.copy().fillna("").groupby(["date", "home_key", "away_key"], dropna=False):
            sorted_group = group.sort_values("captured_at")
            latest = sorted_group.iloc[-1]
            latest_fields.append(
                {
                    "date": str(pd.Timestamp(latest["date"]).date()),
                    "home_key": latest["home_key"],
                    "away_key": latest["away_key"],
                    "external_latest_line_label": latest.get("external_line_label", ""),
                    "external_latest_line_bucket": latest.get("external_line_bucket", ""),
                    "external_latest_spread_favorite": latest.get("external_spread_favorite", ""),
                    "external_latest_total_signal": latest.get("external_total_signal", ""),
                    "external_latest_total_point": latest.get("external_total_point", ""),
                    "external_latest_over_avg_odds": latest.get("external_over_avg_odds", ""),
                    "external_latest_under_avg_odds": latest.get("external_under_avg_odds", ""),
                }
            )
        external_latest = pd.DataFrame(latest_fields)
        external_movement = external_movement.merge(
            external_latest,
            on=["date", "home_key", "away_key"],
            how="left",
        )

    merged = current.copy()
    if not sporttery_movement.empty:
        merged = merged.merge(
            sporttery_movement[
                [
                    "date",
                    "home_key",
                    "away_key",
                    "opening_home_handicap",
                    "latest_home_handicap",
                    "handicap_line_delta",
                    "handicap_movement_direction",
                    "favorite_movement",
                    "snapshots",
                ]
            ],
            on=["date", "home_key", "away_key"],
            how="left",
        )
    if not external_movement.empty:
        merged = merged.merge(
            external_movement,
            on=["date", "home_key", "away_key"],
            how="left",
        )

    rows = []
    for _, row in merged.iterrows():
        sporttery_line = to_float(row.get("sporttery_home_handicap"))
        external_line = to_float(row.get("external_latest_home_spread_point"))
        relation = line_relation(sporttery_line, external_line)
        enriched = row.to_dict()
        enriched["inner_outer_home_line_gap"] = (
            None if sporttery_line is None or external_line is None else round(external_line - sporttery_line, 3)
        )
        enriched["inner_outer_line_relation"] = relation
        flags = build_risk_flags(pd.Series(enriched))
        enriched["market_risk_flags"] = ",".join(flags)
        enriched["market_signal_strength"] = signal_strength(flags)
        enriched["market_signal_note"] = note_for(enriched)
        rows.append(enriched)
    return pd.DataFrame(rows)


def note_for(row: dict[str, Any]) -> str:
    flags = set(str(row.get("market_risk_flags", "")).split(",")) if row.get("market_risk_flags") else set()
    if "no_external_market" in flags:
        return "缺外盘，今天只能按体彩和基础模型观察。"
    if "sporttery_deeper_than_external" in flags or "external_shallow_vs_sporttery_deep" in flags:
        return "体彩比外盘更激进，优先防热和赢球不穿。"
    if "deep_line_but_under_signal" in flags:
        return "让球偏深但大小球偏小，防小胜/不穿。"
    if "external_deeper_than_sporttery" in flags:
        return "外盘比体彩更支持主队，若阵容无利空可提高主队方向权重。"
    if "inner_outer_favorite_conflict" in flags:
        return "内外盘热门冲突，不宜做稳胆。"
    return "内外盘暂无明显冲突，可作为常规方向信号。"


def render_report(features: pd.DataFrame) -> str:
    lines = [
        "# 每日盘口信号特征",
        "",
        f"- 比赛数：{len(features)}",
        f"- 有外盘覆盖：{int(features['external_latest_favorite'].fillna('').astype(str).ne('').sum()) if 'external_latest_favorite' in features else 0}",
        "",
        "| 日期 | 编号 | 比赛 | 体彩让球 | 外盘让球 | 内外盘关系 | 大小球 | 风险 | 说明 |",
        "|---|---|---|---:|---:|---|---|---|---|",
    ]
    for _, row in features.iterrows():
        lines.append(
            "| {date} | {num} | {home} vs {away} | {sline} | {eline} | {rel} | {total} | {risk} | {note} |".format(
                date=row.get("date", ""),
                num=row.get("match_number", ""),
                home=row.get("home_team", ""),
                away=row.get("away_team", ""),
                sline=text_value(row.get("sporttery_home_handicap", "")),
                eline=text_value(row.get("external_latest_home_spread_point", "")),
                rel=text_value(row.get("inner_outer_line_relation", "")),
                total=text_value(row.get("external_latest_total_signal", "")),
                risk=text_value(row.get("market_signal_strength", "")),
                note=text_value(row.get("market_signal_note", "")),
            )
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--market-csv", required=True)
    parser.add_argument("--sporttery-history", default="data/manual/sporttery_handicap_market_history.csv")
    parser.add_argument("--external-history", default="data/manual/external_market_snapshot_history.csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    markets = pd.read_csv(ROOT / args.market_csv).fillna("")
    sporttery_history = pd.read_csv(ROOT / args.sporttery_history).fillna("") if (ROOT / args.sporttery_history).exists() else pd.DataFrame()
    external_history = pd.read_csv(ROOT / args.external_history).fillna("") if (ROOT / args.external_history).exists() else pd.DataFrame()
    if not external_history.empty:
        external_history["home_key"] = external_history["home_team"].map(team_key)
        external_history["away_key"] = external_history["away_team"].map(team_key)
    features = build_market_signal_features(markets, sporttery_history, external_history)

    output = ROOT / args.output
    report_output = ROOT / args.report_output
    audit_output = ROOT / args.audit_output
    output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(output, index=False, encoding="utf-8-sig")
    report_output.write_text(render_report(features), encoding="utf-8")
    audit = {
        "ok": True,
        "rows": int(len(features)),
        "external_covered_rows": int(features["external_latest_favorite"].fillna("").astype(str).ne("").sum()) if "external_latest_favorite" in features else 0,
        "output": str(output),
        "report_output": str(report_output),
    }
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
