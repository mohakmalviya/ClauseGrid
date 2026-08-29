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
