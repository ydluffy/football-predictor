from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class RiskFlag:
    code: str
    detail: dict[str, Any]


def compute_risk_flags(match_row: pd.Series) -> list[RiskFlag]:
    flags: list[RiskFlag] = []

    injury_flag = int(match_row.get("injury_flag", 0) or 0)
    if injury_flag == 1:
        flags.append(RiskFlag(code="injury_flag", detail={}))

    line_move = float(match_row.get("line_move", 0.0) or 0.0)
    if abs(line_move) >= 0.25:
        flags.append(RiskFlag(code="large_line_move", detail={"line_move": line_move}))

    xg_home = float(match_row.get("xg_home", 0.0) or 0.0)
    xg_away = float(match_row.get("xg_away", 0.0) or 0.0)
    if (xg_home + xg_away) <= 0.2:
        flags.append(RiskFlag(code="low_xg_signal", detail={"xg_home": xg_home, "xg_away": xg_away}))

    odds_cols = ["odds_home", "odds_draw", "odds_away"]
    if any(float(match_row.get(c, 0.0) or 0.0) <= 1.01 for c in odds_cols):
        flags.append(RiskFlag(code="invalid_odds", detail={}))

    return flags
