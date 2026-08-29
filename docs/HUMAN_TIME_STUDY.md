# Human-Time Study Protocol

Human time is not currently a measured project result. The hackathon PDF presents it as a useful
comparison row, but inventing a number would violate the requirement to connect every claim to
evidence.

To measure it credibly:

1. Recruit at least three finance, procurement, spreadsheet-audit, or qualified domain-proxy
   reviewers.
2. Use at least ten fixed synthetic workbooks, balanced across simple defects, interaction defects,
   and clean controls. Do not reveal the mutation label.
3. Randomize task order and use a crossover design: each reviewer audits half with the current
   baseline materials and half with FormulaWitness, then swaps conditions for a second set.
4. Start active-time measurement when the reviewer receives the policy and workbook. Stop when they
   submit `REPAIR`, `NO_CHANGE`, or `ABSTAIN` and identify the responsible cell(s).
5. Record correctness, active seconds, review confidence, and whether the reviewer requested more
   evidence. Exclude setup time but report exclusions and interruptions.
6. Report median and interquartile range by condition, paired accuracy, sample size, and every
   failure. Do not report a time-saving percentage unless accuracy is non-inferior.

The application can support this study, but the results require real human participants. Until the
study is run, the submission report must retain `Not measured / No claim` for human time per task.
