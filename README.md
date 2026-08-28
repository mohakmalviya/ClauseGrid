# FormulaWitness

FormulaWitness is an agentic policy-assurance system for operational Excel workbooks. It reads a written supplier rebate/SLA policy and an ordinary `.xlsx` calculator, constructs source-cited rules and boundary counterexamples, executes formulas through a fail-closed worker, localizes semantic drift, proposes the smallest repair, and requires a reviewer before writing a new workbook.

The flagship defect is deliberately plausible: a critical-incident waiver incorrectly bypasses an ordinary SLA penalty. The workbook opens, the formula is valid, and typical rows look reasonable. Only the policy-derived waiver counterexample exposes it.

## Measured result

Frozen benchmark: **SupplierRebate-SLA-16-v2** — 12 one-fault mutants, three clean controls, one three-fault hard case, and 48 sealed vectors per workbook. Revision 2 was preregistered before its scored run after an adversarial audit required real ordered lookup, proportional proration, and a fully disjoint held-out input split.

| System | E2E Semantic Repair Rate | Clean Preservation | Hard case |
|---|---:|---:|---:|
| Direct-agent baseline | 33.3% (4/12) | 100% | 0% |
| FormulaWitness | **100% (12/12)** | **100%** | **100%** |
| Improvement | **+66.7 percentage points** | no regression | +100 pp |

A repair counts only when every sealed output `L6:T6` is semantically correct, workbook integrity passes, the original is unchanged, and the patch respects the one-cell limit (three cells for the hard case). See [evals/results.json](evals/results.json).

## Run it

Requirements: Python 3.11+ and PowerShell for the convenience scripts. Runtime evaluation is offline and does not require Excel, LibreOffice, an LLM key, or network access.

```powershell
.\scripts\setup.ps1
.\scripts\demo.ps1
.\scripts\eval.ps1
.\scripts\serve.ps1
```

Open `http://127.0.0.1:8765`, run the M10 witness audit, inspect the page-cited waiver rule and exact `P6` diff, enter a reviewer identity, and approve. The UI then exposes the frozen proposal, repaired workbook, `Counterexamples` sheet, `rules.yaml`, diff, evidence graph, report, approval record, and JSONL trajectory.

Direct CLI equivalents:

```powershell
.\.venv\Scripts\formulawitness.exe baseline workbooks\mutants\M10_supplier_rebate.xlsx --reviewer reviewer@example.test
.\.venv\Scripts\formulawitness.exe advanced workbooks\mutants\M10_supplier_rebate.xlsx --reviewer reviewer@example.test
.\.venv\Scripts\formulawitness.exe inspect workbooks\reference\supplier_rebate_pristine.xlsx
.\.venv\Scripts\formulawitness.exe eval
```

Omit `--reviewer` to stop at the proposal gate. No repair workbook is written without an explicit reviewer identity.

## What makes it agentic

The advanced workflow is a typed state machine with specialized roles and deterministic gates:

1. `rule-agent` extracts exact quotes and stable page/character offsets.
2. `counterexample-agent` generates lookup-boundary, precedence, waiver, effective-date proration, cap, and rounding witnesses.
3. A separate worker parses only the documented formula subset; workbook code is never executed.
4. `localization-agent` combines dependency cones, failing/passing coverage, and Ochiai scores.
5. `repair-agent` compiles cited rules into constrained one-cell candidates and keeps only changes that improve visible witnesses.
6. `human-reviewer` binds approval to source, rule, case-manifest, and patch hashes.
7. A separate sealed evaluator performs one-shot hidden replay with an independently coded `Decimal`/date oracle.

The baseline receives the same workbook, policy, 20 visible cases, formula/execution tools, patch scope, deterministic policy model, zero-token model budget, and execution limit. It performs one generic policy-derived formula edit without mutation-specific lookup data. FormulaWitness adds typed extraction, ambiguity gating, generated witnesses, dependency localization, multi-candidate replay, and independent verification.

## Safety boundary

- Ordinary `.xlsx` only; `.xlsm`, VBA, OLE/ActiveX, DDE, external links, Power Query/connections, volatile formulas, and network refreshes are rejected.
- The source hash is checked before and after every run; repairs are copy-on-write.
- The evaluator supports arithmetic, comparisons, direct/qualified cell references, ranges, and `IF`, `AND`, `OR`, `MAX`, `MIN`, `ROUND`, and ordered `LOOKUP`. Anything else fails closed.
- Approval is immutable and hash-bound. A stale or unexpected old formula cannot be patched.
- Public rule execution labels visible cases. Held-out vectors and the independent oracle live under `evals/sealed`, outside the installed repair package; evaluation gives each repair process only staged workbook/policy inputs and applies a file-capability guard that denies ordinary access to evaluator files.

This is a focused assurance prototype, not a general Excel replacement. Its main real-world failure mode is ambiguous or conflicting policy language; such rules must produce an abstention and human clarification rather than an invented oracle.

## Repository map

```text
policies/       Synthetic source policy PDF
workbooks/      Pristine, 12 mutants, 3 controls, and hard workbook
src/            Formula parser, safe OOXML layer, agents, UI, and CLI
fixtures/       Frozen build and benchmark manifests
evals/          Sealed evaluator outputs and scored results
artifacts/      Benchmark validation and submission evidence
trajectories/   Submitted baseline/advanced JSONL trajectories
tests/          Unit, integration, security, and evaluation tests
docs/           Architecture, reproduction, limitations, demo, and disclosure
```

More detail: [Architecture](docs/ARCHITECTURE.md), [Reproduction](docs/REPRODUCE.md), [Metric](docs/METRIC.md), [Security](docs/SECURITY.md), and [five-minute demo](docs/DEMO_SCRIPT.md).
