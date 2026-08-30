# Five-minute model-agent demo script

## Before recording

Configure the selected provider only in the server process. Use a provider/model pair that has
already completed this exact manager/falsifier workflow; for the current validated reference:

```powershell
$env:QUBRID_API_KEY = '<set outside the repository>'
.\.venv\Scripts\clausegrid.exe serve `
  --provider qubrid --model 'deepseek-ai/DeepSeek-V3.2' `
  --allow-external-processing
```

Open `http://127.0.0.1:8765`, start M10, and wait for the complete manager/falsifier run. Leave the
result visible before recording so provider latency does not consume the five-minute video. The UI
refuses a non-loopback bind and never receives the credential, endpoint, or model choice from the
browser. The explicit external-processing flag is validated before the server reads the provider
credential.

## 0:00–0:35 — Real-world failure

Open M10 in Excel. The workbook opens and produces plausible settlement values, but its critical
waiver incorrectly bypasses an ordinary SLA penalty. Formula linting cannot prove whether that
exception matches the written policy.

## 0:35–1:25 — Show genuine agent control

Show the configured provider/model label and the completed UI run. Explain that the audit manager,
not a fixed Python sequence, chose which workbook regions, formulas, policy passages, dependency
cones, and experiments to inspect. Open `trajectory.jsonl` and show successive model response,
tool-call, and tool-observation events without exposing hidden chain-of-thought.

## 1:25–2:25 — Policy evidence and experiments

Show the mechanically registered page/character citations. Then show the manager's sandbox
experiments, including their explicit input overrides, observed cells, candidate formula hashes, and
observed values. Emphasize that the evaluator runs a documented formula subset in a separate
credential-free process; workbook code, macros, and network refreshes are never executed.

## 2:25–3:15 — Independent falsification

Show the fresh-context falsifier verdict and its own experiment IDs. If the first proposal was
broken, show how the counterexample changed the manager's next candidate. A repair remains locked
unless the current exact proposal reaches `SURVIVED`; `BROKEN` or `INCONCLUSIVE` forces revision or
human escalation.

## 3:15–4:05 — Exact proposal and human authority

Show the before/after formula, source SHA-256, and proposal hash. Explain that the model has no apply
or approval tool. Enter the local reviewer label and approve. ClauseGrid revalidates the source,
policy, old-formula guard, persisted proposal, and sandbox evidence before publishing
`repaired.xlsx`; the original remains byte-for-byte unchanged.

## 4:05–4:40 — Reproducible evidence pack

Download `proposal.json`, `agent-state.json`, `formula-diff.json`, `report.json`, `approval.json`,
`trajectory.jsonl`, and the repaired workbook. Run the trajectory verifier:

```powershell
.\.venv\Scripts\clausegrid.exe verify-trajectory `
  artifacts\ui\RUN_ID\trajectory.jsonl
```

## 4:40–5:00 — Honest result and limitation

Point to the panel labeled **Legacy deterministic regression evidence** and state explicitly that its
33.3%-versus-100% score validates the deterministic layer, not the model agents. Report the selected
model's separately measured repeated agent result only after that benchmark exists. End with the main
limitation: ambiguous or conflicting real policy must produce abstention and qualified human
judgment, not an invented oracle.

**A spreadsheet returning a number is not evidence that it implements the policy.**
