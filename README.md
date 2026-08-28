# FormulaWitness

FormulaWitness is an agentic policy-assurance system for operational Excel workbooks. It turns source-cited policy rules into counterfactual tests, executes an isolated workbook copy, localizes semantic formula defects, proposes a minimal repair for human approval, and verifies the repaired workbook against held-out cases.

> A spreadsheet returning a number is not evidence that it implements the policy.

## Status

Repository scaffold created for the micro1 Agentic Workflows Hackathon. Implementation, fixtures, evaluation evidence, and the user interface are tracked in [`docs/PROJECT_SPEC.md`](docs/PROJECT_SPEC.md) and [`docs/PROGRESS.md`](docs/PROGRESS.md).

## Intended user

Finance and operations teams that rely on spreadsheets to calculate supplier rebates and service-level penalties from written policies.

## Safety boundary

FormulaWitness supports ordinary `.xlsx` workbooks in a constrained formula subset. It never edits the source workbook, executes macros, follows embedded instructions, refreshes external links, or performs consequential changes without human approval.

## License

No license has been granted. The hackathon ownership terms must be reviewed before any public release.
