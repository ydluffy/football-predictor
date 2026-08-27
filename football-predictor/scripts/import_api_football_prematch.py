from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.api_football_prematch import (  # noqa: E402
    api_football_frames_to_prematch_intelligence,
    append_validated_prematch_intelligence,
    build_api_football_match_mapping,
)
from world_cup.api_football_adapter import import_api_football_realtime  # noqa: E402


def local_env_value(key: str) -> str:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return ""
    prefix = f"{key}="
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Import mapped API-Football prematch lineups and absences")
    parser.add_argument("--league-id", type=int, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--date", default="")
    parser.add_argument("--mapping", default="")
    parser.add_argument("--scan-json", default="")
    parser.add_argument("--mapping-output", default="artifacts/data/api_football_match_mapping_latest.csv")
    parser.add_argument("--observed-at", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--raw-output-dir", default="data/external/api_football_prematch")
    parser.add_argument("--manual-output", default="data/manual/prematch_intelligence.csv")
    parser.add_argument("--validated-output", default="data/processed/prematch_intelligence_validated.csv")
    parser.add_argument("--audit-output", default="artifacts/data/api_football_prematch_import_latest.json")
    args = parser.parse_args()

    observed_at = args.observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    raw_dir = project_path(args.raw_output_dir)
    raw_audit = import_api_football_realtime(
        output_dir=raw_dir,
        league_id=args.league_id,
        season=args.season,
        date=args.date or None,
        api_key=(
            args.api_key
            or os.getenv("API_FOOTBALL_KEY", "")
            or local_env_value("API_FOOTBALL_KEY")
        ),
        timeout=args.timeout,
    )
    payload: dict[str, object] = {"source": "api_football", "raw_import": raw_audit}
    if raw_audit.get("status") == "skipped":
        payload.update({"status": "skipped", "reason": raw_audit.get("reason"), "write_performed": False})
    else:
        fixtures = pd.read_csv(raw_dir / "fixtures.csv", low_memory=False)
        mapping_audit: dict[str, object] = {"mode": "provided"}
        if args.mapping:
            mapping = pd.read_csv(project_path(args.mapping), low_memory=False)
        elif args.scan_json:
            scan = json.loads(project_path(args.scan_json).read_text(encoding="utf-8"))
            mapping, auto_audit = build_api_football_match_mapping(
                pd.DataFrame(scan.get("fixtures", [])),
                fixtures,
            )
            mapping_output = project_path(args.mapping_output)
            mapping_output.parent.mkdir(parents=True, exist_ok=True)
            mapping.to_csv(mapping_output, index=False)
            mapping_audit = {"mode": "automatic", **auto_audit, "output": str(mapping_output)}
        else:
            raise SystemExit("configured API-Football import requires --mapping or --scan-json")
        converted, conversion_audit = api_football_frames_to_prematch_intelligence(
            fixtures=fixtures,
            absences=pd.read_csv(raw_dir / "absences.csv", low_memory=False),
            lineups=pd.read_csv(raw_dir / "realtime_lineups.csv", low_memory=False),
            mapping=mapping,
            observed_at=observed_at,
        )
        write_audit = append_validated_prematch_intelligence(
            converted,
            manual_path=project_path(args.manual_output),
            validated_path=project_path(args.validated_output),
        )
        payload.update(
            {
                "status": "ok" if not raw_audit.get("failed") else "partial",
                "observed_at": observed_at,
                "conversion": conversion_audit,
                "mapping": mapping_audit,
                "validation": write_audit,
                "write_performed": bool(len(converted)),
            }
        )
    audit_output = project_path(args.audit_output)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
