# Model selection evidence

FormulaWitness does not assume that one NVIDIA NIM model is universally best. The CLI requires an
explicit `--model`, and model candidates are evaluated on the same end-to-end audit before they are
recommended. A successful forced tool call is only a compatibility gate; it is not evidence that the
model can complete a policy-grounded repair.

Provider selection is independent of model selection. The runtime supports OpenAI, native
Anthropic/Claude, DeepSeek, NVIDIA NIM, and custom OpenAI-compatible endpoints. See
[model providers](PROVIDERS.md). No untested provider/model pair inherits the status of a validated
pair.

## Current task-specific checkpoint

These runs used the same M10 workbook, controlled policy, manager prompt, fresh-context falsifier,
tools, and resource limits. NVIDIA NIM did not report monetary cost; the CommandCode MiMo run did.

| Model | Full-pipeline result | Evidence from trajectory | Status |
|---|---|---|---|
| `openai/gpt-oss-120b` | `REPAIR`, proposal only | Found the P6 waiver-scope defect, proposed the minimal formula change, and completed the falsifier loop in 121.3 s | Validated reference |
| `xiaomi/mimo-v2.5` | `REPAIR`, proposal only | Found the P6 waiver-scope defect, proposed the same minimal one-cell change, and completed a five-experiment `SURVIVED` falsifier verdict in 266.9 s; provider-reported cost was $0.018584 | Single-run end-to-end validated |
| `openai/gpt-oss-20b` | `NO_CHANGE` | Used 26 manager turns and 10 experiments but accepted the defective waiver semantics | Eliminated for correctness |
| `moonshotai/kimi-k3` | `ABSTAIN` | Identified the exact P6 defect, then exhausted retries on HTTP 429 before proposing or falsifying a repair | Promising, endpoint-unreliable |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | `ABSTAIN` | Requested a human because it claimed it could not read the workbook although workbook tools were available | Eliminated for task/tool judgment |
| `nvidia/nemotron-3-ultra-550b-a55b` | `ABSTAIN` | Repeatedly returned JSON-looking plans as plain content and reached 30 turns with no experiment | Eliminated for tool-protocol reliability |
| `poolside/laguna-xs-2.1` | `ABSTAIN` | Repeated `workbook_manifest` 30 times and performed no experiment | Eliminated for looping |
| `minimaxai/minimax-m3` | `ABSTAIN` | Multiple attempts either looped through verification tools or hit endpoint rate limits before a complete repair | Eliminated for current runtime |
| `deepseek-ai/deepseek-v4-flash-0731` | Incomplete | No first full-pipeline response after four minutes; the run was interrupted | Not operationally validated |

Run IDs and JSONL trajectories are local runtime evidence under ignored `artifacts/` directories;
they are intentionally not committed. The reproducible compatibility probe is
`scripts/probe_nim_models.py`.

## Selection rule

Choose lexicographically, not by a blended popularity score:

1. Correct semantic decision and minimal supported patch.
2. Complete manager-to-falsifier handoff without bypassing approval.
3. Reliable structured tool calls and recovery from tool errors.
4. Reproducibility across fresh runs and unseen workbook defects.
5. Latency and reported cost.

At this checkpoint, GPT-OSS 120B and MiMo V2.5 have each completed the M10 demonstration. Neither
single successful run establishes a production winner. A final recommendation requires repeated
runs on the frozen, blind mutant suite. Until then, the model remains an explicit runtime choice.

## MiMo V2.5 follow-up

MiMo V2.5 is available in the tested CommandCode Go/native pool, not in the NVIDIA NIM model list
returned for the current credential. The dedicated `commandcode-go` transport is retained only to
reproduce that experiment while keeping FormulaWitness orchestration. Authentication, streaming,
tool calls, and usage/cost normalization worked. After adding phase budgets, protocol-preserving
context compaction, a registered-evidence ledger, and bounded repair of missing mandatory tool
calls, run `agent-702385dc5cee-771cae24` completed `REPAIR`. It used 8 manager turns, 14 falsifier
turns, 36 tool calls, and 7 sandbox executions; the falsifier returned `SURVIVED` with five passing
candidate-bound experiments. The 120-event trajectory hash chain verifies. This validates one
end-to-end M10 run, not repeated reliability or production readiness.
