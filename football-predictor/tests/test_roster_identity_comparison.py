from data.roster_identity_comparison import classify, compatible_name
from data.competition_registry import load_team_alias_registry


def test_explicit_roster_team_aliases():
    registry = load_team_alias_registry()
    for source, canonical in (
        ("Galatasaray SK", "Galatasaray"),
        ("Viking FK", "Viking"),
        ("SE Palmeiras", "Palmeiras"),
        ("Fluminense FC", "Fluminense"),
    ):
        assert registry.resolve(source) == registry.resolve(canonical)
        assert registry.resolve(source + " U19") != registry.resolve(canonical)


def test_initial_matching_does_not_allow_wrong_first_name():
    assert compatible_name("J. Kimmich", "Joshua Kimmich")
    assert not compatible_name("J. Kimmich", "Michael Kimmich")
    assert not compatible_name("Kimmich", "Joshua Kimmich")


def test_profile_full_name_adds_candidates_without_ignoring_birth():
    external = {"observations": [{"profile": {"name": "Lisandro Martinez", "dateOfBirth": "1998-01-18"}}]}
    profile = {"firstname": "Lisandro", "lastname": "Martínez", "birth": {"date": "1998-01-18"}}
    assert classify("unmatched label", profile, external) == "name_and_birth_agree"
    profile["birth"]["date"] = "1999-01-18"
    assert classify("unmatched label", profile, external) == "birth_conflict"
    assert classify("unmatched label", {}, external) is None


def test_birth_is_required_and_source_conflict_blocks_agreement():
    external = {"observations": [{"profile": {"name": "Joshua Kimmich", "dateOfBirth": "1995-02-08"}}]}
    assert classify("J. Kimmich", {}, external) == "name_only_needs_birth"
    assert classify("J. Kimmich", {"birth": {"date": "1995-02-08"}}, external) == "name_and_birth_agree"
    assert classify("J. Kimmich", {"birth": {"date": "1996-02-08"}}, external) == "birth_conflict"
    external["observations"].append({"profile": {"name": "Joshua Kimmich", "dateOfBirth": "1996-02-08"}})
    assert classify("J. Kimmich", {}, external) == "source_birth_conflict"
