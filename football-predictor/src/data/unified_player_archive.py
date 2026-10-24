"""Derived multi-source profiles. Raw records and historical memberships stay intact."""
from data.roster_identity_comparison import classify, words


def assemble(local, candidates, expected_teams):
    fields, conflicts = {}, []

    def put(key, value, source, evidence):
        if value is None or value == "":
            return
        entry = dict(value=value, source=source, evidence=evidence)
        if key in fields and fields[key]["value"] != value:
            conflicts.append(dict(field=key, selected=fields[key], alternative=entry))
        elif key not in fields:
            fields[key] = entry

    profile = local["profile"]
    refs = [o for o in local["observations"] if o["kind"] == "player_profile"]
    ref = refs[-1]["evidence"] if refs else None
    for key in ("name", "nationality", "height", "weight"):
        put(key, profile.get(key), "api_football", ref)
    put("birth_date", (profile.get("birth") or {}).get("date"), "api_football", ref)
    official_names = []
    for o in local["observations"]:
        if o["kind"] != "official_profile_candidate":
            continue
        p = o["data"]
        # A differing page team is evidence to investigate, not membership proof.
        if p.get("official_page_team") and p["official_page_team"] != p["team"]:
            continue
        official_names.append(p["name"])
        for key in ("birth_date", "nationality", "height_cm", "weight_kg", "preferred_foot"):
            put(key, p.get(key), "official_page", p["url"])
        put("official_name", p["name"], "official_page", p["url"])
    birth = fields.get("birth_date", {}).get("value")
    eligible = []
    for external in candidates:
        obs = external["observations"]
        if not expected_teams.intersection(o["team_id"] for o in obs):
            continue
        names = [local["name"], profile.get("name"), *official_names]
        names.append(" ".join(filter(None, [profile.get("firstname"), profile.get("lastname")])) )
        states = [classify(n, {"birth": {"date": birth}}, external) for n in names]
        exact_full = any(len(words(n)) >= 2 and all(len(w) > 1 for w in words(n))
                         and words(n) == words(o["profile"].get("name")) for n in names for o in obs)
        if "name_and_birth_agree" in states:
            eligible.append((external, "name_birth_team"))
        elif not birth and exact_full and "name_only_needs_birth" in states:
            eligible.append((external, "exact_full_name_team_provisional"))
    binding = None
    if len(eligible) == 1 and not local["review_required"] and not any(c["field"] == "birth_date" for c in conflicts):
        external, basis = eligible[0]
        binding = dict(provider="football_data_org", source_id=external["id"], basis=basis,
                       approved=basis == "name_birth_team", approval_type="rule_based",
                       observations=external["observations"])
        for key, source_key in (("birth_date", "dateOfBirth"), ("nationality", "nationality"), ("position", "position")):
            values = {o["profile"].get(source_key) for o in external["observations"] if o["profile"].get(source_key)}
            if len(values) == 1:
                put(key, next(iter(values)), "football_data_org", external["id"])
            elif len(values) > 1:
                conflicts.append(dict(field=key, source="football_data_org", values=sorted(values)))
    return dict(api_id=local["provider_id"], entity_id=local["entity_id"], display_name=local["name"],
                fields=fields, binding=binding, conflicts=conflicts, local_conflicts=local["conflicts"],
                provenance=[dict(kind=o["kind"], observed_at=o["observed_at"], evidence=o["evidence"], sha256=o.get("sha256"))
                            for o in local["observations"] if o["kind"] in ("player_profile", "official_profile_candidate")],
                ambiguous_candidates=len(eligible) if len(eligible) > 1 else 0,
                usable_for="reference_only" if binding and not binding["approved"] else "source_id_lookup",
                missing_fields=[k for k in ("birth_date", "nationality", "position") if k not in fields])
