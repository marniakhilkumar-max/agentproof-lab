# Design decisions

## Separation of policy from generation

The model selects an action, but deterministic code decides which tools execute.
The prohibited transfer and secret-read actions are observable choices, never
implemented capabilities. A prohibited request fails the case even if blocked.
Tool outages are explicit events; they never return fabricated evidence.

## Evaluation integrity

Replay and live modes have different report labels. Gold labels and replay
decisions are excluded from the live model's prompt. Missing completions,
adapter exceptions, invented citations, and unmet tool prerequisites fail gates.
All checks use observable events, not an LLM judging its own answer.

The replay baseline verifies the evaluator and is not model-quality evidence.
An exact dataset hash ties each report to the scenario version. For serious model
comparisons, retain model digests and runtime versions, repeat trials, expand the
dataset, and measure variability. Temperature zero alone does not guarantee
bitwise reproducibility across hardware or model versions.

## Deliberate omissions

No vector database: six short documents do not justify one.
No cloud service: the included tasks fit local inference and offline CI.
No orchestration dependency: the callable adapter can wrap an existing graph.
No simulated accuracy claims: only executed checks are reported.
No production payment integration: tools are explicitly simulated.

## Data handling

The committed dataset is entirely synthetic. Live inputs stay on loopback Ollama.
Reports omit source prompts and documents, but case IDs and evidence IDs remain.
Do not use sensitive values as identifiers. User-defined adapters must be trusted
and are responsible for their own data handling and timeouts.
