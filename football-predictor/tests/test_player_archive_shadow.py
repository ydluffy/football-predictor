import pytest
from data.player_archive_shadow import attach


@pytest.fixture
def inputs():
    return (dict(source="api_football", source_player_id="1", source_team_id="2", source_fixture_id="3"),
            {"1": dict(entity_id="e", fields={}, conflicts=[], usable_for="reference_only")}, {("1", "2", "3")})


def test_links_by_id_without_changing_input(inputs):
    row, profiles, memberships = inputs
    result = attach(row, profiles, memberships)
    assert result["archive_status"] == "linked"
    assert result["prediction_features_allowed"] is False
    assert result["archive_usage"] == "reference_only"
    assert "archive_status" not in row


@pytest.mark.parametrize("field,value,status", [
    ("source", "other", "unsupported_source"),
    ("source_player_id", None, "missing_or_invalid_player_id"),
    ("source_player_id", True, "missing_or_invalid_player_id"),
    ("source_player_id", "99", "unknown_player_id"),
    ("source_team_id", None, "missing_match_context"),
    ("source_team_id", "9", "unverified_match_membership"),
    ("source_fixture_id", "9", "unverified_match_membership"),
])
def test_rejects_missing_unknown_or_wrong_context(inputs, field, value, status):
    row, profiles, memberships = inputs
    result = attach(dict(row, **{field: value}), profiles, memberships)
    assert result["archive_status"] == status
    assert "archive_fields" not in result


def _profiles():
    return {"1": dict(
        entity_id="e",
        fields={
            "name": dict(value="J. Kimmich", source="api_football", evidence="profiles/a.json"),
            "position": dict(value="Midfield", source="football_data_org", evidence="359"),
            "nationality": dict(value="Germany", source="unknown_feed", evidence=None),
        },
        conflicts=[],
        usable_for="source_id_lookup",
        provenance=[dict(kind="player_profile", observed_at="2026-10-22T05:29:29+00:00", evidence="profiles/a.json")],
        binding=dict(provider="football_data_org", observations=[dict(observed_at="2026-10-22T13:19:51+00:00")]),
    )}


def test_replay_withholds_fields_observed_after_the_cutoff():
    row = dict(source="api_football", source_player_id="1", source_team_id="2", source_fixture_id="3")
    result = attach(row, _profiles(), {("1", "2", "3")}, as_of="2026-10-22T06:00:00+00:00")
    assert result["archive_status"] == "linked"
    assert list(result["archive_fields"]) == ["name"]
    assert result["archive_withheld_fields"] == [
        {"field": "position", "reason": "observed_after_as_of"},
        {"field": "nationality", "reason": "unknown_observation_time"},
    ]
    assert result["archive_as_of"] == "2026-10-22T06:00:00+00:00"
    assert result["archive_as_of_status"] == "truncated"
    assert result["prediction_features_allowed"] is False
    assert "not an as-of feature join" not in result["history_warning"]


def test_replay_keeps_fields_known_before_the_cutoff():
    row = dict(source="api_football", source_player_id="1", source_team_id="2", source_fixture_id="3")
    result = attach(row, _profiles(), {("1", "2", "3")}, as_of="2026-10-23T00:00:00+00:00")
    assert sorted(result["archive_fields"]) == ["name", "position"]
    assert result["archive_withheld_fields"] == [{"field": "nationality", "reason": "unknown_observation_time"}]
    assert result["archive_as_of_status"] == "truncated"


def test_replay_without_cutoff_keeps_the_snapshot_warning(inputs):
    row, profiles, memberships = inputs
    result = attach(row, profiles, memberships)
    assert "archive_withheld_fields" not in result
    assert result["history_warning"] == "Current profile snapshot; not an as-of feature join"


@pytest.mark.parametrize("value", ["not-a-date", "2026/10/22"])
def test_replay_rejects_an_unparsable_cutoff(inputs, value):
    row, profiles, memberships = inputs
    with pytest.raises(ValueError, match="ISO-8601"):
        attach(row, profiles, memberships, as_of=value)


def test_replay_treats_a_naive_cutoff_as_utc():
    row = dict(source="api_football", source_player_id="1", source_team_id="2", source_fixture_id="3")
    result = attach(row, _profiles(), {("1", "2", "3")}, as_of="2026-10-22T06:00:00")
    assert list(result["archive_fields"]) == ["name"]

