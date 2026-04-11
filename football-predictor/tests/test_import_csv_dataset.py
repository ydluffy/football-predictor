from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from data.import_csv_dataset import import_csv_dataset, summarize_dataset


def test_import_csv_dataset_reads_and_preserves_columns(tmp_path):
    p = Path(tmp_path) / "x.csv"
    df = pd.DataFrame({"A": [1, 2], "B b": ["x", "y"]})
    df.to_csv(p, index=False, encoding="utf-8")

    out = import_csv_dataset(str(p))
    assert list(out.columns) == ["A", "B b"]
    s = summarize_dataset(out)
    assert s.row_count == 2
    assert s.column_count == 2
    assert s.columns == ["A", "B b"]


def test_import_csv_dataset_missing_path_raises(tmp_path):
    p = Path(tmp_path) / "missing.csv"
    with pytest.raises(FileNotFoundError):
        import_csv_dataset(str(p))


def test_import_csv_dataset_directory_path_raises(tmp_path):
    with pytest.raises(IsADirectoryError):
        import_csv_dataset(str(tmp_path))


def test_import_csv_dataset_empty_file_raises(tmp_path):
    p = Path(tmp_path) / "empty.csv"
    p.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        import_csv_dataset(str(p))

