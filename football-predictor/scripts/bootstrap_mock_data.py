from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from config.settings import ensure_project_dirs, get_settings
from data.mock_data_generator import generate_mock_matches
from data.validate_dataset import validate_matches_dataset


def _write_mock_csv(*, feature_version: str, n_rows: int, out_path: Path) -> Path:
    df = generate_mock_matches(n_rows=n_rows, feature_version=feature_version)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-rows", type=int, default=200)
    parser.add_argument("--run-train", choices=["true", "false"], default="true")
    args = parser.parse_args()

    ensure_project_dirs()
    s = get_settings()

    p_v1 = s.data_raw_dir / "mock_matches_v1.csv"
    p_v2 = s.data_raw_dir / "mock_matches_v2.csv"
    p_v3 = s.data_raw_dir / "mock_matches_v3.csv"

    _write_mock_csv(feature_version="v1", n_rows=int(args.n_rows), out_path=p_v1)
    _write_mock_csv(feature_version="v2", n_rows=int(args.n_rows), out_path=p_v2)
    _write_mock_csv(feature_version="v3", n_rows=int(args.n_rows), out_path=p_v3)

    df_v3 = generate_mock_matches(n_rows=int(args.n_rows), feature_version="v3")
    validate_matches_dataset(df_v3, "v3")

    print(str(p_v1))
    print(str(p_v2))
    print(str(p_v3))
    print(str(s.eval_dataset_validation_path))
    print(str(s.eval_dataset_missing_report_path))

    if args.run_train == "true":
        cmd = [
            sys.executable,
            "scripts/run_train.py",
            "--model-type",
            "lightgbm",
            "--feature-version",
            "v3",
            "--calibration",
            "sigmoid",
            "--cv",
            "false",
        ]
        subprocess.run(cmd, cwd=str(s.project_root), check=True)

        print(str(s.lightgbm_model_path))
        print(str(s.eval_results_path))
        print(str(s.eval_metrics_path))
        print(str(s.eval_run_summary_path))
        print(str(s.eval_feature_compare_path))
        print(str(s.eval_calibration_compare_path))
        print(str(s.eval_reliability_table_path))
        print(str(s.eval_model_compare_path))
        if s.eval_league_metrics_path.exists():
            print(str(s.eval_league_metrics_path))
        if s.eval_verifier_results_path.exists():
            print(str(s.eval_verifier_results_path))
        if s.eval_error_analysis_with_risk_path.exists():
            print(str(s.eval_error_analysis_with_risk_path))


if __name__ == "__main__":
    main()

