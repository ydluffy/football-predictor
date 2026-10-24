"""Import reviewed web extractions as pending evidence, not approved profiles."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from data.entity_archive import connect
from data.official_player_evidence import import_official_evidence


def main():
    path = ROOT / "config/player_official_evidence.json"
    content = path.read_bytes()
    data = json.loads(content)
    db = connect(ROOT / "data/processed/entity_archive.sqlite3")
    try:
        count = import_official_evidence(db, data["players"], {
            "path": str(path), "sha256": hashlib.sha256(content).hexdigest(),
            "observed_at": data["checked_on"] + "T00:00:00+08:00"})
        print(json.dumps({"evidence_rows_processed": count, "profiles_overwritten": 0,
                          "bindings_approved": 0, "timestamp_precision": "day"}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
