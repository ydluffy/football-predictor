from __future__ import annotations

from typing import Any

from research_director.agents.data_scout_agent import DataScoutAgent
from research_director.agents.evaluator_agent import EvaluatorAgent
from research_director.agents.feature_lab_agent import FeatureLabAgent
from research_director.agents.model_trainer_agent import ModelTrainerAgent
from research_director.agents.optimizer_agent import OptimizerAgent
from research_director.agents.predictor_agent import PredictorAgent
from research_director.agents.verifier_agent import VerifierAgent


class TaskRouter:
    def __init__(self) -> None:
        self._agents: dict[str, Any] = {
            "data_scout": DataScoutAgent(),
            "feature_lab": FeatureLabAgent(),
            "model_trainer": ModelTrainerAgent(),
            "evaluator": EvaluatorAgent(),
            "predictor": PredictorAgent(),
            "verifier": VerifierAgent(),
            "optimizer": OptimizerAgent(),
        }

    def get(self, agent_name: str):
        return self._agents.get(str(agent_name))

