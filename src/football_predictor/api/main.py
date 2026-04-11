from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from loguru import logger

from football_predictor.agents.verifier import compute_risk_flags
from football_predictor.artifacts import read_model
from football_predictor.decision.orchestrator import apply_risk_adjustment
from football_predictor.features.baseline import build_baseline_features
from football_predictor.models.baseline_logreg import predict_proba
from football_predictor.schemas import MatchRecord, PredictionProba, PredictionRecord, RiskFlag
from football_predictor.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    s = settings or Settings.from_env()
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if not s.model_path.exists():
            raise RuntimeError(f"model not found: {s.model_path}")
        app.state.trained = read_model(s.model_path)
        app.state.settings = s
        logger.info("api:start model_path={}\n", str(s.model_path))
        yield

    app = FastAPI(title="Football Match Prediction API", version="0.1.0", lifespan=lifespan)

    logger.remove()
    logger.add(lambda msg: print(msg, end=""), level=s.log_level)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok"}

    @app.post("/predict", response_model=PredictionRecord)
    def predict(match: MatchRecord) -> PredictionRecord:
        trained = getattr(app.state, "trained", None)
        if trained is None:
            raise HTTPException(status_code=503, detail="model not loaded")

        df = pd.DataFrame([match.model_dump()])
        x_df = build_baseline_features(df)
        x = x_df.to_numpy(dtype=float)
        proba = predict_proba(trained, x)[0]

        risk_flags_raw = compute_risk_flags(df.iloc[0])
        decision = apply_risk_adjustment(
            model_proba=np.array([proba[0], proba[1], proba[2]], dtype=float),
            risk_flags=risk_flags_raw,
        )
        risk_flags = [RiskFlag(code=f.code, detail=f.detail) for f in decision.risk_flags]

        return PredictionRecord(
            match_id=match.match_id,
            date=match.date,
            league=match.league,
            home_team=match.home_team,
            away_team=match.away_team,
            proba=PredictionProba(p_home=float(decision.proba[0]), p_draw=float(decision.proba[1]), p_away=float(decision.proba[2])),
            model_name=getattr(trained, "model_name", "unknown"),
            risk_flags=risk_flags,
            requires_review=decision.requires_review,
            calibration=getattr(trained, "calibration", "sigmoid"),
        )

    return app


app = create_app()
