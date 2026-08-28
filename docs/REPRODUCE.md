# Reproduction guide

## Clean setup

From the repository root with Python 3.11 or newer:

```powershell
.\scripts\setup.ps1
```

Equivalent cross-platform commands:

```text
python -m venv .venv
.venv/bin/python -m pip install --no-deps -r requirements-lock.txt
.venv/bin/python -m pip install -e . --no-deps --no-build-isolation
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.
Workbook regeneration is not required for evaluation; its Codex-bundled authoring dependency is documented in `docs/BUILD_DEPENDENCIES.md`.

The exact Python distribution versions are pinned in `requirements-lock.txt`. On the measured Windows host with Python 3.12 and cached package downloads, clean setup took about 70 seconds and the complete verification command took about 50 seconds; network and machine speed will change those figures. Baseline, advanced, demo, and evaluation runs make no model or network calls, so their model/API cost is **$0**.

## Verify the implementation

```powershell
.\scripts\verify.ps1
```

This runs formatting, lint, strict type checks, all unit/integration/security/evaluation tests, the frozen mutation-kill audit, and the scored benchmark. Expected headline result:

```text
baseline_e2e_srr: 33.333333333333336
advanced_e2e_srr: 100.0
improvement_pp: 66.66666666666666
advanced_clean_preservation: 100.0
```

## Reproduce the flagship artifact

```powershell
.\scripts\demo.ps1
```

Output is written under `artifacts/demo/advanced-<run-hash>/`. The deterministic run ID changes when the source workbook, extracted-rule bundle, visible-case manifest, or workflow version changes.

## Run the interface

```powershell
.\scripts\serve.ps1
```

Visit `http://127.0.0.1:8765`. M10 is selected by default.

## Workbook authoring and visual QA

The committed `.xlsx` fixtures are ready to use. They were authored with the workspace `@oai/artifact-tool` builder in `scripts/build_workbooks.mjs`, then imported and rendered with `scripts/verify_workbooks.mjs`. The source policy was created by `scripts/build_policy_pdf.py` and visually inspected page by page.

Desktop Excel is optional. The final repaired workbook was separately opened, fully recalculated, saved, and reopened in Excel with macros disabled; it contained all six expected sheets and returned `S6=7500`, `T6=PAYABLE`.

Verify the submitted trajectory hash chains without rerunning either agent:

```powershell
.\.venv\Scripts\python.exe -m formulawitness verify-trajectory trajectories\baseline-m10.jsonl
.\.venv\Scripts\python.exe -m formulawitness verify-trajectory trajectories\advanced-m10.jsonl
```

## Reproducibility controls

- Synthetic data only.
- No runtime network calls or model API.
- Fixed visible cases and fixed secret seed for held-out interior points.
- Nonvolatile formula subset and Excel 1900 date serials.
- `Decimal` with half-up final rounding in the hidden oracle.
- Stable source, rule, case, patch, and trajectory hashes.
- Deterministic workflow; repeated runs are unnecessary under the challenge rule that asks repetition only for nondeterministic systems.
