# Model selection evidence

FormulaWitness does not assume that one provider model is universally best. The CLI requires an
explicit `--model`, and model candidates are evaluated on the same end-to-end audit before they are
recommended. A successful forced tool call is only a compatibility gate; it is not evidence that the
model can complete a policy-grounded repair.

Provider selection is independent of model selection. The runtime supports OpenAI, native
Anthropic/Claude, DeepSeek, NVIDIA NIM, OpenCode Zen, and custom OpenAI-compatible endpoints. See
[model providers](PROVIDERS.md). No untested provider/model pair inherits the status of a validated
pair.

## Current task-specific checkpoint

These runs used the same M10 workbook, controlled policy, manager prompt, fresh-context falsifier,
tools, and resource limits. NVIDIA NIM did not report monetary cost.

| Model | Full-pipeline result | Evidence from trajectory | Status |
|---|---|---|---|
| `openai/gpt-oss-120b` | `REPAIR`, proposal only | Found the P6 waiver-scope defect, proposed the minimal formula change, and completed the falsifier loop in 121.3 s | Validated reference |
| `openai/gpt-oss-20b` | `NO_CHANGE` | Used 26 manager turns and 10 experiments but accepted the defective waiver semantics | Eliminated for correctness |
| `moonshotai/kimi-k3` | `ABSTAIN` | Identified the exact P6 defect, then exhausted retries on HTTP 429 before proposing or falsifying a repair | Promising, endpoint-unreliable |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | `ABSTAIN` | Requested a human because it claimed it could not read the workbook although workbook tools were available | Eliminated for task/tool judgment |
| `nvidia/nemotron-3-ultra-550b-a55b` | `ABSTAIN` | Repeatedly returned JSON-looking plans as plain content and reached 30 turns with no experiment | Eliminated for tool-protocol reliability |
| `poolside/laguna-xs-2.1` | `ABSTAIN` | Repeated `workbook_manifest` 30 times and performed no experiment | Eliminated for looping |
| `minimaxai/minimax-m3` | `ABSTAIN` | Multiple attempts either looped through verification tools or hit endpoint rate limits before a complete repair | Eliminated for current runtime |
| `deepseek-ai/deepseek-v4-flash-0731` | Incomplete | No first full-pipeline response after four minutes; the run was interrupted | Not operationally validated |

Run IDs and JSONL trajectories are local runtime evidence under ignored `artifacts/` directories;
they are intentionally not committed. The reproducible compatibility probes are
`scripts/probe_nim_models.py` and `scripts/probe_opencode_models.py`.

## Selection rule

Choose lexicographically, not by a blended popularity score:

1. Correct semantic decision and minimal supported patch.
2. Complete manager-to-falsifier handoff without bypassing approval.
3. Reliable structured tool calls and recovery from tool errors.
4. Reproducibility across fresh runs and unseen workbook defects.
5. Latency and reported cost.

At this checkpoint, GPT-OSS 120B has completed the M10 demonstration. A single successful run does
not establish a production winner. A final recommendation requires repeated runs on the frozen,
blind mutant suite. Until then, the model remains an explicit runtime choice.

## OpenCode Zen free-model compatibility

The OpenCode catalog is dynamic. An authenticated forced-tool probe against the live catalog found
the following current results; the excluded model family requested by the project owner was not
tested or integrated.

| Free model | Forced tool result | Full M10 result | Current status |
|---|---|---|---|
| `big-pickle` | Correct `ping` call | HTTP 429 usage limit before investigation | Transport-compatible; not runnable on the test account |
| `hy3-free` | Correct `ping` call | 21 tool calls, then repeated empty completions | Protocol-unstable |
| `ling-3.0-flash-fin-free` | Correct `ping` call | 31 tool calls, then repeated HTTP 503 responses | Endpoint-unstable |
| `nemotron-3.5-lightning-free` | Correct `ping` call | 32 tool calls, then an incorrect claim that discovery tools were unavailable | Eliminated for task/tool judgment |
| `deepseek-v4-flash-free` | HTTP 400 | Not run | Unavailable for this contract |
| `nemotron-3-ultra-free` | Intermittently accepted the forced call | Repeated empty choice lists before investigation | Protocol-unstable |
| `laguna-s-2.1-free` | Intermittent HTTP 503 / successful tool calls | Two runs reached 30+ tool calls; one violated the serial-tool contract and one ended on repeated upstream HTTP 503 responses | Closest current free candidate, but endpoint-unstable |

A forced function call is only a transport gate. None of the tested OpenCode free models completed
candidate staging plus fresh-context falsification on M10, so none is a production recommendation.
The runtime recovered safely from empty completions and ignored serial-tool settings, preserved the
trace, and abstained when bounded retries were exhausted.
