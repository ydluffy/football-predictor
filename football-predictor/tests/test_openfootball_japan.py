from __future__ import annotations

import json
from pathlib import Path

from data.openfootball_japan import (
    build_openfootball_japan_context_dataset,
    download_openfootball_japan_j1,
    load_east_asia_source_policy,
    parse_openfootball_japan_j1,
)


SAMPLE = """= Japan | J1 League 2025
# Teams 20

▪ Matchday 1

Fri Feb 14 2025
19:00 Gamba Osaka v Cerezo Osaka 2-5 (1-1)

Sat Feb 15
Yokohama FC v FC Tokyo 0-1 (0-0)
Vissel Kobe v Urawa Red Diamonds 0-0

▪ Matchday 5
Wed Jul 2
19:00 Vissel Kobe v Sanfrecce Hiroshima
"""


def test_parser_keeps_results_and_schedule_but_blocks_odds_training() -> None:
    frame = parse_openfootball_japan_j1(
        SAMPLE,
        season=2025,
        source_url="https://example.test/2025_jp1.txt",
    )
    assert len(frame) == 4
    assert frame["status"].tolist() == ["finished", "finished", "finished", "scheduled"]
    assert frame["actual_result"].astype("string").tolist()[:3] == ["A", "A", "D"]
    assert not frame["odds_available"].any()
    assert not frame["model_training_eligible"].any()


def test_context_build_writes_explicit_training_gate(tmp_path: Path) -> None:
    input_dir = tmp_path / "raw"
    input_dir.mkdir()
    (input_dir / "2025_jp1.txt").write_text(SAMPLE, encoding="utf-8")
    output = tmp_path / "context.csv"
    audit_path = tmp_path / "audit.json"
    _, audit = build_openfootball_japan_context_dataset(
        input_dir=input_dir,
        output_path=output,
        audit_path=audit_path,
    )
    assert output.exists()
    assert audit["training_gate"] == "blocked_missing_pre_match_odds"
    assert audit["incomplete_result_seasons"] == ["2025"]
    assert audit["season_quality"]["2025"]["result_completeness"] == 0.75
    assert json.loads(audit_path.read_text(encoding="utf-8"))["model_training_eligible"] is False


def test_policy_prevents_unlicensed_automatic_download(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sources": {
                    "openfootball_japan_j1": {
                        "automatic_download_allowed": False,
                        "storage_allowed": False,
                        "available_years": [2025],
                        "raw_url_template": "https://example.test/{year}.txt"
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    try:
        download_openfootball_japan_j1(output_dir=tmp_path, years=[2025], policy_path=policy_path)
    except PermissionError:
        pass
    else:
        raise AssertionError("unlicensed source must not be downloaded")


def test_kleague_policy_requires_permission() -> None:
    policy = load_east_asia_source_policy("kleague_official_portal")
    assert policy["license"] == "permission_required"
    assert policy["automatic_download_allowed"] is False
