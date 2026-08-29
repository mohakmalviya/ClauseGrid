# Model providers

FormulaWitness requires an explicit model ID and keeps every credential in the server process.
Provider selection changes only the model transport; the manager, independent falsifier, typed tools,
budgets, evidence checks, traces, and human approval boundary remain the same.

| `--provider` | Default endpoint | Default credential variable | Transport |
|---|---|---|---|
| `openai` | `https://api.openai.com/v1` | `OPENAI_API_KEY` | OpenAI-compatible chat completions |
| `anthropic` or `claude` | `https://api.anthropic.com` | `ANTHROPIC_API_KEY` | Native Anthropic Messages API |
| `deepseek` | `https://api.deepseek.com` | `DEEPSEEK_API_KEY` | OpenAI-compatible chat completions |
| `nvidia-nim` | `https://integrate.api.nvidia.com/v1` | `NVIDIA_NIM_API_KEY` | OpenAI-compatible chat completions |
| `openai-compatible` | required `--base-url` | required `--api-key-env` | Custom OpenAI-compatible endpoint |
| `commandcode-go` | `https://api.commandcode.ai` | `COMMAND_CODE_API_KEY` | Temporary native-pool/MiMo test adapter |

Claude is Anthropic's model family, so `claude` is an alias for `anthropic`, not a second API-key
system. FormulaWitness uses the native Messages API rather than Anthropic's OpenAI SDK compatibility
layer. The native adapter translates system messages, tool schemas, assistant tool calls, and tool
results, then normalizes response IDs, tool calls, usage, and stop reasons back into the common
runtime contract. Provider reasoning blocks are not retained.

Model IDs are intentionally not hard-coded because providers add, rename, and retire models. Supply
an exact model ID available to the selected account:

```powershell
$env:OPENAI_API_KEY = '<credential>'
formulawitness agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider openai --model '<openai-model-id>' --allow-external-processing

$env:ANTHROPIC_API_KEY = '<credential>'
formulawitness agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider anthropic --model '<claude-model-id>' --allow-external-processing

$env:DEEPSEEK_API_KEY = '<credential>'
formulawitness agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider deepseek --model '<deepseek-model-id>' --allow-external-processing

$env:NVIDIA_NIM_API_KEY = '<credential>'
formulawitness agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider nvidia-nim --model '<nim-model-id>' --allow-external-processing

$env:LOCAL_GATEWAY_KEY = '<credential-or-local-placeholder>'
formulawitness agent workbooks\mutants\M10_supplier_rebate.xlsx `
  --provider openai-compatible --base-url http://127.0.0.1:9000/v1 `
  --api-key-env LOCAL_GATEWAY_KEY --model '<gateway-model-id>'
```

`--base-url` and `--api-key-env` can override a preset without putting the secret value in command
history. Remote endpoints always require `--allow-external-processing` before the credential is
read. The local browser interface displays provider/model metadata but never accepts or receives a
credential.

## Validation status

The provider-neutral contract and native Anthropic translation are covered by offline unit tests.
NVIDIA NIM and CommandCode/MiMo have authenticated transport evidence. MiMo V2.5 has also completed
one proposal-only M10 manager/falsifier repair with a verified trajectory. That does not certify
every provider/model combination—or MiMo's repeated reliability: each selected model still needs a
compatibility probe and repeated blind end-to-end evaluation because tool-choice behavior, context
limits, rate limits, and model quality differ by provider and model.
