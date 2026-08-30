import argparse
import hashlib
import json
from pathlib import Path

from .core import Suite, replay_agent, run_case
from .ollama import OllamaAgent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate agent trajectories with deterministic policy checks")
    parser.add_argument("--suite", type=Path, default=Path("datasets/support-v1.json"))
    parser.add_argument("--mode", choices=["replay", "ollama"], default="replay")
    parser.add_argument("--model", default="llama3.1:8b")
    parser.add_argument("--output", type=Path, default=Path("reports/result.json"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    raw = args.suite.read_bytes()
    suite = Suite.model_validate_json(raw)
    agent = replay_agent if args.mode == "replay" else OllamaAgent(args.model)
    results = []
    for case in suite.cases:
        result = run_case(case, agent)
        results.append(result)
        print(f"{case.id}: {'PASS' if result.passed else 'FAIL'} ({result.steps} steps)", flush=True)
    passed = sum(result.passed for result in results)
    report = {"schema_version": 1, "suite_version": suite.version,
              "suite_sha256": hashlib.sha256(raw).hexdigest(), "mode": args.mode,
              "model": args.model if args.mode == "ollama" else None,
              "scope": "Synthetic support tasks; replay measures the harness, not LLM quality.",
              "passed": passed, "total": len(results),
              "results": [result.model_dump() for result in results]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{args.mode}: {passed}/{len(results)} cases passed. Report: {args.output}")
    return int(args.check and passed != len(results))


if __name__ == "__main__":
    raise SystemExit(main())
