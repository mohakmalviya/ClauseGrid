# Representative model-agent trajectory

This directory contains one successful live M10 investigation from the current model-directed
workflow. It is separate from `artifacts/submission/m10`, which records the older deterministic
repair pipeline.

## What the run demonstrates

- The audit manager discovered workbook and policy structure through tools.
- It registered exact policy citations and ran four source-workbook experiments.
- It isolated the waiver-scope defect in `RebateCalc!P6` and staged one formula edit.
- A fresh-context falsifier ran five candidate-sensitive experiments.
- The candidate survived falsification and finished as a proposal-only `REPAIR`.
- The original workbook hash remained unchanged and no model had an approval or apply tool.

## Recorded result

- Run ID: `agent-08005c743165-58615c78`
- Model ID recorded by the runtime: `moonshotai/Kimi-K2.5`
- Decision: `REPAIR`
- Manager turns: 18
- Falsifier turns: 8
- Model calls: 27
- Tool calls: 33
- Workbook executions: 9
- Elapsed time: 233.718 seconds
- Trajectory events: 132
- Final event hash: `f93bfcfdb7a3d89a85c6356bcf9fe2ce04f12d1121f5aca4a188b35175a00c6b`

The model/provider response did not report a monetary cost, so no cost claim is made.

## Verify the evidence

From an installed ClauseGrid environment:

```powershell
.\.venv\Scripts\clausegrid.exe verify-trajectory `
  artifacts\submission\agent-m10\trajectory.jsonl
```

Expected output:

```json
{
  "run_id": "agent-08005c743165-58615c78",
  "event_count": 132,
  "final_event_hash": "f93bfcfdb7a3d89a85c6356bcf9fe2ce04f12d1121f5aca4a188b35175a00c6b"
}
```

`trajectory.jsonl` contains observable instructions, model responses, normalized tool calls, tool
observations, controller feedback, retries, budgets, and actor transitions. It does not contain an
API key or hidden chain-of-thought.
