from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from config.settings import get_settings
from research_director.director import ResearchDirector


def _safe_read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _default_artifacts() -> dict[str, object]:
    s = get_settings()
    out: dict[str, object] = {}
    out["metrics_path"] = str(s.eval_metrics_path)
    out["results_path"] = str(s.eval_results_path)
    out["model_compare_path"] = str(s.eval_model_compare_path)
    out["reliability_table_path"] = str(s.eval_reliability_table_path)
    out["model_registry_path"] = str(s.research_model_registry_path)
    out["latest_execution_summary_path"] = str(s.research_latest_execution_summary_path)
    # upgrade_report 在具体 run_dir 下，优先从 latest_execution_summary 的 run_dir 推断
    latest = _safe_read_json(s.research_latest_execution_summary_path)
    up_path: Path | None = None
    if isinstance(latest, dict) and latest.get("run_id"):
        rid = str(latest["run_id"])
        run_dir = s.research_director_runs_dir / rid
        cand = run_dir / "upgrade_report.json"
        if cand.exists():
            up_path = cand
    out["upgrade_report_path"] = str(up_path) if up_path else None
    return out


def _summarize_distribution(results: pd.DataFrame) -> dict[str, object]:
    out: dict[str, object] = {"n": 0}
    if results.empty:
        return out
    n = int(len(results))
    out["n"] = n
    cols = ["p_home", "p_draw", "p_away"]
    if not set(cols) <= set(results.columns):
        return out
    P = results[cols].to_numpy(dtype=float, copy=False)
    avg = P.mean(axis=0).tolist()
    out["avg_p"] = {"home": float(avg[0]), "draw": float(avg[1]), "away": float(avg[2])}
    pred_idx = P.argmax(axis=1)
    pred_counts = {0: int((pred_idx == 0).sum()), 1: int((pred_idx == 1).sum()), 2: int((pred_idx == 2).sum())}
    out["pred_label_counts"] = {"H": pred_counts[0], "D": pred_counts[1], "A": pred_counts[2]}
    if "actual" in results.columns:
        y = results["actual"].astype(str).str.upper()
        out["actual_label_counts"] = {
            "H": int((y == "H").sum()),
            "D": int((y == "D").sum()),
            "A": int((y == "A").sum()),
        }
    # 简单偏置判定：单类预测占比 > 0.7 或 avg_p 某一类 > 0.6
    bias_flags: list[str] = []
    total_pred = float(sum(out["pred_label_counts"].values()))
    if total_pred > 0:
        for k, v in out["pred_label_counts"].items():
            if float(v) / total_pred > 0.7:
                bias_flags.append(f"predicted_{k}_dominant")
                break
    ap = out.get("avg_p") or {}
    if any(float(x) > 0.6 for x in ap.values()):
        bias_flags.append("probability_mass_skewed")
    out["bias_flags"] = bias_flags
    return out


def analyze_latest_run() -> dict[str, object]:
    s = get_settings()
    metrics = _safe_read_json(s.eval_metrics_path)
    results = _safe_read_csv(s.eval_results_path)
    dist = _summarize_distribution(results)
    suggestions: list[str] = []
    if metrics:
        if float(metrics.get("brier", 0.0)) > 0.5:
            suggestions.append("考虑引入校准（sigmoid）并比较 reliability gap")
        if float(metrics.get("logloss", 0.0)) > 1.0:
            suggestions.append("尝试更强模型（lightgbm）或升级到 v2/v3 特征")
    if "bias_flags" in dist and dist["bias_flags"]:
        suggestions.append("检测类别不平衡或赔率分布异常，检查联赛/赛季混合与标签质量")
    return {
        "n_samples": int(dist.get("n", 0)),
        "brier": float(metrics.get("brier", 0.0)) if metrics else None,
        "logloss": float(metrics.get("logloss", 0.0)) if metrics else None,
        "distribution": dist,
        "suggestions": suggestions,
    }


def explain_high_brier() -> dict[str, object]:
    s = get_settings()
    metrics = _safe_read_json(s.eval_metrics_path)
    results = _safe_read_csv(s.eval_results_path)
    dist = _summarize_distribution(results)
    reasons: list[str] = []
    if dist.get("bias_flags"):
        reasons.append("类别或概率分布偏置（bias_flags 命中）")
    reasons.append("特征不足：当前 v1 仅赔率，建议采用 v2 加入 xg/injury/line_move")
    reasons.append("模型表达能力：logit 可能不足，可试 lightgbm 或 stacking")
    if metrics and float(metrics.get("brier", 0.0)) > 0.5:
        reasons.append("未校准：尝试 sigmoid 校准并观察 reliability_table")
    if "actual_label_counts" in dist:
        alc = dist["actual_label_counts"]
        total = sum(alc.values()) or 1
        if max(alc.values()) / total > 0.6:
            reasons.append("类别不平衡：实际标签分布倾斜，建议在切分/采样上做约束")
    return {"brier": metrics.get("brier") if metrics else None, "reasons": reasons, "distribution": dist}


def _parse_run_experiment(text: str) -> dict[str, str]:
    t = text.lower()
    mt = "logit"
    fv = "v1"
    cal = "none"
    dm = "mock"
    for k in ("lightgbm", "lgbm"):
        if k in t:
            mt = "lightgbm"
    if "stacking_oof" in t:
        mt = "stacking_oof"
    elif "stacking" in t:
        mt = "stacking"
    if "v3" in t:
        fv = "v3"
    elif "v2" in t:
        fv = "v2"
    if "sigmoid" in t:
        cal = "sigmoid"
    elif "isotonic" in t:
        cal = "isotonic"
    if "real" in t or "真实" in t or "今天" in t or "今日" in t or "live" in t:
        dm = "real"
    return {"model_type": mt, "feature_version": fv, "calibration": cal, "data_mode": dm}


def run_experiment(command_text: str) -> dict[str, object]:
    cfg = _parse_run_experiment(command_text)
    director = ResearchDirector()
    wf = "candidate_model_upgrade" if ("upgrade" in command_text.lower() or "晋升" in command_text) else "daily_prediction"
    ctx = {
        "model_type": cfg["model_type"],
        "feature_version": cfg["feature_version"],
        "calibration": cfg["calibration"],
        "data_mode": cfg["data_mode"],
        "use_verifier": False,
    }
    if cfg["data_mode"] == "real":
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        s = get_settings()
        schedule_path = s.project_root / "data" / "raw" / "schedules" / f"schedule_{today}.csv"
        if schedule_path.exists():
            ctx["raw_matches_csv"] = str(schedule_path)
            # mapping_path defaults to none, we don't strictly need it if we use standard columns, but the scout agent demands it.
            # We can create a dummy mapping.json
            mapping_path = schedule_path.parent / "mapping.json"
            if not mapping_path.exists():
                mapping_path.write_text("{}", encoding="utf-8")
            ctx["mapping_path"] = str(mapping_path)

    out = director.run(wf, context=ctx)
    metrics = out.get("metrics") if isinstance(out.get("metrics"), dict) else {}
    decision = out.get("decision") if isinstance(out.get("decision"), dict) else None
    return {
        "run_id": out.get("run_id"),
        "workflow": wf,
        "status": out.get("status"),
        "metrics_summary": metrics,
        "decision": decision,
    }


def show_system_status() -> dict[str, object]:
    s = get_settings()
    reg = _safe_read_json(s.research_model_registry_path)
    latest = _safe_read_json(s.research_latest_execution_summary_path)
    metrics = _safe_read_json(s.eval_metrics_path)
    prod = None
    try:
        prod = reg.get("current_production_model")
    except Exception:
        prod = None
    return {
        "production_model": prod,
        "latest_run_id": latest.get("run_id") if isinstance(latest, dict) else None,
        "latest_metrics": {"brier": metrics.get("brier"), "logloss": metrics.get("logloss")} if metrics else None,
        "latest_decision": latest.get("decision_result") if isinstance(latest, dict) else None,
    }


def _read_backtest_status() -> dict[str, object]:
    s = get_settings()
    base = s.project_root / "artifacts" / "backtest"
    summary_path = base / "summary.json"
    bets_path = base / "bets.csv"
    by_league_path = base / "by_league.csv"
    curve_path = base / "equity_curve.csv"
    summary = _safe_read_json(summary_path)
    out: dict[str, object] = {
        "paths": {
            "summary_path": str(summary_path),
            "bets_path": str(bets_path),
            "by_league_path": str(by_league_path),
            "equity_curve_path": str(curve_path),
        },
        "summary": summary if summary else None,
    }
    if by_league_path.exists():
        df = _safe_read_csv(by_league_path)
        if not df.empty:
            out["by_league_top"] = df.head(5).to_dict(orient="records")
    return out


def _fmt_float(x: object, *, digits: int = 4) -> str:
    try:
        v = float(x)  # type: ignore[arg-type]
    except Exception:
        return "NA"
    if v != v:
        return "NA"
    return f"{v:.{digits}f}"


def _format_latest_analysis_message() -> str:
    s = get_settings()
    a = analyze_latest_run()
    bt = _read_backtest_status()
    dist = a.get("distribution") if isinstance(a.get("distribution"), dict) else {}
    avg_p = dist.get("avg_p") if isinstance(dist.get("avg_p"), dict) else {}
    bias = dist.get("bias_flags") if isinstance(dist.get("bias_flags"), list) else []
    suggestions = a.get("suggestions") if isinstance(a.get("suggestions"), list) else []
    lines = [
        f"- 样本量(n_samples): {a.get('n_samples')}",
        f"- brier: {_fmt_float(a.get('brier'))}",
        f"- logloss: {_fmt_float(a.get('logloss'))}",
        f"- 概率均值(avg_p): H={_fmt_float(avg_p.get('home'))}, D={_fmt_float(avg_p.get('draw'))}, A={_fmt_float(avg_p.get('away'))}",
        f"- 偏置(bias_flags): {', '.join(str(x) for x in bias) if bias else '无明显偏置'}",
        f"- 产物: {s.eval_metrics_path} | {s.eval_results_path} | {s.eval_reliability_table_path}",
    ]
    if bt.get("summary"):
        sm = bt["summary"]  # type: ignore[assignment]
        lines.append(
            f"- 回测: n_bets={sm.get('n_bets')} profit={_fmt_float(sm.get('profit'))} roi={_fmt_float(sm.get('roi'))} max_dd={_fmt_float(sm.get('max_drawdown'))} final={_fmt_float(sm.get('final_bankroll'))}"
        )
        lines.append(f"- 回测产物: {bt['paths']['summary_path']} | {bt['paths']['bets_path']}")
    if suggestions:
        lines.append("- 建议: " + "；".join(str(x) for x in suggestions))
    return "\n".join(lines)


def _format_high_brier_message() -> str:
    s = get_settings()
    x = explain_high_brier()
    rs = x.get("reasons") if isinstance(x.get("reasons"), list) else []
    return "\n".join(
        [
            f"- brier: {_fmt_float(x.get('brier'))}",
            f"- 产物: {s.eval_metrics_path} | {s.eval_results_path} | {s.eval_reliability_table_path}",
            "- 可能原因:",
        ]
        + [f"  - {r}" for r in rs]
    )


def _format_backtest_message() -> str:
    bt = _read_backtest_status()
    sm = bt.get("summary")
    if not sm:
        return "\n".join(
            [
                "- 未找到回测产物 summary.json",
                f"- 期望路径: {bt['paths']['summary_path']}",
                "- 先运行: python scripts/run_backtest.py --pred-path artifacts/eval/results.csv --data-path data/processed/real_matches_standardized.csv --out-dir artifacts/backtest",
            ]
        )
    top = bt.get("by_league_top")
    lines = [
        f"- 回测: n_bets={sm.get('n_bets')} profit={_fmt_float(sm.get('profit'))} roi={_fmt_float(sm.get('roi'))} hit_rate={_fmt_float(sm.get('hit_rate'))} max_dd={_fmt_float(sm.get('max_drawdown'))} final={_fmt_float(sm.get('final_bankroll'))}",
        f"- 产物: {bt['paths']['summary_path']} | {bt['paths']['bets_path']} | {bt['paths']['by_league_path']} | {bt['paths']['equity_curve_path']}",
    ]
    if isinstance(top, list) and top:
        lines.append("- 联赛Top(按 n_bets): " + "; ".join(f"{r.get('league')} n={r.get('n_bets')} roi={_fmt_float(r.get('roi'))}" for r in top))
    return "\n".join(lines)


def _format_status_message() -> str:
    s = show_system_status()
    prod = s.get("production_model")
    latest_run = s.get("latest_run_id")
    latest_metrics = s.get("latest_metrics") if isinstance(s.get("latest_metrics"), dict) else {}
    return "\n".join(
        [
            f"- production_model: {prod.get('model_id') if isinstance(prod, dict) else None}",
            f"- latest_run_id: {latest_run}",
            f"- latest_metrics: brier={_fmt_float(latest_metrics.get('brier'))}, logloss={_fmt_float(latest_metrics.get('logloss'))}",
            f"- latest_decision: {s.get('latest_decision')}",
        ]
    )


def _format_today_matches_message() -> str:
    from ingest.fetch_schedule import FootballDataClient

    try:
        client = FootballDataClient()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        df = client.fetch_today_matches(today)

        if (
            not df.empty
            and "is_predictable" in df.columns
            and not df["is_predictable"].fillna(False).any()
        ):
            lines = [f"**今日 ({today}) 公开赛程**：", f"共获取到 {len(df)} 场比赛。"]
            for _, row in df.iterrows():
                lines.append(
                    f"- {row['league']}: {row['home_team']} vs {row['away_team']} ({row['date']})"
                )
            out_path = client.save_schedule(df, today)
            lines.append(f"\n数据已保存至: `{out_path}`")
            lines.append("当前来源不含真实赔率，已标记为 schedule_only，不会用于模型预测。")
            return "\n".join(lines)

        if df.empty:
            return f"今天 ({today}) 没有获取到任何赛程数据。"

        lines = [f"**今日 ({today}) 实时赛程及高级特征**：", f"共获取到 {len(df)} 场比赛。"]

        for _, row in df.iterrows():
            match_str = f"- {row['league']}: {row['home_team']} vs {row['away_team']} ({row['date']})"
            stats_str = f"  - 赔率: 主胜 {row['odds_home']}, 平 {row['odds_draw']}, 客胜 {row['odds_away']}"
            adv_stats_str = f"  - 高级特征: xG主 {row['xg_home']} / xG客 {row['xg_away']}, 赔率变动 {row['line_move']}, 伤停标记 {row['injury_flag']}"
            lines.extend([match_str, stats_str, adv_stats_str])

        out_path = client.save_schedule(df, today)
        lines.append(f"\n*数据已保存至*: `{out_path}`")
        lines.append("*提示*: 你可以回复“用这些数据跑预测”来运行 `daily_prediction` 工作流进行今日推单！")
        return "\n".join(lines)
    except Exception as e:
        return f"[error] 获取今日赛程失败: {e}"

def _try_handle_natural_language(text: str) -> str | None:
    t = text.strip().lower()
    if not t:
        return None

    if any(k in t for k in ("今天", "今日", "球赛", "赛程", "比赛", "live", "实时")) and not any(k in t for k in ("跑", "训练", "预测", "评估")):
        return _format_today_matches_message()

    if any(k in t for k in ("总结", "概览", "分析", "最新结果", "表现", "指标", "metrics", "logloss", "brier")):
        if any(k in t for k in ("为什么", "原因", "高", "解释")) and ("brier" in t or "logloss" in t or "概率" in t):
            return _format_high_brier_message()
        return _format_latest_analysis_message()

    if any(k in t for k in ("回测", "roi", "收益", "亏", "回撤", "下注", "bets")):
        return _format_backtest_message()

    if any(k in t for k in ("跑", "试验", "实验", "对比", "训练", "预测", "upgrade", "晋升", "推单")) and any(
        k in t for k in ("logit", "lightgbm", "lgbm", "stacking", "v1", "v2", "v3", "sigmoid", "isotonic", "real", "真实", "今天", "今日", "这些")
    ):
        out = run_experiment(text)
        return json.dumps(out, ensure_ascii=False, indent=2)

    if any(k in t for k in ("状态", "系统状态", "production", "registry", "模型注册", "当前模型")):
        return _format_status_message()

    return None
