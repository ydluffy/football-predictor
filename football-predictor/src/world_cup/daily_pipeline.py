from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: list[str]
    required_output: Path | None = None


def default_node_executable() -> str:
    return "node"


def build_daily_pipeline_steps(
    *,
    root: str | Path,
    as_of_date: str | None = None,
    python_executable: str | None = None,
    node_executable: str | None = None,
    refresh_espn: bool = False,
    download_leisu: bool = False,
    refresh_sporttery: bool = False,
    sporttery_date: str | None = None,
    sporttery_channel: str = "chrome",
    sporttery_timeout: int = 60000,
    sporttery_markets: str | Path | None = None,
    structured_intelligence: str | Path | None = None,
    absences: str | Path | None = None,
    realtime_lineups: str | Path | None = None,
) -> list[PipelineStep]:
    project = Path(root)
    run_date = as_of_date or date.today().isoformat()
    py = python_executable or sys.executable
    node = node_executable or default_node_executable()

    predictions = Path("artifacts") / "predictions" / f"world_cup_lineup_adjusted_with_leisu_{run_date}.csv"
    prediction_audit = Path("artifacts") / "predictions" / f"world_cup_lineup_adjusted_with_leisu_{run_date}.json"
    data_source_audit = Path("artifacts") / "data" / f"world_cup_data_source_coverage_{run_date}.json"
    leisu_audit = Path("artifacts") / "data" / f"leisu_public_import_{run_date}.json"
    leisu_features_audit = Path("artifacts") / "data" / f"leisu_world_cup_fixture_features_{run_date}.json"
    leisu_structured_intelligence = Path("data") / "external" / "leisu_structured_intelligence.csv"
    leisu_structured_intelligence_audit = (
        Path("artifacts") / "data" / f"leisu_structured_intelligence_import_{run_date}.json"
    )
    sporttery_line_movement = Path("data") / "manual" / "sporttery_handicap_line_movement_features.csv"
    report_output = Path("outputs") / "world_cup_report" / f"2026世界杯预测日报_{run_date}.xlsx"
    review_summary = Path("artifacts") / "reviews" / f"world_cup_review_summary_{run_date}.json"

    lottery_date = sporttery_date or run_date
    generated_sporttery_markets = (
        Path("data") / "manual" / f"sporttery_handicap_markets_{lottery_date}.csv"
    )
    sporttery_market_path = str(
        sporttery_markets or (generated_sporttery_markets if refresh_sporttery else "")
    )
    prediction_command = [
        py,
        "scripts/run_world_cup_lineup_adjusted.py",
        "--as-of-date",
        run_date,
        "--leisu-features",
        "data/external/leisu_world_cup_fixture_features.csv",
        "--output",
        str(predictions),
        "--audit-output",
        str(prediction_audit),
    ]
    if sporttery_market_path:
        prediction_command.extend(["--sporttery-markets", sporttery_market_path])
    prediction_command.extend(["--line-movement", str(sporttery_line_movement)])
    prediction_structured_intelligence = structured_intelligence or leisu_structured_intelligence
    if prediction_structured_intelligence:
        prediction_command.extend(
            ["--structured-intelligence", str(prediction_structured_intelligence)]
        )
    if absences:
        prediction_command.extend(["--absences", str(absences)])
    if realtime_lineups:
        prediction_command.extend(["--realtime-lineups", str(realtime_lineups)])

    steps: list[PipelineStep] = []
    if refresh_espn:
        steps.append(
            PipelineStep(
                "refresh_espn_live_data",
                [
                    py,
                    "scripts/import_espn_world_cup_live.py",
                    "--as-of-date",
                    run_date,
                    "--download",
                    "true",
                ],
                Path("artifacts") / "data" / "espn_world_cup_2026_import.json",
            )
        )
    if refresh_sporttery:
        steps.append(
            PipelineStep(
                "refresh_sporttery_lottery_gov",
                [
                    py,
                    "scripts/refresh_lottery_gov_spf.py",
                    "--date",
                    lottery_date,
                    "--output",
                    str(generated_sporttery_markets),
                    "--raw-output",
                    str(Path("data") / "external" / f"lottery_gov_zqspf_rendered_{lottery_date}.txt"),
                    "--channel",
                    sporttery_channel,
                    "--timeout",
                    str(sporttery_timeout),
                    "--append-history",
                    "true",
                    "--snapshot-type",
                    "latest",
                ],
                generated_sporttery_markets,
            )
        )
    steps.extend(
        [
            PipelineStep(
                "import_leisu_public",
                [
                    py,
                    "scripts/import_leisu_public.py",
                    "--download",
                    "true" if download_leisu else "false",
                    "--cache",
                    "data/external/leisu_home_probe.html"
                    if not download_leisu
                    else f"data/external/leisu_home_{run_date}.html",
                    "--output",
                    "data/external/leisu_public_matches.csv",
                    "--audit-output",
                    str(leisu_audit),
                ],
                leisu_audit,
            ),
            PipelineStep(
                "build_leisu_fixture_features",
                [
                    py,
                    "scripts/build_leisu_world_cup_features.py",
                    "--fixtures",
                    "data/player_level/espn_world_cup_2026/fixtures.csv",
                    "--leisu-matches",
                    "data/external/leisu_public_matches.csv",
                    "--output",
                    "data/external/leisu_world_cup_fixture_features.csv",
                    "--audit-output",
                    str(leisu_features_audit),
                ],
                leisu_features_audit,
            ),
            PipelineStep(
                "import_leisu_structured_intelligence",
                [
                    py,
                    "scripts/import_leisu_intelligence.py",
                    "--leisu-features",
                    "data/external/leisu_world_cup_fixture_features.csv",
                    "--output",
                    str(leisu_structured_intelligence),
                    "--cache-dir",
                    "data/external/leisu-intelligence",
                    "--download",
                    "true" if download_leisu else "false",
                    "--audit-output",
                    str(leisu_structured_intelligence_audit),
                ],
                leisu_structured_intelligence_audit,
            ),
            PipelineStep(
                "build_sporttery_line_movement_features",
                [
                    py,
                    "scripts/build_sporttery_line_movement_features.py",
                    "--history",
                    "data/manual/sporttery_handicap_market_history.csv",
                    "--output",
                    str(sporttery_line_movement),
                ],
                sporttery_line_movement,
            ),
            PipelineStep(
                "run_lineup_adjusted_predictions",
                prediction_command,
                predictions,
            ),
            PipelineStep(
                "audit_world_cup_data_sources",
                [
                    py,
                    "scripts/audit_world_cup_data_sources.py",
                    "--as-of-date",
                    run_date,
                    "--sporttery-markets",
                    sporttery_market_path or str(generated_sporttery_markets),
                    "--leisu-matches",
                    "data/external/leisu_public_matches.csv",
                    "--predictions",
                    str(predictions),
                    "--structured-intelligence",
                    str(leisu_structured_intelligence),
                    "--output",
                    str(data_source_audit),
                ],
                data_source_audit,
            ),
            PipelineStep(
                "build_chinese_excel_report",
                [
                    node,
                    "scripts/build_world_cup_chinese_report.mjs",
                    "--report-date",
                    run_date,
                    "--predictions",
                    str(predictions),
                    "--audit",
                    str(prediction_audit),
                    "--line-movement",
                    str(sporttery_line_movement),
                    "--output-dir",
                    "outputs/world_cup_report",
                ],
                report_output,
            ),
            PipelineStep(
                "run_prediction_review",
                [
                    py,
                    "scripts/run_world_cup_prediction_review.py",
                    "--snapshot-date",
                    run_date,
                    "--predictions",
                    str(predictions),
                    "--scoreboard",
                    "data/external/espn-world-cup/scoreboard_2026.json",
                    "--line-movement",
                    str(sporttery_line_movement),
                    "--output-dir",
                    "artifacts/reviews",
                ],
                review_summary,
            ),
        ]
    )
    return steps


def evaluate_sporttery_quality_gate(
    prediction_audit: dict[str, object],
    *,
    min_coverage: float = 0.8,
    mode: str = "warn",
) -> dict[str, object]:
    fixtures = int(prediction_audit.get("fixtures", 0) or 0)
    used = int(prediction_audit.get("sporttery_handicap_lines_used", 0) or 0)
    coverage = float(
        prediction_audit.get(
            "sporttery_handicap_coverage",
            used / fixtures if fixtures else 0.0,
        )
        or 0.0
    )
    source_status = str(
        prediction_audit.get("sporttery_handicap_quality_status", "unknown")
    )
    gate_mode = mode if mode in {"warn", "fail", "off"} else "warn"
    threshold = max(0.0, min(1.0, float(min_coverage)))
    passed = gate_mode == "off" or coverage >= threshold
    if passed:
        status = "passed"
    elif gate_mode == "fail":
        status = "failed"
    else:
        status = "warn"
    return {
        "name": "sporttery_handicap_coverage",
        "status": status,
        "mode": gate_mode,
        "threshold": threshold,
        "fixtures": fixtures,
        "used": used,
        "coverage": coverage,
        "source_status": source_status,
        "message": (
            f"sporttery handicap coverage {used}/{fixtures} "
            f"({coverage:.1%}), threshold {threshold:.1%}"
        ),
    }


def run_daily_pipeline(
    *,
    root: str | Path,
    as_of_date: str | None = None,
    python_executable: str | None = None,
    node_executable: str | None = None,
    refresh_espn: bool = False,
    download_leisu: bool = False,
    refresh_sporttery: bool = False,
    sporttery_date: str | None = None,
    sporttery_channel: str = "chrome",
    sporttery_timeout: int = 60000,
    sporttery_markets: str | Path | None = None,
    structured_intelligence: str | Path | None = None,
    absences: str | Path | None = None,
    realtime_lineups: str | Path | None = None,
    sporttery_min_coverage: float = 0.8,
    sporttery_quality_mode: str = "warn",
    dry_run: bool = False,
) -> dict[str, object]:
    project = Path(root)
    steps = build_daily_pipeline_steps(
        root=project,
        as_of_date=as_of_date,
        python_executable=python_executable,
        node_executable=node_executable,
        refresh_espn=refresh_espn,
        download_leisu=download_leisu,
        refresh_sporttery=refresh_sporttery,
        sporttery_date=sporttery_date,
        sporttery_channel=sporttery_channel,
        sporttery_timeout=sporttery_timeout,
        sporttery_markets=sporttery_markets,
        structured_intelligence=structured_intelligence,
        absences=absences,
        realtime_lineups=realtime_lineups,
    )
    records: list[dict[str, object]] = []
    quality_gates: list[dict[str, object]] = []
    for step in steps:
        record = {
            "name": step.name,
            "command": step.command,
            "required_output": str(step.required_output) if step.required_output else "",
            "status": "dry_run" if dry_run else "pending",
        }
        if not dry_run:
            completed = subprocess.run(
                step.command,
                cwd=project,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                check=False,
            )
            record["returncode"] = completed.returncode
            record["stdout_tail"] = (completed.stdout or "")[-2000:]
            record["stderr_tail"] = (completed.stderr or "")[-2000:]
            if completed.returncode != 0:
                record["status"] = "failed"
                records.append(record)
                return {"ok": False, "steps": records}
            if step.required_output is not None and not (project / step.required_output).exists():
                record["status"] = "missing_output"
                records.append(record)
                return {"ok": False, "steps": records}
            if step.name == "run_lineup_adjusted_predictions":
                audit_path = project / "artifacts" / "predictions" / f"world_cup_lineup_adjusted_with_leisu_{as_of_date or date.today().isoformat()}.json"
                if audit_path.exists():
                    prediction_audit = json.loads(audit_path.read_text(encoding="utf-8"))
                    gate = evaluate_sporttery_quality_gate(
                        prediction_audit,
                        min_coverage=sporttery_min_coverage,
                        mode=sporttery_quality_mode,
                    )
                    record["data_quality"] = gate
                    quality_gates.append(gate)
                    if gate["status"] == "failed":
                        record["status"] = "data_quality_failed"
                        records.append(record)
                        return {
                            "ok": False,
                            "steps": records,
                            "data_quality_gates": quality_gates,
                        }
            record["status"] = "completed"
        records.append(record)
    return {"ok": True, "steps": records, "data_quality_gates": quality_gates}


def write_pipeline_audit(audit: dict[str, object], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
