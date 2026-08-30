# Model selection evidence

ClauseGrid does not assume that one provider model is universally best. The CLI requires an
explicit `--model`, and model candidates are evaluated on the same end-to-end audit before they are
recommended. A successful forced tool call is only a compatibility gate; it is not evidence that the
model can complete a policy-grounded repair.

Provider selection is independent of model selection. The runtime supports Qubrid, OpenAI, native
Anthropic/Claude, DeepSeek, NVIDIA NIM, OpenCode Zen, and custom OpenAI-compatible endpoints. See
[model providers](PROVIDERS.md). No untested provider/model pair inherits the status of a validated
pair.

## Current task-specific checkpoint

These runs used the same M10 workbook, controlled policy, manager prompt, fresh-context falsifier,
tools, and resource limits. NVIDIA NIM did not report monetary cost.

| Model | Full-pipeline result | Evidence from trajectory | Status |
|---|---|---|---|
| `openai/gpt-oss-120b` | `REPAIR`, proposal only | Found the P6 waiver-scope defect, proposed the minimal formula change, and completed the falsifier loop in 121.3 s | Validated reference |
| `deepseek-v4-flash` through DeepSeek | `REPAIR`, proposal only | Found the P6 waiver-scope defect, proposed the correct minimal P6 formula, and received a fresh-context falsifier `SURVIVED` verdict across three candidate-focused experiments in 78.2 s | Validated M10 smoke; repeat blind trials still required |
| `deepseek-ai/DeepSeek-V3.2` through Qubrid | `ABSTAIN` in two full M10 runs | Passed named and required tool probes. The first run ended on one stale undeclared tool call; after bounded protocol recovery was added, the second recognized the P6 waiver-scope defect but repeatedly targeted nonexistent cells, exhausted 30 manager turns, and never staged a candidate. | Fast and transport-compatible; not task-qualified |
| `openai/gpt-oss-120b` through Qubrid | Tool gate failed | Six live request variants returned reasoning that a function should be called but an empty `tool_calls` array; the alternate Qubrid endpoint returned unstable prose/JSON content rather than a standard tool call. | Qubrid route eliminated despite the same model succeeding through NVIDIA NIM |
| `openai/gpt-oss-20b` | `NO_CHANGE` | Used 26 manager turns and 10 experiments but accepted the defective waiver semantics | Eliminated for correctness |
| `moonshotai/kimi-k3` | `ABSTAIN` | Identified the exact P6 defect, then exhausted retries on HTTP 429 before proposing or falsifying a repair | Promising, endpoint-unreliable |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | `ABSTAIN` | After controller hardening, the latest completed run registered policy citations and two experiments, then returned plain text through all bounded retries while a tool call was mandatory (19 manager turns, 752.1 s). An earlier diagnostic staged the correct P6 hypothesis but crossed the former 15-minute wall guard before falsification. | Transport-compatible; still unreliable for this task |
| `zai-org/GLM-4.7-Flash` through Qubrid | `ABSTAIN` in two full M10 runs | Named and required tool probes passed, but the first run looped on rejected no-op candidates and ended on HTTP 429 after 1,009.3 s. After candidate-loop recovery, the second run executed eight experiments, failed to test waiver scope with graded expectations, proposed no-op/broad candidates, and exhausted 30 manager turns after 1,342.9 s. No candidate reached the falsifier. | Transport-compatible and currently free; eliminated for M10 task accuracy and latency |
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

At this checkpoint, GPT-OSS 120B through NVIDIA NIM has completed the M10 demonstration. The same
model ID did not pass mandatory tool calling through Qubrid, demonstrating that provider serving
behavior is part of model qualification. A single successful run does
not establish a production winner. A final recommendation requires repeated runs on the frozen,
blind mutant suite. The public Blueprint currently uses Qubrid DeepSeek V3.2 as an integration
default, but that deployment choice is not a claim that it outperformed the validated GPT-OSS smoke.
Until repeated blind evidence exists, the model remains an explicit runtime choice.

## DeepSeek V4 official API validation (2026-08-30)

The authenticated DeepSeek catalog exposed `deepseek-v4-flash`, `deepseek-v4-pro`, and
`deepseek-v4-flash-vision-exp`. V4 thinking mode is enabled by default and rejects the named
`tool_choice` required by ClauseGrid's terminal safety actions. Following DeepSeek's documented
thinking-mode switch, the provider preset now sends `thinking.type=disabled` for V4 models. A live
forced named-tool request then returned the exact requested function and arguments.

The blind M10 run through the official DeepSeek endpoint completed in 78.2 seconds using 40 model
calls, 32 tool calls, and ten workbook executions. It proposed only `RebateCalc!P6`, removed the
incorrect waiver short-circuit, and independently exercised waiver-plus-SLA-failure,
waiver-without-SLA-failure, and unwaived-critical branches. All observations matched the policy,
the falsifier returned `SURVIVED` with no counterexamples, the trajectory's 140-event hash chain
verified, and no workbook was written without human approval. This is one successful M10 smoke,
not evidence of reliability across the frozen mutant suite.

## Qubrid GPT-OSS and DeepSeek compatibility

The authenticated Qubrid catalog listed `openai/gpt-oss-120b`, but its live OpenAI-compatible route
did not emit tool calls for forced named, required, automatic, or reasoning-parameter variants. Each
response stopped after hidden-provider reasoning indicated that the function should be called. The
runtime correctly rejected those empty calls rather than interpreting reasoning text as an action.

`deepseek-ai/DeepSeek-V3.2` passed both a forced named-tool probe and ClauseGrid's two-tool
mandatory-choice probe on the first attempt. Its catalog profile uses temperature 1.0 and top-p 0.95.
The first M10 attempt exposed stale tool reuse after controller action narrowing, which led to a new
provider-neutral bounded repair: the client restates the currently declared tools and retries once,
then still fails closed if drift continues. The repaired M10 run made 31 model calls in 170.5 seconds
with one protocol retry. It identified the correct waiver-scope defect in P6, but repeatedly invented
invalid experiment coordinates and reached the manager limit without a candidate or falsifier run.
This is useful integration evidence, not a production-quality result.

## Qubrid GLM-4.7-Flash compatibility

The authenticated Qubrid `/v1/models` endpoint listed `zai-org/GLM-4.7-Flash`. A forced named-tool
probe returned the correct arguments after 106.9 seconds on a cold request. A two-tool
`tool_choice="required"` probe selected the correct tool on its first attempt after 24.0 seconds.
These establish API and structured-tool compatibility only.

Two complete M10 attempts failed the semantic task. The first produced one experiment, repeatedly
submitted a no-op edit, consumed all eight retry credits, and ended safely on an upstream 429. The
second exercised the new rejected-candidate recovery, but its successful experiments contained no
expected outcomes and missed the waiver-plus-independent-violation cross-product required by the
policy. ClauseGrid rejected both candidate submissions and every unsupported no-change action,
then safely abstained at the manager-turn boundary. A focused prompt containing only the relevant
policy, field meanings, and current formula also produced an incorrect repair. The evidence therefore
does not support using this model as a judged or production default merely because its token price is
zero.

## Qubrid zero-price model retest (2026-08-30)

The authenticated Qubrid catalog reported exactly three models with both input and output pricing
set to zero. Each model received the same forced named-tool probe and the same blind M10
manager/falsifier audit. A probe pass was treated only as an admission gate, not as task success.

| Model | Forced-tool gate | Blind M10 result | Operational conclusion |
|---|---|---|---|
| `zai-org/GLM-4.7-Flash` | Passed in 4.8 s | Safely abstained after 73.0 s; 13 model calls and seven tool calls, then repeated upstream HTTP 429 responses before any experiment or candidate | Free endpoint is overloaded and did not complete the investigation |
| `zai-org/GLM-4.5-Flash` | Passed in 59.4 s | Safely abstained after 690.7 s; 18 model calls, 15 tool calls, and four experiments, then malformed tool JSON; no candidate or falsifier run | Too slow and structurally unreliable for the public demo |
| `zai-org/GLM-4.6V-Flash` | First probe returned HTTP 429; retry passed in 4.0 s | Safely abstained after 254.8 s; 22 model calls, 12 tool calls, one experiment, and all eight retry credits consumed by HTTP 429 responses; no candidate | Tool-compatible when available, but endpoint reliability and task focus are insufficient |

None reached candidate staging or independent falsification, so zero token price does not make any
of them a valid ClauseGrid default. The public deployment remains unchanged pending a free model
that completes the end-to-end contract.

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
