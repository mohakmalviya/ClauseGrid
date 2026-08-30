# ClauseGrid submission form

## Title

ClauseGrid - Policy-Aware Spreadsheet Assurance with Falsifying AI Agents

## Description

Finance, procurement, operations, compliance, and audit teams often depend on spreadsheets whose
real rules live in policy PDFs. A workbook can open normally and return a plausible number while its
formula applies the wrong threshold, exception, date rule, cap, or rounding order. Normal formula
linting cannot prove that the spreadsheet follows the written policy, and asking a general AI chat
to compare the files produces a new interpretation on every run.

ClauseGrid turns reviewed policy meaning into a versioned Policy Pack containing exact citations,
approved examples, boundary cases, regression tests, workbook mappings, and tamper-evident hashes.
For unfamiliar evidence, an audit-manager agent chooses policy searches, workbook inspections,
dependency checks, and sandbox experiments. A fresh-context falsifier agent then tries to break the
proposed repair with counterexamples. The agents may investigate and propose, but they cannot
approve or apply a change. Qualified people approve the policy meaning, and deterministic code owns
the recurring PASS, FAIL, or INCONCLUSIVE result.

The public demo shows the key differentiator on the M10 supplier-rebate workbook. Its formula is
valid Excel but incorrectly lets a critical-incident waiver bypass ordinary SLA penalties.
ClauseGrid replays 27 approved checks with zero model calls, catches the retained waiver-scope
regression, identifies the affected policy rules, and preserves the source file.

We evaluated the deterministic workflow on the same frozen cases as a simple baseline: 12
single-formula mutants, three clean controls, one hard multi-error workbook, and 48 sealed inputs per
workbook. The baseline repaired 4 of 12 mutants (33.3%); ClauseGrid repaired 12 of 12 (100%),
preserved all three clean controls, and solved the hard case. These figures measure the deterministic
repair layer, not general model accuracy. The submitted schema-v3 agent trajectory is reported
separately: a live manager/falsifier run found the M10 waiver-scope defect, staged the minimal P6
repair, and survived five independent falsifier experiments. Its 132-event hash chain verifies.

The main lesson is that a spreadsheet returning a number is not evidence that it implements the
policy. Reliable assurance needs a complete witness chain: cited rule, discriminating input,
observed divergence, minimal proposal, counterexample challenge, accountable approval, and
independent replay.

Live demo: https://clausegrid.onrender.com

Source repository: https://github.com/mohakmalviya/ClauseGrid

## Video URL

Replace this line with the public or unlisted YouTube, Loom, or Google Drive URL after uploading the
final video. Confirm that the link opens in a signed-out browser before submitting.

## Source code upload

Upload `ClauseGrid-submission.zip`. It contains the source, agent instructions, synthetic policy and
workbooks, frozen evaluation evidence, improvement changelog, reproduction guide, and representative
agent trajectories. It does not contain `.git`, virtual environments, caches, temporary runs, or API
keys.
