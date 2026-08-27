from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.sporttery_markets import append_sporttery_market_history
from world_cup.sporttery_markets import parse_lottery_gov_spf_text
from world_cup.data_source_audit import audit_source_frame


def _run_fetcher(args: argparse.Namespace, raw_output: Path) -> dict[str, object]:
    command = [
        "node",
        str(_ROOT / "scripts" / "fetch_lottery_gov_spf.mjs"),
        "--url",
        args.url,
        "--output",
        str(raw_output),
        "--channel",
        args.channel,
        "--timeout",
        str(args.timeout),
    ]
    if args.wait_text:
        command.extend(["--wait-text", args.wait_text])
    else:
        command.append("--no-wait-text")
    if args.screenshot:
        command.extend(["--screenshot", str(Path(args.screenshot))])
    if args.headful:
        command.append("--headful")
    proc = subprocess.run(
        command,
        cwd=_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "lottery.gov.cn browser fetch failed\n"
            f"command: {' '.join(command)}\n"
            f"stdout: {proc.stdout}\n"
            f"stderr: {proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": proc.stdout.strip()}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch rendered lottery.gov.cn SPF page and convert it to Sporttery market CSV."
    )
    parser.add_argument("--date", default="", help="Optional match date filter, e.g. 2026-06-26.")
    parser.add_argument("--url", default="https://www.lottery.gov.cn/jc/jsq/zqspf/")
    parser.add_argument("--channel", default="chrome", help="chrome, msedge, or empty string for bundled chromium.")
    parser.add_argument("--timeout", type=int, default=60000)
    parser.add_argument("--wait-text", default="世界杯")
    parser.add_argument("--no-wait-text", action="store_true", help="Do not wait for a page-ready text marker.")
    parser.add_argument(
        "--raw-output",
        default=str(_ROOT / "data" / "external" / "lottery_gov_zqspf_rendered.txt"),
    )
    parser.add_argument("--output", default="", help="CSV output path. Defaults by --date.")
    parser.add_argument("--screenshot", default="", help="Optional page screenshot for diagnostics.")
    parser.add_argument("--updated-at", default="", help="Optional captured timestamp stored in CSV.")
    parser.add_argument(
        "--append-history",
        choices=["true", "false"],
        default="false",
        help="Append parsed rows to sporttery_handicap_market_history.csv.",
    )
    parser.add_argument(
        "--history-output",
        default=str(_ROOT / "data" / "manual" / "sporttery_handicap_market_history.csv"),
    )
    parser.add_argument("--snapshot-type", default="latest")
    parser.add_argument("--captured-at", default="")
    parser.add_argument(
        "--audit-output",
        default="",
        help="Optional JSON audit output. Defaults to artifacts/data/sporttery_lottery_gov_import_DATE.json.",
    )
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()
    if args.no_wait_text:
        args.wait_text = ""

    raw_output = Path(args.raw_output)
    fetch_summary = _run_fetcher(args, raw_output)
    frame = parse_lottery_gov_spf_text(
        raw_output.read_text(encoding="utf-8"),
        updated_at=args.updated_at,
    )
    if args.date:
        run_date = str(pd.Timestamp(args.date).date())
        frame = frame[frame["date"] == run_date].copy()
    else:
        run_date = ""
    output = (
        Path(args.output)
        if args.output
        else (
            _ROOT / "data" / "manual" / f"sporttery_handicap_markets_{run_date}.csv"
            if run_date
            else _ROOT / "data" / "manual" / "lottery_gov_spf_markets.csv"
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    history_count = None
    if args.append_history == "true":
        history = append_sporttery_market_history(
            args.history_output,
            frame,
            snapshot_type=args.snapshot_type,
            captured_at=args.captured_at,
        )
        history_count = int(len(history))
    audit = {
        "ok": True,
        "fetch": fetch_summary,
        "raw_output": str(raw_output),
        "rows": int(len(frame)),
        "date": args.date or "",
        "output": str(output),
        "history_output": args.history_output if args.append_history == "true" else "",
        "history_count": history_count,
    }
    audit["source_audit"] = audit_source_frame(
        "sporttery_lottery_gov",
        frame,
        fetched_at=args.captured_at or args.updated_at or None,
        output_path=output,
        extra={
            "raw_output": str(raw_output),
            "history_output": args.history_output if args.append_history == "true" else "",
            "history_count": history_count,
            "browser_fetch": fetch_summary,
        },
    )
    audit_output = (
        Path(args.audit_output)
        if args.audit_output
        else _ROOT
        / "artifacts"
        / "data"
        / f"sporttery_lottery_gov_import_{run_date or 'latest'}.json"
    )
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
