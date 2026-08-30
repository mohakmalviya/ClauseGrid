# ClauseGrid submission video script

Target length: 4 minutes 40 seconds. The hackathon limit is five minutes.

## Before recording

Open these items before recording so the video stays fast:

1. `https://clausegrid.onrender.com`
2. policy page 3 in `policies/supplier_rebate_sla_policy.pdf`
3. `artifacts/submission/agent-m10/report.json`
4. `artifacts/submission/agent-m10/README.md`
5. `docs/IMPROVEMENT_CHANGELOG.md`

Use the public synthetic M10 case. Do not show an API key, Render environment variables, private
files, browser history, or notifications. Record at 1080p with browser zoom at 100 percent.

## 0:00-0:35 - Problem and user

Say:

> Finance and procurement teams often receive an Excel workbook that calculates a settlement while
> the real business rules live in a policy PDF. The workbook can open normally and return a
> believable number even when one formula applies an exception too broadly. Manual review is slow
> and ordinary formula linting cannot prove that the calculation follows the policy.

Show policy page 3 and point to RB-201 through RB-203. Then show that M10 contains a valid-looking
formula in `RebateCalc!P6`.

## 0:35-1:05 - Baseline

Say:

> Our simple baseline searches for obvious formula patterns and attempts one direct repair. On the
> frozen 12-mutant evaluation it repaired 4 cases, or 33.3 percent. It misses scope, precedence, and
> interacting-rule defects because syntax alone does not establish policy meaning.

Briefly show the baseline row in ClauseGrid's evidence section or `docs/SUBMISSION_REPORT.md`.

## 1:05-2:00 - Run the realistic check

On the public site select **Verify a known workbook**, choose M10, and click **Run approved checks**.

Say:

> ClauseGrid loads the frozen Policy Pack, calculates expected outcomes with an independent rule
> engine, executes the workbook separately, and compares all approved boundary and regression
> cases. This recurring check uses zero model calls and never edits the source workbook.

Show the `FAIL`, `26/27 approved tests passed`, the mismatched P6/R6/S6 values, affected rules
RB-201 through RB-203, and the Policy Pack, test-suite, and evidence hashes.

## 2:00-3:10 - Show the actual agents

Open `artifacts/submission/agent-m10/report.json` and its README.

Say:

> For a new workbook or unfamiliar policy, ClauseGrid uses agents only for investigation. The audit
> manager chooses what policy pages, formula regions, dependencies, and sandbox experiments to
> inspect. It isolated the P6 waiver-scope defect and proposed one formula change. A separate
> fresh-context falsifier then ran five candidate-sensitive experiments across boundary and waiver
> combinations. The proposal survived all five.

Show the recorded counts: 18 manager turns, 8 falsifier turns, 33 tool calls, 9 workbook
executions, 132 trajectory events, and the final trajectory hash. Show one citation, one manager
experiment, and one falsifier experiment. Do not scroll through the whole JSONL file.

## 3:10-3:50 - Explain the difference from a general AI chat

Return to the website and open **Why ClauseGrid**.

Say:

> Claude or another model can perform the initial analysis, and it could even be the investigator
> inside ClauseGrid. The difference is what happens after that. Qualified people approve concrete
> examples once. ClauseGrid freezes those rules and tests, and deterministic code repeats the same
> checks. The model cannot silently redefine correct, approve its own proposal, or edit the source.

Show the three blocks: AI proposes, people approve, code verifies.

## 3:50-4:25 - Measured improvement and changelog

Say:

> On the same frozen cases, the final deterministic workflow repaired 12 of 12 mutants, preserved
> all three clean workbooks, and solved the hard three-error case. That is a 66.7 percentage-point
> improvement over the baseline. These numbers evaluate the deterministic repair layer, not general
> model accuracy. The submitted model-agent run is reported separately.

Open the improvement changelog and point to the removed benchmark-specific substitution experiment.

Say:

> We removed an early shortcut that recognized benchmark construction patterns because a high score
> is meaningless if the solution can see how the test was generated.

## 4:25-4:40 - Limitation and close

Say:

> If the policy is ambiguous or conflicting, ClauseGrid abstains and asks a qualified reviewer. It
> does not invent an oracle. Our main lesson is simple: a spreadsheet returning a number is not
> evidence that it implements the policy. ClauseGrid makes that evidence reproducible.

End on the ClauseGrid hero with the live URL visible.
