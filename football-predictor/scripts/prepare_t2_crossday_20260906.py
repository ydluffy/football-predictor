import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
nums = {f"{n:03d}" for n in range(15, 25)}
scan = json.loads((ROOT / "artifacts/data/sporttery_sales_window_scan_2026-09-06_1819_confirm.json").read_text(encoding="utf-8"))
scan["fixtures"] = [f for f in scan["fixtures"] if f["match_number"] in nums]
scan["planned_tasks"] = []
assert len(scan["fixtures"]) == 10 and all(f["sale_status"] == "on_sale" for f in scan["fixtures"])
(ROOT / "artifacts/data/t2_crossday_20260906_scan.json").write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")


def subset(src, dst, keep):
    with (ROOT / src).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        selected = [row for row in reader if row["match_number"].zfill(3) in keep]
        if "kickoff_time" in fields:
            selected = [row for row in selected if "2026-09-06 23:00" <= row["kickoff_time"] <= "2026-09-07 05:30"]
    with (ROOT / dst).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(selected)
    return len(selected)


assert subset("data/manual/sporttery_handicap_markets_2026-09-06_1819_confirm.csv", "artifacts/data/t2_crossday_20260906_markets_all.csv", nums) == 10
assert subset("data/manual/sporttery_handicap_markets_2026-09-06_1819_confirm.csv", "artifacts/data/t2_crossday_20260906_markets_plan.csv", nums - {"015"}) == 9
assert subset("data/manual/sporttery_play_odds_2026-09-06_1819_confirm.csv", "artifacts/data/t2_crossday_20260906_plays.csv", nums) > 0
print("prepared 10 analysis rows; 9 parlay-eligible rows; 015 excluded")
