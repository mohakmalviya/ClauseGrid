# Agent engineering playbook

This document is the durable design standard for ClauseGrid. It records the conclusions of a
primary-source review of agent architectures, orchestration, tools, safety, state, and evaluation.
It replaces any earlier assumption that naming deterministic stages as agents is enough.

## 1. Non-negotiable definition

A workflow follows a path selected in application code. An agent lets a model direct how it pursues
a goal. The minimum credible runtime loop is:

```text
goal + current state
        |
        v
model selects the next action and tool arguments
        |
        v
environment returns an observation
        |
        v
model updates its hypothesis or plan
        |
        +----> repeat, finish, abstain, or ask a human
```

The following properties are required:

1. The agent receives an outcome to achieve, not a predetermined next stage.
2. A model materially selects tools, arguments, branches, retries, and stopping behavior.
3. Tools interact with an external environment and return observations.
4. Observations can change the next action, hypothesis, or plan.
5. Working state preserves evidence, attempts, open questions, and budgets.
6. Success, abstention, human escalation, turn, time, and cost limits are explicit.
7. The trajectory records model decisions, tool calls, observations, revisions, and approvals.

Long-term semantic memory and multiple agents are optional. One genuine tool-using agent is better
than several fixed stages with agent names.

## 2. What does not establish agenticity

None of the following is sufficient:

- one model call;
- a fixed prompt chain;
- hard-coded Python tool routing;
- deterministic stages named `rule-agent`, `repair-agent`, or similar;
- a framework such as LangGraph, an Agents SDK, AutoGen, CrewAI, or ADK;
- a templated event log presented as an agent trajectory;
- precomputed tests, exact cell maps, gold formulas, or repair lookup tables;
- explanations generated after deterministic code has already selected the answer.

A strong falsification test is: if the model can be replaced by a stub without materially changing
task success, the model is not controlling the workflow.

## 3. Correct ClauseGrid architecture

ClauseGrid should be a hybrid system. A deterministic, checkpointed graph owns safety and
irreversible actions. Model-controlled loops own uncertain reasoning.

```text
INGEST + SAFETY GATE
        |
        v
AUDIT MANAGER <-----------------------------------------------+
        |                                                     |
        +--> policy interpreter                               |
        +--> workbook investigator                            |
        +--> sandbox experiment tools                         |
        +--> patch synthesizer                                |
        +--> independent falsifier -- counterexample/feedback-+
        |
        +--> HUMAN ADJUDICATION when meaning or risk is unresolved
        |
        v
APPROVAL -> APPLY TO COPY -> DETERMINISTIC POST-VALIDATION -> REPORT
```

The manager-as-tools pattern is the default: one audit manager retains responsibility for the run
and invokes bounded specialists. A handoff is appropriate only when another specialist must directly
own the user interaction, such as a policy-ambiguity discussion with a reviewer.

### Audit manager

- Owns the goal, typed run state, budgets, and final recommendation.
- Chooses which specialist or deterministic tool to call next.
- Decides whether evidence is sufficient, a hypothesis should be revised, a different candidate
  should be tried, or a human must decide.
- Cannot publish or overwrite a workbook.

### Policy interpreter

- Retrieves relevant passages dynamically from an unseen policy.
- Produces typed rules with exact citations, interpretations, confidence, and ambiguity flags.
- Does not receive predefined rule text or gold semantics.
- Cannot access workbook-write tools.

### Workbook investigator

- Discovers sheets, regions, inputs, outputs, formulas, and dependency paths.
- Chooses inspections and sandbox experiments based on current hypotheses.
- Does not receive `INPUT_CELL_MAP`, defect locations, or mutation descriptions.

### Patch synthesizer

- Proposes structured candidate edits with rationales and evidence identifiers.
- Never sees gold formulas or sealed evaluation cases.
- Cannot apply a patch; it can only stage a proposal.

### Independent falsifier

- Sees the policy evidence, observed workbook behavior, and staged candidate.
- Generates boundary, precedence, exception, interaction, and regression tests intended to break it.
- Returns counterexamples and actionable feedback rather than merely agreeing.
- Must be evaluated against an advanced-system ablation without this role.

### Deterministic services

Parsing, formula execution, dependency extraction, copy-on-write patching, hashing, diffing,
invariant checks, artifact generation, and sealed scoring remain ordinary deterministic code. They
are tools and safety controls, not agents.

## 4. Tool contracts

Every tool requires:

- a narrow purpose and unambiguous name;
- a strict Pydantic or JSON input and output schema;
- a stable, actionable error envelope;
- least privilege and explicit side-effect classification;
- timeout, retry, and result-size limits;
- a `run_id` or artifact identifier instead of arbitrary filesystem paths;
- trace capture for arguments, results, latency, errors, and artifact hashes.

Read and write capabilities must be separated. A staged patch should be typed data such as:

```json
{
  "workbook_hash": "...",
  "edits": [
    {
      "sheet": "Settlement",
      "cell": "P6",
      "old_formula_hash": "...",
      "new_formula": "=...",
      "rationale": "...",
      "evidence_ids": ["rule-7", "case-12"]
    }
  ],
  "expected_invariants": ["unrelated outputs unchanged"]
}
```

Only a guarded deterministic tool may apply that proposal to a copy. Publishing requires an
approval token bound to the source hash, evidence, exact patch, reviewer, and output hash.

## 5. State and memory

Authoritative run state is typed and checkpointed after each node. It includes:

- source and policy hashes;
- discovered workbook schema;
- cited rule interpretations and ambiguity flags;
- hypotheses and confidence;
- evidence and counterexample identifiers;
- attempted tool calls and patches;
- observed results and falsifier feedback;
- turn, token, tool, time, and cost budgets;
- reviewer decisions and final artifact hashes.

Conversation history is not the evidence database. Long-term semantic memory is unnecessary for the
hackathon and creates leakage risk. It must never contain prior benchmark answers, gold formulas, or
sealed cases.

## 6. Guardrails and human control

Deterministic controls must enforce:

- copy-on-write operation; never modify the submitted original;
- no macro, VBA, external-link, embedded-object, shell, or network execution;
- allowed artifact, sheet, cell, formula-AST, and mutation scopes;
- maximum turns, tool calls, retries, tokens, time, and cost;
- schema validation around every model output and tool call;
- post-patch workbook integrity, recalculation, unrelated-cell, and clean-case checks;
- rollback or idempotent resume after failure.

The run must pause for human review before the only user-visible write. It must also escalate when
policy meaning conflicts, agents disagree, evidence is weak, retry limits are reached, or a broad or
high-impact range would change. An agent that guesses in these situations is defective, not
autonomous.

## 7. Tracing

Store complete, reviewable traces for every run:

- model and prompt/version identifiers;
- structured model outputs and concise decision summaries;
- tool names, arguments, results, and errors;
- state transitions, retries, and stopping decisions;
- specialist calls or handoffs;
- guardrail and approval events;
- input, evidence, patch, and output hashes;
- tokens, latency, and cost.

Do not claim or store hidden chain-of-thought. Store decisions, evidence references, and observable
actions. A fixed list of expected stages is not a substitute for a raw model/tool/observation trace.

## 8. Evaluation standard

### Compared systems

1. Deterministic ClauseGrid remains a non-agent baseline.
2. A fair single-agent baseline gets the same model and read-only/sandbox tools, but one candidate
   and one validation pass with no specialist delegation or adversarial retry.
3. The advanced system uses the manager, specialists, falsifier loop, and human approval.
4. Required ablations remove the falsifier and compare one agent with multiple agents under the same
   budget.

### Blind task design

Each task provides a previously unseen policy and workbook with an unknown layout. The set must
include clean files, single and multiple defects, and ambiguous or insufficient policies. Expected
formulas, seeded locations, hidden cases, and scoring code remain outside the agent-visible tree.

Use three splits:

- development tasks visible during engineering;
- held-out in-domain tasks using new templates and defects;
- held-out out-of-domain tasks using structurally different industries such as insurance claims,
  sales commissions, and freight surcharges.

Freeze code, prompts, schemas, and model configuration before exposing held-out tasks. Run every
trial in a fresh environment without shared cache, prior artifacts, Git history, or evaluator access.

### Primary outcome

A task succeeds only if all conditions hold:

1. the recalculated workbook passes every hidden semantic case;
2. previously correct behavior remains correct;
3. no unauthorized cells or workbook features change;
4. the patch is minimal and the workbook remains usable;
5. genuinely ambiguous or risky tasks produce correct abstention and human escalation.

The primary metric is blind end-to-end semantic repair success rate. Final environment state is the
authority, not the agent's claim that it succeeded.

### Secondary measures

- clean preservation and false-repair rate;
- localization precision and recall;
- citation and interpretation accuracy reviewed by a domain expert;
- correct and unnecessary escalation rates;
- hidden counterexamples passed and repair-overfit rate;
- changed cells and formula edit distance;
- valid, relevant, redundant, and recovered tool calls;
- tokens, cost, latency, turns, and human-review time;
- prompt-injection and safety-policy violation rates.

For stochastic model runs, pin a model snapshot and run at least five independent trials per sealed
task. Report pass@1 and pass^5, distributions, and confidence intervals. Preserve failures as well as
successes. Temperature zero must not be described as deterministic.

### Adversarial cases

Include prompt injection in cells, comments, and policy appendices; renamed or reordered sheets;
decoy ranges; shifted rows; locale, currency, and unit changes; formula precedence and rounding
faults; no-defect files; independent simultaneous defects; conflicting policy language; tool errors;
locked or corrupted files; and candidate patches that fix one output while damaging another.

## 9. Observable proof for judges

The demo must show a sealed workbook whose layout and defect are unknown to the runtime. The trace
should visibly demonstrate:

1. dynamic tool selection;
2. schema discovery without a supplied cell map;
3. a falsifiable hypothesis;
4. a failed or incomplete first hypothesis;
5. a counterexample from the falsifier;
6. a revised investigation or patch;
7. human escalation for a genuinely ambiguous decision;
8. a minimal approved patch passing independent hidden checks.

Different inputs should produce meaningfully different valid trajectories. If every task follows the
same tool sequence, the system still looks scripted.

## 10. Historical audit and implementation status

The pre-rebuild runtime was a deterministic workflow, not a genuine model-directed agent system:

- `advanced.py` fixes the stage order in Python;
- `policy.py` contains the expected `RULE_SPECS`, cell targets, clarifiers, and formula compiler;
- `public_benchmark.py` provides predetermined visible cases;
- the repair loop substitutes formulas already compiled from embedded domain knowledge;
- trajectory events describe fixed stages rather than raw model decisions and tool observations.

The existing strengths remain valuable: copy-on-write safety, formula sandbox, citations, hashing,
approval binding, sealed evaluator, mutation suite, and reproducible artifacts. These components
should become the deterministic tool and evaluation layer for the real agent rather than being
discarded or relabelled.

The current `agent` runtime now satisfies the mechanical definition: a configured model selects
input-dependent tools and arguments, observes results/errors, invokes a fresh-context falsifier,
can revise candidates, and selects finish/abstain/human actions. Raw model/tool/observation events,
budgets, and approval separation are implemented. The `agent-baseline` command provides the fair
one-candidate/no-falsifier comparison. This permits a genuine runtime-agent claim, but not a winning
or performance claim: blind repeated evaluation on unseen workbook-policy pairs remains required.

## Primary sources

- [OpenAI: agent definitions](https://developers.openai.com/api/docs/guides/agents/define-agents)
- [OpenAI: orchestration and handoffs](https://developers.openai.com/api/docs/guides/agents/orchestration)
- [OpenAI: guardrails and human review](https://developers.openai.com/api/docs/guides/agents/guardrails-approvals)
- [OpenAI: evaluating agent workflows](https://developers.openai.com/api/docs/guides/agent-evals)
- [Anthropic: Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic: Trustworthy agents in practice](https://www.anthropic.com/research/trustworthy-agents)
- [Anthropic: Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [LangGraph: workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents)
- [Google ADK: workflows](https://adk.dev/workflows/)
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
- [AgentBench: Evaluating LLMs as Agents](https://arxiv.org/abs/2308.03688)
- [tau-bench: A Benchmark for Tool-Agent-User Interaction](https://arxiv.org/abs/2406.12045)
- [AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses](https://arxiv.org/abs/2406.13352)
