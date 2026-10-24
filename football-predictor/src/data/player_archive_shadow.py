"""Read-only source-ID attachment for shadow diagnostics, never prediction features."""
from datetime import datetime, timezone


def _timestamp(value):
    """Parse an ISO-8601 stamp into an aware datetime; naive input is read as UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"as-of timestamp is not ISO-8601: {value!r}") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _observed_at(field, profile):
    """When the evidence behind one dossier field was captured, or None if unknowable.

    A field whose capture time cannot be proven is withheld, not assumed to predate
    the cutoff, so a post-match snapshot can never leak into a pre-match replay.
    """
    evidence = field.get("evidence")
    stamps = [
        item.get("observed_at")
        for item in profile.get("provenance") or []
        if item.get("evidence") == evidence
    ]
    if not stamps:
        binding = profile.get("binding") or {}
        if binding.get("provider") and field.get("source") == binding.get("provider"):
            stamps = [item.get("observed_at") for item in binding.get("observations") or []]
    known = [stamp for stamp in stamps if stamp]
    return max(known) if known else None


def attach(row, profiles, memberships, as_of=None):
    result = dict(row, shadow_only=True, prediction_features_allowed=False)
    if row.get("source") != "api_football":
        return dict(result, archive_status="unsupported_source")
    pid = row.get("source_player_id")
    if pid is None or isinstance(pid, bool) or not str(pid).isdigit() or int(pid) <= 0:
        return dict(result, archive_status="missing_or_invalid_player_id")
    pid = str(pid)
    profile = profiles.get(pid)
    if profile is None:
        return dict(result, archive_status="unknown_player_id")
    team = row.get("source_team_id")
    fixture = row.get("source_fixture_id")
    if not team or not fixture:
        return dict(result, archive_status="missing_match_context")
    if (pid, str(team), str(fixture)) not in memberships:
        return dict(result, archive_status="unverified_match_membership")
    linked = dict(result, archive_status="linked", archive_entity_id=profile["entity_id"],
                  archive_conflicts=profile["conflicts"], archive_usage=profile["usable_for"])
    if as_of is None:
        return dict(linked, archive_fields=profile["fields"],
                    history_warning="Current profile snapshot; not an as-of feature join")
    cutoff = _timestamp(as_of)
    usable, withheld = {}, []
    for key, field in profile["fields"].items():
        try:
            observed = _timestamp(_observed_at(field, profile))
        except ValueError:
            observed = None
        if observed is not None and observed <= cutoff:
            usable[key] = field
        else:
            withheld.append({"field": key,
                             "reason": "observed_after_as_of" if observed else "unknown_observation_time"})
    return dict(linked, archive_fields=usable, archive_withheld_fields=withheld,
                archive_as_of=cutoff.isoformat(),
                archive_as_of_status="truncated" if withheld else "within_cutoff",
                history_warning=f"Replay truncated at {cutoff.isoformat()}; later or untimed observations withheld")
