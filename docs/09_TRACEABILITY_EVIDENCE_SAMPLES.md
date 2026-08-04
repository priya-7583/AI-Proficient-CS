# 09 - Traceability Evidence Samples

This document includes small, redacted transcript samples from executable workflow runs.
It complements the traceability model in `04_AI_EXECUTION_TRACEABILITY.md`.

## Sample A: Ambiguous scenario clarification

Source run:
- `runs/ambiguous/20260729_024757/PROMPT_TRANSCRIPTS.md`

Prompt (excerpt):
- Scenario: ambiguous
- Normalize the requirement and capture ambiguities if present.

Response (excerpt):
- Build and improve a URL shortener with production-quality reliability controls.
- Clarification resolved: reliability means deterministic failures and stronger validation.

Why it matters:
- Demonstrates ambiguity detection and explicit clarification capture before implementation.

## Sample B: Decomposition and impact analysis

Source run:
- `runs/ambiguous/20260729_024757/PROMPT_TRANSCRIPTS.md`

Prompt (excerpt):
- Produce actionable task sequencing with dependencies.

Response (excerpt):
1. Normalize requirement and define acceptance criteria.
2. Identify impacted files and data flow.
3. Implement changes with bounded scope.
4. Run quality gates.
5. Produce artifacts for review and sign-off.

Impact analysis excerpt:
- Affected modules include `app/service.py` and `tests/test_api.py`.
- Existing endpoint behavior remains backward-compatible.

Why it matters:
- Shows planning discipline and bounded-change reasoning before code edits.

## Sample C: Brownfield run artifact completeness

Source run:
- `runs/brownfield/20260729_024741/RUN_SUMMARY.json`

Summary (excerpt):
- status: succeeded
- quality_gate_exit_code: 0
- changed_files: `app/service.py`, `tests/test_brownfield_generated.py`
- generated_artifacts include:
  - `BEFORE_app_service.py`
  - `AFTER_app_service.py`
  - `BROWNFIELD_DIFF.patch`
  - `PROMPT_TRANSCRIPTS.md`
  - `decision_log.jsonl`, `prompt_log.jsonl`, `stage_events.jsonl`

Why it matters:
- Provides concrete evidence of before/after traceability, review artifacts, and successful validation.
