from __future__ import annotations

from pathlib import Path

from world_cup.daily_pipeline import build_daily_pipeline_steps, evaluate_sporttery_quality_gate


def test_daily_pipeline_builds_offline_steps_in_order():
    steps = build_daily_pipeline_steps(
        root=Path("."),
        as_of_date="2026-06-25",
        python_executable="python",
        node_executable="node",
        refresh_espn=False,
        download_leisu=False,
    )

    assert [step.name for step in steps] == [
        "import_leisu_public",
        "build_leisu_fixture_features",
        "import_leisu_structured_intelligence",
        "build_sporttery_line_movement_features",
        "run_lineup_adjusted_predictions",
        "audit_world_cup_data_sources",
        "build_chinese_excel_report",
        "run_prediction_review",
    ]
    assert steps[0].command[steps[0].command.index("--download") + 1] == "false"
    assert "leisu_structured_intelligence_import_2026-06-25.json" in str(steps[2].required_output)
    assert "sporttery_handicap_line_movement_features.csv" in str(steps[3].required_output)
    assert "world_cup_lineup_adjusted_with_leisu_2026-06-25.csv" in " ".join(steps[4].command)
    assert "--line-movement" in steps[4].command
    assert "--structured-intelligence" in steps[4].command
    assert "world_cup_data_source_coverage_2026-06-25.json" in str(steps[5].required_output)
    assert "xlsx" in str(steps[6].required_output)


def test_daily_pipeline_can_include_espn_refresh_and_leisu_download():
    steps = build_daily_pipeline_steps(
        root=Path("."),
        as_of_date="2026-06-25",
        python_executable="python",
        node_executable="node",
        refresh_espn=True,
        download_leisu=True,
    )

    assert steps[0].name == "refresh_espn_live_data"
    assert steps[1].command[steps[1].command.index("--download") + 1] == "true"
    intelligence_step = next(
        step for step in steps if step.name == "import_leisu_structured_intelligence"
    )
    assert intelligence_step.command[intelligence_step.command.index("--download") + 1] == "true"


def test_daily_pipeline_can_pass_sporttery_market_file():
    steps = build_daily_pipeline_steps(
        root=Path("."),
        as_of_date="2026-06-25",
        python_executable="python",
        node_executable="node",
        refresh_espn=False,
        download_leisu=False,
        sporttery_markets="data/manual/sporttery_handicap_markets_2026-06-25.csv",
    )

    prediction_step = next(
        step for step in steps if step.name == "run_lineup_adjusted_predictions"
    )
    assert prediction_step.name == "run_lineup_adjusted_predictions"
    assert "--sporttery-markets" in prediction_step.command
    assert (
        prediction_step.command[prediction_step.command.index("--sporttery-markets") + 1]
        == "data/manual/sporttery_handicap_markets_2026-06-25.csv"
    )


def test_daily_pipeline_can_refresh_sporttery_before_predictions():
    steps = build_daily_pipeline_steps(
        root=Path("."),
        as_of_date="2026-06-25",
        python_executable="python",
        node_executable="node",
        refresh_espn=False,
        download_leisu=False,
        refresh_sporttery=True,
        sporttery_date="2026-06-26",
        sporttery_channel="msedge",
        sporttery_timeout=30000,
    )

    assert steps[0].name == "refresh_sporttery_lottery_gov"
    assert steps[0].command[steps[0].command.index("--date") + 1] == "2026-06-26"
    assert steps[0].command[steps[0].command.index("--channel") + 1] == "msedge"
    assert steps[0].command[steps[0].command.index("--append-history") + 1] == "true"
    prediction_step = next(
        step for step in steps if step.name == "run_lineup_adjusted_predictions"
    )
    assert (
        prediction_step.command[prediction_step.command.index("--sporttery-markets") + 1]
        == str(Path("data") / "manual" / "sporttery_handicap_markets_2026-06-26.csv")
    )


def test_daily_pipeline_can_pass_realtime_data_sources():
    steps = build_daily_pipeline_steps(
        root=Path("."),
        as_of_date="2026-06-25",
        python_executable="python",
        node_executable="node",
        structured_intelligence="data/manual/intelligence.csv",
        absences="data/manual/absences.csv",
        realtime_lineups="data/manual/lineups.csv",
    )

    prediction_step = next(
        step for step in steps if step.name == "run_lineup_adjusted_predictions"
    )
    assert prediction_step.command[prediction_step.command.index("--structured-intelligence") + 1] == "data/manual/intelligence.csv"
    assert prediction_step.command[prediction_step.command.index("--absences") + 1] == "data/manual/absences.csv"
    assert prediction_step.command[prediction_step.command.index("--realtime-lineups") + 1] == "data/manual/lineups.csv"


def test_sporttery_quality_gate_warns_or_fails_on_low_coverage():
    prediction_audit = {
        "fixtures": 10,
        "sporttery_handicap_lines_used": 3,
        "sporttery_handicap_quality_status": "partial",
    }

    warning = evaluate_sporttery_quality_gate(
        prediction_audit,
        min_coverage=0.8,
        mode="warn",
    )
    failure = evaluate_sporttery_quality_gate(
        prediction_audit,
        min_coverage=0.8,
        mode="fail",
    )
    passed = evaluate_sporttery_quality_gate(
        prediction_audit | {"sporttery_handicap_lines_used": 9},
        min_coverage=0.8,
        mode="fail",
    )

    assert warning["status"] == "warn"
    assert failure["status"] == "failed"
    assert passed["status"] == "passed"
