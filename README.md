# Ball Match Prediction System

This repository contains two cooperating applications with one canonical
Python project:

- `football-predictor/`: the canonical Python data, research, backtest, model,
  and shadow-strategy project.
- `web/`: the Next.js product interface and Supabase-backed online API layer.

The Python project is the source of truth for research conclusions and model
probabilities. Generated data, operational ledgers, model artifacts, and report
exports remain local and are not stored in Git. Their schemas, importers,
validators, configuration, tests, and documentation are versioned.

See
[`football-predictor/docs/repository_governance.md`](football-predictor/docs/repository_governance.md)
for repository boundaries and commit conventions.

The repository root is not an installable Python package. Run Python commands
from `football-predictor/`, or use the root command wrapper below. This avoids
accidentally importing the retired prototype that previously lived under the
root `src/` directory.

## Unified commands

From the repository root:

```powershell
.\scripts\project.ps1 test
.\scripts\project.ps1 train --model-type logit --feature-version v3
.\scripts\project.ps1 api
.\scripts\project.ps1 data-model-quality --dataset path/to/current_scoring_snapshot.csv --reference path/to/approved_reference.csv --metrics artifacts/eval/model_compare.csv
.\scripts\project.ps1 python-lock
.\scripts\project.ps1 python-lock-check
.\scripts\project.ps1 python-lint
.\scripts\project.ps1 python-typecheck
.\scripts\project.ps1 secret-scan
.\scripts\project.ps1 dependency-audit
.\scripts\project.ps1 security
.\scripts\project.ps1 web-lint
.\scripts\project.ps1 web-typecheck
.\scripts\project.ps1 web-build
.\scripts\project.ps1 verify
```

## CI quality gates

GitHub Actions runs two independent jobs on pushes and pull requests:

- Python 3.12: install the exact versions in `football-predictor/requirements.txt`,
  validate the lock, scan tracked files for secrets, audit dependencies, run
  Ruff and mypy, and run the complete pytest suite. Deprecation warnings,
  future warnings, and ambiguous date parsing warnings are treated as failures.
- Node.js 22: install from `package-lock.json`, then run ESLint, TypeScript
  checking, dependency audit, and the optimized Next.js production build.

## Dependency and security governance

`football-predictor/requirements.txt` is the generated Python lock and contains
exact runtime and development versions. After changing `pyproject.toml`, run
`python-lock`, review the diff, then run `verify` and `security`. `verify` keeps
the deterministic lock and tracked-file secret checks offline; `security` adds
the online Python and npm vulnerability audits.

GitHub Dependabot checks Python and npm dependencies weekly, groups compatible
minor/patch updates, and checks GitHub Actions monthly. Update pull requests
must still pass the complete CI gates; they are not auto-merged.

FastAPI application assembly remains in `football-predictor/src/api/main.py`.
Independent endpoint groups belong under `football-predictor/src/api/routes/`
Router factories receive cross-cutting service dependencies explicitly; domain
routers may depend directly on the domain package they exclusively expose.
Dependency-free server-rendered tools live in `football-predictor/src/api/views.py`;
`main.py` only binds those view constants to HTTP endpoints.
World Cup sporttery market schemas, CSV persistence, paste parsing, and routes
are owned by `football-predictor/src/api/routes/sporttery.py`.
Research artifact analysis, experiment command parsing, status summaries, and
natural-language dispatch live in `football-predictor/src/api/services/`.
The OpenAI-compatible transport is isolated in `api/services/chat_client.py`;
all chat schemas and HTTP orchestration live in `api/routes/chat.py`.
Its timeout and bounded retry policy can be configured with
`CHAT_HTTP_TIMEOUT_SECONDS` (default `60`), `CHAT_HTTP_MAX_RETRIES` (default
`2`), and `CHAT_HTTP_RETRY_BACKOFF_SECONDS` (default `0.25`). Retries apply only
to temporary network, timeout, rate-limit, and upstream failures. Transport
errors expose stable error codes and emit structured Loguru context without
credentials.

## Local verification

Python:

```powershell
cd football-predictor
$env:TEMP = "$PWD\_tmp"
$env:TMP = "$PWD\_tmp"
.\.venv\Scripts\python.exe -m pytest -q
```

Web:

```powershell
cd web
npm run lint
npm run build
```
