from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data.sporttery_snapshot_archive import archive_sporttery_scan_inputs  # noqa: E402


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive an existing Sporttery scan as immutable inputs")
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--official-markets", default="")
    parser.add_argument("--play-odds", default="")
    parser.add_argument("--archive-root", default="data/external/sporttery/snapshots")
    parser.add_argument("--index", default="data/manual/sporttery_snapshot_index.csv")
    args = parser.parse_args()

    scan = json.loads(project_path(args.scan_json).read_text(encoding="utf-8"))
    sources = scan.get("sources", {})
    official = args.official_markets or sources.get("official_markets", "")
    plays = args.play_odds or sources.get("play_odds", "")
    if not official or not plays:
        raise SystemExit("scan JSON does not contain official_markets/play_odds; pass them explicitly")
    metadata = archive_sporttery_scan_inputs(
        official_markets_path=project_path(official),
        play_odds_path=project_path(plays),
        scan=scan,
        archive_root=project_path(args.archive_root),
        index_path=project_path(args.index),
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
