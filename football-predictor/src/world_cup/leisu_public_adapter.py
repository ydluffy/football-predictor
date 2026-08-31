from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from world_cup.data_source_audit import audit_source_frame


LEISU_HOME_URL = "https://www.leisu.com/"


def fetch_leisu_home(destination: str | Path, *, timeout: int = 60) -> str:
    response = requests.get(
        LEISU_HOME_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = "utf-8"
    text = response.text
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def parse_leisu_home_matches(html: str, *, fetched_at: str | None = None) -> pd.DataFrame:
    rows = []
    timestamp = fetched_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    for block in re.findall(r'<div class="match-lier">(.+?)(?=<div class="match-lier">|</body>|$)', html, flags=re.S):
        match = re.search(r"live\.leisu\.com/detail-(\d+)", block)
        if not match:
            continue
        names = re.findall(r'<span class="name">([^<]+)</span>', block)
        if len(names) < 2:
            continue
        event = re.search(
            r'<a class="link" href="https://www\.leisu\.com/data/zuqiu/comp-\d+" target="_blank">([^<]+)</a>',
            block,
        )
        time_match = re.search(
            r'<span class="timecolor">([^<]+)</span>\s*<span>([^<]+)</span>',
            block,
        )
        info_count = re.search(r"(?:情报|æƒ…æŠ¥)\s*(\d+)", block)
        rows.append(
            {
                "source": "leisu_public_html",
                "fetched_at": timestamp,
                "leisu_match_id": match.group(1),
                "competition": event.group(1) if event else "",
                "date_text": time_match.group(2) if time_match else "",
                "time_text": time_match.group(1) if time_match else "",
                "home_team_zh": names[0],
                "away_team_zh": names[1],
                "detail_url": f"https://live.leisu.com/detail-{match.group(1)}",
                "analysis_url": f"https://live.leisu.com/shujufenxi-{match.group(1)}",
                "intelligence_url": f"https://www.leisu.com/guide/swot-{match.group(1)}",
                "intelligence_count": int(info_count.group(1)) if info_count else 0,
            }
        )
    return pd.DataFrame(rows).drop_duplicates("leisu_match_id")


def import_leisu_home_matches(
    *,
    cache_path: str | Path,
    output_path: str | Path,
    download: bool = True,
    fetch_method: str = "http",
) -> dict[str, object]:
    if download:
        html = fetch_leisu_home(cache_path)
    else:
        html = Path(cache_path).read_text(encoding="utf-8")
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    matches = parse_leisu_home_matches(html, fetched_at=fetched_at)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    matches.to_csv(output, index=False)
    world_cup = matches[
        matches["competition"].astype(str).str.contains("世界杯|ä¸–ç•Œæ¯", na=False)
    ]
    audit: dict[str, object] = {
        "source": "leisu_public_html",
        "fetched_at": fetched_at,
        "fetch_method": fetch_method,
        "matches": int(len(matches)),
        "world_cup_matches": int(len(world_cup)),
        "output": str(output),
        "detail_pages_blocked": True,
    }
    audit["source_audit"] = audit_source_frame(
        "leisu_public",
        matches,
        fetched_at=fetched_at,
        output_path=output,
        extra={
            "cache_path": str(cache_path),
            "fetch_method": fetch_method,
            "world_cup_matches": int(len(world_cup)),
        },
    )
    return audit
