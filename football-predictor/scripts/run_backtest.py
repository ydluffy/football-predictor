from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from config.settings import ensure_project_dirs, get_settings
from strategy.backtest import BacktestConfig, run_backtest
from strategy.reporting import write_backtest_outputs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-path", default="artifacts/eval/results.csv")
    parser.add_argument("--data-path", default="data/processed/real_matches_standardized.csv")
    parser.add_argument("--out-dir", default="artifacts/backtest")
    args = parser.parse_args()

    ensure_project_dirs()
    s = get_settings()

    pred_p = Path(str(args.pred_path))
    if not pred_p.is_absolute():
        pred_p = (s.project_root / pred_p).resolve()
    if not pred_p.exists():
        raise FileNotFoundError(str(pred_p))

    data_p = Path(str(args.data_path))
    if not data_p.is_absolute():
        data_p = (s.project_root / data_p).resolve()
    if not data_p.exists():
        raise FileNotFoundError(str(data_p))

    out_dir = Path(str(args.out_dir))
    if not out_dir.is_absolute():
        out_dir = (s.project_root / out_dir).resolve()

    pred_df = pd.read_csv(pred_p)
    matches_df = pd.read_csv(data_p)

    cfg = BacktestConfig()
    out = run_backtest(pred_df=pred_df, matches_df=matches_df, cfg=cfg)
    paths = write_backtest_outputs(out_dir=out_dir, bets=out["bets"], summary=out["summary"], by_league=out["by_league"], equity_curve=out["equity_curve"])

    print(json.dumps({"summary": out["summary"], "paths": paths}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

