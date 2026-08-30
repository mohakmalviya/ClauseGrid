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

ClauseGrid supports OpenCode Zen through `--provider opencode` and its OpenAI-compatible chat
endpoint. The credential is read only from `OPENCODE_API_KEY`; model IDs remain explicit and are not
silently selected from the changing free catalog. Compatibility probes send only synthetic prompts.
An end-to-end result is disclosed only after a full manager/falsifier run completes and its trajectory
verifies.

The audit manager chooses tools and stopping actions. The advanced command can invoke a separate
fresh-context falsifier. Workbook execution stays in a no-network subprocess that receives no API
credential. No model can approve or apply a patch.

## Trajectories

Schema-v3 `trajectory.jsonl` stores observable model responses, normalized tool calls, arguments,
tool observations/errors, actor transitions, usage, latency, retries, model id, prompt version, and
the hash chain. It does not request or store hidden chain-of-thought. Credential-like fields and
bearer values are redacted.

The older committed `trajectories/*.jsonl` files belong to the legacy deterministic workflow and
must not be presented as model-agent traces. The representative current model-agent evidence is
`artifacts/submission/agent-m10/trajectory.jsonl`. It is a verified schema-v3 trace containing both
the audit-manager and fresh-context falsifier roles. A new run writes its trajectory under the
selected artifact root.
