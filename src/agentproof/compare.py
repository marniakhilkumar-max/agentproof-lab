"""Compare compatible evaluation reports without hiding per-check regressions."""
import argparse
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .core import Result


class Report(BaseModel):
    schema_version: Literal[1]
    suite_version: str
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mode: Literal["replay", "ollama"]
    model: str | None
    passed: int = Field(ge=0)
    total: int = Field(ge=1)
    results: list[Result] = Field(min_length=1)

    @model_validator(mode="after")
    def consistent(self):
        ids = [item.case_id for item in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate case IDs")
        if self.total != len(ids) or self.passed != sum(r.passed for r in self.results):
            raise ValueError("Report totals disagree with results")
        for result in self.results:
            if not result.checks or result.passed != all(result.checks.values()):
                raise ValueError("Pass flag disagrees with checks")
        if (self.mode == "replay" and self.model is not None) or (self.mode == "ollama" and not self.model):
            raise ValueError("Model metadata disagrees with evaluation mode")
        return self


def compare_reports(baseline: Report, candidate: Report) -> dict:
    for field in ("schema_version", "suite_version", "suite_sha256", "mode"):
        if getattr(baseline, field) != getattr(candidate, field):
            raise ValueError(f"Incompatible {field}")
    before = {r.case_id: r for r in baseline.results}
    after = {r.case_id: r for r in candidate.results}
    if before.keys() != after.keys():
        raise ValueError("Incompatible case IDs")
    regressions = []
    improvements = []
    for case_id in sorted(before):
        old, new = before[case_id], after[case_id]
        if old.checks.keys() != new.checks.keys():
            raise ValueError(f"Incompatible checks for {case_id}")
        lost = sorted(k for k in old.checks if old.checks[k] and not new.checks[k])
        gained = sorted(k for k in old.checks if not old.checks[k] and new.checks[k])
        if lost:
            regressions.append({"case_id": case_id, "checks": lost})
        if gained:
            improvements.append({"case_id": case_id, "checks": gained})
    return {"schema_version": 1, "mode": candidate.mode,
            "baseline_model": baseline.model, "candidate_model": candidate.model,
            "baseline_passed": baseline.passed, "candidate_passed": candidate.passed,
            "total": candidate.total, "regressions": regressions,
            "improvements": improvements, "gate_passed": not regressions}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reject per-check agent evaluation regressions")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        baseline = Report.model_validate_json(args.baseline.read_bytes())
        candidate = Report.model_validate_json(args.candidate.read_bytes())
        summary = compare_reports(baseline, candidate)
    except (OSError, ValueError):
        # Validation exceptions can contain report content; do not export them.
        print("Comparison rejected: invalid, unreadable, or incompatible reports.")
        return 2
    rendered = json.dumps(summary, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if summary["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
