from __future__ import annotations

from pathlib import Path


def test_football_predictor_is_the_only_python_project() -> None:
    python_project = Path(__file__).resolve().parents[1]
    repository_root = python_project.parent

    assert (python_project / "pyproject.toml").is_file()
    assert (python_project / "data" / "templates" / "sample_matches.csv").is_file()
    assert (repository_root / "scripts" / "project.ps1").is_file()

    assert not (repository_root / "pyproject.toml").exists()
    assert not (repository_root / "src").exists()
    assert not (repository_root / "tests").exists()
