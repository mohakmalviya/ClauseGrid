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

Measured change: E2E-SRR increased from 50% to 100% (+50 percentage points) while both systems preserved 100% of clean controls.

## Removed experiment: whole-formula normalization

An early design normalized every core formula to the policy compiler output. It was removed before scored runs. Although it would make defective workbooks semantically correct, it violates the core engineering objective: it rewrites unrelated formulas, destroys evidence about localization quality, and necessarily alters clean controls. Under the frozen metric it fails minimality on all single-fault mutants and yields 0% clean preservation. The current workflow instead searches one-cell candidates (three only for H01) and abstains when a smaller justified patch cannot pass.

## Why the direct baseline remains meaningful

The baseline is not a strawman that always fails. It repairs six defect families, including tier boundaries, incident count, wrong multiplier literal, and the 90-day comparison. It fails omissions, coupled boundary edits, waiver scope, and cap order—the cases that require counterexamples and multi-rule reasoning.
