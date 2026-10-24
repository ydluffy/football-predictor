# Mapping recovery

Daily imports write a sibling `.mapping-review.json` alongside the requested audit.
It records coverage and unresolved fixtures/competitions. A successful HTTP request
does not imply complete coverage: unresolved mappings make the audit partial.

1. Review raw provider responses and the local scan together. Verify competition,
   team category, home/away identity and kickoff; do not merge by fuzzy name alone.
2. Add verified aliases to the existing registry and regression tests. Unknown
   competitions require separate review; mapping a fixture does not authorize a
   new model route. Never remove kickoff or ambiguity guards to raise coverage.
3. Run `scripts/replay_api_football_intelligence.py --scan-json <original-scan>
   --audit-json <original-audit> --output-dir <new-directory>` after the correction.
   This automatically retries the saved batch offline. It verifies archive hashes,
   retains the original observation time, and never falls back to the network.
4. Inspect the isolated audit and recovered candidates. Missing archived lineups
   remain missing, not zero absences or confirmed lineups. Candidates are not
   automatically promoted to production or used to rewrite historical decisions.
5. Future normal collections use the new aliases. Additional live requests must
   use the existing quota controls and actual current observation time. Never
   backdate newly obtained information to a historical pre-match cutoff.

## Entity records: next stage

The alias registry is not a complete entity master. Before adding automatic ID-based
resolution, establish reviewed, versioned records:

- Teams: internal ID, provider IDs, official name, aliases, country, gender,
  age/reserve category, evidence and verification date. Keep stable IDs on rename.
- Competitions: internal/provider IDs, country, category, season and model eligibility.
- Players: internal/provider IDs, public sporting name and position. Do not collect
  private contact or medical records. Provider-reported absence is a sourced claim.
- Memberships: player ID, team ID, valid-from/to dates; transfers must not rewrite
  historical team membership.
- Fixtures: source IDs, team IDs, competition ID, kickoff versions and status.
  A reschedule is reviewed by fixture identity, not a broader time tolerance.

This release implements the review and offline recovery workflow, not this full
entity master or automatic identity approval. Provider-ID-only auto-resolution and
cross-provider collision handling require a separate schema migration and review.
