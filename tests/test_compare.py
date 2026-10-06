import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from agentproof.compare import Report, compare_reports, main


def report():
    return json.loads(Path("examples/llama32-first-run.json").read_text())


def test_identical_reports_pass():
    item = Report.model_validate(report())
    assert compare_reports(item, item)["gate_passed"]


def test_new_check_failure_detected_in_already_failing_case():
    old = report()
    new = copy.deepcopy(old)
    failing = next(r for r in new["results"] if not r["passed"])
    key = next(k for k, value in failing["checks"].items() if value)
    failing["checks"][key] = False
    result = compare_reports(Report.model_validate(old), Report.model_validate(new))
    assert not result["gate_passed"]
    assert result["regressions"] == [{"case_id": failing["case_id"], "checks": [key]}]
    assert result["baseline_passed"] == result["candidate_passed"]


@pytest.mark.parametrize("field,value", [("suite_sha256", "0" * 64), ("suite_version", "other"), ("mode", "replay")])
def test_incompatible_suites_and_modes_rejected(field, value):
    old = report()
    new = copy.deepcopy(old)
    new[field] = value
    if field == "mode":
        new["model"] = None
    with pytest.raises(ValueError):
        compare_reports(Report.model_validate(old), Report.model_validate(new))


def test_missing_case_rejected():
    old = report()
    new = copy.deepcopy(old)
    removed = new["results"].pop()
    new["total"] -= 1
    new["passed"] -= int(removed["passed"])
    with pytest.raises(ValueError):
        compare_reports(Report.model_validate(old), Report.model_validate(new))


def test_changed_check_contract_rejected():
    old = report()
    new = copy.deepcopy(old)
    new["results"][0]["checks"]["extra"] = True
    with pytest.raises(ValueError):
        compare_reports(Report.model_validate(old), Report.model_validate(new))


def test_inconsistent_totals_rejected():
    item = report()
    item["passed"] += 1
    with pytest.raises(ValidationError):
        Report.model_validate(item)


def test_inconsistent_pass_flag_rejected():
    item = report()
    item["results"][0]["passed"] = not item["results"][0]["passed"]
    item["passed"] = sum(r["passed"] for r in item["results"])
    with pytest.raises(ValidationError):
        Report.model_validate(item)


def test_cli_exit_codes_and_sanitized_errors(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(json.dumps(report()))
    candidate.write_text(baseline.read_text())
    output = tmp_path / "summary.json"
    assert main([str(baseline), str(candidate), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["gate_passed"]
    changed = report()
    passing = next(r for r in changed["results"] if r["passed"])
    passing["checks"]["policy"] = False
    passing["passed"] = False
    changed["passed"] -= 1
    candidate.write_text(json.dumps(changed))
    assert main([str(baseline), str(candidate)]) == 1
    candidate.write_text('{"secret": "PRIVATE_SENTINEL"}')
    assert main([str(baseline), str(candidate)]) == 2
    assert "PRIVATE_SENTINEL" not in capsys.readouterr().out


def test_model_changes_allowed_with_explicit_labels():
    old = report()
    new = copy.deepcopy(old)
    new["model"] = "candidate-model"
    result = compare_reports(Report.model_validate(old), Report.model_validate(new))
    assert result["candidate_model"] == "candidate-model"
