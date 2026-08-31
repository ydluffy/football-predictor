from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.market_research import (  # noqa: E402
    build_market_research_from_files,
    render_market_research_report,
    summarize_market_research,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a Sporttery and external market research dataset.",
    )
    parser.add_argument(
        "--predictions",
        required=True,
        help="Prediction CSV with model, Sporttery and external market columns.",
    )
    parser.add_argument(
        "--results",
        required=True,
        help="Fixture/results CSV with match_id, scores and status.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path for the market research dataset.",
    )
    parser.add_argument(
        "--report-output",
        required=True,
        help="Output Markdown path for the Chinese research report.",
    )
    args = parser.parse_args()

    dataset = build_market_research_from_files(
        predictions_path=args.predictions,
        results_path=args.results,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output, index=False, encoding="utf-8-sig")

    summary = summarize_market_research(dataset)
    report = render_market_research_report(dataset, summary)
    report_output = Path(args.report_output)
    report_output.parent.mkdir(parents=True, exist_ok=True)
    report_output.write_text(report, encoding="utf-8")

    print(f"Wrote market research dataset: {output}")
    print(f"Wrote market research report: {report_output}")
    print(f"Finished samples: {summary.finished_rows}/{summary.rows}")


if __name__ == "__main__":
    main()
