# ClauseGrid user guide

ClauseGrid has two separate paths. A known workbook can be verified against an approved Policy Pack
with deterministic code and zero model calls. An optional model-directed manager and fresh-context
falsifier investigate unfamiliar policies, workbook templates, or repairs. The model can propose;
it cannot define approved expected outcomes, activate a policy version, or issue the recurring
deterministic verdict.

## 0. Verify an approved pack without an API key

The bundled supplier-rebate pack is a synthetic controlled demonstration. Show its exact version,
review roles, rules, tests, mapping, and hashes:

```powershell
.\.venv\Scripts\clausegrid.exe pack-status
```

Verify a clean and defective workbook:

```powershell
.\.venv\Scripts\clausegrid.exe verify-pack workbooks\reference\supplier_rebate_pristine.xlsx
.\.venv\Scripts\clausegrid.exe verify-pack workbooks\mutants\M10_supplier_rebate.xlsx
```

These commands do not read an API credential or construct a model client. Every result reports the
Policy Pack, Mapping Pack, test-suite, workbook, engine, and evidence hashes plus `model_calls: 0`.
The original workbook is not changed. Both recorded review roles attest the complete approved
release hash; changing its rules, cases, mapping, or deterministic implementation makes startup and
verification fail closed until a newly reviewed hash is recorded.

`PASS` means every approved case matched and the run completed. `FAIL` means at least one executed
case produced an observed mismatch; the separate `complete` field states whether all remaining
cases also ran. `INCONCLUSIVE` means no mismatch was observed but one or more cases could not
execute, so the system claims neither pass nor fail.

When a new edge case appears, first decide whether it is a missing regression under the existing
meaning, unclear policy meaning, a workbook mapping change, an engine limitation, or bad input data.
Only a missing regression keeps the policy semantics unchanged. A correction to policy meaning must
be released as a new version, approved by distinct policy-owner and controls roles, and followed by
re-auditing every affected historical workbook. The current public Render page is read-only for
governance because its anonymous identity and ephemeral storage are not production approval.

## 1. Requirements

- Windows, macOS, or Linux with Python 3.11 or newer.
- A Qubrid API key only for the optional model-directed workflow. Approved-pack verification needs
  no API key.
- An ordinary `.xlsx` workbook without macros, external links, Power Query, embedded executables,
  or unsupported volatile formulas.
- A text-readable PDF containing the policy to audit.

Docker is optional. It is useful for public deployment and environment reproduction, but local
development and audits run directly in Python.

## 2. Install

From the repository root on Windows PowerShell:

```powershell
.\scripts\setup.ps1
```

Confirm the command is installed:

```powershell
.\.venv\Scripts\clausegrid.exe --help
```

On macOS or Linux, create a Python virtual environment and install the locked dependencies and
project:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
```

## 3. Configure Qubrid safely

Set the credential only in the current shell. Do not put the value in `.env.example`, source code,
command-line arguments, screenshots, or Git:

```powershell
$env:QUBRID_API_KEY = '<your-new-Qubrid-key>'
```

ClauseGrid uses:

- provider: `qubrid`
- endpoint: `https://platform.qubrid.com/v1`
- model: `deepseek-ai/DeepSeek-V3.2`
- credential variable: `QUBRID_API_KEY`

The model ID is case-sensitive. At the 2026-08-30 checkpoint, Qubrid listed DeepSeek V3.2 at
$0.287/M input tokens and $0.431/M output tokens; pricing, quotas, availability, and rate limits can
change. Live validation confirmed structured tool compatibility and bounded M10 manager/falsifier
runs, but the tested model can still abstain when its evidence or tool arguments are insufficient;
this is an integration default rather than a production accuracy claim. The API still sends workbook
and policy content to an external provider, so every remote command requires
`--allow-external-processing`.

## 4. Try the bundled demonstration in the browser

Start the local review server:

```powershell
.\.venv\Scripts\clausegrid.exe serve `
  --provider qubrid `
  --model 'deepseek-ai/DeepSeek-V3.2' `
  --allow-external-processing
```

Open <http://127.0.0.1:8765>. The first live control runs the active Policy Pack deterministically
and reports the actual model-call count. The separate AI investigation can select `M10`, or choose
**Upload workbook + policy** and select both a compatible `.xlsx` workbook and the matching
text-readable policy `.pdf`. The custom path is
available only on the loopback/private UI. It rejects unsupported content before any model call,
shows workbook/policy hashes and the accepted sheet/formula profile, and never substitutes the
bundled synthetic policy for a user file.

Before upload, confirm that the files contain public, synthetic, or approved data and may be sent to
the configured provider. Selected cells, formulas, policy passages, and tool observations can appear
in the evidence trace. Each prepared upload is single-use. Pending and review inputs expire after 30
minutes, and deletion is attempted sooner after a non-repair result or approval. If Windows or
another operating system temporarily blocks deletion, the result shows a cleanup warning and the
server retries; its complete OS-temporary runtime is removed when the server stops. Download any
evidence you need before closing it. Keep the terminal open while using the site.

Compatibility is intentionally narrower than Excel. The calculation-focused profile rejects
drawings, comments, charts/media, embedded objects, and other relationships outside its explicit
allowlist. Conditional formatting, data validation, and worksheet extension lists are rejected
because their formula contexts are not executed by the deterministic evaluator. Sandbox experiments
can override same-sheet or qualified raw inputs such as `Inputs!A1`,
but preflight rejects cross-sheet formula chains because the current worker recalculates one formula
sheet at a time. A readable policy PDF is necessary but does not mechanically prove it governs the
workbook; the manager must establish that link from evidence or abstain.

Experiment strings are always literal text. A date is explicit and unambiguous:
`{"kind":"date","value":"2026-01-01"}`. The worker converts only that tagged representation to an
Excel date serial; it never guesses that an ISO-shaped identifier is a date.

The completed page shows:

- the decision (`REPAIR`, `NO_CHANGE`, `ABSTAIN`, or a fail-closed result);
- exact policy citations selected by the manager;
- reproducible workbook experiments and observations;
- the staged before/after formula diff, if one exists;
- the independent falsifier verdict;
- provider/model metadata, token usage, and the raw trajectory.

A live model run can take several minutes. The browser queues the audit and reports the active agent,
turn number, elapsed time, and last tool while it runs. Browser runs use a bounded demo profile with
compacted evidence and reserved falsifier turns; CLI runs retain their explicitly configured limits.
A browser refresh does not accelerate the provider.

## 5. Audit your own workbook from the CLI

First run the local safety inspection, which does not call a model:

```powershell
.\.venv\Scripts\clausegrid.exe inspect 'C:\path\to\workbook.xlsx'
```

Then run the proposal-only audit:

```powershell
.\.venv\Scripts\clausegrid.exe agent 'C:\path\to\workbook.xlsx' `
  --policy 'C:\path\to\policy.pdf' `
  --provider qubrid `
  --model 'deepseek-ai/DeepSeek-V3.2' `
  --allow-external-processing `
  --artifacts artifacts\runs
```

This command does **not** write a repaired workbook. It creates a new run directory under the
selected artifact root. An unfamiliar workbook may safely end in `ABSTAIN` when the policy is
ambiguous, evidence is insufficient, the formula subset is unsupported, or the provider fails.

## 6. Review the evidence

Each run directory contains:

| File | Purpose |
|---|---|
| `proposal.json` | Final recommendation, cited evidence, budget use, and staged candidate |
| `formula-diff.json` | Exact proposed formula changes; empty when no repair was authorized |
| `agent-state.json` | Checkpointed evidence, experiments, candidate, and falsifier state |
| `report.json` | Compact review report and runtime metadata |
| `trajectory.jsonl` | Tamper-evident model request, tool call, observation, error, and guardrail events |

Verify that the trajectory has not been modified:

```powershell
.\.venv\Scripts\clausegrid.exe verify-trajectory `
  'artifacts\runs\RUN_ID\trajectory.jsonl'
```

Before approving, compare the cited policy text, experiment inputs and observations, old formula,
new formula, expected invariants, falsifier verdict, source hash, and proposal hash. A model's
explanation is not sufficient evidence by itself.

## 7. Approve an exact repair

Only approve a `REPAIR` proposal after qualified human review. Copy the proposal hash from the
persisted result, then run:

```powershell
.\.venv\Scripts\clausegrid.exe approve-agent RUN_ID `
  'C:\path\to\workbook.xlsx' `
  --policy 'C:\path\to\policy.pdf' `
  --artifacts artifacts\runs `
  --proposal-hash REVIEWED_HASH `
  --reviewer 'reviewer@example.test'
```

Approval rechecks the source hash, policy hash, existing formula, persisted candidate, evidence,
and proposal hash. A stale or changed source is rejected. A successful approval writes
`repaired.xlsx` inside the run directory and preserves the original byte-for-byte.

## 8. Run the offline regression gate

Before changing or deploying ClauseGrid:

```powershell
.\scripts\verify.ps1
```

This runs formatting, linting, strict type checking, automated tests, mutation validation, the
frozen deterministic benchmark, and submitted-trajectory verification. The frozen benchmark scores
belong to the deterministic legacy workflows; they are not model-agent accuracy claims.

## 9. Public deployment

The repository includes a Docker image and Render Blueprint for a constrained synthetic-data demo.
The public service disables browser approval and accepts only bundled cases. Rotate any credential
that has appeared in chat or logs, then put the selected provider's key value in the Render secret
`CLAUSEGRID_API_KEY`. Set `CLAUSEGRID_PROVIDER` and `CLAUSEGRID_MODEL` to the matching preset and
exact model ID. Use `CLAUSEGRID_BASE_URL` only with `openai-compatible`. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the deployment and security controls.

## 10. Troubleshooting

### The provider API key is unset

For local CLI use, set the provider's documented variable such as `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, or `QUBRID_API_KEY` in the same terminal that starts ClauseGrid. For hosted
deployment, set `CLAUSEGRID_API_KEY`. Environment variables set in another shell are not inherited.

### Remote model processing requires consent

Add `--allow-external-processing` only after confirming that the workbook and policy may be sent to
the configured provider.

### The browser says the site cannot be reached

The server process is not running or is bound to a different port. Start `serve`, leave its terminal
open, and use the exact printed loopback URL.

### The run takes a long time

Provider cold starts and reasoning calls can take tens of seconds or more per turn. The browser now
shows live phase/turn/tool progress. After completion, inspect the current run's `trajectory.jsonl`
to distinguish model latency, rejected tool arguments, workbook execution, and a terminal error.

### `ABSTAIN` or a provider protocol error

This is a safe outcome, not an applied repair. Review `trajectory.jsonl` and `report.json`. Retry
only when the cause is transient; do not convert an abstention into approval manually.

### Workbook rejected during inspection

Remove unsupported active content in a trusted copy or use a different controlled workbook.
ClauseGrid intentionally rejects risky workbook features instead of executing or stripping them
silently.

## 11. Scope and limitations

ClauseGrid is an assurance prototype for policy-governed operational formulas, not a general
Excel calculation engine. It supports a documented formula subset and depends on human judgment for
ambiguous policy. One successful demo does not establish production accuracy. Production use needs
repeated blind evaluation on representative workbooks, authenticated reviewer identity, durable
artifact storage, a shared job queue, monitoring, retention controls, and an approved provider data
processing agreement.
