"""Freeze the scoped early snapshot and generate observation-only reports."""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-09-04_1803_001_014"


def read(path):
    with (ROOT / path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path, rows):
    with (ROOT / path).open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def run(script, args):
    subprocess.run([sys.executable, "scripts/" + script] + args, cwd=ROOT, check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ledgers = ["data/manual/betting_plan_ledger.csv", "data/manual/fixed_odds_shadow_ledger.csv"]
    before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in ledgers}
    markets = [
        r
        for r in read("data/manual/sporttery_handicap_markets_2026-09-04_1803_confirm.csv")
        if "2026-09-05 00:00" <= r["kickoff_time"] < "2026-09-05 10:00"
    ]
    assert len(markets) == 14
    identities = {(r["date"], r["match_number"], r["home_team"], r["away_team"]) for r in markets}
    plays = [
        r
        for r in read("data/manual/sporttery_play_odds_2026-09-04_1803_confirm.csv")
        if (r["date"], r["match_number"], r["home_team"], r["away_team"]) in identities
    ]
    market = f"data/manual/sporttery_handicap_markets_{STAMP}.csv"
    play = f"data/manual/sporttery_play_odds_{STAMP}.csv"
    write(market, markets)
    write(play, plays)
    model = f"artifacts/data/sporttery_handicap_prediction_{STAMP}.csv"
    run(
        "predict_sporttery_handicap.py",
        [
            "--market-csv",
            market,
            "--analysis-at",
            "2026-09-04T18:03:04+08:00",
            "--output",
            model,
            "--audit-output",
            model.replace(".csv", ".json"),
        ],
    )
    common = [
        "--market-csv",
        market,
        "--start-after",
        "2026-09-04 18:03",
        "--start-before",
        "2026-09-05 10:00",
    ]
    run(
        "build_multi_play_betting_strategy.py",
        common
        + [
            "--max-matches",
            "14",
            "--stake",
            "100",
            "--handicap-model-csv",
            model,
            "--plans-output",
            f"artifacts/data/sporttery_plans_{STAMP}.csv",
            "--matches-output",
            f"artifacts/data/sporttery_match_analysis_{STAMP}.csv",
            "--report-output",
            f"artifacts/betting/sporttery_strategy_{STAMP}.md",
            "--audit-output",
            f"artifacts/data/sporttery_strategy_{STAMP}.json",
        ],
    )
    run(
        "build_sporttery_all_play_candidates.py",
        common
        + [
            "--play-odds-csv",
            play,
            "--budget",
            "100",
            "--base-output",
            f"artifacts/data/sporttery_all_play_base_{STAMP}.csv",
            "--play-output",
            f"artifacts/data/sporttery_all_play_candidates_{STAMP}.csv",
            "--report-output",
            f"artifacts/betting/sporttery_all_play_candidates_{STAMP}.md",
            "--audit-output",
            f"artifacts/data/sporttery_all_play_candidates_{STAMP}.json",
        ],
    )
    after = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in ledgers}
    assert before == after
    old = {
        (r["home_team"], r["away_team"]): r
        for r in read("data/manual/sporttery_handicap_markets_2026-09-04_1228_confirm.csv")
        if "2026-09-05 00:00" <= r["kickoff_time"] < "2026-09-05 10:00"
    }
    delta = [
        {
            "number": r["match_number"],
            "teams": r["home_team"] + "—" + r["away_team"],
            "spf_before": [
                old[(r["home_team"], r["away_team"])]["spf_odds_" + k]
                for k in ("home", "draw", "away")
            ],
            "spf_after": [r["spf_odds_" + k] for k in ("home", "draw", "away")],
        }
        for r in markets
    ]
    audit = {
        "stage": "early_observation_only",
        "market_rows": len(markets),
        "play_rows": len(plays),
        "ledger_hashes": after,
        "production_write": False,
        "fixed_shadow_write": False,
        "movement": delta,
    }
    (ROOT / f"artifacts/data/sporttery_early_analysis_{STAMP}.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
