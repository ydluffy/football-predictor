from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from data.openfootball_japan import (  # noqa: E402
    build_openfootball_japan_context_dataset,
    download_openfootball_japan_j1,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import licensed OpenFootball J1 context data")
    parser.add_argument("--years", default="2019,2020,2021,2022,2023,2024,2025")
    parser.add_argument("--download", choices=["true", "false"], default="false")
    parser.add_argument("--input-dir", default="data/external/openfootball-japan")
    parser.add_argument("--output-path", default="data/processed/j1_openfootball_context.csv")
    parser.add_argument("--audit-path", default="artifacts/data/j1_openfootball_import_latest.json")
    parser.add_argument("--policy-path", default="config/east_asia_data_sources.json")
    args = parser.parse_args()

    years = [int(value.strip()) for value in args.years.split(",") if value.strip()]
    failures: list[dict[str, object]] = []
    if args.download == "true":
        downloaded, failures = download_openfootball_japan_j1(
            output_dir=_ROOT / args.input_dir,
            years=years,
            policy_path=_ROOT / args.policy_path,
        )
        print(f"downloaded_files={len(downloaded)}")
        print(f"download_failures={len(failures)}")

    frame, audit = build_openfootball_japan_context_dataset(
        input_dir=_ROOT / args.input_dir,
        output_path=_ROOT / args.output_path,
        audit_path=_ROOT / args.audit_path,
        policy_path=_ROOT / args.policy_path,
        download_failures=failures,
    )
    print(f"context_rows={len(frame)}")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
