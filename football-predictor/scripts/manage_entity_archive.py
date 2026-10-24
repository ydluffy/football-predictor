"""Import archived API data into a local identity catalog, or inspect its review queue."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from data.entity_archive import connect, ingest, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="data/processed/entity_archive.sqlite3")
    commands = parser.add_subparsers(dest="command", required=True)
    imp = commands.add_parser("import")
    imp.add_argument("--audit-json", required=True)
    imp.add_argument("--mapping-csv", required=True, help="Reviewed/replayed source fixture mapping")
    commands.add_parser("status")
    commands.add_parser("reviews")
    review = commands.add_parser("review")
    review.add_argument("--id", required=True)
    review.add_argument("--decision", choices=["acknowledged", "rejected"], required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    args = parser.parse_args()
    db = connect(args.database)
    try:
        if args.command == "import":
            import csv
            with open(args.mapping_csv, encoding="utf-8-sig", newline="") as stream:
                ids = [row["source_fixture_id"] for row in csv.DictReader(stream)]
            audit = json.loads(Path(args.audit_json).read_text(encoding="utf-8-sig"))
            ingest(db, audit, ids)
        elif args.command == "reviews":
            db.row_factory = __import__("sqlite3").Row
            print(json.dumps([dict(r) for r in db.execute("SELECT * FROM reviews WHERE status='pending' ORDER BY entity_id,id")], ensure_ascii=True))
            return
        elif args.command == "review":
            if not args.note.strip() or not args.reviewer.strip():
                parser.error("reviewer and evidence note cannot be blank")
            with db:
                cursor = db.execute("UPDATE reviews SET status=?,reviewer=?,note=?,reviewed_at=? WHERE id=? AND status='pending'",
                    (args.decision, args.reviewer, args.note, datetime.now(timezone.utc).isoformat(), args.id))
                if cursor.rowcount != 1:
                    raise ValueError("review missing or already resolved")
        print(json.dumps(report(db), ensure_ascii=True))
    finally:
        db.close()


if __name__ == "__main__":
    main()
