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

from strategy.shadow_portfolio_v2 import ShadowPortfolioPolicy, build_shadow_portfolio  # noqa: E402


def _path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a v2 shadow-only betting portfolio")
    parser.add_argument("--config", default="config/shadow_v2.json")
    parser.add_argument("--candidates-csv", required=True)
    parser.add_argument("--budget", type=float, default=None)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    args = parser.parse_args()

    config = json.loads(_path(args.config).read_text(encoding="utf-8"))
    portfolio_config = dict(config["portfolio"])
    if args.budget is not None:
        portfolio_config["budget"] = args.budget
    candidates = pd.read_csv(_path(args.candidates_csv), low_memory=False)
    portfolio, audit = build_shadow_portfolio(candidates, ShadowPortfolioPolicy(**portfolio_config))
    audit["config_path"] = str(_path(args.config))
    output = _path(args.output)
    audit_output = _path(args.audit_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    portfolio.to_csv(output, index=False, encoding="utf-8-sig")
    audit_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
