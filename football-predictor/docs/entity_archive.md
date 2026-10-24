# Local entity archive

This is a source-scoped candidate catalog, not a replacement for production
matching or the existing World Cup player CSV bundle. No paid API calls or cloud
database migrations are performed. The database lives under ignored processed data.

## Three stages

1. Import teams, competitions, seasons and fixtures from archived fixture responses.
   Source IDs produce stable internal UUIDs. Name equality never merges identities.
   Country/season comes from the league; team gender, age group and reserve status
   stay unknown until independently verified. A league country is not a team country.
2. Import player IDs and names from absence and lineup responses. Store team/fixture
   associations as dated observations, not proven contracts or transfer intervals.
   Do not infer birth dates, nationalities or medical diagnoses from names/reasons.
3. Repeat imports are idempotent. New identities, name conflicts and changed fixture
   identity/kickoff enter a persistent review queue. Prior evidence is retained.
   Review acknowledgement does not merge identities or authorize production use.

## Commands (run from football-predictor)

```powershell
.\.venv\Scripts\python.exe scripts/manage_entity_archive.py import --audit-json artifacts/data/final_20261021_004_013_intelligence.json --mapping-csv _tmp/recovery-real-20261022-c/mapping.csv
.\.venv\Scripts\python.exe scripts/manage_entity_archive.py status
.\.venv\Scripts\python.exe scripts/manage_entity_archive.py reviews
.\.venv\Scripts\python.exe scripts/manage_entity_archive.py review --id <review-id> --decision acknowledged --reviewer <name> --note <evidence>
```

Use the original capture audit, not a replay audit: archive filenames and SHA256
are verified, and the original observation timestamp is retained. Mapping CSV
restricts import scope to relevant fixtures. Existing raw files remain unchanged.
Imports are transactional; failures roll back changes. SQLite serializes writers.

## Remaining approval boundary

Cross-provider ID bindings, demographic/category enrichment and verified membership
validity intervals require explicit evidence and review. They are not automatically
promoted by this catalog.
Resolve unknown competitions in the production competition registry separately.
No UI, live scheduler, cloud synchronization or external notification is installed.
Back up the SQLite database alongside raw archives before cloud migration; Git
tracks code and tests, not the personal operational database.

## Reviewed source identity guards (2026-10-22)

`config/api_football_identities.json` records 20 team identities and three league
IDs checked against the archived batch identity report. Official UEFA, LaLiga
and CONMEBOL directories corroborate club names, not the API provider's IDs.
Each team entry retains its official directory URL; the manifest retains the
local batch report reference. These are source-scoped bindings, not global IDs.

The fixture adapter now preserves home and away provider IDs. Production mapping
requires supplied IDs for reviewed teams and leagues to agree with this manifest,
in addition to the existing name and kickoff checks. A conflict enters the review
queue as `source_identity_conflict`; it cannot fall back to same-name matching.
Inputs without IDs still use legacy strict aliases and time checks. Unknown IDs
are not automatically approved. This does not implement ID-only renamed-team
matching, complete player biographies, transfer history or cloud publication.

## Player profile enrichment

Run from the football-predictor directory:

```powershell
.\.venv\Scripts\python.exe scripts/enrich_player_profiles.py
.\.venv\Scripts\python.exe scripts/enrich_player_profiles.py --fetch --max-requests 65 --reserve 30
```

Without `--fetch`, this only exports all player dossiers and missing fields to
`artifacts/data/player_dossiers_latest.json`. With `--fetch`, it checks the current
API-Football quota, reserves 30 daily requests by default and requests only players
without a stored profile. It uses `/players/profiles?player=<source ID>` and never
matches a biography by name. Existing credentials stay in the local environment.
Requests are spaced by at least 6.3 seconds; rejection or malformed responses stop
the run. No subscription upgrade, scheduler, cloud write or production prediction
update occurs. Re-run after quota renewal to continue, not from the beginning.

Raw responses are content-hashed under `data/player_level/profiles/`. Profiles
retain observation timestamps and evidence hashes. Full name, birth, nationality,
height and weight remain null when absent; nationality is provider-reported, not
inferred from name or team. Each fetched profile is a source observation, not an
independent official identity certification. Birth conflicts open review items.
These current biographies do not establish historical transfer dates, match-time
availability, current squad membership or career completeness. Historical lineup
and injury observations are retained separately and are never overwritten.

If another collector is running concurrently, the initial quota snapshot can
change. The importer also checks returned daily remaining-quota headers when
provided, but the reserve is not a cross-process reservation or lock.

## Whole-team roster snapshots

`scripts/enrich_team_squads.py` plans collection for the 20 reviewed provider team
IDs. Use `--fetch --max-requests 20 --reserve 30` for a bounded live run after quota
is available. Without `--fetch` it only writes the pending-team report. The first
successful snapshot of each team is skipped on subsequent runs; this bootstrap
command is not a periodic roster refresh service.

The adapter validates the requested team ID, rejects empty and duplicate-ID
rosters, and rolls back incomplete imports. Player IDs remain source-scoped.
Snapshots retain number, position and age at observation; they do not invent DOB
from age, infer transfers, or mark players missing from a response as departed.
New players expand the catalog beyond the original injury/lineup sample of 133.

FIFA alternative source: https://fdp.fifa.org/assetspublic/ce233/pdf/SquadLists-English.pdf
The 32-page 2025 Club World Cup roster document includes full names, DOB,
nationality, height and position. The document identifies its version as
2025-07-04 14:14 UTC. It is historical competition evidence, not today's roster.
Cross-provider matching still requires reviewed identity evidence; no FIFA
player record has been automatically merged from this document.

REA probe on 2026-10-22: public FIFA statistics page scenario timed out and reported
incomplete browser cleanup and truncated network coverage. No stable JSON data
endpoint was established. Do not treat this probe as a working FIFA API adapter.
