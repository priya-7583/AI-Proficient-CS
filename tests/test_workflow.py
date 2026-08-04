from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from workflow.pipeline import run_pipeline


def test_brownfield_pipeline_generates_before_after_artifacts(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]

    report = run_pipeline(
        str(project_root),
        scenario="brownfield",
        output_root=str(tmp_path / "runs"),
        run_validation=False,
    )

    assert report.status == "succeeded"

    workspace = Path(report.workspace)
    assert (workspace / "REQUIREMENTS_NORMALIZED.md").exists()
    assert (workspace / "IMPACT_ANALYSIS.md").exists()
    assert (workspace / "BEFORE_app_service.py").exists()
    assert (workspace / "AFTER_app_service.py").exists()
    assert (workspace / "BROWNFIELD_DIFF.patch").exists()
    assert (workspace / "source" / "tests" / "test_brownfield_generated.py").exists()

    summary = json.loads((workspace / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["scenario"] == "brownfield"
    assert "app/service.py" in summary["changed_files"]


def test_ambiguous_pipeline_records_clarification(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]

    report = run_pipeline(
        str(project_root),
        scenario="ambiguous",
        output_root=str(tmp_path / "runs"),
        clarification="Reliability means explicit failure semantics and quality-gate enforcement.",
        run_validation=False,
    )

    assert report.status == "succeeded"
    workspace = Path(report.workspace)
    req_text = (workspace / "REQUIREMENTS_NORMALIZED.md").read_text(encoding="utf-8")
    assert "Reliability means explicit failure semantics" in req_text
    assert (workspace / "decision_log.jsonl").exists()


def test_pipeline_enforces_signoff_file(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    signoff_path = tmp_path / "signoff.json"
    signoff_path.write_text(
        json.dumps(
            {
                "approver": "release-manager",
                "approval_plan": True,
                "approval_release": True,
                "approval_plan_note": "reviewed scope",
                "approval_release_note": "validated quality gate",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_pipeline(
        str(project_root),
        scenario="greenfield",
        output_root=str(tmp_path / "runs"),
        require_signoff=True,
        signoff_path=str(signoff_path),
        run_validation=False,
    )

    assert report.status == "succeeded"
    decision_log = Path(report.workspace) / "decision_log.jsonl"
    assert "release-manager" in decision_log.read_text(encoding="utf-8")


def test_quality_gate_report_has_all_gate_sections(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "quality_gate.py"],
        cwd=str(project_root),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    report = json.loads((project_root / "QUALITY_GATE_REPORT.json").read_text(encoding="utf-8"))
    assert set(["analysis", "linting", "typing", "security", "performance", "tests", "overall_ok"]).issubset(report.keys())
    assert report["overall_ok"] is True
