import hashlib
import json

import pandas as pd
import pytest

from data.api_football_recovery import ArchivedApiFootballClient
from data.api_football_prematch import build_api_football_match_mapping


def test_archive_verifies_digest_and_never_fetches_missing_response(tmp_path):
    content = json.dumps({"response": [], "errors": []}).encode()
    file = tmp_path / ("20261021T130937Z_fixtures_2026-10-22_" + hashlib.sha256(content).hexdigest()[:12] + ".json")
    file.write_bytes(content)
    audit = {"raw_files": [str(file)]}
    client = ArchivedApiFootballClient(audit)
    assert client.get("fixtures", {"date": "2026-10-22"})["response"] == []
    with pytest.raises(ValueError, match="missing_archived_response"):
        client.get("fixtures/lineups", {"fixture": 123})
    file.write_bytes(b"{}")
    with pytest.raises(ValueError, match="digest mismatch"):
        ArchivedApiFootballClient(audit)


def test_review_queue_includes_missing_team_and_unknown_competition():
    local = pd.DataFrame([dict(match_id="x", competition_id="UNKNOWN", kickoff="2026-10-22T00:00:00Z",
                               home_team="New club", away_team="Other club")])
    api = pd.DataFrame(columns=["source_fixture_id", "kickoff_time", "home_team", "away_team"])
    _, audit = build_api_football_match_mapping(local, api)
    assert audit["coverage_ratio"] == 0
    assert audit["review_required"]
    assert {x["reason"] for x in audit["review_items"]} == {"unknown_competition", "team_pair_not_found"}
