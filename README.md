# Ball Match Prediction System

This repository contains two cooperating applications:

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
