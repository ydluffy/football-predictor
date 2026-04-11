from __future__ import annotations

import argparse
import json
from pathlib import Path

from football_predictor.pipeline.phase1 import run_phase1
from football_predictor.settings import Settings


def main() -> None:
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(prog="football-predictor")
    parser.add_argument(
        "--data",
        type=str,
        default=str(settings.data_dir / "sample_matches.csv"),
    )
    args = parser.parse_args()

    result = run_phase1(data_path=Path(args.data), settings=settings)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
