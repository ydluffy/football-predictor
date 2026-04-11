from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    base_dir: Path
    artifacts_dir: Path
    data_dir: Path
    model_path: Path
    log_level: str

    @staticmethod
    def from_env() -> "Settings":
        inferred_base_dir = Path(__file__).resolve().parents[2]
        base_dir = Path(os.environ.get("FOOTBALL_PREDICTOR_BASE_DIR", str(inferred_base_dir))).resolve()
        artifacts_dir = base_dir / "artifacts"
        data_dir = base_dir / "data"
        model_path = artifacts_dir / "models" / "baseline_logreg.joblib"
        log_level = os.environ.get("FOOTBALL_PREDICTOR_LOG_LEVEL", "INFO")
        return Settings(
            base_dir=base_dir,
            artifacts_dir=artifacts_dir,
            data_dir=data_dir,
            model_path=model_path,
            log_level=log_level,
        )
