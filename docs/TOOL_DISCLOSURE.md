# Tool and agent disclosure

## Build tools

- OpenAI Codex was the required coding agent used to design, implement, test, and document the repository.
- `@oai/artifact-tool` from the Codex bundled runtime authored and re-imported the synthetic `.xlsx` fixtures; it is not a runtime dependency.
- ReportLab generated the synthetic policy PDF; Poppler rendered it for visual QA.
- `pypdf` provides page-addressable policy text extraction.
- Python OOXML, subprocess, hashing, JSON, `Decimal`, and date code implements deterministic workbook services.

Only synthetic data is used. Hidden evaluator cases and reference formulas are not exposed to the
model runtime.

## Runtime model

The `agent` and `agent-baseline` commands use an explicitly configured provider and model. OpenAI,
DeepSeek, NVIDIA NIM, and custom gateways use the normalized OpenAI-compatible transport;
Anthropic/Claude uses the native Messages API. The verified live smoke used NVIDIA NIM at
`https://integrate.api.nvidia.com/v1` with
`openai/gpt-oss-120b`. The credential was loaded from `NVIDIA_NIM_API_KEY` in process environment;
it was not printed, copied into the repository, or written to an artifact. NIM responses reported
token usage but not monetary cost, so cost is disclosed as `Not reported`.

FormulaWitness temporarily supports CommandCode's Go/native-pool stream through `--provider
commandcode-go`, including `xiaomi/mimo-v2.5`, to preserve the MiMo experiment. The adapter only
translates the same bounded FormulaWitness messages and tools to CommandCode's `/alpha/generate`
protocol. It does not invoke CommandCode's filesystem-capable coding harness. The credential is
read only from `COMMAND_CODE_API_KEY`. Authenticated run `agent-702385dc5cee-771cae24` completed a
proposal-only M10 `REPAIR` with a five-experiment `SURVIVED` falsifier verdict. This is one
end-to-end compatibility result, not a repeated benchmark or production certification.

The audit manager chooses tools and stopping actions. The advanced command can invoke a separate
fresh-context falsifier. Workbook execution stays in a no-network subprocess that receives no API
credential. No model can approve or apply a patch.

## Trajectories

Schema-v3 `trajectory.jsonl` stores observable model responses, normalized tool calls, arguments,
tool observations/errors, actor transitions, usage, latency, retries, model id, prompt version, and
the hash chain. It does not request or store hidden chain-of-thought. Credential-like fields and
bearer values are redacted.

The older committed `trajectories/*.jsonl` files belong to the legacy deterministic workflow and
must not be presented as model-agent traces. A fresh model run writes its trajectory under the
selected artifact root.
