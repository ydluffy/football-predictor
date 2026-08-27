from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from models.sporttery_handicap_inference import predict_current_handicaps


def load_shadow_model(model_path: str | Path, metadata_path: str | Path) -> tuple[Any, dict[str, Any]]:
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if metadata.get("deployment_mode") != "shadow_only":
        raise ValueError("model metadata is not shadow-only")
    if metadata.get("can_trigger_bet_alone") is not False or metadata.get("can_write_production_ledger") is not False:
        raise ValueError("shadow model metadata has unsafe permissions")
    return joblib.load(model_path), metadata


def predict_current_handicaps_shadow_v2(
    markets: pd.DataFrame,
    external_history: pd.DataFrame,
    *,
    model: Any,
    metadata: dict[str, Any],
    analysis_at: object | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if metadata.get("deployment_mode") != "shadow_only":
        raise ValueError("v2 inference requires shadow-only metadata")
    predictions, base_audit = predict_current_handicaps(
        markets,
        external_history,
        model=model,
        metadata=metadata,
        analysis_at=analysis_at,
    )
    eligible = predictions["handicap_model_usage"].isin(["production_auxiliary", "limited_auxiliary"])
    predictions.loc[eligible, "handicap_model_usage"] = "shadow_only"
    predictions.loc[eligible, "handicap_model_reason"] = "v2_shadow_not_production_eligible"
    predictions["shadow_can_trigger_bet"] = False
    predictions["shadow_can_write_production_ledger"] = False
    audit = {
        "rows": int(len(predictions)),
        "shadow_eligible": int(eligible.sum()),
        "blocked": int(predictions["handicap_model_usage"].eq("blocked").sum()),
        "analysis_at": base_audit["analysis_at"],
        "model_id": metadata.get("model_id", ""),
        "mode": "shadow_only",
        "can_trigger_bet_alone": False,
        "can_write_production_ledger": False,
    }
    return predictions, audit
