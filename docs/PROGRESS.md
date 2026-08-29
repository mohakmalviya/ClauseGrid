# Progress log

## Checkpoint 0 - 2026-08-29

- Read and visually verified all ten pages of the hackathon PDF.
- Confirmed the rubric prioritizes purposeful agent engineering, end-to-end usefulness, measured improvement, and clean reproduction.
- Initialized the local repository on `main`.
- Added the reviewed scaffold and authoritative project specification.
- Private GitHub creation and push remain gated on explicit user confirmation.

## Checkpoint 1 - frozen benchmark

- Authored the four-page synthetic policy PDF and the professional reference workbook.
- Froze 12 one-cell mutants, three clean controls, one three-fault hard case, 20 visible witnesses, and 48 held-out vectors.
- Verified every mutant changes exactly one core formula and is killed by at least two held-out vectors.
- Imported and rendered all 17 workbook fixtures; no formula errors remain.

## Checkpoint 2 - baseline and advanced system

- Implemented fail-closed OOXML inspection, formula parser, separate execution worker, source-cited rules, counterexamples, dependency/Ochiai localization, minimal repair, approval binding, and sealed trajectory verification.
- Implemented a direct-agent baseline under the same input and patch contract.
- Replaced the mutation-specific baseline and gold-formula localization check, isolated evaluator modules, and re-froze the benchmark.
- Measured 33.3% baseline versus 100% advanced E2E-SRR (+66.7 pp), with 100% clean preservation and a successful three-fault hard case on benchmark revision 2.
- Added the local review interface and verified audit, approval, downloads, responsive layout, and console state in a browser.

## Checkpoint 3 - verification and submission pack

- Thirty-four automated tests, lint, formatting, strict typing, mutation validation, and benchmark acceptance all pass.
- The repaired M10 workbook imports through the strict artifact reader and opens/recalculates with the four source sheets plus Counterexamples and FormulaWitness_Report intact.
- Added one-command setup, demo, evaluation, server, and verification scripts plus the complete documentation and tool disclosure.
- Created a local submission evidence pack and JSONL trajectories.
- Upgraded submitted trajectories with readable agent instructions, tool responses, feedback, retry counts, and hash-chain verification.
- Added a PDF-aligned submission report, stage-by-stage evidence changelog, honest human-time disclosure and study protocol, reproducible five-run task timing, H01 analysis, and an evidence-backed evaluation panel in the UI.
- The private GitHub remote exists on `main`; a fresh remote clone installs cleanly and passes the complete verification gate. Later evidence hardening is committed and pushed only after the same checks pass.
