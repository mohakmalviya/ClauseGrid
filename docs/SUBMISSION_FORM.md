# ClauseGrid submission form

## Title

ClauseGrid - AI Agents That Check Spreadsheet Formulas Against Policy Rules

## Description

Finance, procurement, compliance, and audit teams often use spreadsheets to calculate payments and
make business decisions. The problem is that the actual rules are usually written in a policy PDF.
A spreadsheet can open and calculate without any Excel error while still using the wrong threshold,
exception, date rule, cap, or rounding order. Finding this by hand means comparing policy text with
formulas one rule at a time.

ClauseGrid checks what a spreadsheet formula actually does against an approved Policy Pack. A
Policy Pack stores the relevant policy citations, examples, boundary cases, regression tests,
workbook cell mappings, and hashes. This gives the team one reviewed definition of correct behaviour
that can be used again instead of asking an AI model to reinterpret the policy on every audit.

When ClauseGrid sees a new or unfamiliar workbook, an audit-manager AI agent reads the relevant
policy pages and workbook formulas, checks dependencies, and runs sandbox experiments. It can then
propose a small formula correction. A fresh-context falsifier agent receives the proposal separately
and tries to break it with counterexamples. Neither agent can approve the proposal or change the
source workbook. A qualified human reviews the evidence, while deterministic verification produces
the recurring PASS, FAIL, or INCONCLUSIVE result.

The public demo uses an M10 supplier-rebate workbook. One formula treats a critical-incident waiver
as if it also removes normal SLA penalties, even though the policy says it does not. The formula is
valid Excel, so normal syntax checks do not catch the problem. ClauseGrid runs 27 approved tests with
zero model calls. It finds the failing waiver case, points to the affected policy rules and cells,
and leaves the original workbook unchanged.

We tested the baseline and the final deterministic workflow on the same frozen test set. It contains
12 workbooks with one formula error, three clean workbooks, one harder workbook with several errors,
and 48 sealed test inputs for each workbook. The simple baseline repaired 4 of 12 faulty workbooks,
or 33.3 percent. ClauseGrid repaired 12 of 12, kept all three clean workbooks unchanged, and solved
the hard case. These numbers test the deterministic repair layer. They do not claim that every AI
model will be 100 percent accurate.

The AI-agent evidence is reported separately. In the submitted schema-v3 trajectory, a real
audit-manager and falsifier run found the M10 error, proposed a one-cell repair in P6, and passed five
falsifier experiments. The trajectory contains 132 hash-linked events, so another person can verify
that the recorded tool calls and results were not changed.

Claude or another general AI model can read a policy and suggest a formula. ClauseGrid keeps that AI
analysis inside a controlled process. Once people approve the Policy Pack, deterministic code checks
the same meaning in the same way every time. AI agents help investigate new cases, but they do not
decide company policy.

The main lesson is simple: a spreadsheet returning a number does not prove that it follows the
policy. ClauseGrid connects each result to the policy citation, test input, observed output, proposed
change, human review, and reproducible evidence.

Live demo: https://clausegrid.onrender.com

Source repository: https://github.com/mohakmalviya/ClauseGrid

## Video URL

Replace this line with the public or unlisted YouTube, Loom, or Google Drive URL after uploading the
final video. Confirm that the link opens in a signed-out browser before submitting.

## Source code upload

Upload `ClauseGrid-submission.zip`. It includes the source code, AI-agent instructions, test policy
and workbooks, fixed evaluation results, improvement changelog, setup steps, and sample agent runs.
It does not include `.git`, virtual environments, caches, temporary runs, or API keys.
