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

from data.prematch_coverage import audit_prematch_coverage, count_world_cup_only_assets  # noqa: E402


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def render_markdown(audit: dict[str, object]) -> str:
    lines = [
        "# 赛前新增信息覆盖审计",
        "",
        f"- 历史比赛：{audit['historical_rows']} 场",
        f"- 世界杯专用资产数量：{audit['world_cup_only_asset_count']}",
        f"- 通用赛前数据集：{'已建立' if audit['generic_prematch_dataset']['exists'] else '尚未建立'}；实际记录 {audit['generic_prematch_dataset']['rows']} 条。",
        "",
        "| 信息组 | 历史候选数据 | 通用赛前记录 | 覆盖比赛 | 字段 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    labels = {
        "confirmed_lineups": "确认阵容",
        "absences": "伤停停赛",
        "prematch_xg": "赛前 xG/强度",
        "travel": "旅行距离",
        "timezone": "时区变化",
        "cross_comp_schedule": "跨赛事赛程",
        "observation_timestamps": "信息观测时间",
    }
    for key, item in audit["field_groups"].items():
        generic = audit["generic_prematch_dataset"]["groups"].get(key, {})
        lines.append(
            f"| {labels.get(key, key)} | {'有' if item['available'] else '无'} | "
            f"{generic.get('rows', 0)} | {generic.get('matches', 0)} | "
            f"{', '.join(item['present_columns']) if item['present_columns'] else '-'} |"
        )
    snapshot = audit["market_snapshot_history"]
    sporttery = audit["sporttery_snapshot_archive"]
    lines.extend(
        [
            "",
            "## 赔率快照",
            "",
            f"- 总行数：{snapshot['rows']}；唯一事件：{snapshot['unique_events']}。",
            f"- 可证明早于开赛：{snapshot['kickoff_safe_rows']} 行。",
            f"- 开赛后或时间无效：{snapshot['post_kickoff_or_invalid_rows']} 行。",
            f"- 体彩不可变快照：{sporttery['unique_snapshots']} 个；安全场次观测 {sporttery['safe_fixture_observations']}，不安全场次观测 {sporttery['unsafe_fixture_observations']}。",
            "",
            "## 闸门结论",
            "",
            "- 现有射门等赛后统计只能通过 shift 后的历史滚动值使用。",
            "- 世界杯专用阵容/伤停资产不能自动视为联赛通用覆盖。",
            "- 在形成足够规模、带 observed_at 的赛前数据前，新增信息模型保持阻断。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit timestamped prematch information coverage")
    parser.add_argument(
        "--historical-path",
        default="data/processed/historical_matches_europe_extended_candidate.csv",
    )
    parser.add_argument(
        "--market-snapshot-path",
        default="data/manual/external_market_snapshot_history.csv",
    )
    parser.add_argument(
        "--prematch-intelligence-path",
        default="data/manual/prematch_intelligence.csv",
    )
    parser.add_argument(
        "--sporttery-snapshot-index",
        default="data/manual/sporttery_snapshot_index.csv",
    )
    parser.add_argument("--json-output", required=True)
    parser.add_argument("--markdown-output", required=True)
    args = parser.parse_args()

    historical = pd.read_csv(project_path(args.historical_path), low_memory=False)
    snapshot_path = project_path(args.market_snapshot_path)
    snapshots = pd.read_csv(snapshot_path, low_memory=False) if snapshot_path.exists() else None
    intelligence_path = project_path(args.prematch_intelligence_path)
    intelligence = pd.read_csv(intelligence_path, low_memory=False) if intelligence_path.exists() else None
    sporttery_index_path = project_path(args.sporttery_snapshot_index)
    sporttery_index = pd.read_csv(sporttery_index_path, low_memory=False) if sporttery_index_path.exists() else None
    audit = audit_prematch_coverage(
        historical,
        market_snapshot_history=snapshots,
        sporttery_snapshot_index=sporttery_index,
        prematch_intelligence=intelligence,
        world_cup_only_asset_count=count_world_cup_only_assets(ROOT / "data"),
    )
    json_output = project_path(args.json_output)
    markdown_output = project_path(args.markdown_output)
    for path in (json_output, markdown_output):
        path.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_output.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
