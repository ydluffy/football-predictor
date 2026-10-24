"""Read public Nowscore match pages into auditable, pre-match market snapshots."""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from bs4.element import NavigableString

from data.competition_registry import load_team_alias_registry, normalize_alias


SHANGHAI = ZoneInfo("Asia/Shanghai")
MATCH_URL = re.compile(r"/odds/match/(\d+)\.htm", re.I)
SALES_DAY_TEXT = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")
XML_RECORD = re.compile(r"<i>(.*?)</i>", re.S | re.I)
LINE_PARTS = {"平手": 0.0, "平/半": 0.25, "半球": 0.5, "半/一": 0.75,
              "一球": 1.0, "一/球半": 1.25, "球半": 1.5, "球半/两": 1.75,
              "两球": 2.0, "两/两半": 2.25, "两半": 2.5, "两半/三": 2.75,
              "三球": 3.0}
# cp.nowscore.com 的盘口接口与变盘历史表使用长写盘口（"平手/半球"），与页面短写（"平/半"）不同。
LONG_LINE_PARTS = {"平手": 0.0, "平手/半球": 0.25, "半球": 0.5, "半球/一球": 0.75,
                   "一球": 1.0, "一球/球半": 1.25, "球半": 1.5, "球半/两球": 1.75,
                   "两球": 2.0, "两球/两球半": 2.25, "两球半": 2.5, "两球半/三球": 2.75,
                   "三球": 3.0, "三球/三球半": 3.25, "三球半": 3.5}
CHANGE_HEADER_CELLS = {"主队", "客队", "大球", "小球", "盘口", "变化时间"}


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _sales_day(value: str) -> str:
    match = SALES_DAY_TEXT.search(value)
    if not match:
        return ""
    return f"{int(match[1]):04d}-{int(match[2]):02d}-{int(match[3]):02d}"


def _row_sales_day(tr) -> str:
    """Return the closest date heading before a match row.

    Nowscore keeps the previous sales day on the page after the new sales day
    opens.  A page-level first-date lookup therefore assigns yesterday to every
    row.  Looking backwards from each row preserves the page's date grouping
    and also handles duplicate match numbers across adjacent sales days.
    """
    previous = tr.find_all_previous(string=SALES_DAY_TEXT)
    for value in previous:
        if isinstance(value, NavigableString):
            parsed = _sales_day(str(value))
            if parsed:
                return parsed
    return ""


def parse_cp_page(html: str) -> tuple[str, list[dict]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tr[matchid]"):
        link = tr.find("a", href=MATCH_URL)
        if not link:
            continue
        href = urljoin("https://live.nowscore.com", link.get("href", ""))
        match = MATCH_URL.search(href)
        cells = tr.find_all("td", recursive=False)
        if urlparse(href).hostname != "live.nowscore.com" or not match or len(cells) < 8:
            continue
        number = re.search(r"\d{3}", _text(cells[0]))
        kickoff_raw = next((td.get("title", "") for td in cells if "开赛时间" in td.get("title", "")), "")
        kickoff_match = re.search(r"20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}", kickoff_raw)
        home = tr.find("a", id=re.compile(r"^HomeTeam_"))
        away = tr.find("a", id=re.compile(r"^GuestTeam_"))
        rows.append({
            "sales_day": _row_sales_day(tr), "match_number": number.group() if number else "",
            "cp_match_id": tr.get("matchid", ""), "nowscore_match_id": match.group(1),
            "competition": tr.get("gamename", ""), "home_team": _text(home), "away_team": _text(away),
            "kickoff": (kickoff_match.group().replace(" ", "T") + "+08:00") if kickoff_match else "",
            "odds_url": href,
        })
    sales_days = sorted({row["sales_day"] for row in rows if row["sales_day"]})
    sales_day = sales_days[-1] if sales_days else ""
    return sales_day, rows


def _canonical(value: str) -> str:
    registry = load_team_alias_registry()
    return normalize_alias(registry.resolve(value) or value)


def align_cp_to_scan(cp_rows: list[dict], fixtures: list[dict], sales_day: str) -> list[dict]:
    aligned = []
    for fixture in fixtures:
        number = str(fixture.get("match_number", "")).zfill(3)
        candidates = [r for r in cp_rows if r["sales_day"] == sales_day and r["match_number"] == number]
        status, reason, chosen = "unmatched", "number_not_found", None
        verified = []
        for candidate in candidates:
            teams_match = (_canonical(candidate["home_team"]) == _canonical(str(fixture.get("home_team_canonical") or fixture.get("home_team") or ""))
                           and _canonical(candidate["away_team"]) == _canonical(str(fixture.get("away_team_canonical") or fixture.get("away_team") or "")))
            try:
                delta = abs((datetime.fromisoformat(candidate["kickoff"]) - datetime.fromisoformat(str(fixture["kickoff"]))).total_seconds()) / 60
            except (ValueError, KeyError, TypeError):
                delta = math.inf
            if teams_match and delta <= 15:
                verified.append(candidate)
        if len(verified) == 1:
            chosen = verified[0]
            status, reason = "mapped", "number_teams_kickoff_verified"
        elif len(verified) > 1:
            status, reason = "ambiguous", "duplicate_match_number"
        elif len(candidates) == 1:
            chosen = candidates[0]
            status, reason = "needs_review", "team_or_kickoff_mismatch"
        elif len(candidates) > 1:
            status, reason = "ambiguous", "duplicate_number_no_verified_candidate"
        aligned.append({**fixture, "nowscore_match_id": chosen["nowscore_match_id"] if chosen else "",
                        "nowscore_cp_match_id": chosen["cp_match_id"] if chosen else "",
                        "nowscore_odds_url": chosen["odds_url"] if chosen else "",
                        "nowscore_home_team": chosen["home_team"] if chosen else "",
                        "nowscore_away_team": chosen["away_team"] if chosen else "",
                        "mapping_status": status, "mapping_reason": reason})
    return aligned


def asian_line(value: str) -> float | None:
    clean = value.strip().replace("受让", "*").replace("受", "*").replace("球半/二", "球半/两")
    away_favored = "*" in clean
    clean = clean.replace("*", "")
    if clean not in LINE_PARTS:
        return None
    return LINE_PARTS[clean] if away_favored else -LINE_PARTS[clean]


def _float(value: str) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _hong_kong_to_decimal(value: str) -> float | None:
    parsed = _float(value)
    return round(parsed + 1, 4) if parsed is not None else None


def parse_odds_page(html: str, match_id: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tr.datatr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 20:
            continue
        links = cells[-1].find_all("a", href=True)
        detail = next((a for a in links if "3in1Odds" in a["href"]), None)
        company_id = parse_qs(urlparse(detail["href"]).query).get("companyid", [""])[0] if detail else ""
        if not company_id:
            continue
        values = [_text(cell) for cell in cells]
        for stage, offset in (("opening", 1), ("current", 4)):
            rows.append({"nowscore_match_id": match_id, "bookmaker_id": company_id,
                         "bookmaker_name": values[0], "market": "asian_handicap", "stage": stage,
                         "home_handicap_raw": values[offset + 1], "home_handicap": asian_line(values[offset + 1]),
                         "home_price_raw": values[offset], "away_price_raw": values[offset + 2],
                         "home_odds": _hong_kong_to_decimal(values[offset]),
                         "away_odds": _hong_kong_to_decimal(values[offset + 2]),
                         "price_format": "hong_kong_water_to_decimal"})
        for stage, offset in (("opening", 7), ("current", 10)):
            rows.append({"nowscore_match_id": match_id, "bookmaker_id": company_id,
                         "bookmaker_name": values[0], "market": "h2h", "stage": stage,
                         "home_odds": _float(values[offset]), "draw_odds": _float(values[offset + 1]),
                         "away_odds": _float(values[offset + 2]), "price_format": "decimal"})
        for stage, offset in (("opening", 13), ("current", 16)):
            rows.append({"nowscore_match_id": match_id, "bookmaker_id": company_id,
                         "bookmaker_name": values[0], "market": "totals", "stage": stage,
                         "total_line_raw": values[offset + 1], "over_price_raw": values[offset],
                         "under_price_raw": values[offset + 2],
                         "over_odds": _hong_kong_to_decimal(values[offset]),
                         "under_odds": _hong_kong_to_decimal(values[offset + 2]),
                         "price_format": "hong_kong_water_to_decimal"})
    return rows


def _xml_records(text: str) -> list[list[str]]:
    """Split the `<i>a,b,c</i>` records used by the cp.nowscore.com feeds."""
    return [record.split(",") for record in XML_RECORD.findall(text)]


def _xml_quote(record: list[str], market: str, stage: str, fields: dict) -> dict:
    return {"cp_match_id": record[1], "bookmaker_id": record[0], "bookmaker_name": f"company_{record[0]}",
            "odds_id": record[2], "market": market, "stage": stage, **fields}


def parse_asian_xml(text: str) -> dict[str, list[dict]]:
    """Parse /data/yp101.xml：`公司ID,竞彩场次ID,oddsId,主水,盘口,客水`.

    水位为香港水位，盘口为正数表示主队让球，与页面 ``asian_line`` 的负号约定相反。
    """
    grouped: dict[str, list[dict]] = {}
    for record in _xml_records(text):
        if len(record) < 6:
            continue
        line = _float(record[4])
        quote = _xml_quote(record, "asian_handicap", "current", {
            "home_handicap_raw": record[4], "home_handicap": -line if line is not None else None,
            "home_price_raw": record[3], "away_price_raw": record[5],
            "home_odds": _hong_kong_to_decimal(record[3]), "away_odds": _hong_kong_to_decimal(record[5]),
            "price_format": "hong_kong_water_to_decimal"})
        grouped.setdefault(record[1], []).append(quote)
    return grouped


def parse_totals_xml(text: str) -> dict[str, list[dict]]:
    """Parse /data/dx101.xml：`公司ID,竞彩场次ID,oddsId,大球水,盘口,小球水`."""
    grouped: dict[str, list[dict]] = {}
    for record in _xml_records(text):
        if len(record) < 6:
            continue
        quote = _xml_quote(record, "totals", "current", {
            "total_line_raw": record[4], "over_price_raw": record[3], "under_price_raw": record[5],
            "over_odds": _hong_kong_to_decimal(record[3]), "under_odds": _hong_kong_to_decimal(record[5]),
            "price_format": "hong_kong_water_to_decimal"})
        grouped.setdefault(record[1], []).append(quote)
    return grouped


def parse_h2h_xml(text: str) -> dict[str, list[dict]]:
    """Parse /data/op101.xml：`公司ID,竞彩场次ID,oddsId,初主,初和,初客,终主,终和,终客`.

    ``公司ID=0`` 为跨机构平均值行，保留但不参与公司维度统计。
    """
    grouped: dict[str, list[dict]] = {}
    for record in _xml_records(text):
        if len(record) < 9:
            continue
        for stage, offset in (("opening", 3), ("current", 6)):
            quote = _xml_quote(record, "h2h", stage, {
                "home_odds": _float(record[offset]), "draw_odds": _float(record[offset + 1]),
                "away_odds": _float(record[offset + 2]), "price_format": "decimal"})
            grouped.setdefault(record[1], []).append(quote)
    return grouped


def long_asian_line(value: str) -> float | None:
    """Resolve the long-form handicap used by cp.nowscore.com ("平手/半球") to a signed line."""
    clean = value.strip()
    away_favored = "受" in clean
    clean = clean.replace("受让", "").replace("受", "")
    if clean not in LONG_LINE_PARTS:
        return None
    return LONG_LINE_PARTS[clean] if away_favored else -LONG_LINE_PARTS[clean]


def parse_change_table(html: str) -> list[dict]:
    """Parse /handle/odds.aspx?cmd=*change 的“近5次变化记录”表（主队|盘口|客队|变化时间）。"""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) != 4:
            continue
        values = [_text(cell) for cell in cells]
        if values[0] in CHANGE_HEADER_CELLS or values[1] in CHANGE_HEADER_CELLS:
            continue
        rows.append({"home_price_raw": values[0], "handicap_raw": values[1], "away_price_raw": values[2],
                     "changed_at_raw": values[3], "home_odds": _hong_kong_to_decimal(values[0]),
                     "away_odds": _hong_kong_to_decimal(values[2]), "handicap": long_asian_line(values[1]),
                     "is_opening": "初" in values[3]})
    return rows


def xml_quotes(feeds: dict[str, dict[str, list[dict]]], cp_match_id: str, nowscore_match_id: str) -> list[dict]:
    """Collect every feed quote for one 竞彩场次，keyed by the cp feed's 竞彩场次ID."""
    if not cp_match_id:
        return []
    quotes = []
    for feed in ("asian", "h2h", "totals"):
        quotes.extend({**quote, "nowscore_match_id": nowscore_match_id}
                      for quote in feeds.get(feed, {}).get(cp_match_id, []))
    return quotes


def to_outer_rows(quotes: list[dict], fixture: dict, captured_at: datetime, raw_sha256: str, raw_path: str,
                  source_time_verified: bool = True) -> list[dict]:
    kickoff = datetime.fromisoformat(str(fixture["kickoff"]))
    before = captured_at < kickoff
    output = []
    for quote in quotes:
        if quote["market"] != "asian_handicap" or quote["stage"] != "current":
            continue
        line, home, away = quote["home_handicap"], quote["home_odds"], quote["away_odds"]
        valid = line is not None and home is not None and away is not None and home > 1 and away > 1
        eligible = source_time_verified and before and valid and fixture["mapping_status"] == "mapped"
        key = f"{captured_at.isoformat()}|{fixture['nowscore_match_id']}|{quote['bookmaker_id']}|asian"
        balance = abs(math.log(home / away)) if valid else None
        output.append({
            "record_id": hashlib.sha256(key.encode()).hexdigest()[:24],
            "snapshot_id": "nowscore_" + captured_at.strftime("%Y%m%dT%H%M%SZ"),
            "captured_at": captured_at.isoformat(), "source": "nowscore", "source_fixture_id": fixture["nowscore_match_id"],
            "match_id": fixture.get("match_id", ""), "competition_id": fixture.get("competition_id", ""),
            "league_id": "", "league_name": fixture.get("competition", ""), "kickoff_at": kickoff.isoformat(),
            "home_team": fixture.get("home_team", ""), "away_team": fixture.get("away_team", ""),
            "bookmaker_id": quote["bookmaker_id"], "bookmaker_name": quote["bookmaker_name"],
            "bet_id": "asian_handicap", "bet_name": "Asian Handicap", "home_handicap": line,
            "away_handicap": -line if line is not None else None, "home_odds": home, "away_odds": away,
            "raw_home_value": quote["home_price_raw"], "raw_away_value": quote["away_price_raw"],
            "provider_updated_at": "", "raw_sha256": raw_sha256, "raw_archive_path": raw_path,
            "mapping_status": fixture["mapping_status"], "before_kickoff": before,
            "quarter_line": line is not None and abs(line * 4 - round(line * 4)) < 1e-8,
            "price_balance_score": balance, "is_bookmaker_main_line": True,
            "primary_line_price_balanced": balance is not None and balance <= 0.5,
            "eligible_for_research": eligible,
            "eligible_for_primary_research": eligible and balance is not None and balance <= 0.5,
            "reject_reason": "" if eligible else ("offline_capture_time_unverified" if not source_time_verified
                                                        else "post_kickoff" if not before else "unmapped_or_invalid_quote"),
        })
    return output
