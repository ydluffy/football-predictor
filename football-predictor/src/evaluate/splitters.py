from __future__ import annotations

import numpy as np
import pandas as pd


def time_based_split(
    df: pd.DataFrame,
    date_col: str = "date",
    test_size: float = 0.2,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if date_col not in df.columns:
        raise ValueError(f"缺少 date 字段: {date_col}")

    if not (0.0 < float(test_size) < 1.0):
        raise ValueError("test_size 必须在 (0, 1) 区间内")

    data = df.copy()
    data[date_col] = pd.to_datetime(data[date_col], errors="coerce")
    if data[date_col].isna().any():
        raise ValueError("date 存在无法解析的值")

    data = data.sort_values(date_col, kind="mergesort").reset_index(drop=True)
    n = len(data)
    if n == 0:
        raise ValueError("空数据：DataFrame 无任何记录")

    tentative = int(np.floor(n * (1.0 - float(test_size))))
    if tentative <= 0 or tentative >= n:
        raise ValueError("test_size 导致无法切分出训练/测试集")

    last_train_date = data.loc[tentative - 1, date_col]
    mask = data[date_col].gt(last_train_date).to_numpy()
    if not mask.any():
        raise ValueError("无法构造训练集早于测试集的时间切分")
    test_start = int(np.where(mask)[0][0])

    train_df = data.iloc[:test_start].reset_index(drop=True)
    test_df = data.iloc[test_start:].reset_index(drop=True)
    if train_df[date_col].max() >= test_df[date_col].min():
        raise ValueError("训练集必须早于测试集")
    return train_df, test_df
