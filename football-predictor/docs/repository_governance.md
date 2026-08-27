# Repository version-control policy

This repository keeps reproducible implementation assets in Git and keeps
mutable operational data outside Git.

## Canonical project layout

`football-predictor/` is the only installable Python project. The repository
root intentionally has no `pyproject.toml`, Python `src/`, or Python `tests/`
tree. Use `scripts/project.ps1` from the repository root or run commands from
inside `football-predictor/`. The root-level prototype was retired after its
sample dataset was moved to `football-predictor/data/templates`.

## Tracked in Git

- Python and TypeScript source code.
- Tests, database migrations, configuration, and documentation.
- Data schemas, empty templates, competition registries, and team mappings.
- Small deterministic fixtures required by automated tests.

## Kept local

- Credentials and local environment files. Only `.env.example` is tracked.
- Virtual environments, dependency caches, test temporary directories, and
  tool-specific local state.
- Raw or downloaded datasets under `data/raw`, `data/external`,
  `data/processed`, `data/interim`, and `data/player_level`.
- Mutable operational evidence under `data/manual`, including odds snapshots,
  betting ledgers, and shadow ledgers.
- Generated models, evaluations, reports, previews, and other files under
  `artifacts` or `outputs`.
- Personal screenshots and betting evidence outside the documented data
  acquisition workflow.

Ignoring a file does not back it up. Operational evidence must remain in its
immutable snapshot store and should be copied to durable storage according to
the scheduled-task retention policy. Index files and hashes are the audit
trail; source code and schemas are the reproducibility contract.

## Commit boundaries

Prefer reviewable commits in this order:

1. Repository policy, configuration, and data contracts.
2. Data acquisition and normalization code with its tests.
3. Feature, model, and evaluation code with its tests.
4. Strategy, API, and presentation changes with their tests.
5. Documentation updated to match the implemented behavior.

Do not combine generated data refreshes with implementation changes. Before a
commit, run `git status --short`, inspect staged changes with `git diff --cached`,
and run the relevant automated tests.
