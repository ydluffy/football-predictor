from data.unified_player_archive import assemble


def local(name="Full Name", birth=None):
    return dict(provider_id="1", entity_id="entity", name=name,
                profile={"birth": {"date": birth}}, observations=[], review_required=False, conflicts=[])


def candidate(pid="2", birth="2000-01-01", team="3"):
    return dict(id=pid, observations=[dict(team_id=team, profile={
        "name": "Full Name", "dateOfBirth": birth, "position": "Defence", "nationality": "Spain"})])


def test_exact_name_without_birth_is_reference_not_approved():
    result = assemble(local(), [candidate()], {"3"})
    assert result["fields"]["birth_date"]["value"] == "2000-01-01"
    assert not result["binding"]["approved"]
    assert result["usable_for"] == "reference_only"


def test_birth_team_agreement_and_ambiguity():
    p = local(birth="2000-01-01")
    assert assemble(p, [candidate()], {"3"})["binding"]["approved"]
    assert assemble(p, [candidate(), candidate("4")], {"3"})["binding"] is None
    assert assemble(p, [candidate(team="9")], {"3"})["binding"] is None
    assert assemble(p, [candidate(birth="2001-01-01")], {"3"})["binding"] is None


def test_initial_alone_does_not_supply_birth_and_conflicts_block():
    assert assemble(local("F. Name"), [candidate()], {"3"})["binding"] is None
    p = local(birth="2000-01-01")
    p["review_required"] = True
    assert assemble(p, [candidate()], {"3"})["binding"] is None
