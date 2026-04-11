from __future__ import annotations

import importlib.util
from pathlib import Path

from config.settings import get_settings


def _load_main():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "run_research_director.py"
    spec = importlib.util.spec_from_file_location("run_research_director_script", str(script_path))
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 scripts/run_research_director.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, module.main


def test_run_research_director_parses_candidate_upgrade_alias_and_prints(monkeypatch, tmp_path, capsys):
    module, main = _load_main()
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    calls = {}

    class _FakeDirector:
        def __init__(self, gate=None):
            self.gate = gate

        def run(self, workflow, *, context=None, run_id=None, resume=False):
            calls["workflow"] = workflow
            calls["context"] = dict(context or {})
            return {
                "run_id": "RID",
                "run_dir": str(root / "artifacts" / "research_director" / "runs" / "RID"),
                "workflow_name": workflow,
                "status": "completed",
                "steps": [],
                "artifacts": [{"name": "x", "path": "p", "artifact_type": "json"}],
                "metrics": {},
                "decision": {"decision": "keep_current", "gate_reasons": ["high_risk_blocked"]},
            }

    monkeypatch.setattr(module, "ResearchDirector", _FakeDirector)
    monkeypatch.setattr(module, "preflight_real_data", lambda **kwargs: type("X", (), {"status": "ok", "reasons": []})())
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_research_director.py",
            "--workflow",
            "candidate_upgrade",
            "--model-type",
            "logit",
            "--feature-version",
            "v3",
            "--calibration",
            "none",
            "--use-verifier",
            "false",
            "--data-mode",
            "mock",
        ],
    )
    main()
    out = capsys.readouterr().out
    assert calls["workflow"] == "candidate_model_upgrade"
    assert "run_id=RID" in out
    assert "decision=" in out
    assert "gate_reasons=" in out


def test_run_research_director_show_registry_without_workflow(monkeypatch, tmp_path, capsys):
    module, main = _load_main()
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    class _M:
        def __init__(self, model_id, status):
            self.model_id = model_id
            self.model_type = "logit"
            self.feature_version = "v3"
            self.calibration_method = "none"
            self.status = status
            self.artifact_path = "p.pkl"

    class _Reg:
        def __init__(self):
            self.candidate_models = [_M("c1", "candidate"), _M("c2", "rejected")]

    monkeypatch.setattr(module, "get_current_production_model", lambda: _M("p1", "production"))
    monkeypatch.setattr(module, "load_registry", lambda: _Reg())
    monkeypatch.setattr(module, "preflight_real_data", lambda **kwargs: type("X", (), {"status": "ok", "reasons": []})())

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_research_director.py",
            "--show-registry",
            "true",
            "--registry-limit",
            "1",
        ],
    )
    main()
    out = capsys.readouterr().out
    assert "registry.production" in out
    assert "model_id=p1" in out
    assert "registry.candidates_recent" in out
    assert "model_id=c2" in out


def test_run_research_director_real_mode_prints_preflight_and_paths(monkeypatch, tmp_path, capsys):
    module, main = _load_main()
    root = tmp_path / "football-predictor"
    monkeypatch.setenv("FOOTBALL_PREDICTOR_ROOT", str(root))
    get_settings.cache_clear()

    class _FakeDirector:
        def __init__(self, gate=None):
            self.gate = gate

        def run(self, workflow, *, context=None, run_id=None, resume=False):
            return {
                "run_id": "RID",
                "run_dir": str(root / "artifacts" / "research_director" / "runs" / "RID"),
                "workflow_name": workflow,
                "status": "completed",
                "steps": [],
                "artifacts": [],
                "metrics": {"steps": {"data": {"standardized_data_path": "std.csv", "validation_path": "val.json", "missing_report_path": "miss.csv"}}},
                "decision": None,
            }

    monkeypatch.setattr(module, "ResearchDirector", _FakeDirector)
    monkeypatch.setattr(module, "preflight_real_data", lambda **kwargs: type("X", (), {"status": "ok", "reasons": ["x"]})())

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_research_director.py",
            "--workflow",
            "daily_prediction",
            "--data-mode",
            "real",
            "--raw-matches-csv",
            str(root / "data" / "external" / "incoming_matches.csv"),
            "--mapping-path",
            str(root / "data" / "mappings" / "example_mapping_v3.json"),
        ],
    )
    main()
    out = capsys.readouterr().out
    assert "raw_matches_csv=" in out
    assert "mapping_path=" in out
    assert "preflight_status=" in out
    assert "preflight_reasons=" in out
    assert "standardized_data_path=std.csv" in out
    assert "validation_path=val.json" in out
    assert "missing_report_path=miss.csv" in out
