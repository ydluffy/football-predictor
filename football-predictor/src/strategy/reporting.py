from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def write_backtest_outputs(*, out_dir: Path, bets: pd.DataFrame, summary: dict[str, Any], by_league: pd.DataFrame, equity_curve: pd.DataFrame) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    bets_path = out_dir / "bets.csv"
    summary_path = out_dir / "summary.json"
    by_league_path = out_dir / "by_league.csv"
    curve_path = out_dir / "equity_curve.csv"

    bets.to_csv(bets_path, index=False)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    by_league.to_csv(by_league_path, index=False)
    equity_curve.to_csv(curve_path, index=False)

    return {
        "bets_path": str(bets_path),
        "summary_path": str(summary_path),
        "by_league_path": str(by_league_path),
        "equity_curve_path": str(curve_path),
    }

