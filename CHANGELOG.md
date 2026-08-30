# Changelog

## Unreleased

- Added server-side provider presets for OpenRouter, Groq, Together, Gemini, Mistral, and xAI, plus
  a provider-neutral `CLAUSEGRID_API_KEY` deployment secret and configurable custom gateway URL.
- Renamed the product and primary command to ClauseGrid while retaining the legacy
  `formulawitness` import namespace and CLI alias for artifact and automation compatibility.
- Added private local `.xlsx` + matching policy `.pdf` uploads with pre-model compatibility checks,
  isolated temporary storage, exact-hash audit/approval binding, and browser consent disclosure.
- Bounded formula ranges and OOXML sheets/cells/shared strings, rejected XML entity declarations,
  and added deterministic equality `COUNTIF` support required by control sheets.
- Replaced active-content path denylists with OOXML relationship/content-type allowlists, moved PDF
  extraction into a disposable time-bounded worker, and revalidated upload hashes around every run.
- Restricted uploaded packages to UTF-8 XML with store/deflate compression, rejected hidden
  conditional-format/data-validation formula contexts, added one-pass calculation preflight, and
  replaced policy-search wildcard regexes with ordered literal scans.
- Made sandbox dates explicitly tagged, evaluated formulas in dependency order, normalized
  self-qualified active-sheet references, and gated repaired downloads on the hash-valid approval
  commit marker.
- Made prepared uploads single-use with bounded expiry, pre-terminal cleanup attempts, visible retry
  warnings when the operating system temporarily blocks deletion, qualified cross-sheet raw-input
  experiments, and fail-closed cross-sheet formula-chain rejection.
- Aligned the submission report and UI with the hackathon evaluation format: stage-by-stage experiments, challenging-case learning, measured automated runtime, model/API cost, and an explicit no-claim disclosure for unmeasured human time.
- Isolated the sealed evaluator from both repair workers and enforced all-formula minimality.
- Replaced the mutation-specific baseline with a generic policy-derived direct repair.
- Added ambiguity abstention, immutable approval reruns, shared execution budgets, and tamper-evident trajectory verification.
- Added real ordered-range lookup and proportional effective-date proration, a disjoint 48-case sealed split, strict typing, a pinned build environment, and refreshed submission evidence.

## 0.1.0 — 2026-08-29

- Added synthetic supplier rebate/SLA policy PDF and professional reference workbook.
- Added 12 one-cell mutants, three clean controls, and a three-fault hard case.
- Added strict OOXML safety checks and an allowlisted formula worker.
- Added source-cited rule extraction, counterexample generation, dependency/spectrum localization, minimal repair, approval binding, and sealed replay.
- Added direct-agent baseline and frozen E2E-SRR evaluation.
- Added local review UI and downloadable evidence pack.
- Added unit, integration, security, mutation, spreadsheet-render, and clean-preservation validation.

See [docs/IMPROVEMENT_CHANGELOG.md](docs/IMPROVEMENT_CHANGELOG.md) for the measured baseline-to-advanced change and removed experiment.
