# FormulaWitness project specification

## Objective

Build a complete, reproducible, hackathon-ready agentic system that reads a written enterprise supplier-rebate and SLA policy plus an operational `.xlsx` workbook, constructs policy-derived counterexamples, executes an isolated copy, identifies semantic policy violations, localizes responsible formulas, proposes minimal repairs for human approval, and independently verifies the repaired workbook.

## User and bottleneck

The primary user is a finance or operations reviewer responsible for a supplier settlement workbook. Existing structural audits can find broken references or inconsistent formulas, but a syntactically valid formula can still violate a written threshold, precedence, cap, rounding, date, lookup, or proration rule while returning plausible numbers.

## Scope

- One flagship supplier-rebate and SLA-settlement policy and workbook.
- Ordinary `.xlsx` files only.
- A documented subset of formulas supported by the sandboxed evaluator.
- No VBA, macros, Power Query, external link refreshes, embedded code, or production data.
- The original workbook is immutable; repairs are written to a copy after human approval.
- Public or synthetic data only.

## Required workflow

1. Extract source-cited, typed policy rules and preserve ambiguity.
2. Inspect workbook inputs, outputs, formulas, and dependencies.
3. Generate discriminating boundary and counterfactual cases.
4. Execute cases in an isolated workbook copy.
5. Compare results with an independent hidden oracle.
6. Localize faults using dependency and passing/failing evidence.
7. Propose the smallest formula repair.
8. Require explicit human approval before writing the repaired artifact.
9. Replay held-out cases and clean regressions.
10. Produce the repaired workbook and a complete evidence pack.

## Frozen evaluation contract

- Twelve independently seeded defective workbook variants.
- At least three clean controls.
- Coverage of threshold boundaries, precedence/exceptions, cap/rounding order, effective dates/proration, lookup behavior, and one difficult multi-rule interaction.
- The scoring oracle and held-out cases are inaccessible to both compared agents.
- Baseline and advanced solutions receive the same input bundle, tools, cases, model configuration, and comparable execution/token budgets.

### Primary metric

End-to-End Semantic Repair Rate: a case succeeds only if the defect is detected, the repaired copy passes every hidden policy case and clean regression, and no unrelated formula is modified.

## Baseline

A direct repair agent receives the workbook, policy, allowed tools, public cases, shared deterministic policy model, and a single instruction to audit and minimally repair the workbook. It receives no structured extraction, counterexample, localization, or verifier loop beyond the common tool boundary.

## Advanced solution

FormulaWitness adds source-linked rule representation, ambiguity states, counterexample-guided experimentation, dependency/spectrum localization, constrained patching, human approval, and independent replay.

## Required deliverables

- Realistic policy PDF and clean reference workbook.
- Twelve defective variants and three clean controls.
- Hidden deterministic oracle.
- Baseline and advanced commands and results.
- Usable interface.
- Repaired workbook with a `Counterexamples` sheet.
- `rules.yaml`, formula diff, evidence graph, evaluation report, and JSONL trajectories.
- One-command setup/demo/evaluation paths.
- README, architecture, reproduction guide, dependency/runtime/cost notes.
- Improvement changelog including one removed experiment.
- Main failure mode, limitations, formula boundary, and five-minute demo script.

## Completion gates

- Clean-environment setup succeeds.
- Formatting, linting, typing, unit, integration, security, and end-to-end checks pass.
- Evaluation cases are frozen before optimization and show no leakage.
- Baseline and advanced runs are repeated when model nondeterminism applies.
- Advanced improves the primary metric by at least 20 percentage points without increasing false repairs.
- Every result claim links to submitted evidence.
- Final artifacts and interface are manually verified.
