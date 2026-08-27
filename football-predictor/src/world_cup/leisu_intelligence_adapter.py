from __future__ import annotations

import re
from html import unescape
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


KEYWORD_RULES: list[tuple[str, float, tuple[str, ...]]] = [
    ("injury", 2.0, ("伤", "伤病", "受伤", "缺阵", "injury", "injured", "doubtful", "out")),
    ("suspension", 2.0, ("停赛", "红牌", "禁赛", "suspend", "suspended", "red card")),
    ("lineup", 1.5, ("首发", "阵容", "轮换", "替补", "lineup", "starting", "rotation")),
    ("tactical", 1.0, ("战术", "防守", "进攻", "控球", "高压", "反击", "tactical", "pressing")),
    ("motivation", 1.0, ("出线", "晋级", "战意", "必须取胜", "motivation", "qualify")),
    ("schedule", 1.0, ("赛程", "休息", "体能", "连续", "travel", "rest", "fatigue")),
    ("form", 1.0, ("状态", "近况", "连胜", "不胜", "form", "recent")),
    ("weather", 0.8, ("天气", "高温", "下雨", "湿度", "weather", "rain", "heat")),
]


def fetch_leisu_intelligence_page(url: str, destination: str | Path, *, timeout: int = 60) -> str:
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    html = response.text
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return html


def html_to_lines(html: str) -> list[str]:
    text = re.sub(r"(?is)<(script|style|noscript|svg).*?>.*?</\1>", "\n", html or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|section|article|tr|h\d)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if len(line) < 4:
            continue
        if line in {"雷速体育", "足球", "篮球", "情报"}:
            continue
        lines.append(line)
    return lines


def classify_intelligence_line(text: str) -> tuple[str, float] | None:
    normalized = text.casefold()
    for category, severity, keywords in KEYWORD_RULES:
        if any(keyword.casefold() in normalized for keyword in keywords):
            return category, severity
    return None


def infer_team_from_text(
    text: str,
    *,
    home_team: str,
    away_team: str,
    home_team_zh: str = "",
    away_team_zh: str = "",
) -> str:
    candidates = [
        (home_team, home_team),
        (away_team, away_team),
        (home_team_zh, home_team),
        (away_team_zh, away_team),
    ]
    for needle, team in candidates:
        if needle and str(needle) in text:
            return str(team)
    return ""


def parse_leisu_intelligence_html(
    html: str,
    *,
    match_id: object,
    home_team: str,
    away_team: str,
    url: str,
    home_team_zh: str = "",
    away_team_zh: str = "",
    updated_at: str | None = None,
) -> pd.DataFrame:
    timestamp = updated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for line in html_to_lines(html):
        classified = classify_intelligence_line(line)
        if classified is None:
            continue
        category, severity = classified
        key = (category, line)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "match_id": str(match_id).replace(".0", ""),
                "team": infer_team_from_text(
                    line,
                    home_team=home_team,
                    away_team=away_team,
                    home_team_zh=home_team_zh,
                    away_team_zh=away_team_zh,
                ),
                "category": category,
                "severity": severity,
                "text": line,
                "source": "leisu_intelligence_page",
                "url": url,
                "updated_at": timestamp,
            }
        )
    return pd.DataFrame(
        rows,
        columns=[
            "match_id",
            "team",
            "category",
            "severity",
            "text",
            "source",
            "url",
            "updated_at",
        ],
    )


def import_leisu_intelligence_pages(
    *,
    leisu_features_path: str | Path,
    output_path: str | Path,
    cache_dir: str | Path,
    download: bool = True,
    limit: int = 0,
) -> dict[str, object]:
    features = pd.read_csv(leisu_features_path, dtype={"leisu_match_id": str}).fillna("")
    candidates = features[
        features.get("leisu_public_match_linked", 0).astype(str).isin({"1", "1.0", "true", "True"})
        & features.get("leisu_intelligence_url", "").astype(str).str.strip().ne("")
    ].copy()
    if limit > 0:
        candidates = candidates.head(limit)

    cache_root = Path(cache_dir)
    frames: list[pd.DataFrame] = []
    fetched = 0
    failed: list[dict[str, str]] = []
    for _, row in candidates.iterrows():
        leisu_id = str(row.get("leisu_match_id", "")).replace(".0", "")
        url = str(row.get("leisu_intelligence_url", "")).strip()
        if not leisu_id or not url:
            continue
        cache_path = cache_root / f"{leisu_id}.html"
        try:
            if download:
                html = fetch_leisu_intelligence_page(url, cache_path)
                fetched += 1
            else:
                html = cache_path.read_text(encoding="utf-8")
            frames.append(
                parse_leisu_intelligence_html(
                    html,
                    match_id=row.get("match_id", ""),
                    home_team=str(row.get("home_team", "")),
                    away_team=str(row.get("away_team", "")),
                    home_team_zh=str(row.get("leisu_home_team_zh", "")),
                    away_team_zh=str(row.get("leisu_away_team_zh", "")),
                    url=url,
                )
            )
        except Exception as exc:  # pragma: no cover - network failures are environment specific.
            failed.append({"leisu_match_id": leisu_id, "url": url, "error": str(exc)})

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    out = pd.concat(frames, ignore_index=True) if frames else parse_leisu_intelligence_html(
        "",
        match_id="",
        home_team="",
        away_team="",
        url="",
    )
    out.to_csv(output, index=False)

    return {
        "source": "leisu_intelligence_page",
        "input": str(leisu_features_path),
        "output": str(output),
        "cache_dir": str(cache_root),
        "candidate_pages": int(len(candidates)),
        "downloaded_pages": fetched,
        "parsed_rows": int(len(out)),
        "failed_pages": failed,
        "download": bool(download),
    }
