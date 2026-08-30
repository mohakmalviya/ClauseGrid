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

- The complete automated test count is reported by the current verification run; lint, formatting,
  strict typing, mutation validation, and benchmark acceptance are all gated by `scripts/verify.ps1`.
- The repaired M10 workbook imports through the strict artifact reader and opens/recalculates with the four source sheets plus Counterexamples and FormulaWitness_Report intact.
- Added one-command setup, demo, evaluation, server, and verification scripts plus the complete documentation and tool disclosure.
- Created a local submission evidence pack and JSONL trajectories.
- Upgraded submitted trajectories with readable agent instructions, tool responses, feedback, retry counts, and hash-chain verification.
- Added a PDF-aligned submission report, stage-by-stage evidence changelog, honest human-time disclosure and study protocol, reproducible five-run task timing, H01 analysis, and an evidence-backed evaluation panel in the UI.
- The private GitHub remote exists on `main`; a fresh remote clone installs cleanly and passes the complete verification gate. Later evidence hardening is committed and pushed only after the same checks pass.

## Checkpoint 4 - genuine model runtime

- Reclassified the original baseline/advanced implementation as legacy deterministic workflows; its frozen scores are not agent scores.
- Added a provider-neutral OpenAI-compatible client, environment-only NIM credential handling, bounded retry/rate pacing, typed messages/tools, and secret-safe errors.
- Added template-neutral workbook discovery, policy-only citation retrieval, generic sandbox experiments, model/runtime budgets, and raw schema-v3 hash-chained traces.
- Added a model-controlled audit manager and fresh-context falsifier. Only a surviving candidate can be submitted; neither actor can approve or write a workbook.
- Added the fair `agent-baseline` comparison with the same model/tools/limits, one candidate, one candidate validation, and no falsifier.
- Added separate hash-bound human approval, changed-formula scope validation, and post-copy replay of candidate evidence.
- Live NIM smoke with `openai/gpt-oss-120b` completed with a proposal-only P6 repair after 17 manager turns, 10 falsifier turns, 27 tool calls, and six sandbox executions. This is implementation evidence, not a benchmark score; provider cost was not reported.

## Checkpoint 5 - provider-neutral runtime

- Added explicit OpenAI, native Anthropic/Claude, DeepSeek, NVIDIA NIM, OpenCode Zen, and custom
  OpenAI-compatible provider choices with provider-specific environment variables.
- Added native Anthropic Messages translation for system messages, typed tools, tool history,
  tool results, usage, IDs, stop reasons, bounded responses, and non-retention of reasoning blocks.
- Kept the exact model ID explicit and documented that each provider/model pair requires its own
  compatibility and blind end-to-end evaluation.
- Added protocol-preserving context compaction, a bounded registered-evidence ledger, investigation/
  coordination/terminal tool-call reserves, and bounded recovery when a provider returns plain text
  despite a mandatory tool request.
- Removed the temporary native-pool transport and replaced it with OpenCode Zen's documented
  OpenAI-compatible endpoint. Live free-model compatibility probing is recorded separately from
  end-to-end repair evidence.
- Hardened the model boundary against empty completions, empty choice lists, and providers that
  ignore `parallel_tool_calls=false`; every recovery is bounded and usage remains traceable.
- Exercised seven currently listed OpenCode free chat models. The strongest run reached 33 workbook
  and policy tool calls, but no tested free model completed candidate staging and fresh-context
  falsification; current failures are recorded rather than promoted as production success.

## Checkpoint 6 - live-controller and public-demo hardening

- Reproduced NVIDIA Lightning failures caused by ignored serial-tool settings, repeated deterministic
  reads, impossible early actions, ungraded or duplicate experiments, quoted-formula truncation,
  discovery starvation, repeated inconclusive falsification, and a 15-minute wall-clock cutoff.
- Added semantic read caching, one-shot tool retirement, bounded evidence compaction, provider-call
  serialization, structural formula transforms, quote-safe templates, and stricter evidence gates.
- Added controller phases that force executable manager and falsifier evidence, stop broad discovery
  with decision time reserved, hide mechanically impossible actions, require revision/new evidence
  after an inconclusive verdict, and reserve a final fail-closed verdict/decision turn.
- The latest completed exact Lightning diagnostic registered policy evidence and two experiments,
  then failed closed when the hosted model returned plain text through every bounded mandatory-tool
  retry: `ABSTAIN`, 19 manager turns, zero falsifier turns, 752.1 seconds, and no proposed or written
  patch. This is operational evidence, not a passing accuracy result.
- Added the `agent-eval` repeated blind comparison harness with exact-hash scoring approval, sealed
  post-run oracle access, Wilson intervals, fairness metadata, and atomic result publication. No
  repeated paid/live agent benchmark is claimed yet.
- Added a constrained public-demo mode, non-root Docker image, runtime-only secrets, asynchronous jobs,
  same-origin and Host enforcement, authenticated administrator approval, rate limits, transient
  storage, Render Blueprint, and deployment documentation. Sealed evaluator code/data are excluded
  from the image.

## Checkpoint 7 - Qubrid integration and live GLM evaluation

- Added `qubrid` as a first-class OpenAI-compatible provider using the runtime-only
  `QUBRID_API_KEY`, exact endpoint/model identifiers, provider tests, deployment metadata, and a
  complete user guide.
- Verified `zai-org/GLM-4.7-Flash` with authenticated named-tool and mandatory-any-tool probes. The
  calls were correct but took 106.9 seconds cold and 24.0 seconds warm.
- Preserved two complete M10 failures. The first ended on Qubrid HTTP 429 after a rejected-candidate
  loop. The second used the new recovery path, executed eight experiments, but still proposed no-op
  candidates, missed the waiver-scope defect, and exhausted 30 manager turns. Both preserved the
  source and ended `ABSTAIN`; neither invoked the falsifier or wrote a workbook.
- Added provider-neutral recovery that forces fresh executable evidence after two rejected
  candidates and removes repeatedly rejected no-change actions before they consume the remaining
  coordination budget.
- A focused policy/formula diagnostic also produced an incorrect correction, so GLM-4.7-Flash is
  recorded as transport-compatible but not task-qualified. Zero price is not treated as correctness.

## Checkpoint 8 - Qubrid model replacement and stale-tool recovery

- Rejected `openai/gpt-oss-120b` on Qubrid after six live request variants returned no observable
  function call despite provider reasoning that the call should be made. This does not invalidate the
  earlier successful GPT-OSS run through NVIDIA NIM; it shows that provider routes require separate
  qualification.
- Selected `deepseek-ai/DeepSeek-V3.2` as the Qubrid integration default after correct named and
  required tool probes. Its catalog settings are temperature 1.0 and top-p 0.95.
- Added bounded recovery when a model reuses a tool that the controller has removed from the current
  action set. The runtime states the exact current tools, retries within the existing attempt budget,
  preserves usage, and fails closed if the model repeats the violation.
- Ran M10 twice. The first exposed stale tool reuse. The repaired run reached the correct P6
  waiver-scope diagnosis in 170.5 seconds, but invented invalid experiment cells, exhausted 30
  manager turns, and never staged or falsified a candidate. DeepSeek is therefore an integration
  default, not a task-qualified or production model.

## Checkpoint 9 - private real-workbook input path

- Added a local/private browser path that requires the user's `.xlsx` and governing text-readable
  `.pdf`; the bundled synthetic policy is never substituted for a custom workbook.
- Added pre-model OOXML relationship/content-type allowlists, XML-entity, workbook-size,
  formula-count/text, exact executable-subset, dependency-cycle, range, address, shared-string,
  isolated PDF-readability, and aggregate discovery-output checks.
- Hardened the final input gate to parse every accepted package part as UTF-8 XML, allow only
  store/deflate ZIP methods, reject conditional-format/data-validation/extension formula contexts,
  and execute the complete supported formula graph once before model tokens are spent.
- Bound every accepted input to exact workbook and policy hashes, a server-generated single-use ID,
  isolated OS-temporary storage, a 30-minute expiry, the resulting run, and exact approval.
- Added qualified cross-sheet raw-input experiments and rejected cross-sheet formula-to-formula
  chains that the current one-sheet recalculation worker cannot evaluate safely.
- Added explicit tagged dates, dependency-ordered evaluation, and active-sheet reference
  normalization so experiments cannot confuse cached values with live candidate dependencies.
- Verified both terminal lifecycles: deletion is attempted before a non-repair job or approval is
  exposed; repair inputs otherwise remain only through review, and the copied repaired workbook
  remains downloadable from isolated run artifacts. Simulated operating-system deletion failures
  produce a terminal result with an explicit warning and bounded retry queue rather than a job stuck
  in `running`.
- Browser smoke used the real M10 `.xlsx` and four-page policy PDF, reported 22 formulas and four
  sheets with exact hashes, completed fail-closed, rendered correctly at desktop/mobile widths, and
  produced no browser console errors. This is implementation evidence, not a model accuracy score.

## Checkpoint 10 - provider-neutral deployment configuration

- Preserved native Anthropic Messages transport and the existing OpenAI-compatible boundary, then
  added explicit presets for OpenRouter, Groq, Together, Gemini, Mistral, and xAI.
- Added one provider-neutral hosting secret, `CLAUSEGRID_API_KEY`, selected by server-side
  `CLAUSEGRID_PROVIDER` and `CLAUSEGRID_MODEL` values. Custom compatible gateways additionally use
  `CLAUSEGRID_BASE_URL`; secret values never enter command arguments or browser configuration.
- Retained provider-specific local credential variables and legacy deployment-variable fallbacks so
  existing scripts and deployments remain usable during migration.
- Added unit coverage for every preset, native Anthropic selection, generic-secret isolation,
  custom endpoints, and deployment argument construction.

## Checkpoint 11 - official DeepSeek V4 compatibility and M10 validation

- Queried the authenticated DeepSeek catalog without persisting the credential; the account exposed
  `deepseek-v4-flash`, `deepseek-v4-pro`, and `deepseek-v4-flash-vision-exp`.
- Reproduced DeepSeek V4's rejection of forced named tools while default thinking mode was enabled,
  then added a provider/model-specific non-thinking profile that preserves ClauseGrid's mandatory
  tool boundary without storing or replaying hidden reasoning.
- Completed a blind official-endpoint M10 run with `deepseek-v4-flash` in 78.2 seconds. The manager
  proposed the correct minimal `RebateCalc!P6` repair and the fresh-context falsifier returned
  `SURVIVED` after three candidate-focused experiments with no counterexample.
- Verified the 140-event trajectory hash chain, source preservation, proposal-only approval boundary,
  the full 248-test suite, Ruff, and mypy. This remains a single-task smoke rather than a production
  reliability claim.

## Checkpoint 12 - Qubrid DeepSeek V4 route qualification

- Confirmed `deepseek-ai/DeepSeek-V4-Flash` in Qubrid's authenticated catalog and reproduced its
  thinking-mode rejection of mandatory named tools; non-thinking mode passed the forced tool gate.
- Extended the DeepSeek V4 non-thinking, forced-serial profile to Qubrid without changing other
  provider/model pairs.
- Allowed `falsify_candidate` to receive the optional proposal id models commonly echo from
  `stage_candidate`, but only when it exactly matches the controller's current staged candidate;
  stale or substituted ids remain rejected.
- Ran two blind M10 audits. One staged the exact P6 correction but exhausted turns on the former
  argument mismatch. After the compatibility fix, a fresh run repeatedly attempted invalid
  formula-cell value overrides and never staged a candidate. Both ended safely as `ABSTAIN`.
- Kept the deployment default unchanged because catalog presence and one correct intermediate
  hypothesis do not satisfy the manager/falsifier acceptance contract.

## Checkpoint 13 - Render cold-start recovery

- Reproduced a transient Render free-tier routing response where the public origin returned plain
  text `404 Not Found` before the same origin and every JSON API route returned `200`.
- Added a health-first browser bootstrap and bounded retries for idempotent GET requests when the
  hosting edge returns a non-JSON `404`, `502`, `503`, or `504` during startup.
- Replaced unconditional JSON parsing with content-aware response decoding so a hosting error is
  reported with its endpoint and status instead of crashing as an `Unexpected token` exception.
- Kept POST and upload requests non-retrying to avoid duplicating audits or external processing
  after an ambiguous network failure.

## Checkpoint 14 - public runtime privacy, uploads, and durable policy evidence

- Reproduced a live run that registered four exact policy citations, then reached a terminal turn
  whose compact controller ledger retained only their handles. The model incorrectly claimed the
  policy text was unavailable and safely `ABSTAIN`ed.
- Added bounded exact-quote previews to both normal and highly compact evidence ledgers so terminal
  and coordination turns retain policy meaning after the original tool observations are compacted.
- Removed provider/model routing metadata from anonymous config and job responses, replaced the UI
  identity with a managed-runtime label, and withheld raw trajectory downloads in public mode while
  preserving the original server-side artifacts.
- Enabled same-origin public `.xlsx`/`.pdf` uploads on Render with consent, compatibility preflight,
  separate upload throttling, single-use hash binding, audit limits, expiry, cleanup, and ephemeral
  isolation. Browser approval remains disabled.
- A fresh live M10 audit completed in 175.8 seconds and retained the exact RB-202/RB-203 policy
  meaning through terminal coordination. It localized P6 and reached falsification; the falsifier
  correctly marked the model's unsafe `=1` proposal `BROKEN`. The manager then exhausted its turn
  budget, so the run remained a safe `ABSTAIN`, not a successful repair or model-qualification claim.
- Live Render preflight accepted the synthetic workbook/policy pair as 22 formulas across four
  sheets and four PDF pages. Anonymous config/results omitted runtime identity, and direct public
  requests for proposal, report, and raw trajectory artifacts returned `404`.

## Checkpoint 15 - explicit AI-assistant differentiation

- Added an above-the-fold comparison that answers the expected objection directly: Claude or
  another AI assistant can analyze the files and propose a formula, while ClauseGrid is the
  enforced assurance system around that model.
- The public copy now distinguishes recommendation generation from exact citations, executable
  counterexamples, fresh-context falsification, source preservation, and human-controlled writes
  without claiming that the underlying model lacks spreadsheet-analysis capability.

## Checkpoint 16 - approved Policy Pack and zero-model recurring verification

- Added a version-controlled supplier-rebate Policy Pack release with clearly labelled synthetic
  policy-owner and controls-review approvals, generated boundary tests, and a permanent
  waiver-scope regression case whose expected output cannot be supplied by configuration.
- Added an independent Decimal/date `RuleIR` oracle that imports no spreadsheet formula evaluator,
  removing the prior common-mode risk from approved expected outcomes.
- Added an approval-bound release hash covering the exact rules, full test suite, mapping, declared
  versions, and deterministic implementation hashes. Both distinct demo roles attest that release;
  stale approvals fail closed. Separate test-suite and Mapping Pack hashes remain visible.
- Added deterministic recurring verification bound to the workbook and engine. The CLI and
  `/api/verify` report the actual `model_calls: 0` and verify that source bytes remain unchanged.
- Added a public read-only explanation of the required production governance workflow: edge-case
  classification, distinct human roles, immutable successor versions, incorrect-policy withdrawal,
  and affected-audit replay. The page explicitly says the demo has no writable version or audit
  registry and does not misrepresent anonymous Render interactions as production approval.
- Added tests comparing the new oracle to the sealed semantic reference, validating pack quorum and
  hash stability, proving repeatable no-model verification, and requiring the approved suite to
  detect all twelve public formula mutants.
- Added active-constraint cases for negative-before-floor eligible spend, post-period active-day
  flooring, and an unpenalized rebate above the cap. Dedicated mutations that remove each control
  are now killed, while C01-C03 remain clean. Workbook execution failures return structured
  `INCONCLUSIVE` evidence rather than being misreported as policy violations.

## Checkpoint 17 - demo-first workbench and first-user walkthrough

- Replaced the long landing-page stack with a full-width workbench whose two explicit modes are
  recurring deterministic verification and optional AI-assisted investigation.
- Added an above-the-fold M10 quick check, a stable empty-result region, compact supporting
  explanations, expandable Policy Pack evidence, and responsive layouts that remove the earlier
  narrow result column and nested-card sprawl.
- Added a seven-step spotlight walkthrough with replay controls, Next, Back, Skip, Escape and arrow
  keys, focus containment and restoration, resize tracking, mobile bottom-sheet behavior, and
  first-visit persistence. The tour switches modes only while explaining them and restores the
  user's prior mode when it closes.
- Added roving keyboard focus to both tab groups, hid AI workflow and result state from recurring
  verification, disabled mode changes during a running AI audit, and exposed runtime failures in
  the status badge instead of always claiming readiness.
- Removed the disconnected left sidebar and moved all five section links, live Policy Pack version,
  approved-rule count, and walkthrough control into a compact responsive top bar. The workbench
  header, tabs, stages, and result cards now share one gutter and one column grid so their dividers
  and content rails stay aligned at desktop and mobile widths.
- Replaced the former 8–12 px interface typography with a shared readable scale: 16 px body text,
  15 px navigation, 14 px controls, 13 px supporting copy, and a 12 px metadata floor. Tablet and
  phone headers now reflow instead of shrinking text, and low-contrast metadata colors were
  darkened. A regression test prevents future explicit font sizes below the 12 px floor.
- Removed the desktop-only 700 px mode minimum that created an empty workbench band, aligned both
  stage labels as block-level flex rows, and placed investigation actions and runtime status in one
  full-width control row. The two differentiation cards now use shared subgrid rows so their
  kickers, headings, copy, and diagrams line up without forced card heights.
- Renamed the top navigation link to `Why ClauseGrid` and added an above-the-fold
  `How this differs from Claude` link while retaining the complete comparison and agent-role
  explanation below the workbench.
- Browser checks ran the first-screen M10 path and confirmed the expected 26/27 result with exact
  cell evidence, exercised both tab systems by keyboard, walked to the result explanation, and
  verified mode restoration. The focused UI suite passes 32 tests; the complete suite passes 306.
