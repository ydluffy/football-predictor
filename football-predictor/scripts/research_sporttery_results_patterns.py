from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _score_parts(score: object) -> tuple[int | None, int | None]:
    text = str(score or "").replace("-", ":")
    parts = text.split(":")
    if len(parts) != 2:
        return None, None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def _spf(home: int | None, away: int | None) -> str:
    if home is None or away is None:
        return ""
    if home > away:
        return "胜"
    if home == away:
        return "平"
    return "负"


def _rqspf(home: int | None, away: int | None, handicap: object) -> str:
    if home is None or away is None:
        return ""
    try:
        adjusted_home = home + int(str(handicap).replace("+", ""))
    except ValueError:
        return ""
    if adjusted_home > away:
        return "让胜"
    if adjusted_home == away:
        return "让平"
    return "让负"


def _half_full(half_score: object, full_score: object) -> str:
    half_home, half_away = _score_parts(half_score)
    full_home, full_away = _score_parts(full_score)
    mapping = {"胜": "H", "平": "D", "负": "A"}
    half = mapping.get(_spf(half_home, half_away), "")
    full = mapping.get(_spf(full_home, full_away), "")
    return f"{half}-{full}" if half and full else ""


def _favorite(row: pd.Series) -> str:
    odds = {
        "home": pd.to_numeric(row.get("spf_home_odds", ""), errors="coerce"),
        "draw": pd.to_numeric(row.get("spf_draw_odds", ""), errors="coerce"),
        "away": pd.to_numeric(row.get("spf_away_odds", ""), errors="coerce"),
    }
    if any(pd.isna(value) or value <= 0 for value in odds.values()):
        return ""
    return min(odds, key=odds.get)


def _favorite_result(row: pd.Series) -> str:
    favorite = row.get("favorite", "")
    spf = row.get("spf_result", "")
    if not favorite:
        return "unknown"
    if favorite == "draw":
        return "hit" if spf == "平" else "miss"
    if favorite == "home":
        return "hit" if spf == "胜" else "miss"
    return "hit" if spf == "负" else "miss"


def load_world_cup(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, encoding="utf-8-sig").fillna("")
    rows = []
    for _, row in frame.iterrows():
        full_home, full_away = _score_parts(row.get("full_time_90_score"))
        half_home, half_away = _score_parts(row.get("half_time_score"))
        total_goals = (full_home + full_away) if full_home is not None and full_away is not None else None
        rows.append(
            {
                "source": "world_cup_pasted",
                "match_number": str(row.get("match_number", "")),
                "date": row.get("date", ""),
                "home_team": row.get("home_team", ""),
                "away_team": row.get("away_team", ""),
                "home_handicap": row.get("home_handicap", ""),
                "half_time_score": str(row.get("half_time_score", "")).replace("-", ":"),
                "full_time_score": str(row.get("full_time_90_score", "")).replace("-", ":"),
                "half_goals": (half_home + half_away) if half_home is not None and half_away is not None else None,
                "total_goals": total_goals,
                "spf_result": _spf(full_home, full_away),
                "rqspf_result": _rqspf(full_home, full_away, row.get("home_handicap", "")),
                "half_full": _half_full(row.get("half_time_score"), row.get("full_time_90_score")),
                "spf_home_odds": row.get("spf_home_odds", ""),
                "spf_draw_odds": row.get("spf_draw_odds", ""),
                "spf_away_odds": row.get("spf_away_odds", ""),
            }
        )
    out = pd.DataFrame(rows)
    out["favorite"] = out.apply(_favorite, axis=1)
    out["favorite_result"] = out.apply(_favorite_result, axis=1)
    return out


def load_official_results(paths: list[Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        if not path.exists():
            continue
        frame = pd.read_csv(path, encoding="utf-8-sig").fillna("")
        if frame.empty:
            continue
        rows = []
        for _, row in frame.iterrows():
            full_home, full_away = _score_parts(row.get("full_time_score"))
            half_home, half_away = _score_parts(row.get("half_time_score"))
            rows.append(
                {
                    "source": "sporttery_official",
                    "match_number": row.get("match_number", ""),
                    "date": row.get("date", ""),
                    "home_team": row.get("home_team", ""),
                    "away_team": row.get("away_team", ""),
                    "home_handicap": row.get("handicap", ""),
                    "half_time_score": row.get("half_time_score", ""),
                    "full_time_score": row.get("full_time_score", ""),
                    "half_goals": (half_home + half_away) if half_home is not None and half_away is not None else None,
                    "total_goals": (full_home + full_away) if full_home is not None and full_away is not None else None,
                    "spf_result": row.get("spf_result", ""),
                    "rqspf_result": row.get("rqspf_result", ""),
                    "half_full": _half_full(row.get("half_time_score"), row.get("full_time_score")),
                    "spf_home_odds": row.get("spf_odds_home", ""),
                    "spf_draw_odds": row.get("spf_odds_draw", ""),
                    "spf_away_odds": row.get("spf_odds_away", ""),
                }
            )
        frames.append(pd.DataFrame(rows))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).drop_duplicates(["match_number", "home_team", "away_team", "full_time_score"])
    out["favorite"] = out.apply(_favorite, axis=1)
    out["favorite_result"] = out.apply(_favorite_result, axis=1)
    return out


def _count_table(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    if frame.empty or column not in frame.columns:
        return pd.DataFrame()
    counts = frame[column].value_counts(dropna=False).rename_axis(column).reset_index(name="count")
    counts["rate"] = (counts["count"] / counts["count"].sum()).round(4)
    return counts


def _group_rate(frame: pd.DataFrame, group: str, target: str) -> pd.DataFrame:
    if frame.empty or group not in frame.columns or target not in frame.columns:
        return pd.DataFrame()
    rows = []
    for key, part in frame.groupby(group, dropna=False):
        counts = part[target].value_counts(dropna=False)
        total = int(len(part))
        row = {group: key, "matches": total}
        for label, count in counts.items():
            row[str(label)] = int(count)
            row[f"{label}_rate"] = round(int(count) / total, 4) if total else 0
        rows.append(row)
    return pd.DataFrame(rows)


def _markdown_table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "暂无。"
    lines = [
        "| " + " | ".join(str(column) for column in frame.columns) + " |",
        "| " + " | ".join("---" for _ in frame.columns) + " |",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def write_report(path: Path, world_cup: pd.DataFrame, official: pd.DataFrame, combined: pd.DataFrame) -> None:
    total_buckets = combined.copy()
    total_buckets["total_goals_bucket"] = total_buckets["total_goals"].map(
        lambda value: "unknown" if pd.isna(value) else ("0-1" if value <= 1 else "2-3" if value <= 3 else "4+")
    )
    favorite_frame = combined[combined["favorite"].astype(str).str.len() > 0].copy()
    lines = [
        "# 补赛果模型训练与规律研究",
        "",
        "说明：这不是严格投注收益回测，因为很多比赛没有当时的赛前预测方案；它用于补充赛果规律、训练特征和投注剧本优先级。",
        "",
        f"- 世界杯粘贴赛果样本：{len(world_cup)} 场",
        f"- 官方体彩近期赛果样本：{len(official)} 场",
        f"- 合并研究样本：{len(combined)} 场",
        "",
        "## 总进球分布",
        "",
        _markdown_table(_count_table(total_buckets, "total_goals_bucket")),
        "",
        "## 精确总进球",
        "",
        _markdown_table(_count_table(combined, "total_goals")),
        "",
        "## 胜平负结果分布",
        "",
        _markdown_table(_count_table(combined, "spf_result")),
        "",
        "## 让球结果分布",
        "",
        _markdown_table(_count_table(combined, "rqspf_result")),
        "",
        "## 半全场分布",
        "",
        _markdown_table(_count_table(combined, "half_full")),
        "",
        "## 按让球数拆分让球结果",
        "",
        _markdown_table(_group_rate(combined, "home_handicap", "rqspf_result")),
        "",
        "## 赔率热门命中情况（仅有赔率样本）",
        "",
        _markdown_table(_count_table(favorite_frame, "favorite_result")),
        "",
        "## 按热门方向拆分",
        "",
        _markdown_table(_group_rate(favorite_frame, "favorite", "favorite_result")),
        "",
        "## 投注组合启发",
        "",
        "- 总进球应优先围绕 2-3 球建模，再根据强弱差/淘汰赛节奏决定是否扩到 1 球或 4+。",
        "- 让球玩法必须按让球数拆分，不能只统计让胜/让平/让负总数；+1 和 -1 的含义完全不同。",
        "- 半全场中 D-* 组合是重要观察项，适合作为焦点战、淘汰赛、强强对话的防线玩法。",
        "- 有赔率样本时，要把最低赔率热门是否命中、是否赢盘分开：热门赢球不等于让球命中。",
        "- 这些规律只能指导方案生成，不能替代严格赛前留档回测。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Research historical Sporttery result patterns.")
    parser.add_argument("--world-cup-results", default="data/manual/sporttery_world_cup_results_pasted_001_096.csv")
    parser.add_argument("--official-results-dir", default="data/external/sporttery_results")
    parser.add_argument("--dataset-output", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--metrics-output", required=True)
    args = parser.parse_args()

    world_cup = load_world_cup(ROOT / args.world_cup_results)
    official_paths = sorted((ROOT / args.official_results_dir).glob("*.csv"))
    official = load_official_results(official_paths)
    combined = pd.concat([world_cup, official], ignore_index=True)
    combined = combined.drop_duplicates(["date", "home_team", "away_team", "full_time_score"])

    dataset_output = ROOT / args.dataset_output
    report_output = ROOT / args.report_output
    metrics_output = ROOT / args.metrics_output
    dataset_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    metrics_output.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(dataset_output, index=False, encoding="utf-8-sig")
    write_report(report_output, world_cup, official, combined)
    metrics = {
        "world_cup_rows": int(len(world_cup)),
        "official_rows": int(len(official)),
        "combined_rows": int(len(combined)),
        "dataset_output": str(dataset_output),
        "report_output": str(report_output),
    }
    metrics_output.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
