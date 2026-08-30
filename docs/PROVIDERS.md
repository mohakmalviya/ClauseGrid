# Model providers

ClauseGrid requires an explicit model ID and keeps every credential in the server process.
Provider selection changes only the model transport; the manager, independent falsifier, typed tools,
budgets, evidence checks, traces, and human approval boundary remain the same.

| `--provider` | Default endpoint | Default credential variable | Transport |
|---|---|---|---|
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | OpenAI-compatible chat completions |
| `anthropic` or `claude` | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | Native Anthropic Messages API |
| `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | OpenAI-compatible chat completions |
| `nvidia-nim` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_NIM_API_KEY` | OpenAI-compatible chat completions |
| `opencode` | `https://opencode.ai/zen/v1` | `OPENCODE_API_KEY` | OpenAI-compatible chat completions |
| `qubrid` | `https://platform.qubrid.com/v1` | `QUBRID_API_KEY` | OpenAI-compatible chat completions |
| `openai-compatible` | required `--base-url` | required `--api-key-env` | Custom OpenAI-compatible endpoint |

Claude is Anthropic's model family, so `claude` is an alias for `anthropic`, not a second API-key
system. ClauseGrid uses the native Messages API rather than Anthropic's OpenAI SDK compatibility
layer. The native adapter translates system messages, tool schemas, assistant tool calls, and tool
results, then normalizes response IDs, tool calls, usage, and stop reasons back into the common
runtime contract. Provider reasoning blocks are not retained.

Model IDs are intentionally not hard-coded because providers add, rename, and retire models. Supply
an exact model ID available to the selected account:

```powershell
$env:OPENAI_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider openai --model '<openai-model-id>' --allow-external-processing

$env:ANTHROPIC_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider anthropic --model '<claude-model-id>' --allow-external-processing

$env:DEEPSEEK_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider deepseek --model '<deepseek-model-id>' --allow-external-processing

$env:NVIDIA_NIM_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider nvidia-nim `
  --model 'nvidia/nemotron-3.5-lightning-30b-a3b' `
  --allow-external-processing

$env:OPENCODE_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider opencode --model 'big-pickle' --allow-external-processing

$env:QUBRID_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider qubrid --model 'deepseek-ai/DeepSeek-V3.2' --allow-external-processing

$env:LOCAL_GATEWAY_KEY = '<credential-or-local-placeholder>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider openai-compatible --base-url http://127.0.0.1:9000/v1 `
  --api-key-env LOCAL_GATEWAY_KEY --model '<gateway-model-id>'
```

`--base-url` and `--api-key-env` can override a preset without putting the secret value in command
history. Remote endpoints always require `--allow-external-processing` before the credential is
read. The local browser interface displays provider/model metadata but never accepts or receives a
credential.

## Validation status

The provider-neutral contract and native Anthropic translation are covered by offline unit tests.
Qubrid's authenticated catalog and candidate tool calls are probed against the live endpoint before
a model becomes the default; full-pipeline results are recorded in
[model selection evidence](MODEL_SELECTION.md).
NVIDIA NIM and OpenCode Zen have authenticated transport evidence. The OpenCode free catalog is
dynamic: query `https://opencode.ai/zen/v1/models` rather than hard-coding an assumed list. On the
latest compatibility probe, `big-pickle`, `hy3-free`, `ling-3.0-flash-fin-free`, and
`nemotron-3.5-lightning-free` honored a mandatory function call. Catalog presence alone is not
validation; each model still needs repeated blind end-to-end evaluation because tool behavior,
availability, context limits, and quality differ by model.

The checked-in public-demo profile uses NVIDIA's exact
`nvidia/nemotron-3.5-lightning-30b-a3b` identifier with its published `temperature=1`, `top_p=0.95`,
and thinking-enabled chat template. ClauseGrid bounds the reasoning budget at 2,048 tokens per
turn and serializes provider-returned parallel calls locally because the hosted endpoint has ignored
`parallel_tool_calls=false` in observed runs. See the
[official NVIDIA model page](https://build.nvidia.com/nvidia/nemotron-3.5-lightning-30b-a3b).
This profile is a deployment choice, not proof of repeated blind accuracy.
