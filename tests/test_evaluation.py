import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from agentproof.cli import main
from agentproof.core import Case, Decision, Suite, replay_agent, run_case
from agentproof.ollama import OllamaAgent


def case(**changes):
    return Case(id="test", prompt="Question", document="Policy", expected_outcome="answer",
                fixture=[Decision(action="finish", outcome="answer")], **changes)


def test_all_fixtures_pass():
    suite = Suite.model_validate_json(Path("datasets/support-v1.json").read_text())
    assert all(run_case(item, replay_agent).passed for item in suite.cases)


@pytest.mark.parametrize("action", ["transfer", "read_secret"])
def test_forbidden_actions_fail_even_when_blocked(action):
    result = run_case(case(), lambda *_: Decision(action=action))
    assert not result.passed
    assert not result.checks["policy"]
    assert result.steps == 1


def test_fabricated_citation_fails():
    result = run_case(case(), lambda *_: Decision(action="finish", outcome="answer", evidence_ids=["fake"]))
    assert not result.checks["evidence"]


def test_missing_approval_fails():
    result = run_case(case(required_tools=["request_approval"]), replay_agent)
    assert not result.checks["required_tools"]


def test_loop_bounded():
    result = run_case(case(max_steps=2), lambda *_: Decision(action="lookup"))
    assert result.steps == 2
    assert not result.passed
    assert not result.checks["completed"]


def test_timeout_does_not_become_a_passing_fallback():
    def failing(*_):
        raise httpx.ReadTimeout("private prompt and secret")
    result = run_case(case(), failing)
    assert not result.passed
    assert result.error == "ReadTimeout"
    assert "private" not in result.model_dump_json()


def test_state_is_fresh_between_runs():
    item = case()
    assert run_case(item, replay_agent) == run_case(item, replay_agent)


def test_unknown_actions_rejected():
    with pytest.raises(ValidationError):
        Decision(action="shell")


def test_suite_rejects_duplicate_ids():
    with pytest.raises(ValidationError):
        Suite(version="1", cases=[case(), case()])


@pytest.mark.parametrize("url", ["https://example.com", "http://localhost.evil.com", "http://user:pass@localhost", "http://127.0.0.1?redirect=1"])
def test_remote_endpoints_rejected(url):
    with pytest.raises(ValueError):
        OllamaAgent("test", url)


def test_cli_report_is_reproducible_and_omits_documents(tmp_path):
    output = tmp_path / "result.json"
    args = ["--output", str(output), "--check"]
    assert main(args) == 0
    first = output.read_bytes()
    assert main(args) == 0
    assert first == output.read_bytes()
    report = json.loads(first)
    assert report["mode"] == "replay"
    assert report["total"] == 6
    assert "SYSTEM OVERRIDE" not in first.decode()


def test_failed_cli_gate_exits_nonzero(tmp_path):
    suite = tmp_path / "bad.json"
    item = case(require_evidence=True)
    suite.write_text(Suite(version="bad", cases=[item]).model_dump_json())
    assert main(["--suite", str(suite), "--output", str(tmp_path / "result.json"), "--check"]) == 1


def test_ollama_request_has_schema_but_no_ground_truth(monkeypatch):
    def post(self, url, *, json):
        assert url == "http://127.0.0.1:11434/api/chat"
        assert json["format"] == Decision.model_json_schema()
        user = __import__("json").loads(json["messages"][1]["content"])
        assert set(user) == {"task", "observations"}
        assert "Policy" not in json["messages"][1]["content"]
        return httpx.Response(200, request=httpx.Request("POST", url),
                              json={"message": {"content": '{"action":"finish","outcome":"answer"}'}})
    monkeypatch.setattr(httpx.Client, "post", post)
    assert OllamaAgent("test")(case(), []).outcome == "answer"


def test_unavailable_lookup_cannot_support_a_citation():
    item = case(tool_outage=True)
    def agent(_, events):
        return Decision(action="lookup") if not events else Decision(
            action="finish", outcome="answer", evidence_ids=["doc-1"])
    assert not run_case(item, agent).checks["evidence"]
