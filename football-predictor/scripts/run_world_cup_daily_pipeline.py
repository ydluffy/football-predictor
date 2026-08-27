from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.daily_pipeline import run_daily_pipeline, write_pipeline_audit


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--refresh-espn", choices=["true", "false"], default="false")
    parser.add_argument("--download-leisu", choices=["true", "false"], default="false")
    parser.add_argument("--refresh-sporttery", choices=["true", "false"], default="false")
    parser.add_argument(
        "--sporttery-date",
        default="",
        help="Date used to filter lottery.gov.cn rows. Useful for cross-midnight fixtures.",
    )
    parser.add_argument("--sporttery-channel", default="chrome")
    parser.add_argument("--sporttery-timeout", type=int, default=60000)
    parser.add_argument("--dry-run", choices=["true", "false"], default="false")
    parser.add_argument("--node", default="node")
    parser.add_argument(
        "--sporttery-markets",
        default="",
        help="Optional China Sports Lottery handicap market CSV for official handicap lines.",
    )
    parser.add_argument("--structured-intelligence", default="")
    parser.add_argument("--absences", default="")
    parser.add_argument("--realtime-lineups", default="")
    parser.add_argument(
        "--sporttery-min-coverage",
        type=float,
        default=0.8,
        help="Minimum Sporttery handicap coverage required by the quality gate.",
    )
    parser.add_argument(
        "--sporttery-quality-mode",
        choices=["warn", "fail", "off"],
        default="warn",
        help="warn records low coverage, fail stops the pipeline, off disables the gate.",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/pipeline/world_cup_daily_pipeline.json",
    )
    args = parser.parse_args()

    audit = run_daily_pipeline(
        root=_ROOT,
        as_of_date=args.as_of_date,
        python_executable=sys.executable,
        node_executable=args.node,
        refresh_espn=args.refresh_espn == "true",
        download_leisu=args.download_leisu == "true",
        refresh_sporttery=args.refresh_sporttery == "true",
        sporttery_date=args.sporttery_date or None,
        sporttery_channel=args.sporttery_channel,
        sporttery_timeout=args.sporttery_timeout,
        sporttery_markets=args.sporttery_markets or None,
        structured_intelligence=args.structured_intelligence or None,
        absences=args.absences or None,
        realtime_lineups=args.realtime_lineups or None,
        sporttery_min_coverage=args.sporttery_min_coverage,
        sporttery_quality_mode=args.sporttery_quality_mode,
        dry_run=args.dry_run == "true",
    )
    audit["as_of_date"] = args.as_of_date
    audit["refresh_espn"] = args.refresh_espn == "true"
    audit["download_leisu"] = args.download_leisu == "true"
    audit["refresh_sporttery"] = args.refresh_sporttery == "true"
    audit["sporttery_date"] = args.sporttery_date
    audit["sporttery_markets"] = args.sporttery_markets
    audit["structured_intelligence"] = args.structured_intelligence
    audit["absences"] = args.absences
    audit["realtime_lineups"] = args.realtime_lineups
    audit["sporttery_min_coverage"] = args.sporttery_min_coverage
    audit["sporttery_quality_mode"] = args.sporttery_quality_mode
    write_pipeline_audit(audit, _ROOT / args.audit_output)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    raise SystemExit(0 if audit["ok"] else 1)


if __name__ == "__main__":
    main()
