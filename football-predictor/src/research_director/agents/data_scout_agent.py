from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from config.settings import ensure_project_dirs, get_settings
from data.mock_data_generator import generate_mock_matches
from data.validate_dataset import validate_matches_dataset
from ingest.real_data_ingest import ingest_matches_csv
from research_director.agents.agent_base import AgentBase, StepArtifact, StepResult


class DataScoutAgent(AgentBase):
    name = "data_scout"

    def plan(self, *, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": "ensure_today_matches_exists",
            "feature_version": str(context.get("feature_version") or "v3"),
            "data_mode": str(context.get("data_mode") or "mock"),
            "raw_matches_csv": context.get("raw_matches_csv"),
            "today_matches_path": context.get("today_matches_path"),
            "mapping_spec": context.get("mapping_spec"),
            "mapping_path": context.get("mapping_path"),
            "data_sources": context.get("data_sources"),
            "keep_actual_result": bool(context.get("keep_actual_result", False)),
            "output_csv_path": context.get("output_csv_path"),
        }

    def execute(self, *, context: dict[str, Any], gate: Any) -> StepResult:
        ensure_project_dirs()
        s = get_settings()
        started = self._now()
        code_root = Path(__file__).resolve().parents[3]

        run_dir = Path(str(context.get("run_dir") or (s.research_director_runs_dir / str(context["run_id"]))))
        run_dir.mkdir(parents=True, exist_ok=True)
        keep_actual = bool(context.get("keep_actual_result", False))
        default_out = run_dir / ("real_matches_standardized.csv" if keep_actual else "daily_matches.csv")
        today_path = Path(str(context.get("output_csv_path") or context.get("today_matches_path") or default_out))
        if not today_path.is_absolute():
            today_path = (s.project_root / today_path).resolve()

        feature_version = str(context.get("feature_version") or "v3")
        data_mode = str(context.get("data_mode") or "mock")
        raw_matches_csv = context.get("raw_matches_csv")
        mapping_path = context.get("mapping_path")
        mapping_spec = context.get("mapping_spec")
        n_rows = int(context.get("n_rows") or 200)
        data_sources = context.get("data_sources")

        created = False
        artifacts: list[StepArtifact] = []
        if data_mode == "real" and not raw_matches_csv and not (isinstance(data_sources, list) and data_sources):
            finished = self._now()
            return StepResult(
                status="review_required",
                summary="real_mode_missing_input",
                started_at=started,
                finished_at=finished,
                artifacts=[],
                metrics={"error_message": "data_mode=real 需要提供 raw_matches_csv + mapping_path（或 data_sources）"},
            )
        if data_mode == "real" and raw_matches_csv:
            raw_p = Path(str(raw_matches_csv))
            if not raw_p.is_absolute():
                raw_p = (s.project_root / raw_p).resolve()
            if not raw_p.exists():
                finished = self._now()
                return StepResult(
                    status="review_required",
                    summary="raw_matches_csv_not_found",
                    started_at=started,
                    finished_at=finished,
                    artifacts=[],
                    metrics={"error_message": f"raw_matches_csv 不存在: {raw_p}"},
                )

            if not mapping_path:
                finished = self._now()
                return StepResult(
                    status="review_required",
                    summary="mapping_path_missing",
                    started_at=started,
                    finished_at=finished,
                    artifacts=[],
                    metrics={"error_message": "data_mode=real 需要提供 mapping_path"},
                )

            mp = Path(str(mapping_path))
            if not mp.is_absolute():
                mp = (s.project_root / mp).resolve()
            if not mp.exists():
                finished = self._now()
                return StepResult(
                    status="review_required",
                    summary="mapping_path_not_found",
                    started_at=started,
                    finished_at=finished,
                    artifacts=[],
                    metrics={"error_message": f"mapping_path 不存在: {mp}"},
                )

            import_root = run_dir / "import_sandbox"
            env = dict(os.environ)
            env["FOOTBALL_PREDICTOR_ROOT"] = str(import_root)

            cmd = [
                sys.executable,
                "scripts/import_real_csv.py",
                "--input-path",
                str(raw_p),
                "--mapping-path",
                str(mp),
                "--feature-version",
                str(feature_version),
            ]
            proc = subprocess.run(cmd, cwd=str(code_root), env=env, capture_output=True, text=True)
            stdout_path = run_dir / "data_scout_stdout.txt"
            stderr_path = run_dir / "data_scout_stderr.txt"
            stdout_path.write_text(proc.stdout or "", encoding="utf-8")
            stderr_path.write_text(proc.stderr or "", encoding="utf-8")
            artifacts.append(StepArtifact(name="data_scout_stdout", path=str(stdout_path), artifact_type="txt", metadata={}))
            artifacts.append(StepArtifact(name="data_scout_stderr", path=str(stderr_path), artifact_type="txt", metadata={}))
            if proc.returncode != 0:
                finished = self._now()
                return StepResult(
                    status="failed",
                    summary="import_real_csv_failed",
                    started_at=started,
                    finished_at=finished,
                    artifacts=artifacts,
                    metrics={"returncode": int(proc.returncode), "error_message": "import_real_csv.py 执行失败"},
                )

            standardized_src = import_root / "data" / "processed" / "real_matches_standardized.csv"
            if not standardized_src.exists():
                finished = self._now()
                return StepResult(
                    status="failed",
                    summary="standardized_output_missing",
                    started_at=started,
                    finished_at=finished,
                    artifacts=artifacts,
                    metrics={"error_message": f"标准化输出缺失: {standardized_src}"},
                )

            df = pd.read_csv(standardized_src)
            if not keep_actual and "actual_result" in df.columns:
                df["actual_result"] = ""
            today_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(today_path, index=False)
            created = True

            preview_src = import_root / "data" / "interim" / "imported_preview.csv"
            preview_dst = run_dir / "imported_preview.csv"
            if preview_src.exists():
                preview_dst.write_bytes(preview_src.read_bytes())
                artifacts.append(StepArtifact(name="import_preview_path", path=str(preview_dst), artifact_type="csv", metadata={}))

            import_summary_dst = run_dir / "import_summary.json"
            import_summary_src = import_root / "artifacts" / "eval" / "import_summary.json"
            if import_summary_src.exists():
                import_summary_dst.write_bytes(import_summary_src.read_bytes())
                artifacts.append(StepArtifact(name="import_summary_path", path=str(import_summary_dst), artifact_type="json", metadata={}))

            mapping_report_dst = run_dir / "field_mapping_report.csv"
            mapping_report_src = import_root / "artifacts" / "eval" / "field_mapping_report.csv"
            if mapping_report_src.exists():
                mapping_report_dst.write_bytes(mapping_report_src.read_bytes())
                artifacts.append(StepArtifact(name="field_mapping_report_path", path=str(mapping_report_dst), artifact_type="csv", metadata={}))

            validation_dst = run_dir / "import_validation.json"
            validation_src = import_root / "artifacts" / "eval" / "dataset_validation.json"
            if validation_src.exists():
                validation_dst.write_bytes(validation_src.read_bytes())
                artifacts.append(StepArtifact(name="validation_path", path=str(validation_dst), artifact_type="json", metadata={}))

            missing_dst = run_dir / "import_missing_report.csv"
            missing_src = import_root / "artifacts" / "eval" / "dataset_missing_report.csv"
            if missing_src.exists():
                missing_dst.write_bytes(missing_src.read_bytes())
                artifacts.append(StepArtifact(name="missing_report_path", path=str(missing_dst), artifact_type="csv", metadata={}))

        elif isinstance(data_sources, list) and data_sources:
            dfs: list[pd.DataFrame] = []
            sources_dir = run_dir / "sources"
            sources_dir.mkdir(parents=True, exist_ok=True)
            for idx, src in enumerate(data_sources):
                if not isinstance(src, dict):
                    continue
                src_raw = src.get("raw_matches_csv")
                if not src_raw:
                    continue
                src_fv = str(src.get("feature_version") or feature_version)
                src_spec = src.get("mapping_spec")
                out_p = sources_dir / f"source_{idx+1:02d}_standardized.csv"
                ingest_out = ingest_matches_csv(
                    str(src_raw),
                    output_csv_path=str(out_p),
                    mapping_spec=src_spec,
                    mapping_record_path=str(sources_dir / f"source_{idx+1:02d}_mapping_record.json"),
                    validation_path=str(sources_dir / f"source_{idx+1:02d}_validation.json"),
                    missing_report_path=str(sources_dir / f"source_{idx+1:02d}_missing.csv"),
                    feature_version=src_fv,
                )
                df_i = pd.read_csv(ingest_out.output_path)
                dfs.append(df_i)
                artifacts.append(StepArtifact(name=f"source_{idx+1:02d}_standardized", path=str(ingest_out.output_path), artifact_type="csv", metadata={"rows": int(len(df_i))}))
                artifacts.append(StepArtifact(name=f"source_{idx+1:02d}_validation", path=str(ingest_out.validation_path), artifact_type="json", metadata={}))
                artifacts.append(StepArtifact(name=f"source_{idx+1:02d}_missing", path=str(ingest_out.missing_report_path), artifact_type="csv", metadata={}))

            if not dfs:
                df = pd.DataFrame()
            else:
                df = pd.concat(dfs, axis=0, ignore_index=True)
            created = True
            if not keep_actual and "actual_result" in df.columns:
                df["actual_result"] = ""
            today_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(today_path, index=False)
        elif raw_matches_csv and mapping_path:
            mp = Path(str(mapping_path))
            if not mp.is_absolute():
                mp = (s.project_root / mp).resolve()
            cmd = [
                sys.executable,
                "scripts/import_real_csv.py",
                "--input-path",
                str(raw_matches_csv),
                "--mapping-path",
                str(mp),
                "--feature-version",
                str(feature_version),
            ]
            proc = subprocess.run(cmd, cwd=str(code_root), env=dict(os.environ), capture_output=True, text=True)
            (run_dir / "data_scout_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
            (run_dir / "data_scout_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
            artifacts.append(StepArtifact(name="data_scout_stdout", path=str(run_dir / "data_scout_stdout.txt"), artifact_type="txt", metadata={}))
            artifacts.append(StepArtifact(name="data_scout_stderr", path=str(run_dir / "data_scout_stderr.txt"), artifact_type="txt", metadata={}))
            if proc.returncode != 0:
                finished = self._now()
                return StepResult(status="failed", summary="import_real_csv_failed", started_at=started, finished_at=finished, artifacts=artifacts, metrics={"returncode": int(proc.returncode)})

            standardized = s.data_processed_dir / "real_matches_standardized.csv"
            df = pd.read_csv(standardized)
            if not keep_actual and "actual_result" in df.columns:
                df["actual_result"] = ""
            today_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(today_path, index=False)
            created = True
        elif raw_matches_csv:
            ingest_out = ingest_matches_csv(
                raw_matches_csv,
                output_csv_path=str(today_path),
                mapping_spec=mapping_spec,
                mapping_record_path=str(run_dir / "ingest_mapping_record.json"),
                validation_path=str(run_dir / "ingest_validation.json"),
                missing_report_path=str(run_dir / "ingest_missing_report.csv"),
                feature_version=feature_version,
            )
            created = True
            df = pd.read_csv(ingest_out.output_path)
            if not keep_actual and "actual_result" in df.columns:
                df["actual_result"] = ""
                df.to_csv(today_path, index=False)
        elif not today_path.exists():
            if data_mode == "real":
                finished = self._now()
                return StepResult(
                    status="review_required",
                    summary="real_mode_no_input",
                    started_at=started,
                    finished_at=finished,
                    artifacts=[],
                    metrics={"error_message": "data_mode=real 未提供 raw_matches_csv/mapping_path，且 today_matches_path 不存在，禁止 fallback 到 mock"},
                )
            cmd = [sys.executable, "scripts/bootstrap_mock_data.py", "--n-rows", str(n_rows), "--run-train", "false"]
            proc = subprocess.run(cmd, cwd=str(code_root), env=dict(os.environ), capture_output=True, text=True)
            (run_dir / "data_scout_stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
            (run_dir / "data_scout_stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
            artifacts.append(StepArtifact(name="data_scout_stdout", path=str(run_dir / "data_scout_stdout.txt"), artifact_type="txt", metadata={}))
            artifacts.append(StepArtifact(name="data_scout_stderr", path=str(run_dir / "data_scout_stderr.txt"), artifact_type="txt", metadata={}))
            if proc.returncode != 0:
                df = generate_mock_matches(n_rows=n_rows, feature_version="v1")
            else:
                if feature_version == "v1":
                    src = s.data_raw_dir / "mock_matches_v1.csv"
                elif feature_version == "v2":
                    src = s.data_raw_dir / "mock_matches_v2.csv"
                else:
                    src = s.data_raw_dir / "mock_matches_v3.csv"
                df = pd.read_csv(src) if src.exists() else generate_mock_matches(n_rows=n_rows, feature_version="v1")

            if not keep_actual and "actual_result" in df.columns:
                df["actual_result"] = ""
            today_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(today_path, index=False)
            created = True
        else:
            df = pd.read_csv(today_path)

        validation_path = run_dir / "dataset_validation.json"
        missing_path = run_dir / "dataset_missing_report.csv"
        report = validate_matches_dataset(df, feature_version, output_json_path=str(validation_path), missing_report_csv_path=str(missing_path))
        data_quality_ok = bool(report.get("is_trainable", len(report.get("required_fields_missing") or []) == 0))
        required_fields_missing = list(report.get("required_fields_missing") or [])
        required_field_null_counts = dict(report.get("required_field_null_counts") or {})
        row_count = int(len(df))

        finished = self._now()
        artifacts.append(
            StepArtifact(
                name="today_matches_csv" if not keep_actual else "matches_standardized_csv",
                path=str(today_path),
                artifact_type="csv",
                metadata={"created": bool(created)},
            )
        )
        artifacts.append(StepArtifact(name="dataset_validation", path=str(validation_path), artifact_type="json", metadata={}))
        artifacts.append(StepArtifact(name="dataset_missing_report", path=str(missing_path), artifact_type="csv", metadata={}))

        if data_mode == "real" and not data_quality_ok:
            return StepResult(
                status="review_required",
                summary="required_fields_missing",
                started_at=started,
                finished_at=finished,
                artifacts=artifacts,
                metrics={
                    "created": bool(created),
                    "data_quality_ok": bool(data_quality_ok),
                    "standardized_data_path": str(today_path),
                    "import_summary_path": str(run_dir / "import_summary.json") if (run_dir / "import_summary.json").exists() else None,
                    "validation_path": str(run_dir / "import_validation.json") if (run_dir / "import_validation.json").exists() else str(validation_path),
                    "missing_report_path": str(run_dir / "import_missing_report.csv") if (run_dir / "import_missing_report.csv").exists() else str(missing_path),
                    "row_count": row_count,
                    "required_fields_missing": required_fields_missing,
                    "required_field_null_counts": required_field_null_counts,
                    "error_message": "real 模式数据缺少关键字段，需人工检查 mapping 或源数据",
                },
            )
        return StepResult(
            status="completed",
            summary="created" if created else "exists",
            started_at=started,
            finished_at=finished,
            artifacts=artifacts,
            metrics={
                "created": bool(created),
                "data_quality_ok": bool(data_quality_ok),
                "standardized_data_path": str(today_path),
                "import_summary_path": str(run_dir / "import_summary.json") if (run_dir / "import_summary.json").exists() else None,
                "validation_path": str(run_dir / "import_validation.json") if (run_dir / "import_validation.json").exists() else str(validation_path),
                "missing_report_path": str(run_dir / "import_missing_report.csv") if (run_dir / "import_missing_report.csv").exists() else str(missing_path),
                "row_count": row_count,
                "required_fields_missing": required_fields_missing,
                "required_field_null_counts": required_field_null_counts,
            },
        )

    def summarize(self, result: StepResult) -> str:
        return result.summary
