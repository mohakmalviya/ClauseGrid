# Architecture

## Model-directed system flow

```text
workbook + policy
       |
       v
deterministic safety gate
       |
       v
Audit Manager (model-controlled loop) <------------------------------+
  | policy retrieval + exact citations                               |
  | workbook discovery + dependency inspection                       |
  | sandbox experiments + candidate staging                          |
  +----> fresh-context Falsifier ---- counterexample / verdict -------+
       |
       +----> repair proposal / no change / abstain / human request
       |
       v
separate reviewer hash approval
       |
       v
guarded patch to copy -> formula-scope validation -> experiment replay
```

Python fixes no investigation sequence. The model selects tools, arguments, retries, candidate
revisions, specialist invocation, and terminal action. Python validates schemas, executes narrow
tools, enforces budgets, and prevents irreversible model actions.

## Runtime components

- `model_client.py`: provider-neutral OpenAI-compatible client. Credentials come only from a named
  environment variable. It implements bounded retry, request pacing, timeout, normalized tool calls,
  usage accounting, and secret-safe errors.
- `agent_loop.py`: feeds each model-selected tool observation back to the same actor until a terminal
  tool, budget, or error stops the run.
- `agent_tools.py`: run-scoped typed tools for policy retrieval, workbook discovery, dependency
  inspection, sandbox experiments, candidate staging, falsification, submission, no-change, and
  human escalation. Tools never accept filesystem paths.
- `falsifier.py`: independent fresh context with read/sandbox tools and no stage, submit, approval,
  or apply capability. `BROKEN` requires an executed counterexample; conclusive verdicts require
  executed evidence.
- `agentic.py`: deterministic safety gate, state/artifact persistence, proposal-only execution, fair
  single-agent mode, separate approval, copy-on-write publication, changed-formula validation, and
  replay of the candidate experiments on the copied workbook.
- `policy_text.py`: policy-only PDF retrieval with exact mechanically verified citations. It does not
  import the frozen supplier rule compiler.
- `workbook_tools.py`: template-neutral manifest, region, formula, and dependency inspection.
- `experiment_worker.py`: separate no-network formula process receiving explicit sheet/cell inputs,
  observations, and hash-guarded candidate formulas. It imports no policy, benchmark, or evaluator.
- `trace.py`: schema-v3 raw observable model/tool/observation events in a tamper-evident hash chain.
  It stores no hidden chain-of-thought and redacts credential fields and bearer values.
- `agent_budget.py`: fail-closed manager/falsifier turns, model calls, tool calls, tokens, workbook
  executions, retries, elapsed time, and optional reported-cost limits.

## Authority boundary

The model can read bounded evidence, run a formula candidate in the sandbox, and stage typed data.
It cannot access paths, shell, Python execution, environment variables, arbitrary networking,
evaluator files, approval, or workbook-write tools. The API client runs in the controller process;
the workbook worker receives a minimal environment without API credentials.

`approve-agent` requires a reviewer identity and the hash of the exact persisted proposal. It
revalidates source/policy hashes and old formulas, patches a pending copy, proves that only authorized
formula targets changed, replays the candidate experiments, and only then publishes
`repaired.xlsx`. The source is never modified.

## Comparison modes

- `agent-baseline`: same model, policy/workbook discovery tools, sandbox, budgets, and guardrails;
  one candidate, one candidate validation, no falsifier, and no second candidate.
- `agent`: manager plus independent falsifier feedback and candidate revision.
- `baseline`, `advanced`, and `eval`: retained legacy deterministic workflows. Their frozen
  33.3%-versus-100% benchmark is regression evidence for the deterministic layer, not agent evidence.

## Evaluation boundary

The agentic runtime does not import `policy.py`, `public_benchmark.py`, `benchmark.py`,
`evaluation.py`, `evals.*`, mutation descriptions, sealed cases, or reference formulas. A fair agent
claim still requires a frozen blind set of unseen workbook-policy pairs, at least five trials per
task, the single-agent comparison, falsifier ablation, and independent scoring. The successful live
NIM smoke is implementation evidence, not a benchmark score.

## Known scope

FormulaWitness executes a documented nonvolatile formula subset rather than Excel itself. Macros,
external links, embedded objects, connections, volatile/network formulas, unsupported syntax,
ambiguous policy meaning, stale hashes, broad changes, and exhausted budgets fail closed.
