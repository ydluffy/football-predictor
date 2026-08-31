from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from data.historical_dataset import (
    DEFAULT_DIVISIONS,
    build_historical_dataset,
    download_football_data_files,
    load_division_profile,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", default="2020-21,2021-22,2022-23,2023-24,2024-25,2025-26")
    parser.add_argument("--divisions", default=",".join(DEFAULT_DIVISIONS))
    parser.add_argument("--profile", default="", help="Named profile from config/historical_data_sources.json")
    parser.add_argument("--source-config", default="config/historical_data_sources.json")
    parser.add_argument("--download", choices=["true", "false"], default="false")
    parser.add_argument("--input-dir", default="data/external/football-data")
    parser.add_argument("--mapping-path", default="data/mappings/football_data_mapping.json")
    parser.add_argument("--output-path", default="data/processed/historical_matches_trainable.csv")
    parser.add_argument("--audit-path", default="artifacts/eval/historical_dataset_audit.json")
    args = parser.parse_args()

    seasons = [x.strip() for x in args.seasons.split(",") if x.strip()]
    divisions = (
        list(load_division_profile(args.profile, config_path=_ROOT / args.source_config))
        if args.profile
        else [x.strip() for x in args.divisions.split(",") if x.strip()]
    )
    if args.download == "true":
        downloaded = download_football_data_files(
            output_dir=_ROOT / args.input_dir,
            seasons=seasons,
            divisions=divisions,
        )
        print(f"downloaded_files={len(downloaded)}")

    df, audit = build_historical_dataset(
        input_dir=_ROOT / args.input_dir,
        mapping_path=_ROOT / args.mapping_path,
        output_path=_ROOT / args.output_path,
        audit_path=_ROOT / args.audit_path,
        divisions=divisions,
    )
    print(f"trainable_rows={len(df)}")
    print(audit)


if __name__ == "__main__":
    main()
