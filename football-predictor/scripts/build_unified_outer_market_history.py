from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data.unified_outer_market_history import build_unified_histories  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unified API-Football and The Odds API histories")
    parser.add_argument("--api-football-history", default="data/external/api_football_odds/history.csv")
    parser.add_argument("--the-odds-root", default="data/external/the_odds_api_sporttery/snapshots")
    parser.add_argument("--outer-output", default="data/external/outer_market_snapshots/history.csv")
    parser.add_argument("--model-output", default="data/manual/external_market_snapshot_history.csv")
    parser.add_argument("--audit-output", default="artifacts/data/unified_outer_market_history_latest.json")
    args = parser.parse_args()
    outer, model, audit = build_unified_histories(
        api_football_history=_path(args.api_football_history),
        the_odds_snapshot_root=_path(args.the_odds_root),
    )
    outer_path = _path(args.outer_output); model_path = _path(args.model_output); audit_path = _path(args.audit_output)
    for path in (outer_path, model_path, audit_path): path.parent.mkdir(parents=True, exist_ok=True)
    outer.to_csv(outer_path, index=False, encoding="utf-8-sig")
    model.to_csv(model_path, index=False, encoding="utf-8-sig")
    audit.update({"outer_output": str(outer_path), "model_output": str(model_path)})
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
