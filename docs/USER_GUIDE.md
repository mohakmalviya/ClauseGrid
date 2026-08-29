# FormulaWitness user guide

FormulaWitness audits ordinary `.xlsx` workbooks against a written PDF policy. A model-directed
manager chooses what to inspect and which sandbox experiments to run. A separate fresh-context
falsifier challenges any proposed formula repair. The system never edits the submitted workbook
during an audit: it produces a reviewable proposal, and only a separate human approval command can
write a repaired copy.

## 1. Requirements

- Windows, macOS, or Linux with Python 3.11 or newer.
- A Qubrid API key for the default model-directed workflow.
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
.\.venv\Scripts\formulawitness.exe --help
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

FormulaWitness uses:

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
.\.venv\Scripts\formulawitness.exe serve `
  --provider qubrid `
  --model 'deepseek-ai/DeepSeek-V3.2' `
  --allow-external-processing
```

Open <http://127.0.0.1:8765>, select `M10`, and start an audit. Keep the terminal open while using
the site. The local UI accepts only bundled synthetic cases; use the CLI for your own workbook.

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

## 5. Audit your own workbook

First run the local safety inspection, which does not call a model:

```powershell
.\.venv\Scripts\formulawitness.exe inspect 'C:\path\to\workbook.xlsx'
```

Then run the proposal-only audit:

```powershell
.\.venv\Scripts\formulawitness.exe agent 'C:\path\to\workbook.xlsx' `
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
.\.venv\Scripts\formulawitness.exe verify-trajectory `
  'artifacts\runs\RUN_ID\trajectory.jsonl'
```

Before approving, compare the cited policy text, experiment inputs and observations, old formula,
new formula, expected invariants, falsifier verdict, source hash, and proposal hash. A model's
explanation is not sufficient evidence by itself.

## 7. Approve an exact repair

Only approve a `REPAIR` proposal after qualified human review. Copy the proposal hash from the
persisted result, then run:

```powershell
.\.venv\Scripts\formulawitness.exe approve-agent RUN_ID `
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

Before changing or deploying FormulaWitness:

```powershell
.\scripts\verify.ps1
```

This runs formatting, linting, strict type checking, automated tests, mutation validation, the
frozen deterministic benchmark, and submitted-trajectory verification. The frozen benchmark scores
belong to the deterministic legacy workflows; they are not model-agent accuracy claims.

## 9. Public deployment

The repository includes a Docker image and Render Blueprint for a constrained synthetic-data demo.
The public service disables browser approval and accepts only bundled cases. Rotate any credential
that has appeared in chat or logs, then configure `QUBRID_API_KEY` as a Render secret. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the deployment and security controls.

## 10. Troubleshooting

### `QUBRID_API_KEY` is unset

Set it in the same terminal that starts FormulaWitness. Environment variables set in another shell
are not inherited.

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
FormulaWitness intentionally rejects risky workbook features instead of executing or stripping them
silently.

## 11. Scope and limitations

FormulaWitness is an assurance prototype for policy-governed operational formulas, not a general
Excel calculation engine. It supports a documented formula subset and depends on human judgment for
ambiguous policy. One successful demo does not establish production accuracy. Production use needs
repeated blind evaluation on representative workbooks, authenticated reviewer identity, durable
artifact storage, a shared job queue, monitoring, retention controls, and an approved provider data
processing agreement.
