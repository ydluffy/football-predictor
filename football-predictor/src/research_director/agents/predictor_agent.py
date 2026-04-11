from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from models.artifact_manifest import ModelArtifactLoadError
from config.settings import ensure_project_dirs, get_settings
from features.basic_features import build_inference_features
from models.artifact_check import check_model_artifact
from models.model_factory import load_model, predict_model_proba
from research_director.fallback_policy import normalize_fallback_policy
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class PredictorAgent(AgentBase):
    name = "predictor"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "predict",
            "feature_version": str(context.get("feature_version") or "v3"),
            "model_type": str(context.get("model_type") or "logit"),
            "model_path": context.get("model_path"),
        }

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)

        existing = context.get("predictions_path") or context.get("eval_results_path") or context.get("existing_results_path")
        if existing:
            rp = Path(str(existing))
            if not rp.is_absolute():
                rp = (s.project_root / rp).resolve()
            if rp.exists():
                df_res = pd.read_csv(rp)
                if {"p_home", "p_draw", "p_away"} <= set(df_res.columns):
                    mid = df_res.get("match_id")
                    if mid is None:
                        mid = pd.Series(range(len(df_res)), index=df_res.index).astype(str)
                    else:
                        mid = mid.astype(str)

                    p_home = pd.to_numeric(df_res["p_home"], errors="coerce").astype(float)
                    p_draw = pd.to_numeric(df_res["p_draw"], errors="coerce").astype(float)
                    p_away = pd.to_numeric(df_res["p_away"], errors="coerce").astype(float)
                    if "predicted_label" in df_res.columns:
                        pred = df_res["predicted_label"].astype(str)
                    else:
                        proba = np.stack([p_home.to_numpy(dtype=float), p_draw.to_numpy(dtype=float), p_away.to_numpy(dtype=float)], axis=1)
                        labels = np.array(["H", "D", "A"], dtype=object)
                        pred = labels[proba.argmax(axis=1)]

                    out = pd.DataFrame({"match_id": mid, "p_home": p_home, "p_draw": p_draw, "p_away": p_away, "predicted_label": pred})
                    out_path = run_dir / "daily_predictions.csv"
                    out.to_csv(out_path, index=False)
                    finished = self._now()
                    return StepResult(
                        status="completed",
                        summary="predicted",
                        started_at=started,
                        finished_at=finished,
                        artifacts=[StepArtifact(name="daily_predictions", path=str(out_path), artifact_type="csv", metadata={"rows": int(len(out))})],
                        metrics={"rows": int(len(out)), "source": "existing_results", "source_path": str(rp)},
                    )

        inp = Path(str(context.get("today_matches_path") or (run_dir / "daily_matches.csv")))
        if not inp.is_absolute():
            inp = (s.project_root / inp).resolve()
        df = pd.read_csv(inp)

        feature_version = str(context.get("feature_version") or "v3")
        model_type = str(context.get("model_type") or "logit")
        fallback_policy = normalize_fallback_policy(context.get("fallback_policy")) or "graceful"
        model_path = context.get("model_path")
        if model_path:
            mp = Path(str(model_path))
            if not mp.is_absolute():
                mp = (s.project_root / mp).resolve()
        else:
            if model_type == "lightgbm":
                mp = s.lightgbm_model_path
            elif model_type == "stacking":
                mp = s.stacking_meta_model_path
            elif model_type == "stacking_oof":
                mp = s.stacking_oof_meta_model_path
            else:
                mp = s.logit_model_path

        used_model = False
        model_load_error = None
        model_artifact_status = None
        manifest_check = None
        prediction_source = None
        if mp.exists():
            try:
                chk = check_model_artifact(artifact_path=mp, manifest_path=None)
                model_artifact_status = chk.status
                manifest_check = {"status": chk.status, "warnings": chk.warnings, "details": chk.details}
                if chk.status == "incompatible":
                    raise ModelArtifactLoadError(code="artifact_incompatible", message="模型产物不兼容", details=chk.details)
                X, _ = build_inference_features(df, feature_version=feature_version)
                model = load_model(model_type, mp)
                proba_df = predict_model_proba(model_type, model, X)
                p_home = proba_df["p_home"].astype(float)
                p_draw = proba_df["p_draw"].astype(float)
                p_away = proba_df["p_away"].astype(float)
                used_model = True
            except Exception as e:
                if isinstance(e, ModelArtifactLoadError):
                    model_load_error = f"{e.code}: {e.details}"
                else:
                    model_load_error = f"{type(e).__name__}: {e}"
        else:
            model_artifact_status = "incompatible"
            manifest_check = {
                "status": "incompatible",
                "warnings": [],
                "details": {"reason": "artifact_missing", "artifact_path": str(mp)},
            }
            model_load_error = "artifact_missing"

        if not used_model:
            prediction_source = "odds_proxy_fallback"
            if fallback_policy == "strict":
                finished = self._now()
                return StepResult(
                    status="failed",
                    summary="model_load_failed",
                    started_at=started,
                    finished_at=finished,
                    artifacts=[],
                    metrics={
                        "rows": int(len(df)),
                        "model_used": False,
                        "fallback_used": False,
                        "fallback_policy": fallback_policy,
                        "prediction_source": None,
                        "model_artifact_status": model_artifact_status,
                        "manifest_check": manifest_check,
                        "model_type": model_type,
                        "model_path": str(mp),
                        "model_load_error": model_load_error,
                    },
                )

            eps = 1e-12
            oh = pd.to_numeric(df.get("odds_home"), errors="coerce").astype(float).clip(lower=eps)
            od = pd.to_numeric(df.get("odds_draw"), errors="coerce").astype(float).clip(lower=eps)
            oa = pd.to_numeric(df.get("odds_away"), errors="coerce").astype(float).clip(lower=eps)

            imp_h = 1.0 / oh
            imp_d = 1.0 / od
            imp_a = 1.0 / oa
            s_imp = (imp_h + imp_d + imp_a).clip(lower=eps)
            p_home = (imp_h / s_imp).astype(float)
            p_draw = (imp_d / s_imp).astype(float)
            p_away = (imp_a / s_imp).astype(float)
        else:
            prediction_source = "model"

        proba = np.stack([p_home.to_numpy(dtype=float), p_draw.to_numpy(dtype=float), p_away.to_numpy(dtype=float)], axis=1)
        labels = np.array(["H", "D", "A"], dtype=object)
        pred = labels[proba.argmax(axis=1)]

        match_id = df.get("match_id")
        if match_id is None:
            match_id = pd.Series(range(len(df)), index=df.index).astype(str)
        else:
            match_id = match_id.astype(str)

        out = pd.DataFrame(
            {
                "match_id": match_id,
                "p_home": p_home,
                "p_draw": p_draw,
                "p_away": p_away,
                "predicted_label": pred,
                "prediction_source": prediction_source,
            }
        ).replace([np.inf, -np.inf], np.nan)

        # Value Bet & Kelly Criterion calculations
        from models.betting_agent import calculate_ev_and_kelly
        if all(col in df.columns for col in ["odds_home", "odds_draw", "odds_away"]):
            out = calculate_ev_and_kelly(
                predictions=out,
                odds_home=df["odds_home"],
                odds_draw=df["odds_draw"],
                odds_away=df["odds_away"],
                kelly_fraction=0.25
            )

        out_path = run_dir / "daily_predictions.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(out_path, index=False)

        finished = self._now()
        return StepResult(
            status="completed",
            summary="predicted",
            started_at=started,
            finished_at=finished,
            artifacts=[StepArtifact(name="daily_predictions", path=str(out_path), artifact_type="csv", metadata={"rows": int(len(out))})],
            metrics={
                "rows": int(len(out)),
                "model_used": bool(used_model),
                "fallback_used": bool(not used_model),
                "fallback_policy": fallback_policy,
                "prediction_source": prediction_source,
                "model_artifact_status": model_artifact_status,
                "manifest_check": manifest_check,
                "model_type": model_type,
                "model_path": str(mp),
                "model_load_error": model_load_error,
            },
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
