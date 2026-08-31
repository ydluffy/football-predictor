from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from world_cup.leisu_public_adapter import import_leisu_home_matches


def _fetch_with_browser(args: argparse.Namespace) -> dict[str, object]:
    command = [
        "node",
        str(_ROOT / "scripts" / "fetch_leisu_public.mjs"),
        "--output",
        str(_ROOT / args.cache),
        "--channel",
        args.channel,
        "--timeout",
        str(args.timeout),
        "--wait-text",
        args.wait_text,
    ]
    if args.screenshot:
        command.extend(["--screenshot", str(_ROOT / args.screenshot)])
    if args.headful:
        command.append("--headful")
    proc = subprocess.run(command, cwd=_ROOT, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(
            "leisu browser fetch failed\n"
            f"command: {' '.join(command)}\n"
            f"stdout: {proc.stdout}\n"
            f"stderr: {proc.stderr}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": True, "stdout": proc.stdout.strip()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", choices=["true", "false"], default="true")
    parser.add_argument(
        "--method",
        choices=["http", "browser", "cache"],
        default="http",
        help="http uses requests, browser uses Playwright rendering, cache parses --cache only.",
    )
    parser.add_argument(
        "--cache",
        default="data/external/leisu_home.html",
    )
    parser.add_argument(
        "--output",
        default="data/external/leisu_public_matches.csv",
    )
    parser.add_argument(
        "--audit-output",
        default="artifacts/data/leisu_public_import.json",
    )
    parser.add_argument("--channel", default="chrome")
    parser.add_argument("--timeout", type=int, default=60000)
    parser.add_argument("--wait-text", default="情报")
    parser.add_argument("--screenshot", default="")
    parser.add_argument("--headful", action="store_true")
    args = parser.parse_args()
    browser_fetch = None
    download = args.download == "true"
    method = args.method
    if method == "cache":
        download = False
    elif method == "browser" and download:
        browser_fetch = _fetch_with_browser(args)
        download = False
    audit = import_leisu_home_matches(
        cache_path=_ROOT / args.cache,
        output_path=_ROOT / args.output,
        download=download,
        fetch_method=method,
    )
    if browser_fetch is not None:
        audit["browser_fetch"] = browser_fetch
    audit_path = _ROOT / args.audit_output
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
