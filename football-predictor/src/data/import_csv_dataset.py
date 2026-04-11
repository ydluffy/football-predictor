from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class CsvDatasetSummary:
    row_count: int
    column_count: int
    columns: list[str]


def import_csv_dataset(input_path: str) -> pd.DataFrame:
    p = Path(input_path)
    if not p.exists():
        raise FileNotFoundError(f"找不到文件: {input_path}")
    if p.is_dir():
        raise IsADirectoryError(f"输入路径是目录: {input_path}")
    try:
        df = pd.read_csv(p, encoding="utf-8")
    except UnicodeDecodeError as e:
        raise UnicodeDecodeError(e.encoding, e.object, e.start, e.end, "CSV 编码错误：请使用 UTF-8 或先转码") from e
    except pd.errors.EmptyDataError as e:
        raise ValueError("空文件：CSV 无任何内容") from e
    except Exception as e:
        raise ValueError(f"CSV 读取失败: {e}") from e

    if df.shape[0] == 0:
        raise ValueError("空文件：CSV 无任何记录")
    return df


def summarize_dataset(df: pd.DataFrame) -> CsvDatasetSummary:
    return CsvDatasetSummary(
        row_count=int(df.shape[0]),
        column_count=int(df.shape[1]),
        columns=[str(c) for c in df.columns],
    )

