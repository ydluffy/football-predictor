"""Reapply corrected mappings without spending quota or modifying production data."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data.api_football_daily_intelligence import collect_api_football_daily_intelligence
from data.api_football_recovery import ArchivedApiFootballClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--audit-json", required=True)
    parser.add_argument("--output-dir", required=True, help="New isolated directory; must not exist")
    args = parser.parse_args()
    audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8-sig"))
    scan = json.loads(Path(args.scan_json).read_text(encoding="utf-8-sig"))
    client = ArchivedApiFootballClient(audit)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    rows, mapping, result = collect_api_football_daily_intelligence(
        client=client, scan_fixtures=pd.DataFrame(scan["fixtures"]),
        date=audit["fixture_dates"][0], observed_at=audit["observed_at"],
        raw_root=output / "raw", include_lineups=True,
        include_schedule_load=bool(audit.get("schedule_dates")),
        schedule_days=len(audit.get("schedule_dates") or []) or 7,
    )
    result.update(replay=True, network_requests=0, production_written=False,
                  original_audit=str(Path(args.audit_json).resolve()))
    rows.to_csv(output / "recovered_candidates.csv", index=False)
    mapping.to_csv(output / "mapping.csv", index=False)
    (output / "audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "mapping": result["mapping"],
                      "converted_rows": len(rows), "failures": result["failures"]}, ensure_ascii=True))


if __name__ == "__main__":
    main()
