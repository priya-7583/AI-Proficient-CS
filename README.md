# AI-Proficient URL Shortener

This folder is a separate engineer-led, AI-assisted implementation designed for
AI proficiency evaluation against the URL shortener assignment.

## What is included

- Production-style FastAPI URL shortener service
- Core APIs (create, resolve, details, stats, deactivate, health)
- Reliability controls (rate limiting, idempotent create, alias conflict guard,
  secure code generation, expiration support)
- Mutating endpoint auth via API key or JWT role (`writer`/`admin`)
- Redis-backed distributed rate limiting option (`SHORTENER_REDIS_URL`)
- Analytics (click count, unique visitors via IP hash, top referrers)
- Executable scenario workflow with approval gates and run artifacts
- Automated tests
- Full assignment deliverable docs (requirements, decomposition, architecture,
  scenarios, risk controls, final summary)

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8020
```

## Run tests

```powershell
python -m pytest -q tests
```

## Run quality gate

```powershell
python quality_gate.py
```

Quality gate checks include analysis, linting (`ruff`), typing (`mypy`),
security secret scan, performance benchmark, and tests.

## Run executable scenario workflow

```powershell
python run_workflow.py --scenario greenfield
python run_workflow.py --scenario brownfield
python run_workflow.py --scenario ambiguous --clarification "Reliability means deterministic failures and stronger validation."
```

Each workflow run writes reviewable artifacts under `runs/<scenario>/<run_id>/`
including requirement normalization, decomposition, impact analysis, quality
gate validation, decision logs, prompt logs, saved prompt transcripts, and run summaries.

CI automation: `.github/workflows/quality-gate.yml` runs quality gate + tests on
push and pull requests.

## Key endpoints

- `POST /api/v1/links`
- `GET /{short_code}`
- `GET /api/v1/links/{short_code}`
- `GET /api/v1/links/{short_code}/stats`
- `DELETE /api/v1/links/{short_code}`
- `GET /api/v1/health`

Mutating endpoint auth:

1. `X-API-Key: <SHORTENER_API_KEY>`
2. `Authorization: Bearer <jwt>` with role `writer` or `admin`

Set `SHORTENER_REQUIRE_MUTATING_AUTH=0` for local-only open mode.

## Deliverable docs

See `docs/` for:

- Requirement normalization and ambiguity handling
- Task decomposition and sequencing
- Brownfield reasoning
- AI-assisted execution traceability
- Executable workflow and controlled oversight
- Architecture and control flow
- Validation and risk controls
- Final engineering summary
- Greenfield, brownfield, and ambiguous scenarios
