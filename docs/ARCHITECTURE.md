# Architecture

## System flow

```text
Policy PDF ──> cited rule agent ──> approved typed rules ──> counterexample planner
                                                        │
Workbook ──> safety gate ──> isolated allowlist worker ─┴─> observed witnesses
                                                        │
                     dependency graph + spectrum localizer
                                                        │
                     constrained minimal patch candidates
                                                        │
                      human hash-bound approval gate
                                                        │
             repaired copy + evidence pack ──> sealed evaluator
```

No repair component imports the hidden oracle. Visible expected results come from policy-compiled formulas; final scoring comes from a separate hand-coded `Decimal` and calendar-date implementation.

## Components

- `policy.py`: extracts 11 exact source spans from the PDF, verifies offsets/hashes, records ambiguity state, and compiles the narrow public rule model.
- `ooxml.py`: rejects active/external content, reads cells/formulas without Excel, enforces old-formula guards, and applies copy-on-write patches.
- `formula.py`: recursive-descent parser and evaluator for a documented nonvolatile subset. Unknown syntax raises `FormulaError`.
- `worker.py` / `runner.py`: evaluates all visible cases in a fresh subprocess and temporary working directory with a minimal environment. The workbook cannot invoke Python, shell, filesystem, or networking APIs because only parsed allowlisted AST nodes execute.
- `advanced.py`: counterexample-guided typed workflow, dependency/spectrum localization, greedy minimal patch search, and approval binding.
- `baseline.py`: direct one-pass policy/formula audit used as the fair comparison.
- `evaluation.py` and `oracle.py`: sealed replay, integrity/minimality checks, clean-control scoring, and the independent oracle.
- `ui.py`: local review application with cited rules, witnesses, formula diff, approval, and downloads.

## Dependency/spectrum localization

For each output mismatch, FormulaWitness calculates the backward formula dependency cone. Each candidate cell records failing coverage, passing coverage, affected outputs, direct mismatch count, and Ochiai suspiciousness:

```text
failed_covered / sqrt(total_failed × (failed_covered + passed_covered))
```

The score is evidence, not certainty. Candidate generation remains restricted to formulas compiled from cited, unambiguous policy rules. The repair stage then accepts only a candidate that increases visible-case passes and stays within the patch-cell budget.

## Approval binding

The approval hash covers:

- source workbook SHA-256;
- extracted-rule bundle hash;
- visible case-manifest hash;
- exact formula-diff hash;
- reviewer identity and decision.

The patcher also checks the exact old formula immediately before writing. A changed input or stale proposal therefore cannot silently reuse approval.

## Isolation claim

FormulaWitness does not claim to emulate every Excel feature or provide a kernel-level sandbox on every operating system. It provides a smaller, auditable boundary: untrusted workbook content is data; a separate worker parses a strict formula grammar; no workbook-supplied code is loaded; unsupported content fails closed. The runner can additionally be placed in a container with networking disabled for deployment.
