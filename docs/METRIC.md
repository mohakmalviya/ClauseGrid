# Evaluation contract

## Primary metric

**End-to-End Semantic Repair Rate (E2E-SRR)** over M01–M12.

A mutant succeeds only when:

1. all 48 sealed vectors match the independent oracle on every intermediate and final output `L6:T6`;
2. workbook safety and integrity checks pass;
3. the original workbook hash is unchanged; and
4. at most one core formula cell changed.

The three-fault H01 workbook permits three changed core cells and is reported separately. Clean controls succeed only with correct sealed semantics and **zero** core formula changes. Clean results are never folded into the primary rate.

## Supporting metrics

- Clean Preservation Rate;
- hard multi-rule repair rate;
- visible counterexample pass rate;
- localization evidence and changed-cell count;
- first sealed failure ID for evaluator debugging after freeze.

## Legacy deterministic fairness

Baseline and advanced systems receive the same policy, workbook, 20 public cases, formula visibility, patch scope, allowed operations, `deterministic-offline-v1` policy model, zero-token model budget, and 160-case execution limit. Neither receives sealed inputs, the independent oracle, mutation descriptions, or pristine formulas. The direct baseline makes one generic policy-derived edit and visible replay; it deliberately has no staged rule IR, ambiguity gate, generated boundary suite, dependency/spectrum localizer, or multi-candidate verifier loop—those are the intervention being measured.

Both systems are deterministic and their first frozen candidate is scored. There is no hidden-result retry.

The results above apply only to the legacy `baseline` and `advanced` commands.

## Model-agent evaluation contract

The fair single-agent baseline and manager/falsifier system receive the same model, workbook, policy,
read/sandbox tools, total budgets, timeouts, and formula patch scope. `agent-baseline` is limited to
one candidate and one candidate-validation experiment. `agent` adds the independent falsifier and
may revise a broken candidate. Neither sees sealed cases, an oracle, mutation descriptions, fixed
cell maps, or reference formulas.

Freeze code, prompts, schemas, model id, and task set before scoring. Use unseen workbook layouts and
at least one out-of-domain policy, include clean and ambiguous tasks, run at least five independent
trials per task, and report blind E2E-SRR, clean preservation, correct abstention, false repairs,
tool/turn/token/cost distributions, and falsifier ablation. No such score is claimed yet.
