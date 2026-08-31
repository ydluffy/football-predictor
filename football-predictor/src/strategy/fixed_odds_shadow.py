from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd


LEDGER_COLUMNS = [
    "date", "time_window", "plan_id", "plan_type", "selections", "stake",
    "estimated_odds", "actual_odds", "result", "payout", "net_profit", "roi", "review_note",
]


def _text(value: object) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()


def _load(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.stat().st_size:
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    return pd.read_csv(path, dtype=str, keep_default_na=False).reindex(columns=LEDGER_COLUMNS)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    frame.to_csv(part, index=False, encoding="utf-8-sig")
    part.replace(path)


def record_fixed_odds_shadow(
    plans: pd.DataFrame,
    *,
    sales_day: str,
    time_window: str,
    analysis_at: str,
    stage: str,
    ledger_path: str | Path,
    virtual_stake: float = 2.0,
    source_plan_csv: str = "",
) -> dict[str, Any]:
    """Freeze one fixed-odds observation per sales-day/time-window.

    The output deliberately uses a separate ledger with the standard settlement
    columns.  It never writes the production betting ledger.
    """
    if stage != "final":
        raise ValueError("fixed-odds shadow observations may only be recorded at final stage")
    if virtual_stake <= 0:
        raise ValueError("virtual_stake must be positive")
    candidates = plans[plans.get("plan_type", pd.Series(dtype=str)).astype(str).eq("固定赔率观察")].copy()
    path = Path(ledger_path)
    existing = _load(path)
    safe_window = re.sub(r"[^0-9A-Za-z]+", "_", time_window).strip("_") or "ALL"
    plan_id = f"FIXED_ODDS_SHADOW_{sales_day.replace('-', '')}_{safe_window}"
    if plan_id in set(existing["plan_id"].astype(str)):
        return {
            "status": "duplicate_ignored", "rows_added": 0, "ledger_rows": int(len(existing)),
            "plan_id": plan_id, "production_ledger_write_performed": False,
        }
    if candidates.empty:
        return {
            "status": "no_eligible_plan", "rows_added": 0, "ledger_rows": int(len(existing)),
            "plan_id": plan_id, "production_ledger_write_performed": False,
        }
    selected = candidates.iloc[0]
    odds_min = float(selected.get("estimated_odds_min") or 0)
    odds_max = float(selected.get("estimated_odds_max") or odds_min)
    if odds_min <= 1.0 or abs(odds_max - odds_min) > 1e-9:
        raise ValueError("fixed-odds shadow plan must contain exactly one combined odds value")
    row = {
        "date": sales_day,
        "time_window": time_window,
        "plan_id": plan_id,
        "plan_type": "固定赔率观察/影子",
        "selections": _text(selected.get("selections")),
        "stake": f"{virtual_stake:.2f}",
        "estimated_odds": f"{odds_min:.4f}",
        "actual_odds": "",
        "result": "pending",
        "payout": "",
        "net_profit": "",
        "roi": "",
        "review_note": (
            f"虚拟观察；analysis_at={analysis_at}；source={source_plan_csv}；"
            "不得复制到真实投注台账"
        ),
    }
    combined = pd.concat([existing, pd.DataFrame([row], columns=LEDGER_COLUMNS)], ignore_index=True)
    _atomic_csv(combined, path)
    return {
        "status": "recorded", "rows_added": 1, "ledger_rows": int(len(combined)),
        "plan_id": plan_id, "odds": odds_min, "selection": row["selections"],
        "production_ledger_write_performed": False,
    }
