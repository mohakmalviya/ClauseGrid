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

## Fairness

Baseline and advanced systems receive the same policy, workbook, formula visibility, patch scope, allowed operations, and execution budget. Neither receives sealed inputs, the independent oracle, mutation descriptions, or pristine formulas. The direct baseline deliberately has no staged rule IR, generated boundary suite, dependency/spectrum localizer, or candidate-verifier loop—those are the intervention being measured.

Both systems are deterministic and their first frozen candidate is scored. There is no hidden-result retry.
