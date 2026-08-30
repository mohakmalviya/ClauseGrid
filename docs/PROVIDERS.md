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
| `openrouter` | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | OpenAI-compatible chat completions |
| `groq` | `https://api.groq.com/openai/v1` | `GROQ_API_KEY` | OpenAI-compatible chat completions |
| `together` | `https://api.together.ai/v1` | `TOGETHER_API_KEY` | OpenAI-compatible chat completions |
| `gemini` | `https://generativelanguage.googleapis.com/v1beta/openai` | `GEMINI_API_KEY` | Gemini OpenAI compatibility layer |
| `mistral` | `https://api.mistral.ai/v1` | `MISTRAL_API_KEY` | OpenAI-compatible chat completions |
| `xai` | `https://api.x.ai/v1` | `XAI_API_KEY` | OpenAI-compatible chat completions |
| `openai-compatible` | required `--base-url` | required `--api-key-env` | Custom OpenAI-compatible endpoint |

Claude is Anthropic's model family, so `claude` is an alias for `anthropic`, not a second API-key
system. ClauseGrid uses the native Messages API rather than Anthropic's OpenAI SDK compatibility
layer. The native adapter translates system messages, tool schemas, assistant tool calls, and tool
results, then normalizes response IDs, tool calls, usage, and stop reasons back into the common
runtime contract. Provider reasoning blocks are not retained.

DeepSeek V4 models default to thinking mode, while their Chat Completions thinking mode rejects the
forced named tool selections used at ClauseGrid's safety boundaries. The `deepseek` preset therefore
uses DeepSeek V4 non-thinking mode, which supports those mandatory calls without requiring hidden
reasoning content to be stored or replayed.

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

$env:OPENROUTER_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider openrouter --model '<provider/model-id>' --allow-external-processing

$env:GEMINI_API_KEY = '<credential>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider gemini --model '<gemini-model-id>' --allow-external-processing

$env:LOCAL_GATEWAY_KEY = '<credential-or-local-placeholder>'
clausegrid agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider openai-compatible --base-url http://127.0.0.1:9000/v1 `
  --api-key-env LOCAL_GATEWAY_KEY --model '<gateway-model-id>'
```

`--base-url` and `--api-key-env` can override a preset without putting the secret value in command
history. Remote endpoints always require `--allow-external-processing` before the credential is
read. The local browser interface displays provider/model metadata but never accepts or receives a
credential.

For Render and other hosts, `CLAUSEGRID_API_KEY` is a provider-neutral secret slot. Set
`CLAUSEGRID_PROVIDER` and `CLAUSEGRID_MODEL`, then place that selected provider's key value in
`CLAUSEGRID_API_KEY`. For a custom gateway also set `CLAUSEGRID_PROVIDER=openai-compatible` and
`CLAUSEGRID_BASE_URL`. The key value is never copied into process arguments or returned to the UI.

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

Provider support establishes transport compatibility, not model fitness. Every selected model must
honor mandatory tool calls and survive the blind end-to-end evaluation before it is described as
qualified. ClauseGrid fails closed when a nominally compatible endpoint returns prose, malformed
tool JSON, undeclared tools, empty completions, or repeated provider errors.
