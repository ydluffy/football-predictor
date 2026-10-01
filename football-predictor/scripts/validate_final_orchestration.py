"""Fail closed when a READY final gate skipped the production strategy stage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate-json", required=True)
    parser.add_argument("--strategy-audit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    gate = json.loads(Path(args.gate_json).read_text(encoding="utf-8"))
    strategy_path = Path(args.strategy_audit)
    failures: list[str] = []
    strategy = {}
    if gate.get("phase") == "READY_FOR_FINAL_ANALYSIS":
        if not strategy_path.exists():
            failures.append("ready_gate_missing_production_strategy_audit")
        else:
            strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
            if not strategy.get("ok"):
                failures.append("production_strategy_audit_not_ok")
            if "production_plan_rows" not in strategy:
                failures.append("production_strategy_count_missing")

    result = {
        "ok": not failures,
        "gate_phase": gate.get("phase"),
        "production_strategy_executed": bool(strategy),
        "production_plan_rows": strategy.get("production_plan_rows"),
        "stake_rule": "100_yuan_per_formal_safe_or_value_plan",
        "shadow_model_can_block_production_strategy": False,
        "failures": failures,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
