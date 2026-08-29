# Reproduction guide

## Setup

From the repository root with Python 3.11 or newer:

```powershell
.\scripts\setup.ps1
```

Equivalent commands:

```text
python -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

## Deterministic regression gate

```powershell
.\scripts\verify.ps1
```

This runs formatting, lint, strict typing, all tests, mutation validation, and the frozen legacy
benchmark. Its 33.3% baseline and 100% advanced result belongs only to the legacy deterministic
workflows.

## Model-directed audit

Set the credential outside the repository. Do not put it in a command argument or committed file.

```powershell
$env:NVIDIA_NIM_API_KEY = '<credential>'
.\.venv\Scripts\python.exe -m formulawitness agent `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --policy policies\supplier_rebate_sla_policy.pdf `
  --provider nvidia-nim `
  --model openai/gpt-oss-120b `
  --allow-external-processing `
  --artifacts artifacts\runs
```

The command stops at a proposal. It does not write a repaired workbook. Inspect `proposal.json`,
`formula-diff.json`, `agent-state.json`, `report.json`, and `trajectory.jsonl`. Verify the hash chain:

To evaluate MiMo V2.5 through an authenticated CommandCode Go/native account:

```powershell
$env:COMMAND_CODE_API_KEY = '<credential>'
.\.venv\Scripts\python.exe -m formulawitness agent `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider commandcode-go `
  --model xiaomi/mimo-v2.5 `
  --allow-external-processing `
  --artifacts artifacts\runs
```

This path uses FormulaWitness's manager, falsifier, tools, budgets, and trace. It does not launch the
CommandCode coding CLI or grant an external coding harness workspace access.

OpenAI, native Anthropic/Claude, DeepSeek, NVIDIA NIM, and a custom OpenAI-compatible gateway use
the same agent commands. See [model providers](PROVIDERS.md) for exact credential variables and
examples. CommandCode/MiMo is a temporary compatibility path, not the default architecture.

```powershell
.\.venv\Scripts\python.exe -m formulawitness verify-trajectory `
  artifacts\runs\RUN_ID\trajectory.jsonl
```

After review, calculate the canonical proposal hash with the same `object_hash` implementation, then
apply that exact proposal:

```powershell
.\.venv\Scripts\python.exe -m formulawitness approve-agent RUN_ID `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --policy policies\supplier_rebate_sla_policy.pdf `
  --artifacts artifacts\runs `
  --proposal-hash REVIEWED_HASH `
  --reviewer reviewer@example.test
```

## Fair single-agent comparison

Use the same endpoint, model, workbook, policy, and limits:

```powershell
.\.venv\Scripts\python.exe -m formulawitness agent-baseline `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider nvidia-nim `
  --model openai/gpt-oss-120b `
  --allow-external-processing
```

This mode permits one candidate and one sandbox candidate validation, with no falsifier or retry to
a second candidate. One run is not a performance result. A scored claim requires a frozen blind task
set and at least five independent trials per task.

## Credential and cost disclosure

The controller needs network access for the configured model endpoint; workbook workers do not.
Every non-loopback endpoint requires the explicit `--allow-external-processing` flag. The CLI rejects
the command before reading its credential environment variable when consent is absent. A loopback
development endpoint may omit the flag. Provider credentials remain server-side and are never sent
in browser request payloads.
Trajectories record model id, token usage, request timing, retries, and stop reason. They do not store
the API key or hidden reasoning. NVIDIA NIM did not report monetary cost in the tested response, so
cost is `Not reported`, not `$0`.
