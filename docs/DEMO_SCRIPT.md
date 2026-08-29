# Five-minute demo script

## 0:00–0:35 — Problem

Open M10 in Excel. Point out that it opens cleanly, has no broken references, and returns plausible values. Show policy page 3: a critical waiver waives only critical exclusion, not ordinary SLA penalties.

## 0:35–1:05 — Baseline

Run:

```powershell
.\.venv\Scripts\formulawitness.exe baseline workbooks\mutants\M10_supplier_rebate.xlsx
```

The direct audit returns `NO_CHANGE`. This is the real bottleneck: a valid formula can encode the wrong exception precedence.

## 1:05–2:20 — Witness generation

Start `scripts\serve.ps1`, open the UI, and run M10. Show:

- exact page-cited policy quotes;
- 20 visible counterexamples;
- V17: incident present, waiver `Y`, delivery breach present;
- expected `P6=0.75`, actual `P6=1`, propagating to `R6` and `S6`.

## 2:20–3:15 — Localization and repair

Show `P6` ranked with dependency and spectrum evidence. Compare the before/after formula. The proposed change is one cell and restores ordinary SLA evaluation after the critical waiver.

## 3:15–3:55 — Human gate and evidence

Enter a reviewer identity and approve. Download:

- `repaired.xlsx`;
- `proposal.json`;
- `rules.yaml`;
- `formula-diff.json`;
- `evidence-graph.json`;
- `counterexamples.json`;
- `report.json`;
- `approval.json`;
- `trajectory.jsonl`.

Open the repaired workbook. Show the new `Counterexamples` and `FormulaWitness_Report` sheets and confirm the original file is unchanged.

## 3:55–4:35 — Sealed replay

Run `scripts\eval.ps1`. Explain that hidden cases and the independent oracle are outside both repair workflows and are evaluated once after candidate freeze.

## 4:35–5:00 — Result and limitation

Show the comparison table in `docs/SUBMISSION_REPORT.md`: 33.3% baseline versus 100% FormulaWitness, +66.7 pp, with 100% clean preservation and H01 improving from 0% to 100%. State that the five-run M10 median was 0.331 seconds for the baseline and 0.451 seconds for FormulaWitness, model/API cost was $0 for both, and human time was not measured because no qualified-reviewer study was run. Briefly explain that the adversarial benchmark refreeze and removal of leakage-prone gold-formula logic mattered more than adding another agent. End with the limitation that ambiguous real policies must trigger abstention and clarification, then the hot take: **“A spreadsheet returning a number is not evidence that it implements the policy.”**
