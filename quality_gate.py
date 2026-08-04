from __future__ import annotations

import json
import pathlib
import py_compile
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

from app.db import Database
from app.service import LinkService

ROOT = pathlib.Path(__file__).resolve().parent

SECRET_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scan_for_secrets() -> list[str]:
    findings: list[str] = []
    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        if p.suffix.lower() not in {".py", ".md", ".txt", ".json", ".env"}:
            continue
        if ".venv" in p.parts or "__pycache__" in p.parts or "runs" in p.parts:
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in SECRET_PATTERNS:
            if pat.search(text):
                findings.append(str(p.relative_to(ROOT)))
                break
    return findings


def _python_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for p in ROOT.rglob("*.py"):
        if ".venv" in p.parts or "__pycache__" in p.parts or "runs" in p.parts:
            continue
        out.append(p)
    return out


def _analysis_gate() -> tuple[bool, list[str]]:
    errors: list[str] = []
    for p in _python_files():
        try:
            py_compile.compile(str(p), doraise=True)
        except Exception as exc:
            errors.append(f"{p.relative_to(ROOT)}: {exc}")
    return (len(errors) == 0), errors


def _run_tool(cmd: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, output


def _lint_gate() -> tuple[bool, str]:
    return _run_tool(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "app",
            "tests",
            "workflow",
            "run_workflow.py",
            "quality_gate.py",
            "--select",
            "E9,F",
        ]
    )


def _typing_gate() -> tuple[bool, str]:
    return _run_tool([sys.executable, "-m", "mypy", "app", "workflow", "run_workflow.py"])


def _performance_gate() -> tuple[bool, dict]:
    start = time.perf_counter()
    with tempfile.TemporaryDirectory() as td:
        db = Database(str(pathlib.Path(td) / "perf.db"))
        db.initialize()
        service = LinkService(db)

        created_codes: list[str] = []
        for i in range(40):
            created = service.create_link(
                original_url=f"https://example.com/perf/{i}",
                custom_alias=None,
                created_by="perf",
                expires_in_minutes=None,
            )
            code = created["short_code"]
            created_codes.append(code)
            service.record_click(code, None, "perf-agent", "10.0.0.1")

        for code in created_codes:
            service.resolve_link(code)
            service.get_stats(code)

    elapsed = time.perf_counter() - start
    threshold_s = 15.0
    return (elapsed <= threshold_s), {"elapsed_s": round(elapsed, 3), "threshold_s": threshold_s}


def _run_pytest() -> tuple[int, str, list[str]]:
    # Gate against canonical tests to avoid archived run-artifact test collisions.
    test_targets = ["tests/test_api.py"]
    generated = ROOT / "tests" / "test_brownfield_generated.py"
    if generated.exists():
        test_targets.append("tests/test_brownfield_generated.py")

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *test_targets],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    out = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode, out, test_targets


def main() -> int:
    analysis_ok, analysis_errors = _analysis_gate()
    lint_ok, lint_output = _lint_gate()
    typing_ok, typing_output = _typing_gate()
    findings = _scan_for_secrets()
    rc, out, targets = _run_pytest()

    perf_ok, perf_detail = _performance_gate()

    security_ok = len(findings) == 0
    tests_ok = rc == 0
    all_ok = analysis_ok and lint_ok and typing_ok and security_ok and tests_ok and perf_ok

    report = {
        "timestamp": _now(),
        "analysis": {"ok": analysis_ok, "errors": analysis_errors},
        "linting": {"ok": lint_ok, "output": lint_output},
        "typing": {"ok": typing_ok, "output": typing_output},
        "security": {"ok": security_ok, "secret_scan_findings": findings},
        "performance": {"ok": perf_ok, **perf_detail},
        "tests": {"ok": tests_ok, "exit_code": rc, "targets": targets},
        "overall_ok": all_ok,
        "pytest_exit_code": rc,
        "pytest_targets": targets,
        "pytest_output_tail": "\n".join(out.splitlines()[-80:]),
    }
    (ROOT / "QUALITY_GATE_REPORT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if not analysis_ok:
        print("Analysis failed:")
        for e in analysis_errors[:40]:
            print(f"- {e}")
    if not lint_ok:
        print("Lint failed:")
        print(lint_output)
    if not typing_ok:
        print("Typing gate failed:")
        print(typing_output)
    if not security_ok:
        print("Secret-like patterns detected in:")
        for f in findings:
            print(f"- {f}")
    if not perf_ok:
        print(f"Performance gate failed: elapsed={perf_detail['elapsed_s']}s threshold={perf_detail['threshold_s']}s")
    print(report["pytest_output_tail"])
    if all_ok:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
