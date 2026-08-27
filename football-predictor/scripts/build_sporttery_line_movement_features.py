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

from world_cup.sporttery_markets import build_sporttery_line_movement_features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history",
        default="data/manual/sporttery_handicap_market_history.csv",
    )
    parser.add_argument(
        "--output",
        default="data/manual/sporttery_handicap_line_movement_features.csv",
    )
    args = parser.parse_args()

    history_path = _ROOT / args.history
    if history_path.exists():
        history = pd.read_csv(history_path)
    else:
        history = pd.DataFrame()
    movement = build_sporttery_line_movement_features(history)
    output_path = _ROOT / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    movement.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(
        json.dumps(
            {
                "history": str(history_path),
                "output": str(output_path),
                "matches": int(len(movement)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
