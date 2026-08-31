from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from config.settings import ensure_project_dirs, get_settings
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class ModelTrainerAgent(AgentBase):
    name = "model_trainer"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "train_candidate_model",
            "model_type": str(context.get("model_type") or "lightgbm"),
            "feature_version": str(context.get("feature_version") or "v3"),
            "calibration": str(context.get("calibration") or "none"),
            "cv": str(context.get("cv") or "false"),
            "use_verifier": str(context.get("use_verifier") or "false"),
            "data_path": context.get("matches_path") or context.get("data_path"),
            "isolate": bool(context.get("isolate", True)),
        }

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()
        code_root = Path(__file__).resolve().parents[3]

        if not bool(getattr(gate, "allow_high_risk", False)):
            finished = self._now()
            return StepResult(
                status="blocked",
                summary="blocked_high_risk",
                started_at=started,
                finished_at=finished,
                artifacts=[],
                metrics={},
            )

        model_type = str(context.get("model_type") or "lightgbm")
        feature_version = str(context.get("feature_version") or "v3")
        calibration = str(context.get("calibration") or "none")
        cv = str(context.get("cv") or "false")
        use_verifier = str(context.get("use_verifier") or "false")
        data_path = context.get("data_path") or context.get("matches_path")
        isolate = bool(context.get("isolate", True))

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        if isolate:
            sandbox_root = run_dir / "sandbox_project"
            sandbox_root.mkdir(parents=True, exist_ok=True)
            env["FOOTBALL_PREDICTOR_ROOT"] = str(sandbox_root)

        cmd = [
            sys.executable,
            "scripts/run_train.py",
            "--model-type",
            model_type,
            "--feature-version",
            feature_version,
            "--calibration",
            calibration,
            "--cv",
            cv,
            "--use-verifier",
            use_verifier,
        ]
        if data_path:
            cmd.extend(["--data-path", str(data_path)])
        proc = subprocess.run(cmd, cwd=str(code_root), env=env, capture_output=True, text=True)

        finished = self._now()
        stdout_path = run_dir / "train_stdout.txt"
        stderr_path = run_dir / "train_stderr.txt"
        stdout_path.write_text(proc.stdout or "", encoding="utf-8")
        stderr_path.write_text(proc.stderr or "", encoding="utf-8")

        artifacts = [
            StepArtifact(name="train_stdout", path=str(stdout_path), artifact_type="txt", metadata={"bytes": int(stdout_path.stat().st_size)}),
            StepArtifact(name="train_stderr", path=str(stderr_path), artifact_type="txt", metadata={"bytes": int(stderr_path.stat().st_size)}),
        ]

        parsed_metrics: dict[str, Any] = {}
        produced_paths: list[Path] = []
        for line in (proc.stdout or "").splitlines():
            t = line.strip()
            if t.startswith("{") and t.endswith("}"):
                try:
                    parsed_metrics = json.loads(t)
                except Exception:
                    parsed_metrics = {}
            if (t.endswith((".csv", ".json", ".pkl")) or (".csv" in t or ".json" in t or ".pkl" in t)) and (":" in t or "/" in t or "\\" in t):
                try:
                    p = Path(t)
                    if p.exists():
                        produced_paths.append(p)
                except Exception:
                    continue

        if proc.returncode != 0:
            return StepResult(
                status="failed",
                summary="train_failed",
                started_at=started,
                finished_at=finished,
                artifacts=artifacts,
                metrics={"returncode": int(proc.returncode)},
            )

        for p in produced_paths:
            ext = p.suffix.lower().lstrip(".") or "file"
            artifacts.append(StepArtifact(name=p.name, path=str(p), artifact_type=ext, metadata={}))

        return StepResult(
            status="completed",
            summary="trained",
            started_at=started,
            finished_at=finished,
            artifacts=artifacts,
            metrics={
                "model_type": model_type,
                "feature_version": feature_version,
                "calibration": calibration,
                "cv": cv,
                "use_verifier": use_verifier,
                "data_path": str(data_path) if data_path else None,
                "isolate": bool(isolate),
                "train_metrics": parsed_metrics,
            },
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
