# Repeated blind model-agent evaluation

`agent-eval` compares the single-agent baseline with the manager/falsifier
pipeline using the same provider, model object, and normalized aggregate limits.
It is a paid live-model benchmark; unit tests use injected fakes and do not call a
provider.

## Default experiment

The default is five trials for each mode on `M10`, `H01`, and `C03`:

- `M10`: narrow waiver-scope defect;
- `H01`: interacting multi-formula defect;
- `C03`: clean waiver control.

That is `3 cases × 5 trials × 2 modes = 30` model-agent runs. The controller
rejects fewer than five trials. Select a different unique public case set with
`--cases`, but retain at least five trials for a repeated comparison.

```powershell
$env:NVIDIA_NIM_API_KEY = "<secret>"
formulawitness agent-eval `
  --provider nvidia-nim `
  --model "<provider-model-id>" `
  --allow-external-processing `
  --cases M10 H01 C03 `
  --trials 5 `
  --artifacts artifacts/agent-evaluation `
  --output evals/agent-results.json
```

For the CommandCode transport, set `COMMAND_CODE_API_KEY`, select
`--provider commandcode-go`, and pass the exact model ID supported by that
account. Credential values are read only from the named server-side environment
variable; they are never CLI values or result fields.
Non-loopback endpoints require `--allow-external-processing`; this gate runs before
the credential environment variable is read. Loopback development endpoints may
omit the flag.

## Blindness and approval boundary

Each trial gets a fresh opaque run ID and a fresh directory containing only
`workbook.xlsx` and `policy.pdf`. The agent call does not receive the benchmark
case ID, defect family, maximum patch count, reference workbook, gold formula,
held-out cases, or sealed oracle.

The controller enforces this order:

1. Run one proposal-only agent configuration.
2. Hash the immutable `proposal.json` evidence pack.
3. Only for a `REPAIR` decision, apply that exact hash through the existing
   approval boundary using the evaluation-controller identity.
4. Only after the agent has stopped, lazily import and invoke the sealed semantic
   oracle on the resulting candidate. `NO_CHANGE`, `ABSTAIN`, and `REJECT`
   decisions are scored without approval and without creating a repaired file.

Evaluation-controller approval is for benchmark execution only. It is not a
substitute for a human deployment approval.

## Recorded evidence

Every run records success, semantic correctness, minimality, clean preservation,
abstention, proposal and end-to-end latency, input/output/total tokens, model and
tool calls, workbook executions, retries, and cost when the provider reports it.
Raw budget snapshots and normalized limits are retained.

Method and per-case aggregates include success counts/rates and Wilson 95%
intervals. The reported improvement includes a percentage-point difference and a
conservative interval derived from the two Wilson intervals. Cost aggregates
include reporting coverage so an absent provider cost is not silently treated as
zero.

The complete JSON document is flushed to a sibling temporary file and atomically
replaced at `--output`; interrupted experiments cannot leave a partial result
masquerading as a completed benchmark.

No live results are checked into the repository by this implementation. Run the
command only after confirming provider quota and expected cost.
