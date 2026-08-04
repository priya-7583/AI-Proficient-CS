from __future__ import annotations

import argparse
from pathlib import Path

from workflow.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AI-Proficient execution workflow")
    parser.add_argument("--scenario", choices=["greenfield", "brownfield", "ambiguous"], required=True)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--no-validate", action="store_true")
    parser.add_argument("--clarification", default=None)
    parser.add_argument("--require-signoff", action="store_true")
    parser.add_argument("--signoff-file", default=None)
    args = parser.parse_args()

    report = run_pipeline(
        str(Path(__file__).resolve().parent),
        scenario=args.scenario,
        output_root=args.output_root,
        auto_approve=True,
        require_signoff=args.require_signoff,
        signoff_path=args.signoff_file,
        clarification=args.clarification,
        run_validation=not args.no_validate,
    )

    print(f"run_id={report.run_id}")
    print(f"scenario={report.scenario}")
    print(f"status={report.status}")
    print(f"workspace={report.workspace}")
    print(f"quality_gate_exit_code={report.quality_gate_exit_code}")
    # Non-zero return indicates workflow or validation failure in automation.
    return 0 if report.status == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
