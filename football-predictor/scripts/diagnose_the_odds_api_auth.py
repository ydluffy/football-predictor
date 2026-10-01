"""Check The Odds API authentication without spending odds-query credits.

Only sanitized status, provider error code, and quota headers are printed.
Never log request URLs or exception messages because they contain the API key.
"""

import os
import sys
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data.the_odds_sporttery import load_project_env  # noqa: E402


def main() -> int:
    load_project_env()
    key = os.getenv("THE_ODDS_API_KEY", "")
    if not key:
        print("status=not_configured")
        return 1

    try:
        response = requests.get(
            "https://api.the-odds-api.com/v4/sports/",
            params={"apiKey": key},
            timeout=12,
        )
    except requests.RequestException as exc:
        print(f"status=network_error error_type={type(exc).__name__}")
        return 2

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    error_code = payload.get("error_code", "") if isinstance(payload, dict) else ""
    print(f"http_status={response.status_code}")
    print(f"error_code={error_code}")
    for name in ("x-requests-remaining", "x-requests-used", "x-requests-last"):
        print(f"{name}={response.headers.get(name, '')}")
    return 0 if response.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
