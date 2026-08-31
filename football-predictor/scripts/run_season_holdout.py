from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from evaluate.season_holdout import run_season_holdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-path", default="data/processed/historical_matches_trainable.csv")
    parser.add_argument("--feature-version", choices=["v1", "v4", "v5", "v6", "v7", "v8"], default="v1")
    parser.add_argument("--model-type", choices=["logit", "lightgbm"], default="logit")
    parser.add_argument("--min-train-seasons", type=int, default=2)
    parser.add_argument("--output-path", default="artifacts/eval/season_holdout.csv")
    args = parser.parse_args()

    df = pd.read_csv(_ROOT / args.data_path, low_memory=False)
    out = run_season_holdout(
        df,
        feature_version=args.feature_version,
        model_type=args.model_type,
        min_train_seasons=args.min_train_seasons,
    )
    output = _ROOT / args.output_path
    output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(output, index=False)
    print(str(output))
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
