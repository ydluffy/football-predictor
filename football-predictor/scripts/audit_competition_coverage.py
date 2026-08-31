from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.competition_registry import load_competition_registry  # noqa: E402
from data.transform_rules import parse_match_dates  # noqa: E402


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _first_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)


def _ratio(frame: pd.DataFrame, columns: tuple[str, ...]) -> float:
    available = [column for column in columns if column in frame.columns]
    if not available or frame.empty:
        return 0.0
    return float(frame[available].notna().all(axis=1).mean())


def audit_files(paths: list[Path], registry_path: Path) -> dict[str, Any]:
    registry = load_competition_registry(registry_path)
    rows: list[dict[str, Any]] = []
    unknown_labels: dict[str, int] = {}
    for path in paths:
        frame = pd.read_csv(path, low_memory=False)
        competition_col = _first_column(frame, ("competition_id", "competition", "league", "tournament"))
        date_col = _first_column(frame, ("date", "match_date", "kickoff", "utc_date"))
        season_col = _first_column(frame, ("season", "season_id"))
        if competition_col is None:
            labels = pd.Series(["" for _ in range(len(frame))], index=frame.index, dtype="string")
        else:
            labels = frame[competition_col].astype("string").fillna("")
        dates = parse_match_dates(frame[date_col]) if date_col else pd.Series(pd.NaT, index=frame.index)
        for label, group_index in labels.groupby(labels, dropna=False).groups.items():
            group = frame.loc[group_index]
            metadata = registry.annotate(label)
            group_dates = dates.loc[group_index].dropna()
            if season_col:
                seasons = sorted(group[season_col].dropna().astype(str).unique().tolist())
            else:
                seasons = []
            record = {
                "source_file": str(path),
                "source_label": str(label),
                **metadata,
                "rows": int(len(group)),
                "date_min": None if group_dates.empty else group_dates.min().date().isoformat(),
                "date_max": None if group_dates.empty else group_dates.max().date().isoformat(),
                "seasons": seasons,
                "season_count": len(seasons),
                "result_completeness": _ratio(group, ("home_goals", "away_goals")),
                "odds_1x2_completeness": _ratio(group, ("odds_home", "odds_draw", "odds_away")),
                "team_completeness": _ratio(group, ("home_team", "away_team")),
            }
            rows.append(record)
            if not metadata["competition_known"]:
                unknown_labels[str(label)] = unknown_labels.get(str(label), 0) + int(len(group))

    total_rows = sum(int(item["rows"]) for item in rows)
    known_rows = sum(int(item["rows"]) for item in rows if item["competition_known"])
    return {
        "schema_version": 1,
        "input_files": [str(path) for path in paths],
        "registry_path": str(registry_path),
        "summary": {
            "rows": total_rows,
            "known_competition_rows": known_rows,
            "unknown_competition_rows": total_rows - known_rows,
            "known_competition_ratio": float(known_rows / total_rows) if total_rows else 0.0,
            "competition_groups": len(rows),
        },
        "unknown_labels": dict(sorted(unknown_labels.items(), key=lambda item: (-item[1], item[0]))),
        "competitions": sorted(rows, key=lambda item: (item["competition_id"], item["source_file"])),
    }


def render_markdown(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# 赛事数据覆盖审计",
        "",
        f"- 总记录：{summary['rows']}",
        f"- 已识别赛事记录：{summary['known_competition_rows']}",
        f"- 未识别赛事记录：{summary['unknown_competition_rows']}",
        f"- 赛事识别率：{summary['known_competition_ratio']:.2%}",
        "",
        "## 分赛事覆盖",
        "",
        "| 赛事 | 原始标签 | 场次 | 赛季数 | 日期范围 | 赛果完整度 | 1X2赔率完整度 | 历史模型覆盖 | 路由状态 |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for item in audit["competitions"]:
        lines.append(
            f"| {item['competition_id']} | {item['source_label']} | {item['rows']} | "
            f"{item['season_count']} | {item['date_min'] or '-'} 至 {item['date_max'] or '-'} | "
            f"{item['result_completeness']:.2%} | {item['odds_1x2_completeness']:.2%} | "
            f"{'是' if item['historical_model_coverage'] else '否'} | {item['model_route_status']} |"
        )
    lines.extend(["", "## 未识别赛事标签", ""])
    if audit["unknown_labels"]:
        lines.extend(f"- `{label or '<empty>'}`：{count} 场" for label, count in audit["unknown_labels"].items())
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit competition, season, result, and odds coverage")
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help="CSV input path; may be repeated",
    )
    parser.add_argument("--registry", default="config/competitions.json")
    parser.add_argument("--json-output", default="artifacts/data/competition_coverage_audit_latest.json")
    parser.add_argument("--markdown-output", default="artifacts/data/competition_coverage_audit_latest.md")
    args = parser.parse_args()
    inputs = args.input or ["data/processed/historical_matches_trainable.csv"]
    paths = [project_path(value) for value in inputs]
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)
    audit = audit_files(paths, project_path(args.registry))
    json_output = project_path(args.json_output)
    markdown_output = project_path(args.markdown_output)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({"json": str(json_output), "markdown": str(markdown_output), "summary": audit["summary"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
