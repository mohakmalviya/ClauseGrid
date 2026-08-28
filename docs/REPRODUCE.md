# Reproduction guide

## Clean setup

From the repository root with Python 3.11 or newer:

```powershell
.\scripts\setup.ps1
```

Equivalent cross-platform commands:

```text
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

## Verify the implementation

```powershell
.\scripts\verify.ps1
```

This runs formatting checks, lint, 12 unit/integration/security/evaluation tests, the frozen mutation-kill audit, and the scored benchmark. Expected headline result:

```text
baseline_e2e_srr: 50.0
advanced_e2e_srr: 100.0
improvement_pp: 50.0
advanced_clean_preservation: 100.0
```

## Reproduce the flagship artifact

```powershell
.\scripts\demo.ps1
```

Output is written under `artifacts/demo/advanced-<source-hash>/`. The deterministic run ID changes only when the source workbook or workflow version changes.

## Run the interface

```powershell
.\scripts\serve.ps1
```

Visit `http://127.0.0.1:8765`. M10 is selected by default.

## Workbook authoring and visual QA

The committed `.xlsx` fixtures are ready to use. They were authored with the workspace `@oai/artifact-tool` builder in `scripts/build_workbooks.mjs`, then imported and rendered with `scripts/verify_workbooks.mjs`. The source policy was created by `scripts/build_policy_pdf.py` and visually inspected page by page.

Desktop Excel is optional. The final repaired workbook was separately opened, fully recalculated, saved, and reopened in Excel with macros disabled; it contained all five expected sheets and returned `S6=7500`, `T6=PAYABLE`.

## Reproducibility controls

- Synthetic data only.
- No runtime network calls or model API.
- Fixed visible cases and fixed secret seed for held-out interior points.
- Nonvolatile formula subset and Excel 1900 date serials.
- `Decimal` with half-up final rounding in the hidden oracle.
- Stable source, rule, case, patch, and trajectory hashes.
- Deterministic workflow; repeated runs are unnecessary under the challenge rule that asks repetition only for nondeterministic systems.
