from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class _TeamState:
    elo: float = 1500.0
    goals_for: float = 1.25
    goals_against: float = 1.25
    matches: int = 0


def _poisson_probability(goals: int, expected: float) -> float:
    return math.exp(-expected) * expected**goals / math.factorial(goals)


class WorldCupBaselineModel:
    def __init__(
        self,
        *,
        k_factor: float = 24.0,
        form_alpha: float = 0.18,
        max_goals: int = 8,
        home_advantage: float = 55.0,
        draw_correlation: float = 0.0,
    ) -> None:
        self.k_factor = float(k_factor)
        self.form_alpha = float(form_alpha)
        self.max_goals = int(max_goals)
        self.home_advantage = float(home_advantage)
        self.draw_correlation = float(draw_correlation)
        self._states: defaultdict[str, _TeamState] = defaultdict(_TeamState)
        self._global_goals = 1.25
        self._matches_seen = 0

    def fit(self, matches: pd.DataFrame) -> "WorldCupBaselineModel":
        required = {"home_team", "away_team", "home_goals", "away_goals"}
        missing = required - set(matches.columns)
        if missing:
            raise ValueError(f"missing World Cup training columns: {sorted(missing)}")
        order = [c for c in ("date", "tournament_year", "match_order") if c in matches.columns]
        data = matches.sort_values(order, kind="mergesort") if order else matches
        for row in data.itertuples(index=False):
            self.update(
                str(row.home_team),
                str(row.away_team),
                int(row.home_goals),
                int(row.away_goals),
                neutral=bool(getattr(row, "neutral", True)),
                importance=float(getattr(row, "importance", 1.0)),
            )
        return self

    def expected_goals(
        self,
        home_team: str,
        away_team: str,
        *,
        neutral: bool = True,
    ) -> tuple[float, float]:
        home = self._states[str(home_team)]
        away = self._states[str(away_team)]
        baseline = max(self._global_goals, 0.35)
        home_attack = home.goals_for / baseline
        away_attack = away.goals_for / baseline
        home_defense = home.goals_against / baseline
        away_defense = away.goals_against / baseline
        elo_difference = home.elo - away.elo + (0.0 if neutral else self.home_advantage)
        elo_multiplier = math.exp(elo_difference / 900.0)

        expected_home = baseline * home_attack * away_defense * elo_multiplier
        expected_away = baseline * away_attack * home_defense / elo_multiplier
        return float(np.clip(expected_home, 0.15, 4.5)), float(np.clip(expected_away, 0.15, 4.5))

    def predict_match(
        self,
        home_team: str,
        away_team: str,
        *,
        neutral: bool = True,
        goal_scale: float = 1.0,
        home_goal_multiplier: float = 1.0,
        away_goal_multiplier: float = 1.0,
    ) -> dict[str, object]:
        expected_home, expected_away = self.expected_goals(
            home_team,
            away_team,
            neutral=neutral,
        )
        scale = float(np.clip(goal_scale, 0.7, 1.4))
        expected_home = float(
            np.clip(
                expected_home
                * scale
                * float(np.clip(home_goal_multiplier, 0.75, 1.25)),
                0.15,
                5.5,
            )
        )
        expected_away = float(
            np.clip(
                expected_away
                * scale
                * float(np.clip(away_goal_multiplier, 0.75, 1.25)),
                0.15,
                5.5,
            )
        )
        home_probs = np.array(
            [_poisson_probability(goals, expected_home) for goals in range(self.max_goals + 1)]
        )
        away_probs = np.array(
            [_poisson_probability(goals, expected_away) for goals in range(self.max_goals + 1)]
        )
        matrix = np.outer(home_probs, away_probs)
        if self.draw_correlation != 0.0 and self.max_goals >= 1:
            rho = self.draw_correlation
            corrections = {
                (0, 0): 1.0 - expected_home * expected_away * rho,
                (0, 1): 1.0 + expected_home * rho,
                (1, 0): 1.0 + expected_away * rho,
                (1, 1): 1.0 - rho,
            }
            for (home_goals, away_goals), correction in corrections.items():
                matrix[home_goals, away_goals] *= max(correction, 0.01)
        matrix = matrix / matrix.sum()
        p_home = float(np.tril(matrix, k=-1).sum())
        p_draw = float(np.trace(matrix))
        p_away = float(np.triu(matrix, k=1).sum())
        score_index = np.unravel_index(int(matrix.argmax()), matrix.shape)
        return {
            "home_team": str(home_team),
            "away_team": str(away_team),
            "expected_home_goals": expected_home,
            "expected_away_goals": expected_away,
            "goal_environment_scale": scale,
            "p_home": p_home,
            "p_draw": p_draw,
            "p_away": p_away,
            "most_likely_home_goals": int(score_index[0]),
            "most_likely_away_goals": int(score_index[1]),
            "score_matrix": matrix,
        }

    def update(
        self,
        home_team: str,
        away_team: str,
        home_goals: int,
        away_goals: int,
        *,
        neutral: bool = True,
        importance: float = 1.0,
    ) -> None:
        home = self._states[str(home_team)]
        away = self._states[str(away_team)]
        home_rating = home.elo + (0.0 if neutral else self.home_advantage)
        expected_home_result = 1.0 / (1.0 + 10.0 ** ((away.elo - home_rating) / 400.0))
        actual_home_result = 1.0 if home_goals > away_goals else 0.5 if home_goals == away_goals else 0.0
        weight = float(np.clip(importance, 0.1, 2.0))
        delta = self.k_factor * weight * (actual_home_result - expected_home_result)
        home.elo += delta
        away.elo -= delta

        alpha = float(np.clip(self.form_alpha * weight, 0.02, 0.45))
        home.goals_for = (1.0 - alpha) * home.goals_for + alpha * float(home_goals)
        home.goals_against = (1.0 - alpha) * home.goals_against + alpha * float(away_goals)
        away.goals_for = (1.0 - alpha) * away.goals_for + alpha * float(away_goals)
        away.goals_against = (1.0 - alpha) * away.goals_against + alpha * float(home_goals)
        home.matches += 1
        away.matches += 1

        total_goals_per_team = (float(home_goals) + float(away_goals)) / 2.0
        self._global_goals = (
            self._global_goals * self._matches_seen + total_goals_per_team
        ) / (self._matches_seen + 1)
        self._matches_seen += 1

    def team_rating(self, team: str) -> float:
        return float(self._states[str(team)].elo)
