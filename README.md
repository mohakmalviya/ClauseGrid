# FormulaWitness

FormulaWitness is a model-directed policy-assurance system for operational Excel workbooks. An audit manager discovers an unfamiliar workbook and policy through typed tools, forms and tests repair hypotheses, and sends staged candidates to a fresh-context falsifier. Deterministic services own formula execution, hashes, budgets, copy-on-write patching, and approval. A reviewer is required before any repaired workbook is written.

The flagship defect is deliberately plausible: a critical-incident waiver incorrectly bypasses an ordinary SLA penalty. The workbook opens, the formula is valid, and typical rows look reasonable. Only the policy-derived waiver counterexample exposes it.

## Intended user and bottleneck

FormulaWitness is for finance, procurement, and supplier-operations reviewers who approve rebate and SLA settlements. Their policy is written in prose while the payable amount is implemented in formulas, so ordinary spreadsheet linting can miss a syntactically valid threshold, exception, lookup, date, or rounding rule that silently overpays or underpays a supplier. FormulaWitness turns that manual policy-to-formula review into a cited, reproducible witness and preserves the final judgment for a qualified reviewer.

## Competition provenance

FormulaWitness began as the reviewed scaffold in root commit `0941c68`; the policy, synthetic workbooks, application, benchmark, interface, and evidence were created during the competition. Codex was the required coding agent. The language runtimes and dependencies listed in `requirements-lock.txt` were pre-existing tools. No pre-existing FormulaWitness application code or private dataset was used.

## Legacy deterministic benchmark

Frozen benchmark: **SupplierRebate-SLA-16-v2** — 12 one-fault mutants, three clean controls, one three-fault hard case, and 48 sealed vectors per workbook. Revision 2 was preregistered before its scored run after an adversarial audit required real ordered lookup, proportional proration, and a fully disjoint held-out input split.

| System | E2E Semantic Repair Rate | Clean Preservation | Hard case |
|---|---:|---:|---:|
| Deterministic direct baseline | 33.3% (4/12) | 100% | 0% |
| Deterministic advanced workflow | **100% (12/12)** | **100%** | **100%** |
| Improvement | **+66.7 percentage points** | no regression | +100 pp |

A repair counts only when every sealed output `L6:T6` is semantically correct, workbook integrity passes, the original is unchanged, and the patch respects the one-cell limit (three cells for the hard case). See [evals/results.json](evals/results.json). These numbers predate the model runtime and must not be presented as agent performance.

The archived hackathon-format comparison reports $0 API cost only for the legacy deterministic workflows. Model-agent cost is `Not reported`. No human time-saving claim is made without a qualified-reviewer study.

## Run it

Requirements: Python 3.11+ and PowerShell. Legacy deterministic evaluation remains offline. The
model-directed commands support OpenAI, native Anthropic/Claude, DeepSeek, NVIDIA NIM, OpenCode
Zen, and custom OpenAI-compatible endpoints. Credentials are read from provider-specific environment variables;
the key is never accepted as a CLI argument or persisted. Provider cost is recorded as `Not
reported` unless the provider supplies it.

```powershell
.\scripts\setup.ps1
.\scripts\eval.ps1
$env:NVIDIA_NIM_API_KEY = '<set outside the repository>'
.\.venv\Scripts\formulawitness.exe serve `
  --provider nvidia-nim --model openai/gpt-oss-120b `
  --allow-external-processing
```

Open `http://127.0.0.1:8765`, run M10, and inspect the model-selected policy citations,
sandbox experiments, independent falsifier verdict, exact formula diff, proposal hash, and raw JSONL
trajectory. If and only if a repair survives falsification, enter a local reviewer label to approve the
exact proposal and write a copied workbook. Provider, model, endpoint, and credential configuration
are server-side; the unauthenticated demo server refuses non-loopback binding.

Direct CLI equivalents:

```powershell
.\.venv\Scripts\formulawitness.exe baseline workbooks\mutants\M10_supplier_rebate.xlsx --reviewer reviewer@example.test
.\.venv\Scripts\formulawitness.exe advanced workbooks\mutants\M10_supplier_rebate.xlsx --reviewer reviewer@example.test
.\.venv\Scripts\formulawitness.exe inspect workbooks\reference\supplier_rebate_pristine.xlsx
.\.venv\Scripts\formulawitness.exe eval
```

Model-directed proposal and approval commands:

```powershell
$env:NVIDIA_NIM_API_KEY = '<set outside the repository>'
.\.venv\Scripts\formulawitness.exe agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider nvidia-nim --model openai/gpt-oss-120b --allow-external-processing
.\.venv\Scripts\formulawitness.exe agent-baseline workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider nvidia-nim --model openai/gpt-oss-120b --allow-external-processing
$env:OPENCODE_API_KEY = '<set outside the repository>'
.\.venv\Scripts\formulawitness.exe agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider opencode --model big-pickle --allow-external-processing
.\.venv\Scripts\formulawitness.exe approve-agent RUN_ID `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --proposal-hash REVIEWED_HASH --reviewer reviewer@example.test
```

The `agent` command is always proposal-only. Only the separate `approve-agent` command or local UI
approval gate can write a repaired copy, and both require an explicit reviewer label.
Any non-loopback model endpoint additionally requires `--allow-external-processing`; the CLI checks
this consent before reading the configured credential environment variable. Loopback development may
omit it. Browser requests never contain the provider credential.
Model choice is intentionally explicit; see [model selection evidence](docs/MODEL_SELECTION.md) for the
current task-specific tournament and its limitations.

The `opencode` provider uses OpenCode Zen's OpenAI-compatible chat endpoint. Model IDs remain
explicit because the free catalog and availability can change; query OpenCode's live model catalog
before running. FormulaWitness reads only `OPENCODE_API_KEY` from the process environment. See
[model providers](docs/PROVIDERS.md) for the currently verified free-model compatibility results.

## What makes it agentic

The `agent` command runs a real model-controlled loop:

1. The audit manager chooses workbook discovery, policy retrieval, dependency, and sandbox tools with input-dependent arguments.
2. Raw model responses, tool calls, observations, errors, retries, usage, and state transitions are stored in a tamper-evident JSONL trajectory.
3. Tool observations can change the next action. The live NIM smoke run includes a malformed falsifier experiment followed by a corrected call and successful sandbox execution.
4. The manager can revise a broken candidate, finish, abstain, or request a human. Python does not select a fixed investigation sequence.
5. A staged proposal launches a separate falsifier with fresh context and read/sandbox-only tools. Only `SURVIVED` can unlock `submit_repair`.
6. The model never receives an apply or approval tool. Reviewer approval is a separate hash-bound command followed by deterministic replay on a copy.

`agent-baseline` is the fair one-model comparison: the same provider, discovery tools, sandbox, and limits, but one candidate, one candidate validation, and no falsifier. The old `baseline`, `advanced`, and `eval` commands are retained and explicitly labeled legacy deterministic workflows.

## Safety boundary

- Ordinary `.xlsx` only; `.xlsm`, VBA, OLE/ActiveX, DDE, external links, Power Query/connections, volatile formulas, and network refreshes are rejected.
- The source hash is checked before and after every run; repairs are copy-on-write.
- The evaluator supports arithmetic, comparisons, direct/qualified cell references, ranges, and `IF`, `AND`, `OR`, `MAX`, `MIN`, `ROUND`, and ordered `LOOKUP`. Anything else fails closed.
- Approval is immutable and hash-bound. A stale or unexpected old formula cannot be patched.
- Public rule execution labels visible cases. Held-out vectors and the independent oracle live under `evals/sealed`, outside the installed repair package; evaluation gives each repair process only staged workbook/policy inputs and applies a file-capability guard that denies ordinary access to evaluator files.

This is a focused assurance prototype, not a general Excel replacement. Its main real-world failure mode is ambiguous or conflicting policy language; such rules must produce an abstention and human clarification rather than an invented oracle.

## Repository map

```text
policies/       Synthetic source policy PDF
workbooks/      Pristine, 12 mutants, 3 controls, and hard workbook
src/            Formula parser, safe OOXML layer, agents, UI, and CLI
fixtures/       Frozen build and benchmark manifests
evals/          Sealed evaluator outputs and scored results
artifacts/      Benchmark validation and submission evidence
trajectories/   Submitted baseline/advanced JSONL trajectories
tests/          Unit, integration, security, and evaluation tests
docs/           Architecture, reproduction, limitations, demo, and disclosure
```

More detail: [Submission report](docs/SUBMISSION_REPORT.md), [Improvement changelog](docs/IMPROVEMENT_CHANGELOG.md), [Architecture](docs/ARCHITECTURE.md), [Model providers](docs/PROVIDERS.md), [Reproduction](docs/REPRODUCE.md), [Metric](docs/METRIC.md), [Security](docs/SECURITY.md), and [five-minute demo](docs/DEMO_SCRIPT.md).
