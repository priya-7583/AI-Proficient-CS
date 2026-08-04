# 08 - Executable Workflow and Controlled Oversight

This project now includes a runnable workflow that executes assignment scenarios
with explicit stage artifacts, approval decisions, traceability logs, and
quality-gate validation.

## Runner

Use:

```powershell
python run_workflow.py --scenario greenfield
python run_workflow.py --scenario brownfield
python run_workflow.py --scenario ambiguous --clarification "Reliability means deterministic failures and strong validation."
```

Optional fast mode (skip validation):

```powershell
python run_workflow.py --scenario brownfield --no-validate
```

Require explicit sign-off file for high-impact stages:

```powershell
python run_workflow.py --scenario brownfield --require-signoff --signoff-file signoff.json
```

## Workflow stages

1. Requirement normalization
2. Task decomposition
3. Impact analysis
4. Approval gate (plan)
5. Implementation
6. Validation (quality gate)
7. Approval gate (release)
8. Summary and index persistence

## Artifacts generated per run

- `REQUIREMENTS_NORMALIZED.md`
- `TASK_DECOMPOSITION.md`
- `IMPACT_ANALYSIS.md`
- `VALIDATION_REPORT.md`
- `RUN_SUMMARY.json`
- `stage_events.jsonl`
- `prompt_log.jsonl`
- `decision_log.jsonl`
- `PROMPT_TRANSCRIPTS.md`
- Brownfield-only: before/after snapshots and diff patch

## Brownfield automation evidence

Brownfield runs copy source into an isolated run workspace and automatically
apply a deterministic enhancement (`get_recent_clicks`) to `app/service.py`.
Before and after snapshots plus unified diff prove change impact and control.

## Quality gate

`quality_gate.py` performs:

1. Python compile analysis
2. `ruff` lint check
3. `mypy` typing check
4. secret-pattern scan
5. performance smoke benchmark
6. pytest execution (`tests/`)
7. JSON report output (`QUALITY_GATE_REPORT.json`)

This creates reproducible validation evidence for review sign-off.
