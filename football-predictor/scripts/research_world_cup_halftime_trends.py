from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.halftime_trends import build_world_cup_halftime_match_rows
from world_cup.halftime_trends import download_statsbomb_world_cup_events
from world_cup.halftime_trends import summarize_halftime_trends


def _pct(value: float) -> str:
    return f"{value:.1%}"


def _markdown_report(tables: dict[str, object], *, matches: int) -> str:
    stage = tables["stage_summary"]
    half_full = tables["half_full_distribution"]
    goals = tables["goal_distribution"]
    lines = [
        "# World Cup Half-Time / Full-Time Trends",
        "",
        f"- Source: StatsBomb open data, FIFA World Cup 2018 and 2022.",
        f"- Matches with event data: {matches}.",
        "- Betting scope: 90-minute regulation time only; extra time and penalties are excluded.",
        "",
        "## Stage Summary",
        "",
        "| Stage | Matches | Avg FT Goals | Avg HT Goals | HT Draw | FT Draw | HT Over0.5 | FT Over2.5 | BTTS |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in stage.iterrows():
        lines.append(
            "| {stage_bucket} | {matches:.0f} | {avg_ft_goals:.2f} | {avg_ht_goals:.2f} | {draw_ht_rate} | {draw_ft_rate} | {over_0_5_ht_rate} | {over_2_5_ft_rate} | {both_teams_scored_rate} |".format(
                stage_bucket=row["stage_bucket"],
                matches=row["matches"],
                avg_ft_goals=row["avg_ft_goals"],
                avg_ht_goals=row["avg_ht_goals"],
                draw_ht_rate=_pct(row["draw_ht_rate"]),
                draw_ft_rate=_pct(row["draw_ft_rate"]),
                over_0_5_ht_rate=_pct(row["over_0_5_ht_rate"]),
                over_2_5_ft_rate=_pct(row["over_2_5_ft_rate"]),
                both_teams_scored_rate=_pct(row["both_teams_scored_rate"]),
            )
        )
    lines += [
        "",
        "## Top Half/Full-Time Results",
        "",
        "| Stage | Half/Full | Matches | Share |",
        "|---|---|---:|---:|",
    ]
    for _, row in (
        half_full.sort_values(["stage_bucket", "matches"], ascending=[True, False])
        .groupby("stage_bucket")
        .head(6)
        .iterrows()
    ):
        lines.append(
            f"| {row['stage_bucket']} | {row['half_full_result']} | {int(row['matches'])} | {_pct(row['share'])} |"
        )
    lines += [
        "",
        "## Full-Time Goal Count Distribution",
        "",
        "| Stage | Goals | Matches | Share |",
        "|---|---:|---:|---:|",
    ]
    for _, row in goals.iterrows():
        lines.append(
            f"| {row['stage_bucket']} | {int(row['full_time_total_goals_90'])} | {int(row['matches'])} | {_pct(row['share'])} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Research World Cup 90-minute total-goal and half/full-time trends."
    )
    parser.add_argument("--cache-dir", default="data/external/statsbomb-open-data")
    parser.add_argument("--download-events", choices=["true", "false"], default="true")
    parser.add_argument("--output-dir", default="artifacts/research/world_cup_halftime_trends")
    args = parser.parse_args()

    cache = _ROOT / args.cache_dir
    output = _ROOT / args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    download_audit = (
        download_statsbomb_world_cup_events(cache)
        if args.download_events == "true"
        else {}
    )
    matches = build_world_cup_halftime_match_rows(cache)
    tables = summarize_halftime_trends(matches)

    match_path = output / "world_cup_halftime_match_rows.csv"
    matches.to_csv(match_path, index=False, encoding="utf-8-sig")
    table_paths: dict[str, str] = {}
    for name, table in tables.items():
        path = output / f"{name}.csv"
        table.to_csv(path, index=False, encoding="utf-8-sig")
        table_paths[name] = str(path)
    report_path = output / "world_cup_halftime_trends_report.md"
    report_path.write_text(_markdown_report(tables, matches=len(matches)), encoding="utf-8")
    audit = {
        "download": download_audit,
        "matches": int(len(matches)),
        "seasons": sorted(matches["season"].unique().tolist()) if not matches.empty else [],
        "outputs": {"matches": str(match_path), **table_paths, "report": str(report_path)},
    }
    audit_path = output / "world_cup_halftime_trends_audit.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
