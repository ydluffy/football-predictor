from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import ProxyHandler, Request, build_opener

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
from strategy.shadow_evidence import settle_shadow_evidence  # noqa: E402
API_URL = "https://webapi.sporttery.cn/gateway/uniform/football/getUniformMatchResultV1.qry"


HEADERS = {
    "accept": "application/json, text/javascript, */*; q=0.01",
    "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "origin": "https://www.lottery.gov.cn",
    "referer": "https://www.lottery.gov.cn/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0"
    ),
}


@dataclass(frozen=True)
class MatchResult:
    date: str
    match_number: str
    competition: str
    home_team: str
    away_team: str
    all_home_team: str
    all_away_team: str
    handicap: int
    half_time_score: str
    full_time_score: str
    spf_result: str
    rqspf_result: str
    spf_odds_home: str
    spf_odds_draw: str
    spf_odds_away: str
    status: str
    source_match_id: str


def fetch_json(start_date: str, end_date: str, proxy: str = "") -> dict[str, Any]:
    query = (
        f"matchBeginDate={start_date}&matchEndDate={end_date}"
        "&leagueId=&pageSize=100&pageNo=1&isFix=0&matchPage=1&pcOrWap=1"
    )
    req = Request(f"{API_URL}?{query}", headers=HEADERS, method="GET")
    handlers = []
    if proxy:
        handlers.append(ProxyHandler({"http": proxy, "https": proxy}))
    opener = build_opener(*handlers)
    with opener.open(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def sales_window_result_end(end_date: str) -> str:
    """Include the next calendar day because a Sporttery sales day crosses midnight."""
    parsed = date.fromisoformat(end_date)
    return (parsed + timedelta(days=1)).isoformat()


def results_for_sales_day(results: pd.DataFrame, sales_day: str) -> pd.DataFrame:
    """Limit settlement evidence to the sales day and its following calendar day."""
    if results.empty or "date" not in results.columns:
        return results
    try:
        start = date.fromisoformat(str(sales_day))
    except ValueError:
        return results.iloc[0:0]
    allowed = {start.isoformat(), (start + timedelta(days=1)).isoformat()}
    return results[results["date"].astype(str).isin(allowed)].copy()


def _score_parts(score: str) -> tuple[int | None, int | None]:
    match = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", str(score or ""))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _spf_result(score: str) -> str:
    home, away = _score_parts(score)
    if home is None or away is None:
        return ""
    if home > away:
        return "胜"
    if home == away:
        return "平"
    return "负"


def _rqspf_result(score: str, handicap: int) -> str:
    home, away = _score_parts(score)
    if home is None or away is None:
        return ""
    adjusted_home = home + handicap
    if adjusted_home > away:
        return "让胜"
    if adjusted_home == away:
        return "让平"
    return "让负"


def parse_results(payload: dict[str, Any]) -> list[MatchResult]:
    if str(payload.get("errorCode")) != "0":
        raise RuntimeError(f"sporttery api error: {payload.get('errorMessage') or payload}")
    rows = payload.get("value", {}).get("matchResult", [])
    results: list[MatchResult] = []
    for row in rows:
        score = str(row.get("sectionsNo999") or "")
        try:
            handicap = int(str(row.get("goalLine") or "0"))
        except ValueError:
            handicap = 0
        results.append(
            MatchResult(
                date=str(row.get("matchDate") or ""),
                match_number=str(row.get("matchNumStr") or ""),
                competition=str(row.get("leagueNameAbbr") or row.get("leagueName") or ""),
                home_team=str(row.get("homeTeam") or ""),
                away_team=str(row.get("awayTeam") or ""),
                all_home_team=str(row.get("allHomeTeam") or row.get("homeTeam") or ""),
                all_away_team=str(row.get("allAwayTeam") or row.get("awayTeam") or ""),
                handicap=handicap,
                half_time_score=str(row.get("sectionsNo1") or ""),
                full_time_score=score,
                spf_result=_spf_result(score),
                rqspf_result=_rqspf_result(score, handicap),
                spf_odds_home=str(row.get("h") or ""),
                spf_odds_draw=str(row.get("d") or ""),
                spf_odds_away=str(row.get("a") or ""),
                status="已完成" if str(row.get("matchResultStatus")) == "2" else str(row.get("matchResultStatus") or ""),
                source_match_id=str(row.get("matchId") or ""),
            )
        )
    return results


def results_to_frame(results: list[MatchResult]) -> pd.DataFrame:
    return pd.DataFrame([r.__dict__ for r in results])


def normalize_name(value: str) -> str:
    value = str(value or "")
    return re.sub(r"[\s·\-/（）()]", "", value).lower()


def team_matches(selection_team: str, row: pd.Series) -> str:
    needle = normalize_name(selection_team)
    if not needle:
        return ""
    home_candidates = [row.get("home_team", ""), row.get("all_home_team", "")]
    away_candidates = [row.get("away_team", ""), row.get("all_away_team", "")]
    for name in home_candidates:
        hay = normalize_name(str(name))
        if needle in hay or hay in needle:
            return "home"
    for name in away_candidates:
        hay = normalize_name(str(name))
        if needle in hay or hay in needle:
            return "away"
    return ""


def parse_selection(selection: str) -> dict[str, str]:
    value = selection.strip()
    compact_value = re.sub(r"@\d+(?:\.\d+)?$", "", value).strip()
    inline_handicap_rq = re.fullmatch(
        r"(?P<number>\d{3})\s+(?P<home>.+?)\((?P<handicap>[+-]\d+)\)vs(?P<away>.+?)\s+让球胜平负:(?P<pick>让胜|让平|让负)",
        compact_value,
    )
    if inline_handicap_rq:
        return {
            "team": inline_handicap_rq.group("home").strip(),
            "away_team": inline_handicap_rq.group("away").strip(),
            "match_number": inline_handicap_rq.group("number"),
            "handicap": inline_handicap_rq.group("handicap"),
            "market": "rqspf",
            "pick": inline_handicap_rq.group("pick"),
        }
    compact_rq = re.fullmatch(
        r"(?P<number>\d{3})\s+(?P<home>.+?)vs(?P<away>.+?)\s+让球胜平负\((?P<handicap>[+-]\d+)\):(?P<pick>让胜|让平|让负)",
        compact_value,
    )
    if compact_rq:
        return {
            "team": compact_rq.group("home").strip(),
            "away_team": compact_rq.group("away").strip(),
            "match_number": compact_rq.group("number"),
            "handicap": compact_rq.group("handicap"),
            "market": "rqspf",
            "pick": compact_rq.group("pick"),
        }
    compact_spf = re.fullmatch(
        r"(?P<number>\d{3})\s+(?P<home>.+?)vs(?P<away>.+?)\s+胜平负:(?P<pick>主胜|平|客胜)",
        compact_value,
    )
    if compact_spf:
        pick_map = {"主胜": "胜", "平": "平", "客胜": "负"}
        return {
            "team": compact_spf.group("home").strip(),
            "away_team": compact_spf.group("away").strip(),
            "match_number": compact_spf.group("number"),
            "handicap": "",
            "market": "spf",
            "pick": pick_map[compact_spf.group("pick")],
        }
    rq_match = re.fullmatch(r"(.+?)([+-]\d+)让([胜平负])", value)
    if rq_match:
        return {
            "team": rq_match.group(1).strip(),
            "handicap": rq_match.group(2),
            "market": "rqspf",
            "pick": f"让{rq_match.group(3)}",
        }
    spf_match = re.fullmatch(r"(.+?)(胜|平|负)", value)
    if spf_match:
        return {
            "team": spf_match.group(1).strip(),
            "handicap": "",
            "market": "spf",
            "pick": spf_match.group(2),
        }
    return {"team": value, "handicap": "", "market": "unknown", "pick": ""}


def evaluate_selection(selection: str, results: pd.DataFrame) -> tuple[bool | None, str]:
    parsed = parse_selection(selection)
    if parsed["market"] == "unknown":
        return None, f"无法解析选择：{selection}"
    matches: list[pd.Series] = []
    sides: list[str] = []
    for _, row in results.iterrows():
        match_number = parsed.get("match_number", "")
        if match_number and not str(row.get("match_number", "")).endswith(match_number):
            continue
        side = team_matches(parsed["team"], row)
        if side:
            away_team = parsed.get("away_team", "")
            if away_team and team_matches(away_team, row) != "away":
                continue
            if parsed["market"] == "rqspf" and parsed["handicap"]:
                try:
                    wanted_handicap = int(parsed["handicap"])
                    if int(row["handicap"]) != wanted_handicap:
                        continue
                except ValueError:
                    continue
            matches.append(row)
            sides.append(side)
    if not matches:
        return None, f"未匹配比赛：{selection}"
    row = matches[0]
    side = sides[0]
    home_score, away_score = _score_parts(str(row.get("full_time_score", "")))
    if home_score is None or away_score is None:
        return None, f"{row['match_number']} {row['home_team']} vs {row['away_team']} 待90分钟官方赛果"
    if parsed["market"] == "rqspf":
        actual = str(row["rqspf_result"])
        return actual == parsed["pick"], f"{row['match_number']} {row['home_team']}({row['handicap']:+d}) {row['full_time_score']} {actual}"
    actual_spf = str(row["spf_result"])
    if parsed["pick"] == "平":
        expected = "平"
    elif side == "home":
        expected = "胜" if parsed["pick"] == "胜" else "负"
    else:
        expected = "负" if parsed["pick"] == "胜" else "胜"
    return actual_spf == expected, f"{row['match_number']} {row['home_team']} vs {row['away_team']} {row['full_time_score']} SPF={actual_spf}"


def split_plan_selections(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"\s+\+\s+", str(value or "")) if part.strip()]


def parse_odds_value(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if "=" in text:
        text = text.rsplit("=", 1)[1].strip()
    if "*" in text:
        factors = [float(part.strip()) for part in text.split("*") if part.strip()]
        return math.prod(factors)
    return float(text)


def review_ledger(ledger_path: Path, results: pd.DataFrame, output_path: Path | None = None) -> pd.DataFrame:
    ledger = pd.read_csv(ledger_path, encoding="utf-8-sig", keep_default_na=False)
    for idx, row in ledger.iterrows():
        current_result = str(row.get("result", "")).strip()
        if current_result and current_result not in {"待赛", "待赛果", "待官方赛果", "pending"}:
            continue
        selections = split_plan_selections(str(row.get("selections", "")))
        if not selections:
            continue
        plan_results = results_for_sales_day(results, str(row.get("date", "")))
        evaluated = [evaluate_selection(selection, plan_results) for selection in selections]
        if any(item[0] is None for item in evaluated):
            ledger.at[idx, "review_note"] = f"待官方赛果匹配：{'；'.join(item[1] for item in evaluated)}"
            continue
        hit = all(bool(item[0]) for item in evaluated)
        notes = "；".join(item[1] for item in evaluated)
        stake = float(row.get("stake") or 0)
        odds = row.get("actual_odds") or row.get("estimated_odds") or ""
        payout = 0.0
        if hit and str(odds).strip():
            payout = stake * parse_odds_value(odds)
        net = payout - stake
        roi = net / stake if stake else 0.0
        ledger.at[idx, "result"] = "命中" if hit else "未中"
        ledger.at[idx, "payout"] = f"{payout:.2f}"
        ledger.at[idx, "net_profit"] = f"{net:.2f}"
        ledger.at[idx, "roi"] = f"{roi:.4f}"
        ledger.at[idx, "review_note"] = f"体彩官方接口自动复盘：{notes}"
    if output_path:
        ledger.to_csv(output_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    return ledger


def write_review(report_path: Path, ledger: pd.DataFrame, reviewed_only: bool = True) -> None:
    if reviewed_only:
        frame = ledger[ledger["result"].astype(str).isin(["命中", "未中"])].copy()
    else:
        frame = ledger.copy()
    stake = pd.to_numeric(frame["stake"], errors="coerce").fillna(0).sum()
    payout = pd.to_numeric(frame["payout"], errors="coerce").fillna(0).sum()
    net = payout - stake
    hits = int((frame["result"] == "命中").sum())
    total = int(len(frame))
    roi = net / stake if stake else 0
    lines = [
        "# 体彩官方接口自动复盘",
        "",
        f"- 方案数：{total}",
        f"- 命中：{hits}",
        f"- 未中：{total - hits}",
        f"- 总本金：{stake:.2f}",
        f"- 总返奖：{payout:.2f}",
        f"- 净收益：{net:.2f}",
        f"- ROI：{roi:.2%}",
        "",
        "| 日期 | 方案 | 类型 | 选择 | 结果 | 返奖 | 净收益 |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for _, row in frame.iterrows():
        lines.append(
            f"| {row.get('date','')} | {row.get('plan_id','')} | {row.get('plan_type','')} | "
            f"{row.get('selections','')} | {row.get('result','')} | {row.get('payout','')} | {row.get('net_profit','')} |"
        )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Sporttery football match results and optionally review ledger.")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--proxy", default="")
    parser.add_argument("--input-json", default="")
    parser.add_argument("--raw-output", default="")
    parser.add_argument("--output-csv", default="")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--ledger-output", default="")
    parser.add_argument("--review-output", default="")
    parser.add_argument("--shadow-prediction-ledger", default="data/manual/shadow_prediction_ledger_v2.csv")
    parser.add_argument("--shadow-portfolio-ledger", default="data/manual/shadow_portfolio_ledger_v2.csv")
    parser.add_argument("--fixed-odds-shadow-ledger", default="data/manual/fixed_odds_shadow_ledger.csv")
    parser.add_argument("--shadow-audit-output", default="artifacts/data/shadow_evidence_settlement_latest.json")
    parser.add_argument("--skip-shadow-settlement", action="store_true")
    parser.add_argument(
        "--calendar-date-only",
        action="store_true",
        help="Do not extend the query through the next calendar day. By default ledger settlement treats start/end as Sporttery sales days.",
    )
    args = parser.parse_args()

    effective_end_date = args.end_date
    fixed_odds_path = Path(args.fixed_odds_shadow_ledger)
    if not fixed_odds_path.is_absolute():
        fixed_odds_path = ROOT / fixed_odds_path
    sales_window_extension_applied = bool(
        (args.ledger or fixed_odds_path.exists()) and not args.calendar_date_only
    )
    if sales_window_extension_applied:
        effective_end_date = sales_window_result_end(args.end_date)

    if args.input_json:
        payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    else:
        payload = fetch_json(args.start_date, effective_end_date, proxy=args.proxy)
    if args.raw_output:
        raw_output = Path(args.raw_output)
        raw_output.parent.mkdir(parents=True, exist_ok=True)
        raw_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    results = parse_results(payload)
    frame = results_to_frame(results)
    output_csv = Path(args.output_csv) if args.output_csv else ROOT / "data" / "external" / "sporttery_results" / f"sporttery_results_{args.start_date}_{effective_end_date}.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_csv, index=False, encoding="utf-8-sig")

    summary: dict[str, Any] = {
        "rows": int(len(frame)),
        "output_csv": str(output_csv),
        "requested_start_date": args.start_date,
        "requested_end_date": args.end_date,
        "effective_end_date": effective_end_date,
        "sales_window_extension_applied": sales_window_extension_applied,
    }
    if args.ledger:
        ledger_path = Path(args.ledger)
        ledger_output = Path(args.ledger_output) if args.ledger_output else ledger_path
        ledger = review_ledger(ledger_path, frame, ledger_output)
        summary["ledger_output"] = str(ledger_output)
        if args.review_output:
            write_review(Path(args.review_output), ledger)
            summary["review_output"] = args.review_output
    if fixed_odds_path.exists():
        fixed_ledger = review_ledger(fixed_odds_path, frame, fixed_odds_path)
        settled_fixed = fixed_ledger[fixed_ledger["result"].astype(str).isin(["命中", "未中"])].copy()
        fixed_stake = pd.to_numeric(settled_fixed.get("stake"), errors="coerce").fillna(0.0).sum()
        fixed_payout = pd.to_numeric(settled_fixed.get("payout"), errors="coerce").fillna(0.0).sum()
        fixed_hits = int(settled_fixed["result"].astype(str).eq("命中").sum())
        summary["fixed_odds_shadow"] = {
            "ledger": str(fixed_odds_path),
            "settled_plans": int(len(settled_fixed)),
            "hits": fixed_hits,
            "hit_rate": round(fixed_hits / len(settled_fixed), 6) if len(settled_fixed) else None,
            "stake": round(float(fixed_stake), 2),
            "payout": round(float(fixed_payout), 2),
            "net": round(float(fixed_payout - fixed_stake), 2),
            "roi": round(float((fixed_payout - fixed_stake) / fixed_stake), 6) if fixed_stake else None,
            "production_ledger_write_performed": False,
        }
    if not args.skip_shadow_settlement:
        prediction_path = Path(args.shadow_prediction_ledger)
        portfolio_path = Path(args.shadow_portfolio_ledger)
        if not prediction_path.is_absolute(): prediction_path = ROOT / prediction_path
        if not portfolio_path.is_absolute(): portfolio_path = ROOT / portfolio_path
        shadow_audit = settle_shadow_evidence(
            prediction_ledger_path=prediction_path,
            portfolio_ledger_path=portfolio_path,
            results=frame,
            settled_at=datetime.now().astimezone().replace(microsecond=0).isoformat(),
        )
        shadow_audit_path = Path(args.shadow_audit_output)
        if not shadow_audit_path.is_absolute(): shadow_audit_path = ROOT / shadow_audit_path
        shadow_audit_path.parent.mkdir(parents=True, exist_ok=True)
        shadow_audit_path.write_text(json.dumps(shadow_audit, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["shadow_evidence"] = shadow_audit
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
