from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV


_LABELS = ("H", "D", "A")
_LABEL_TO_COL = {"H": "p_home", "D": "p_draw", "A": "p_away"}
_PROBA_COLUMNS = ["p_home", "p_draw", "p_away"]


def fit_calibrator(
    model,
    X_train,
    y_train,
    method: str = "sigmoid",
    *,
    cv: int = 3,
):
    if method not in {"sigmoid", "isotonic"}:
        raise ValueError("method 仅支持 sigmoid/isotonic")

    y = pd.Series(y_train).astype(str).str.upper()
    invalid = sorted(set(y.unique()) - set(_LABELS))
    if invalid:
        raise ValueError(f"y_train 存在非法取值: {invalid}")

    counts = y.value_counts()
    min_count = int(counts.min()) if len(counts) else 0
    effective_cv = int(min(cv, min_count))
    if effective_cv < 2:
        raise ValueError("样本不足：无法进行校准交叉验证（至少需要每类 >= 2 条样本）")

    if method == "isotonic":
        if len(y) < 100 or min_count < 10:
            raise ValueError("isotonic 样本不足：建议改用 sigmoid 或增加样本量")

    calibrator = CalibratedClassifierCV(estimator=model, method=method, cv=effective_cv)
    calibrator.fit(X_train, y)
    return calibrator


def predict_calibrated_proba(calibrator, X_test) -> pd.DataFrame:
    proba = calibrator.predict_proba(X_test)
    classes = [str(c).upper() for c in calibrator.classes_]

    out = pd.DataFrame(0.0, index=getattr(X_test, "index", None), columns=_PROBA_COLUMNS)
    for i, c in enumerate(classes):
        col = _LABEL_TO_COL.get(c)
        if col:
            out[col] = proba[:, i]

    p = out.to_numpy(dtype=float)
    p = np.clip(p, 1e-15, 1.0)
    row_sum = p.sum(axis=1, keepdims=True)
    row_sum[row_sum == 0.0] = 1.0
    p = p / row_sum
    out.loc[:, _PROBA_COLUMNS] = p
    return out
