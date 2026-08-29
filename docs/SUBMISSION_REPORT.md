# Hackathon Submission Report

> **Status correction:** the 33.3%-versus-100% table below evaluates the legacy deterministic
> workflows. It is retained as regression evidence and must not be described as model-agent
> performance. The current model-directed manager/falsifier has a successful live NIM smoke but has
> not yet been scored on a frozen blind agent benchmark. Model API cost is not reported by NIM.

## Problem and intended user

Finance, procurement, and supplier-operations reviewers approve settlements whose governing
policy is prose while the payable amount is encoded in spreadsheet formulas. A workbook can open,
calculate, and return a plausible number while implementing the wrong threshold, exception,
lookup, date, or rounding rule. The business risk is a silent overpayment or underpayment that
ordinary spreadsheet linting cannot explain against policy.

FormulaWitness converts the policy into cited typed rules and discriminating counterexamples,
executes the workbook through a fail-closed worker, localizes semantic drift, proposes the smallest
supported repair, requires human approval, and independently replays the repaired copy.

## Evaluation contract defined before the final run

The primary metric is End-to-End Semantic Repair Rate over 12 single-fault mutants. Success
requires all 48 sealed vectors to match an independent oracle on `L6:T6`, workbook integrity to
pass, the source hash to remain unchanged, no unrelated formula to change, and no more than one
core cell to change. The advanced solution was accepted only if it improved by at least 20
percentage points without increasing false repairs. Clean controls and H01 are reported separately.

## Final comparison

| Metric | Simple baseline | FormulaWitness | Change |
|---|---:|---:|---:|
| Primary outcome: E2E-SRR | 33.3% (4/12) | **100% (12/12)** | **+66.7 pp** |
| Clean preservation | 100% (3/3) | **100% (3/3)** | no regression |
| Challenging case H01 | 0% (0/1) | **100% (1/1)** | **+100 pp** |
| Automated wall-clock, M10 median of 5 | 0.331 s | 0.451 s | +0.121 s |
| Human time per task | Not measured | Not measured | No claim |
| Model/API cost per task | $0.00 (legacy) | $0.00 (legacy) | $0.00 (legacy) |

The runtime row is an end-to-end local measurement on the recorded Windows/Python environment;
it is not a latency guarantee. FormulaWitness spends about 0.12 additional seconds on M10 to
produce the evidence, repair, approval record, and repaired copy that the direct baseline misses.
Local compute was not monetized. Human time is explicitly **not measured** because no qualified-
reviewer timing study has been run; the project makes no unsupported time-saving claim. The
reproducible samples and environment are in
`artifacts/submission/performance-results.json`, and a proper study protocol is in
[HUMAN_TIME_STUDY.md](HUMAN_TIME_STUDY.md).

Complete per-case correctness evidence is in `evals/results.json` and the submitted copy at
`artifacts/submission/evaluation-results.json`.

## Model-agent implementation checkpoint

The current `agent` command is a model-controlled audit manager with generic discovery/retrieval/
sandbox tools and an independent fresh-context falsifier. A live `openai/gpt-oss-120b` NIM run on
M10 produced a proposal-only P6 repair after 17 manager turns, 10 falsifier turns, 27 tool calls,
and six sandbox executions. The run included a falsifier tool-schema failure followed by a corrected
model call and successful experiment, demonstrating observation-driven replanning. This is a smoke
test, not a correctness rate. The `agent-baseline` command provides the one-candidate/no-falsifier
comparison required for future blind repeated evaluation.

## Challenging case and what it revealed

H01 combines a wrong ordered lookup, an over-broad critical-waiver exception, and an incorrect cap
order. The errors interact through downstream settlement cells, so fixing the first visible symptom
is insufficient. The baseline returned `NO_CHANGE`, passed 9/48 sealed vectors, and failed first at
H10. FormulaWitness changed exactly `N6`, `P6`, and `S6`, passed 48/48, preserved the source, and
made no unrelated change.

The case revealed why FormulaWitness replays the complete public witness set after each candidate
and permits a bounded three-step search only for the declared three-fault case. Localization is a
ranking, not proof; complete replay and minimality are the acceptance gate.

## Improvement story

The stage-by-stage baseline, experiments, evidence, decisions, removed leakage-prone design, main
failure mode, and hot take are recorded in
[IMPROVEMENT_CHANGELOG.md](IMPROVEMENT_CHANGELOG.md). The main measured contribution is the
combination of typed policy evidence, discriminating witnesses, dependency/spectrum localization,
constrained replay, and sealed verification-not the number of named agents.

## Competition provenance

The Git root commit `0941c68` contains only the reviewed scaffold and project specification. The
policy, workbooks, implementation, evaluation, interface, artifacts, and documentation were added
during the competition. OpenAI Codex was the required coding agent. ReportLab, pypdf, Pillow,
pytest, mypy, Ruff, Hatchling, and the Codex-bundled workbook authoring tool were pre-existing tools;
no pre-existing FormulaWitness application code or private dataset was used.

## Deliverable status

| PDF deliverable | Evidence | Status |
|---|---|---|
| Complete code and improvement changelog | repository, `README.md`, agent instructions, changelog | complete |
| Clean-environment reproduction guide | `docs/REPRODUCE.md`, pinned lock, verified remote clone | complete |
| Solution video, maximum five minutes | `docs/DEMO_SCRIPT.md` | **recording/upload still required from the entrant** |
| Representative agent trajectories | `trajectories/*.jsonl`, hash-chain verifier | complete |

The code must not be described as fully submitted until the entrant records the video and supplies
the video link in the hackathon form.
