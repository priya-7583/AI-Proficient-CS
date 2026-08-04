from __future__ import annotations

import difflib
import json
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class WorkflowReport:
    run_id: str
    scenario: str
    status: str
    workspace: str
    quality_gate_exit_code: Optional[int]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, default=str) + "\n")


def _stage(log_path: Path, name: str, status: str, detail: str) -> None:
    _append_jsonl(
        log_path,
        {"at": _now_iso(), "stage": name, "status": status, "detail": detail},
    )


def _copy_project_source(project_root: Path, source_root: Path) -> None:
    source_root.mkdir(parents=True, exist_ok=True)
    for rel in [
        "app",
        "tests",
        "workflow",
        "requirements.txt",
        "README.md",
        "quality_gate.py",
        "run_workflow.py",
        "mypy.ini",
        "pytest.ini",
    ]:
        src = project_root / rel
        dst = source_root / rel
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def _normalize_requirement(scenario: str, clarification: Optional[str]) -> str:
    if scenario == "ambiguous":
        answer = clarification or "Reliability means deterministic errors, idempotency, and quality-gate enforcement."
        return (
            "Build and improve a URL shortener with production-quality reliability controls.\n\n"
            "Clarification resolved:\n"
            f"- {answer}"
        )
    if scenario == "brownfield":
        return "Enhance an existing shortener with recent-click analytics while preserving existing API behavior."
    return "Build a URL shortener with create, resolve, stats, deactivate, and health APIs."


def _decomposition_for(scenario: str) -> str:
    common = [
        "1. Normalize requirement and define acceptance criteria.",
        "2. Identify impacted files and data flow.",
        "3. Implement changes with bounded scope.",
        "4. Run quality gates (pytest + secret scan).",
        "5. Produce artifacts for review and sign-off.",
    ]
    if scenario == "brownfield":
        common.insert(2, "3. Capture before/after diff for changed modules.")
    return "\n".join(common)


def _brownfield_enhance(source_root: Path) -> dict:
    service_path = source_root / "app" / "service.py"
    before = service_path.read_text(encoding="utf-8")

    marker = "    def deactivate(self, short_code: str) -> bool:\n"
    if marker not in before:
        raise RuntimeError("Unable to locate insertion point in app/service.py")

    enhancement = textwrap.indent(
        textwrap.dedent(
            """
            def get_recent_clicks(self, short_code: str, limit: int = 5) -> list[dict]:
                with self.db.connection() as conn:
                    exists = conn.execute(
                        "SELECT 1 FROM links WHERE short_code = ?",
                        (short_code,),
                    ).fetchone()
                    if not exists:
                        raise LinkNotFoundError(short_code)

                    rows = conn.execute(
                        "SELECT clicked_at, referrer, user_agent "
                        "FROM clicks "
                        "WHERE short_code = ? "
                        "ORDER BY clicked_at DESC LIMIT ?",
                        (short_code, limit),
                    ).fetchall()

                return [
                    {
                        "clicked_at": row["clicked_at"],
                        "referrer": row["referrer"],
                        "user_agent": row["user_agent"],
                    }
                    for row in rows
                ]

            """
        ),
        "    ",
    )

    after = before.replace(marker, enhancement + marker)
    service_path.write_text(after, encoding="utf-8")

    generated_test = source_root / "tests" / "test_brownfield_generated.py"
    generated_test_content = textwrap.dedent(
        """
            from __future__ import annotations

            from pathlib import Path

            from app.db import Database
            from app.service import LinkService


            def test_recent_clicks_brownfield_enhancement(tmp_path: Path) -> None:
                db = Database(str(tmp_path / "brownfield.db"))
                db.initialize()
                service = LinkService(db)

                created = service.create_link(
                    original_url="https://example.com/recent",
                    custom_alias="recent01",
                    created_by="brownfield",
                    expires_in_minutes=None,
                )
                code = created["short_code"]

                service.record_click(code, "https://ref1", "ua1", "10.0.0.1")
                service.record_click(code, "https://ref2", "ua2", "10.0.0.2")

                rows = service.get_recent_clicks(code, limit=2)
                assert len(rows) == 2
                assert rows[0]["clicked_at"] >= rows[1]["clicked_at"]
            """
    ).strip() + "\n"
    generated_test.write_text(generated_test_content, encoding="utf-8")

    diff = "\n".join(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile="before/app/service.py",
            tofile="after/app/service.py",
            lineterm="",
        )
    )

    return {
        "before": before,
        "after": after,
        "diff": diff,
        "changed_files": ["app/service.py", "tests/test_brownfield_generated.py"],
    }


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_prompt_transcript(
    workspace: Path,
    *,
    scenario: str,
    normalized_requirement: str,
    decomposition: str,
    impact_analysis: str,
    changed_files: list[str],
) -> None:
    transcript = textwrap.dedent(
        f"""
        # Prompt Transcript (Representative)

        ## Stage: requirements
        ### Prompt
        Scenario: {scenario}
        Normalize the requirement and capture ambiguities if present.

        ### Response
        {normalized_requirement}

        ## Stage: decomposition
        ### Prompt
        Produce actionable task sequencing with dependencies.

        ### Response
        {decomposition}

        ## Stage: impact_analysis
        ### Prompt
        Identify impacted modules, APIs, and data flow.

        ### Response
        {impact_analysis}

        ## Stage: implement
        ### Prompt
        Apply scoped implementation changes and preserve compatibility.

        ### Response
        changed_files={changed_files}
        """
    ).strip()
    _write(workspace / "PROMPT_TRANSCRIPTS.md", transcript + "\n")


def run_pipeline(
    project_root: str,
    *,
    scenario: str,
    output_root: Optional[str] = None,
    auto_approve: bool = True,
    require_signoff: bool = False,
    signoff_path: Optional[str] = None,
    clarification: Optional[str] = None,
    run_validation: bool = True,
) -> WorkflowReport:
    if scenario not in {"greenfield", "brownfield", "ambiguous"}:
        raise ValueError("scenario must be greenfield, brownfield, or ambiguous")

    root = Path(project_root).resolve()
    runs_base = Path(output_root).resolve() if output_root else root / "runs"
    run_id = _now().strftime("%Y%m%d_%H%M%S")
    workspace = runs_base / scenario / run_id
    source_root = workspace / "source"

    stage_log = workspace / "stage_events.jsonl"
    prompt_log = workspace / "prompt_log.jsonl"
    decision_log = workspace / "decision_log.jsonl"

    signoff_data: dict = {}
    if require_signoff:
        if not signoff_path:
            raise RuntimeError("require_signoff=True needs signoff_path")
        signoff_file = Path(signoff_path)
        if not signoff_file.exists():
            raise RuntimeError(f"signoff file not found: {signoff_file}")
        signoff_data = json.loads(signoff_file.read_text(encoding="utf-8-sig"))

    _stage(stage_log, "init", "started", f"scenario={scenario}")
    _copy_project_source(root, source_root)
    _stage(stage_log, "copy_source", "succeeded", str(source_root))

    normalized = _normalize_requirement(scenario, clarification)
    _write(workspace / "REQUIREMENTS_NORMALIZED.md", normalized + "\n")
    _append_jsonl(prompt_log, {"at": _now_iso(), "stage": "requirements", "prompt": normalized})
    _stage(stage_log, "requirements", "succeeded", "normalized requirement written")

    decomposition = _decomposition_for(scenario)
    _write(workspace / "TASK_DECOMPOSITION.md", decomposition + "\n")
    _append_jsonl(prompt_log, {"at": _now_iso(), "stage": "decomposition", "prompt": decomposition})
    _stage(stage_log, "decomposition", "succeeded", "task graph written")

    impact = textwrap.dedent(
        """
        # Impact Analysis

        ## Affected modules
        - app/service.py
        - tests/test_api.py

        ## API/Data flow impact
        - Service layer analytics methods are extended.
        - API remains backward-compatible for existing endpoints.

        ## Compatibility notes
        - Existing create/resolve/stats behavior must remain unchanged.
        """
    ).strip()
    _write(workspace / "IMPACT_ANALYSIS.md", impact + "\n")
    _stage(stage_log, "impact_analysis", "succeeded", "impact analysis generated")

    if require_signoff:
        if not bool(signoff_data.get("approval_plan", False)):
            raise RuntimeError("approval_plan denied or missing in signoff file")
        approver = str(signoff_data.get("approver", "engineer"))
        plan_note = str(signoff_data.get("approval_plan_note", "approved by signoff file"))
    else:
        if not auto_approve:
            raise RuntimeError("Interactive approval is not enabled in this execution mode.")
        approver = "engineer"
        plan_note = "auto-approved for scripted execution"

    _append_jsonl(
        decision_log,
        {
            "at": _now_iso(),
            "stage": "approval_plan",
            "decision": "approved",
            "actor": approver,
            "rationale": plan_note,
        },
    )
    _stage(stage_log, "approval_plan", "succeeded", "approved")

    changed_files: list[str] = []
    if scenario == "brownfield":
        result = _brownfield_enhance(source_root)
        changed_files = result["changed_files"]
        _write(workspace / "BEFORE_app_service.py", result["before"])
        _write(workspace / "AFTER_app_service.py", result["after"])
        _write(workspace / "BROWNFIELD_DIFF.patch", result["diff"] + "\n")
        _append_jsonl(
            decision_log,
            {
                "at": _now_iso(),
                "stage": "implement",
                "decision": "edited",
                "actor": "engineer",
                "rationale": "added recent click analytics method and generated regression test",
                "changed_files": changed_files,
            },
        )
    else:
        _append_jsonl(
            decision_log,
            {
                "at": _now_iso(),
                "stage": "implement",
                "decision": "accepted",
                "actor": "engineer",
                "rationale": "existing implementation satisfies this scenario scope",
            },
        )
    _stage(stage_log, "implement", "succeeded", f"changed_files={changed_files}")

    _write_prompt_transcript(
        workspace,
        scenario=scenario,
        normalized_requirement=normalized,
        decomposition=decomposition,
        impact_analysis=impact,
        changed_files=changed_files,
    )

    gate_exit: Optional[int] = None
    validation_tail = "validation skipped"
    if run_validation:
        proc = subprocess.run(
            [sys.executable, "quality_gate.py"],
            cwd=str(source_root),
            capture_output=True,
            text=True,
        )
        gate_exit = proc.returncode
        validation_tail = (proc.stdout + "\n" + proc.stderr).strip()
        if proc.returncode != 0:
            _stage(stage_log, "validate", "failed", "quality gate failed")
            status = "failed"
        else:
            _stage(stage_log, "validate", "succeeded", "quality gate passed")
            status = "succeeded"
    else:
        _stage(stage_log, "validate", "skipped", "run_validation=False")
        status = "succeeded"

    if require_signoff:
        if not bool(signoff_data.get("approval_release", False)):
            raise RuntimeError("approval_release denied or missing in signoff file")
        release_note = str(signoff_data.get("approval_release_note", "release approved by signoff file"))
    else:
        release_note = "quality gates reviewed"

    _append_jsonl(
        decision_log,
        {
            "at": _now_iso(),
            "stage": "approval_release",
            "decision": "approved",
            "actor": approver,
            "rationale": release_note,
        },
    )
    _stage(stage_log, "approval_release", "succeeded", "approved")

    validation_tail_display = "\n".join(validation_tail.splitlines()[-120:])

    _write(
        workspace / "VALIDATION_REPORT.md",
        "# Validation Report\n\n"
        f"status: {status}\n\n"
        "## quality gate output\n\n"
        "```\n"
        f"{validation_tail_display}\n"
        "```\n",
    )

    summary = {
        "run_id": run_id,
        "scenario": scenario,
        "status": status,
        "workspace": str(workspace),
        "quality_gate_exit_code": gate_exit,
        "changed_files": changed_files,
        "generated_artifacts": sorted(p.name for p in workspace.iterdir()),
    }
    _write(workspace / "RUN_SUMMARY.json", json.dumps(summary, indent=2) + "\n")
    _append_jsonl(runs_base / "run_index.jsonl", {"at": _now_iso(), **summary})
    _stage(stage_log, "complete", status, "pipeline complete")

    return WorkflowReport(
        run_id=run_id,
        scenario=scenario,
        status=status,
        workspace=str(workspace),
        quality_gate_exit_code=gate_exit,
    )
