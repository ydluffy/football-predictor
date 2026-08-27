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
.\scripts\project.ps1 web-lint
.\scripts\project.ps1 web-typecheck
.\scripts\project.ps1 web-build
.\scripts\project.ps1 verify
```

## CI quality gates

GitHub Actions runs two independent jobs on pushes and pull requests:

- Python 3.12: install `football-predictor[dev]` and run the complete pytest suite.
- Node.js 22: install from `package-lock.json`, then run ESLint, TypeScript
  checking, and the optimized Next.js production build.

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
