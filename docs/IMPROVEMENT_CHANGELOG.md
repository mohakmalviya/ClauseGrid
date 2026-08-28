# Improvement changelog

## Baseline → advanced

| Capability | Direct baseline | FormulaWitness |
|---|---|---|
| Policy reading | one-pass phrase/formula audit | exact source spans and typed rules |
| Tests | no generated boundary suite | 20 visible, policy-derived witnesses |
| Execution | available but not staged | separate fail-closed worker |
| Localization | direct textual suspicion | dependency cones + Ochiai spectrum |
| Repair | first local substitution | constrained candidates, visible replay, minimality |
| Review | diff only | evidence, counterexample, hashes, approval |
| Final verification | none | one-shot 48-vector sealed replay |

Measured change on frozen benchmark revision 2 after replacing the mutation-specific baseline table, removing gold-formula comparison from localization, and compiling candidates from cited rule IR: E2E-SRR increased from 33.3% to 100% (+66.7 percentage points) while both systems preserved 100% of clean controls.

## Removed experiment: whole-formula normalization

An early design normalized every core formula to the policy compiler output. It was removed before scored runs. Although it would make defective workbooks semantically correct, it violates the core engineering objective: it rewrites unrelated formulas, destroys evidence about localization quality, and necessarily alters clean controls. Under the frozen metric it fails minimality on all single-fault mutants and yields 0% clean preservation. The current workflow instead searches one-cell candidates (three only for H01) and abstains when a smaller justified patch cannot pass.

## Why the direct baseline remains meaningful

The baseline is not a strawman that always fails. It repairs four simple SLA defects: delivery and quality boundary operators, incident count, and a wrong combined-penalty literal. It fails omitted deductions, narrow lookup shifts, waiver scope, a proration-denominator defect, and cap order—the cases that require structured counterexamples, rule IR, or multi-rule reasoning.
