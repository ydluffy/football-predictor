from __future__ import annotations

import math
from dataclasses import dataclass


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def predict_1x2(lambda_home: float, lambda_away: float, max_goals: int = 6) -> tuple[float, float, float]:
    p_home = 0.0
    p_draw = 0.0
    p_away = 0.0
    ph = [_poisson_pmf(i, lambda_home) for i in range(max_goals + 1)]
    pa = [_poisson_pmf(i, lambda_away) for i in range(max_goals + 1)]
    for i in range(max_goals + 1):
        for j in range(max_goals + 1):
            p = ph[i] * pa[j]
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    s = p_home + p_draw + p_away
    if s <= 0:
        return (1 / 3, 1 / 3, 1 / 3)
    return (p_home / s, p_draw / s, p_away / s)


@dataclass(frozen=True)
class TeamAverages:
    goals_for: float
    goals_against: float
    matches: int


def compute_team_averages(matches: list[dict], team_id: int) -> TeamAverages:
    gf = 0.0
    ga = 0.0
    n = 0
    for m in matches:
        hs = m.get("home_score")
        as_ = m.get("away_score")
        if hs is None or as_ is None:
            continue
        if m.get("home_team_id") == team_id:
            gf += float(hs)
            ga += float(as_)
            n += 1
        elif m.get("away_team_id") == team_id:
            gf += float(as_)
            ga += float(hs)
            n += 1
    if n == 0:
        return TeamAverages(goals_for=1.2, goals_against=1.2, matches=0)
    return TeamAverages(goals_for=gf / n, goals_against=ga / n, matches=n)


def compute_lambdas(home: TeamAverages, away: TeamAverages) -> tuple[float, float]:
    lam_home = (home.goals_for + away.goals_against) / 2.0
    lam_away = (away.goals_for + home.goals_against) / 2.0
    lam_home *= 1.08
    lam_home = max(0.1, min(lam_home, 4.0))
    lam_away = max(0.1, min(lam_away, 4.0))
    return lam_home, lam_away


def confidence_from_probs(p_home: float, p_draw: float, p_away: float) -> float:
    eps = 1e-12
    h = -(p_home * math.log(p_home + eps) + p_draw * math.log(p_draw + eps) + p_away * math.log(p_away + eps))
    return float(max(0.0, min(1.0, 1.0 - (h / math.log(3.0)))))

