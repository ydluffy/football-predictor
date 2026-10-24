"""Freeze/settle local paper experiments without fetching data or touching official ledgers."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from strategy.october_research import build_experiments, number, settle, timestamp  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(markets: list[dict], gate: dict, now: pd.Timestamp, config: dict) -> list[dict]:
    if config["mode"] != "simulation_only" or config["real_money_allowed"] is not False:
        raise ValueError("simulation-only configuration required")
    if now < timestamp(config["effective_from"]):
        raise ValueError("protocol is not effective yet")
    if gate.get("phase") != "READY_FOR_FINAL_ANALYSIS" or gate.get("may_create_plan") is not True or gate.get("failures"):
        raise ValueError("current official gate must be READY")
    deadlines = gate["deadlines"]
    start, lock = timestamp(deadlines["decision_start"]), timestamp(deadlines["decision_lock"])
    if not start <= now < min(lock, timestamp(deadlines["sales_cutoff"])):
        raise ValueError("outside the current decision window; no backdating")
    captured = timestamp(gate["freshness"]["official_captured_at"])
    if not start <= captured <= timestamp(gate["as_of"]) <= now or now - timestamp(gate["as_of"]) > pd.Timedelta(minutes=10):
        raise ValueError("gate/snapshot is stale or future-dated; refresh gate")
    expected = {number(value) for value in gate["expected_match_numbers"]}
    selected = []
    for row in markets:
        row = dict(row)
        row["match_number"] = number(row["match_number"])
        if row["match_number"] not in expected:
            continue
        if not row.get("home_team") or not row.get("away_team") or not now < timestamp(row["kickoff_time"]):
            raise ValueError("missing identity or match already started")
        # The CSV must be the exact current snapshot, not a historical file with a new gate.
        if timestamp(row.get("updated_at") or row.get("captured_at")) != captured:
            raise ValueError("market capture does not match official gate")
        if row.get("sale_status", "on_sale") != "on_sale":
            raise ValueError("match is not on sale")
        selected.append(row)
    if {row["match_number"] for row in selected} != expected or len(selected) != len(expected):
        raise ValueError("expected batch missing or duplicate match identity")
    return sorted(selected, key=lambda row: row["match_number"])


def write_new(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation never overwrites a previously frozen batch.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)


def report(snapshot: dict, path: Path) -> None:
    lines = ["# 10月宽松模拟研究", "", "全部为虚拟资金；理论单关不代表已核实可出票。", "",
        "## 逐场概率与净胜球", ""]
    for row in snapshot["matches"]:
        margins = {key: value for key, value in row.items() if key.startswith("margin_probability_")}
        lines.append(f"- {row['match_number']} {row['home_team']} vs {row['away_team']}：净胜球分布 {json.dumps(margins, ensure_ascii=False) if margins else '不可用，不从让球概率或赔率反推精确分布'}；模型状态 {row.get('handicap_model_usage', '未接入')}。")
    lines.extend(["", "## 模拟方案", ""])
    for experiment in snapshot["experiments"]:
        selections = " + ".join(leg["match_number"] + " " + "/".join(selection["label"] + "@" + str(selection["odds"]) for selection in leg["selections"]) for leg in experiment["legs"])
        sources = ", ".join(sorted({leg["probability_source"] for leg in experiment["legs"]}))
        lines.append(f"- {experiment['experiment_id']}：{selections}；{len(experiment['tickets'])}注，虚拟投入{experiment['stake']:.2f}元；来源 {sources}；资格 {experiment['ticket_eligibility']}。")
    lines.extend(["", "## 跳过记录", "", json.dumps(snapshot["skips"], ensure_ascii=False), "",
        "同场结构变体不算独立预测。比分、总进球和半全场没有完整官方报价与对应预测时，只留方向，不编造收益。"])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["freeze", "settle", "summarize"])
    parser.add_argument("--market-csv", type=Path)
    parser.add_argument("--gate-json", type=Path)
    parser.add_argument("--handicap-model-csv", type=Path)
    parser.add_argument("--batch-id", default="")
    parser.add_argument("--sales-day", default="")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--results-csv", type=Path)
    args = parser.parse_args()
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    directory = ROOT / "artifacts/data/october_research"
    if args.stage == "summarize":
        from strategy.october_research import summarize
        reviews = [json.loads(path.read_text(encoding="utf-8")) for path in (directory / "reviews").glob("*.json")]
        # Select one latest review per immutable snapshot; never count revised results twice.
        latest = {}
        for review in reviews:
            key = review["snapshot_sha256"]
            if key not in latest or review["reviewed_at"] > latest[key]["reviewed_at"]:
                latest[key] = review
        pairs = []
        for path in directory.glob("*.json"):
            if path.name == "summary.json":
                continue
            key = digest(path)
            pairs.append((json.loads(path.read_text(encoding="utf-8")), latest.get(key)))
        value = summarize(pairs)
        value["as_of"] = now.isoformat()
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "summary.json").write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps(value, ensure_ascii=False))
        return
    if args.stage == "settle":
        if not args.snapshot or not args.results_csv:
            parser.error("settle requires --snapshot and --results-csv")
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        review = settle(snapshot, pd.read_csv(args.results_csv, dtype=str).fillna("").to_dict("records"))
        review.update({"snapshot_sha256": digest(args.snapshot), "results_sha256": digest(args.results_csv), "reviewed_at": now.isoformat()})
        review['settlement_engine_sha256'] = digest(Path(__file__).resolve().parents[1] / 'src/strategy/october_research.py')
        output = directory / "reviews" / f"{args.snapshot.stem}_{digest(args.results_csv)[:16]}_{review['settlement_engine_sha256'][:8]}.json"
        if not output.exists():
            write_new(output, review)
        print(json.dumps({"review": str(output), "settled": len(review["settled"]), "pending": len(review["pending"])}, ensure_ascii=False))
        return
    if not args.market_csv or not args.gate_json or not args.batch_id or not args.sales_day:
        parser.error("freeze requires --market-csv --gate-json --batch-id --sales-day")
    if any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in args.batch_id):  # pragma: allowlist secret - non-secret status or character set
        raise ValueError("batch id must contain letters, digits, underscores or hyphens")
    config = json.loads((ROOT / "config/october_research.json").read_text(encoding="utf-8"))
    gate = json.loads(args.gate_json.read_text(encoding="utf-8"))
    rows = freeze(pd.read_csv(args.market_csv, dtype=str).fillna("").to_dict("records"), gate, now, config)
    day = pd.Timestamp(args.sales_day).date().isoformat()
    sales_start = timestamp(day) + pd.Timedelta(hours=10)
    if any(not sales_start <= timestamp(row["kickoff_time"]) < sales_start + pd.Timedelta(days=1) for row in rows):
        raise ValueError("kickoff outside specified sales day")
    model_skips = []
    if args.handicap_model_csv:
        predictions = pd.read_csv(args.handicap_model_csv, dtype=str).fillna("").to_dict("records")
        for row in rows:
            matches = [pred for pred in predictions if number(pred["match_number"]) == row["match_number"]
                and pred.get("home_team") == row["home_team"] and pred.get("away_team") == row["away_team"]
                and timestamp(pred["kickoff_time"]) == timestamp(row["kickoff_time"])]
            if len(matches) != 1:
                model_skips.append({"match_number": row["match_number"], "reason": "model_identity_missing_or_ambiguous"})
                continue
            pred = matches[0]
            if pred.get("handicap_model_usage") == "blocked":
                row["handicap_model_usage"] = "blocked"
                row["handicap_model_reason"] = pred.get("handicap_model_reason", "")
                continue
            predicted = pred.get("prediction_at", "")
            source = pred.get("handicap_model_source_captured_at", "")
            if not predicted or not source or not captured_model_time_valid(source, predicted, gate, now):
                model_skips.append({"match_number": row["match_number"], "reason": "model_timestamp_invalid_or_missing"})
                continue
            row.update({key: value for key, value in pred.items() if key.startswith(("handicap_model_", "margin_probability_"))})
    experiments, skips = build_experiments(rows, config)
    snapshot = {"protocol_version": config["protocol_version"], "config": config, "sales_day": day,
        "batch_id": args.batch_id, "frozen_at": now.isoformat(), "simulation_only": True,
        "market_sha256": digest(args.market_csv), "gate_sha256": digest(args.gate_json),
        "model_csv_sha256": digest(args.handicap_model_csv) if args.handicap_model_csv else None,
        "matches": rows, "experiments": experiments, "skips": skips + model_skips}
    output = directory / f"{day}_{args.batch_id}.json"
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if any(existing.get(key) != snapshot.get(key) for key in ("market_sha256", "gate_sha256", "model_csv_sha256", "config")):
            raise ValueError("batch already frozen with different inputs; cannot change selections")
        snapshot = existing
    else:
        write_new(output, snapshot)
    report(snapshot, output.with_suffix(".md"))
    print(json.dumps({"snapshot": str(output), "experiments": len(snapshot["experiments"]), "skips": len(snapshot["skips"])}, ensure_ascii=False))


def captured_model_time_valid(source: str, predicted: str, gate: dict, now: pd.Timestamp) -> bool:
    return timestamp(source) <= timestamp(predicted) <= now and timestamp(predicted) >= timestamp(gate["freshness"]["official_captured_at"])


if __name__ == "__main__":
    main()
