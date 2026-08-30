# ClauseGrid

ClauseGrid is policy-to-spreadsheet assurance for operational Excel workbooks. Qualified reviewers
approve cited policy meaning as an immutable Policy Pack; recurring audits then compare known
workbooks with an independent deterministic rule oracle and require zero model calls. An optional
model-directed manager/falsifier path remains available for unfamiliar policies, mappings, and
repair investigation, but a model never owns the approved expected result or recurring verdict.

The flagship defect is deliberately plausible: a critical-incident waiver incorrectly bypasses an ordinary SLA penalty. The workbook opens, the formula is valid, and typical rows look reasonable. Only the policy-derived waiver counterexample exposes it.

## Intended user and bottleneck

ClauseGrid is for finance, procurement, and supplier-operations reviewers who approve rebate and SLA settlements. Their policy is written in prose while the payable amount is implemented in formulas, so ordinary spreadsheet linting can miss a syntactically valid threshold, exception, lookup, date, or rounding rule that silently overpays or underpays a supplier. ClauseGrid turns that manual policy-to-formula review into a cited, reproducible witness and preserves the final judgment for a qualified reviewer.

## Approved Policy Pack and zero-model replay

The repository contains one complete, deliberately narrow supplier-rebate Policy Pack. Its
version-controlled release metadata requires separate policy-owner and controls-review roles. Exact
rules and citations, generated boundary cases, a retained waiver-scope regression, a workbook
mapping, engine versions, and the exact deterministic implementations are materialized into one
approved release hash with separate test-suite and mapping hashes. Both demo review records attest
the same release hash, so changing a rule, test, mapping, generator, or engine invalidates approval.

Expected results are computed by `policy_oracle.py` using direct `Decimal` and date semantics. It
does not import the spreadsheet formula evaluator. The workbook is executed separately, so a shared
formula-engine bug cannot make both sides agree. The public pack uses clearly labelled synthetic
demo approvals; production approval requires authenticated identities and durable storage.

```powershell
# Neither command reads an API key or calls a model.
.\.venv\Scripts\clausegrid.exe pack-status
.\.venv\Scripts\clausegrid.exe verify-pack workbooks\reference\supplier_rebate_pristine.xlsx
.\.venv\Scripts\clausegrid.exe verify-pack workbooks\mutants\M10_supplier_rebate.xlsx
```

The first workbook returns `PASS`; M10 returns `FAIL` because the permanent waiver-scope regression
case catches it. A run with no observed mismatch but incomplete execution returns `INCONCLUSIVE`,
not a fabricated pass or failure. If a mismatch is observed during an incomplete run, the result is
`FAIL` with `complete: false`, preserving both facts. A discovered edge case must be classified before it changes anything: an existing
rule may gain a regression test, unclear meaning requires a new Policy Pack, a moved cell changes
the Mapping Pack, and engine or source-data problems remain separate. An active version is never
edited in place. The bundled and public demo is intentionally read-only: it verifies one controlled
release but does not implement authenticated draft approval, supersession, or historical audit
lookup. Those require the durable governance service described in the architecture.

## Competition provenance

ClauseGrid began as the reviewed scaffold in root commit `0941c68`; the policy, synthetic workbooks, application, benchmark, interface, and evidence were created during the competition. Codex was the required coding agent. The language runtimes and dependencies listed in `requirements-lock.txt` were pre-existing tools. No pre-existing ClauseGrid application code or private dataset was used.

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
model-directed commands support Qubrid, OpenAI, native Anthropic/Claude, DeepSeek, NVIDIA NIM,
OpenCode Zen, OpenRouter, Groq, Together, Gemini, Mistral, xAI, and custom OpenAI-compatible
endpoints. Credentials are read from provider-specific environment variables;
the key is never accepted as a CLI argument or persisted. Provider cost is recorded as `Not
reported` unless the provider supplies it.

```powershell
.\scripts\setup.ps1
.\scripts\eval.ps1
$env:QUBRID_API_KEY = '<set outside the repository>'
.\.venv\Scripts\clausegrid.exe serve `
  --provider qubrid --model 'deepseek-ai/DeepSeek-V3.2' `
  --allow-external-processing
```

Open `http://127.0.0.1:8765`, then either run M10 or select **Upload workbook + policy** to privately
stage a compatible `.xlsx` together with its governing text-readable `.pdf`. Custom inputs pass
OOXML, formula-profile, PDF, size, and hash preflight before the model is called. They live under an
isolated OS-temporary runtime rather than the repository. Deletion is attempted before exposing a
non-repair result or successful approval; an operating-system deletion failure is shown explicitly
and queued for retry instead of leaving the job running. Inspect the model-selected policy citations, sandbox experiments, independent falsifier
verdict, exact formula diff, proposal hash, and raw JSONL trajectory. If and only if a repair survives
falsification, enter a local reviewer label to approve the exact proposal and write a copied workbook.
Provider, model, endpoint, and credential configuration are server-side. The public browser receives
only a generic managed-runtime label; exact runtime identity remains in controlled audit artifacts.

The page first exposes the active synthetic Policy Pack and a **Run deterministic verification**
control. That route uses the committed pack and makes zero model calls. The slower AI investigation
below it is a separate onboarding/diagnostic path and never modifies the active pack.

Real-file mode requires both files. ClauseGrid will not silently compare an uploaded workbook
against the bundled synthetic supplier policy. The browser also requires confirmation that the data
is public, synthetic, or approved for processing by the configured model provider. Pending uploads
and retained review inputs expire after 30 minutes, and browser retries reuse the same prepared
upload. Stopping the server removes the complete temporary runtime. The Render demo enables the same
path behind same-origin checks, separate upload throttling, audit rate limits, and ephemeral storage;
it remains an anonymous demonstration and must not receive confidential data.

Direct CLI equivalents:

```powershell
.\.venv\Scripts\clausegrid.exe baseline workbooks\mutants\M10_supplier_rebate.xlsx --reviewer reviewer@example.test
.\.venv\Scripts\clausegrid.exe advanced workbooks\mutants\M10_supplier_rebate.xlsx --reviewer reviewer@example.test
.\.venv\Scripts\clausegrid.exe inspect workbooks\reference\supplier_rebate_pristine.xlsx
.\.venv\Scripts\clausegrid.exe eval
```

Model-directed proposal and approval commands:

```powershell
$env:QUBRID_API_KEY = '<set outside the repository>'
.\.venv\Scripts\clausegrid.exe agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider qubrid --model 'deepseek-ai/DeepSeek-V3.2' `
  --allow-external-processing
.\.venv\Scripts\clausegrid.exe agent-baseline workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider nvidia-nim --model openai/gpt-oss-120b --allow-external-processing
$env:OPENCODE_API_KEY = '<set outside the repository>'
.\.venv\Scripts\clausegrid.exe agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider opencode --model big-pickle --allow-external-processing
.\.venv\Scripts\clausegrid.exe approve-agent RUN_ID `
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
before running. ClauseGrid reads only `OPENCODE_API_KEY` from the process environment. See
[model providers](docs/PROVIDERS.md) for the currently verified free-model compatibility results.

The `qubrid` preset uses `https://platform.qubrid.com/v1` and reads `QUBRID_API_KEY`. Qubrid model
IDs remain explicit and are not the public deployment default. Task-level evidence and eliminated
alternatives are recorded in [model selection evidence](docs/MODEL_SELECTION.md).

## Publish the synthetic public demo

The repository includes a non-root Docker image, an environment-only deployment entry point, and a
Render Blueprint. Public mode accepts bundled benchmarks plus explicitly consented `.xlsx`/`.pdf`
pairs, runs one audit at a time in a background job, applies upload and audit request limits, enforces
the configured HTTPS Host/Origin, and never sends provider identity, credentials, or administrator
credentials to the browser. It also exposes the committed synthetic Policy Pack and its zero-model
verification route. Browser policy or repair approval is disabled; the public site demonstrates the
mechanism rather than treating anonymous clicks as governance.

1. Push the private repository to GitHub and create a Render Blueprint from `render.yaml`.
2. Enter a fresh Qubrid key as the Blueprint's `CLAUSEGRID_API_KEY` secret.
3. The Blueprint selects `qubrid` and `deepseek-ai/DeepSeek-V4-Flash`; change both values together
   if you deliberately choose a different provider/model route.
4. Deploy. Render supplies `RENDER_EXTERNAL_URL`; the container binds to Render's `PORT` on
   `0.0.0.0` and exposes `/healthz`.

The service is intentionally single-instance and stores run artifacts in `/tmp`; jobs and downloads
do not survive a restart. This is an internet-visible hackathon demonstration, not a production
multi-tenant service. Exact commands, controls, and operational limits are in
[deployment](docs/DEPLOYMENT.md).

## What makes it agentic

The `agent` command runs a real model-controlled loop:

1. The audit manager chooses workbook discovery, policy retrieval, dependency, and sandbox tools with input-dependent arguments.
2. Raw model responses, tool calls, observations, errors, retries, usage, and state transitions are stored in a tamper-evident JSONL trajectory.
3. Tool observations and validation failures change the next action. The controller caches repeated reads, forces executable evidence after bounded discovery, and reserves decision/verdict turns so malformed actions cannot consume the entire run.
4. The manager can revise a broken candidate, finish, abstain, or request a human. Python does not select a fixed investigation sequence.
5. A staged proposal launches a separate falsifier with fresh context and read/sandbox-only tools. It must run expectation-graded, candidate-sensitive experiments before a conclusive verdict; only `SURVIVED` can unlock `submit_repair`.
6. The model never receives an apply or approval tool. Reviewer approval is a separate hash-bound command followed by deterministic replay on a copy.

`agent-baseline` is the fair one-model comparison: the same provider, discovery tools, sandbox, and limits, but one candidate, one candidate validation, and no falsifier. The old `baseline`, `advanced`, and `eval` commands are retained and explicitly labeled legacy deterministic workflows.

## Safety boundary

- Calculation-focused `.xlsx` only; `.xlsm`, VBA, OLE/ActiveX, DDE, external links, Power Query/connections, drawings, conditional formatting, data validation, worksheet extensions, volatile formulas, and network refreshes are rejected.
- The source hash is checked before and after every run; repairs are copy-on-write.
- The evaluator supports arithmetic, comparisons, bounded direct/qualified cell references and ranges, plus `IF`, `AND`, `OR`, `MAX`, `MIN`, `ROUND`, ordered `LOOKUP`, and literal equality `COUNTIF`. The uploaded workbook's initial calculation is executed during preflight; anything outside this profile fails closed before a custom browser run spends model tokens.
- Experiments can vary same-sheet inputs or qualified raw inputs such as `Inputs!A1`. Cross-sheet formula-to-formula chains are rejected during upload preflight because the current sandbox recalculates one formula sheet at a time.
- Approval is immutable and hash-bound. A stale or unexpected old formula cannot be patched.
- Repaired bytes are not offered for download unless the approval commit marker is valid and binds
  their exact SHA-256 hash.
- Public rule execution labels visible cases. Held-out vectors and the independent oracle live under `evals/sealed`, outside the installed repair package; evaluation gives each repair process only staged workbook/policy inputs and applies a file-capability guard that denies ordinary access to evaluator files.

This is a focused assurance prototype, not a general Excel replacement. Its main real-world failure mode is ambiguous or conflicting policy language; such rules must produce an abstention and human clarification rather than an invented oracle.

## Repository map

```text
policies/       Synthetic source policy PDF
policy_packs/   Version-controlled controlled-pack release and regression cases
workbooks/      Pristine, 12 mutants, 3 controls, and hard workbook
src/            Formula parser, safe OOXML layer, agents, UI, and CLI
fixtures/       Frozen build and benchmark manifests
evals/          Sealed evaluator outputs and scored results
artifacts/      Benchmark validation and submission evidence
trajectories/   Submitted baseline/advanced JSONL trajectories
tests/          Unit, integration, security, and evaluation tests
docs/           Architecture, reproduction, limitations, demo, and disclosure
```

Start with the [user guide](docs/USER_GUIDE.md). More detail: [Submission report](docs/SUBMISSION_REPORT.md), [Improvement changelog](docs/IMPROVEMENT_CHANGELOG.md), [Architecture](docs/ARCHITECTURE.md), [Model providers](docs/PROVIDERS.md), [Reproduction](docs/REPRODUCE.md), [Metric](docs/METRIC.md), [Security](docs/SECURITY.md), [deployment](docs/DEPLOYMENT.md), and [five-minute demo](docs/DEMO_SCRIPT.md).
