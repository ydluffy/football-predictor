from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REQUIRED = {
    "ticket_id", "sales_date", "source", "plan_type", "selections",
    "total_stake", "payout", "result", "settlement_status",
}
SETTLED_RESULTS = {"win", "loss", "push"}


def audit(frame: pd.DataFrame) -> dict[str, object]:
    missing_columns = sorted(REQUIRED - set(frame.columns))
    if missing_columns:
        return {"ok": False, "missing_columns": missing_columns, "promotion_eligible": False}
    result = frame["result"].astype(str).str.strip().str.lower()
    settled = frame["settlement_status"].astype(str).str.strip().str.lower().eq("settled")
    settled_result = result[settled & result.isin(SETTLED_RESULTS)]
    wins = int(settled_result.eq("win").sum())
    losses = int(settled_result.eq("loss").sum())
    pushes = int(settled_result.eq("push").sum())
    one_sided = bool(wins > 0 and losses == 0) or bool(losses > 0 and wins == 0)
    duplicate_ids = int(frame["ticket_id"].astype(str).duplicated(keep=False).sum())
    return {
        "ok": duplicate_ids == 0,
        "rows": int(len(frame)),
        "settled_rows": int(len(settled_result)),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "one_sided_sample": one_sided,
        "duplicate_ticket_id_rows": duplicate_ids,
        "promotion_eligible": bool(wins > 0 and losses > 0 and duplicate_ids == 0),
        "warning": "当前样本只有单侧赛果，存在幸存者偏差，禁止据此提升为生产策略。" if one_sided else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit external betting-ticket samples for survivorship bias.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    input_path = root / args.input
    frame = pd.read_csv(input_path).fillna("")
    payload = audit(frame)
    output_path = root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
