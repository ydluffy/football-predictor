from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import joblib


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_dataframe_csv(path: Path, df: pd.DataFrame) -> None:
    ensure_dir(path.parent)
    df.to_csv(path, index=False)


def write_model(path: Path, model: object) -> None:
    ensure_dir(path.parent)
    joblib.dump(model, path)


def read_model(path: Path) -> object:
    return joblib.load(path)
