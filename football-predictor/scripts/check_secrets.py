from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXCLUDED_FILES = r"(^|/)(package-lock\.json|requirements\.txt)$"


def _scanner_path() -> Path:
    executable_name = "detect-secrets.exe" if os.name == "nt" else "detect-secrets"
    return Path(sys.executable).resolve().parent / executable_name


def main() -> int:
    scanner = _scanner_path()
    if not scanner.exists():
        print("detect-secrets is not installed; install the Python dev dependencies.", file=sys.stderr)
        return 2

    completed = subprocess.run(
        [
            str(scanner),
            "scan",
            "--no-verify",
            "--exclude-files",
            _EXCLUDED_FILES,
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        print(completed.stderr or completed.stdout, file=sys.stderr)
        return completed.returncode

    report: dict[str, Any] = json.loads(completed.stdout)
    findings = report.get("results", {})
    if not findings:
        print("Secret scan passed (tracked files, generated lock files excluded).")
        return 0

    print("Potential secrets detected:", file=sys.stderr)
    for filename, matches in sorted(findings.items()):
        for match in matches:
            print(
                f"- {filename}:{match.get('line_number')} {match.get('type')}",
                file=sys.stderr,
            )
    print("Remove the secret or annotate a verified test value with an allowlist pragma.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
