from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from evaluate.asian_handicap_research import (  # noqa: E402
    audit_live_market_archives,
    build_exact_handicap_dataset,
    summarize_exact_handicaps,
)


FOCUS_DEPTHS = {0.25, 0.5, 1.0, 1.5, 2.0}


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    return json.loads(frame.to_json(orient="records")) if not frame.empty else []


def render_report(payload: dict[str, object]) -> str:
    audit = payload["audit"]
    lines = [
        "# 精确亚洲盘口历史研究",
        "",
        "## 数据结论",
        "",
        f"- 历史源总场次：{audit['source_rows']:,}",
        f"- 可用初盘亚洲盘：{audit['research_rows']:,}",
        f"- 可用终盘亚洲盘：{audit['closing_complete_rows']:,}",
        f"- 覆盖：{audit['leagues']} 个联赛、{audit['seasons']} 个赛季，{audit['date_min']} 至 {audit['date_max']}",
        "- 数据包含初盘与终盘，但不是逐分钟盘口流；本报告只用于历史研究。",
        "",
        "## 当前内外盘归档",
        "",
        f"- 体彩让球历史：{payload['live_archive_audit']['sporttery_rows']} 条、"
        f"{payload['live_archive_audit']['sporttery_unique_fixtures']} 场、"
        f"{payload['live_archive_audit']['sporttery_snapshot_times']} 个抓取时间。",
        f"- 外盘快照历史：{payload['live_archive_audit']['external_rows']} 条、"
        f"{payload['live_archive_audit']['external_unique_events']} 场、"
        f"{payload['live_archive_audit']['external_snapshot_times']} 个抓取时间。",
        "- 两套近期归档尚未形成可训练的同场同时间历史配对，继续保持阻断。",
        "",
        "## 重点盘口",
        "",
        "| 盘口 | 样本 | 全赢 | 半赢 | 走盘 | 半输 | 全输 | 初盘热门ROI | 状态 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in payload["focus_lines"]:
        lines.append(
            f"| {row['opening_line_label']} | {row['matches']:,} | {row['full_win']} | {row['half_win']} | "
            f"{row['push']} | {row['half_loss']} | {row['full_loss']} | {row['opening_favorite_roi']:.2%} | {row['status']} |"
        )
    lines.extend(
        [
            "",
            "## 使用边界",
            "",
            "- ROI 是机械地投注盘口热门方的研究基准，不是推荐收益，也不直接生成投注方案。",
            "- 平半、半一、一球/球半等四分之一盘已按两半注分别结算，保留半赢和半输。",
            "- 当前历史体彩让球盘没有与这批欧洲外盘逐场、逐时点对齐，因此不能把外盘研究冒充为历史内外盘差异回测。",
            "- 只有同一比赛、同一赛前时点完成体彩与外盘唯一映射后，内外盘差值才允许进入候选特征。",
            "- 本阶段不修改生产模型、影子配置和投注逻辑。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest exact quarter-goal Asian handicap lines")
    parser.add_argument("--data-path", default="data/processed/historical_matches_europe_extended_candidate.csv")
    parser.add_argument("--dataset-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    parser.add_argument("--minimum-observation", type=int, default=100)
    parser.add_argument("--sporttery-history", default="data/manual/sporttery_handicap_market_history.csv")
    parser.add_argument("--external-history", default="data/manual/external_market_snapshot_history.csv")
    args = parser.parse_args()

    data_path = project_path(args.data_path)
    dataset, audit = build_exact_handicap_dataset(pd.read_csv(data_path, low_memory=False))
    by_line = summarize_exact_handicaps(
        dataset,
        group_columns=["opening_line_depth", "opening_line_label"],
        minimum_observation=args.minimum_observation,
    )
    by_league_line = summarize_exact_handicaps(
        dataset,
        group_columns=["league", "opening_line_depth", "opening_line_label"],
        minimum_observation=args.minimum_observation,
    )
    by_season_line = summarize_exact_handicaps(
        dataset,
        group_columns=["season", "opening_line_depth", "opening_line_label"],
        minimum_observation=args.minimum_observation,
    )
    focus = by_line.loc[by_line["opening_line_depth"].isin(FOCUS_DEPTHS)].copy()
    sporttery_path = project_path(args.sporttery_history)
    external_path = project_path(args.external_history)
    sporttery_history = pd.read_csv(sporttery_path, low_memory=False) if sporttery_path.exists() else pd.DataFrame()
    external_history = pd.read_csv(external_path, low_memory=False) if external_path.exists() else pd.DataFrame()
    live_archive_audit = audit_live_market_archives(sporttery_history, external_history)
    payload: dict[str, object] = {
        "schema_version": 1,
        "data_path": str(data_path),
        "audit": audit,
        "minimum_observation": args.minimum_observation,
        "focus_lines": records(focus),
        "all_lines": records(by_line),
        "league_line_groups": records(by_league_line),
        "season_line_groups": records(by_season_line),
        "live_archive_audit": live_archive_audit,
        "production_change_performed": False,
        "inner_outer_training_gate": "blocked_until_time_aligned_sporttery_history_exists",
    }
    dataset_output = project_path(args.dataset_output)
    summary_output = project_path(args.summary_output)
    json_output = project_path(args.json_output)
    markdown_output = project_path(args.markdown_output)
    for path in (dataset_output, summary_output, json_output, markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(dataset_output, index=False)
    by_league_line.to_csv(summary_output, index=False)
    json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_report(payload), encoding="utf-8")
    print(json.dumps({"audit": audit, "focus_lines": payload["focus_lines"]}, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
