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
$env:QUBRID_API_KEY = '<credential>'
.\.venv\Scripts\python.exe -m formulawitness agent `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --policy policies\supplier_rebate_sla_policy.pdf `
  --provider qubrid `
  --model 'deepseek-ai/DeepSeek-V4-Flash' `
  --allow-external-processing `
  --artifacts artifacts\runs
```

The command stops at a proposal. It does not write a repaired workbook. Inspect `proposal.json`,
`formula-diff.json`, `agent-state.json`, `report.json`, and `trajectory.jsonl`.

The public provider catalog and model behavior can change, so a new live run is not expected to
reproduce the exact same wording, latency, or proposal. The submitted representative run is fixed
evidence and can be verified without an API key:

```powershell
.\.venv\Scripts\clausegrid.exe verify-trajectory `
  artifacts\submission\agent-m10\trajectory.jsonl
```

Expected: run ID `agent-08005c743165-58615c78`, 132 events, and final hash
`f93bfcfdb7a3d89a85c6356bcf9fe2ce04f12d1121f5aca4a188b35175a00c6b`.

To evaluate a currently available OpenCode Zen free model:

```powershell
$env:OPENCODE_API_KEY = '<credential>'
.\.venv\Scripts\python.exe -m formulawitness agent `
  workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider opencode `
  --model big-pickle `
  --allow-external-processing `
  --artifacts artifacts\opencode-runs
```

Query `https://opencode.ai/zen/v1/models` immediately before the run because free-model availability
changes. This path uses ClauseGrid's manager, falsifier, tools, budgets, and trace; it does not
launch an external coding harness or grant it workspace access.

Qubrid, OpenAI, native Anthropic/Claude, DeepSeek, NVIDIA NIM, OpenCode Zen, and a custom OpenAI-compatible
gateway use the same agent commands. See [model providers](PROVIDERS.md) for exact credential
variables, compatibility limits, and examples.

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
