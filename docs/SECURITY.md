# Security and trust boundaries

## Accepted

- ordinary `.xlsx` packages below the configured size/entry limits;
- direct or qualified references and ascending ranges in the benchmark calculator;
- arithmetic, comparisons, and `IF`, `AND`, `OR`, `MAX`, `MIN`, `ROUND`, `LOOKUP`.

## Rejected

- `.xls`, `.xlsm`, VBA, macro projects, ActiveX, OLE embeddings;
- external relationships, external workbook links, connections, QueryTables, and Power Query;
- DDE and network refreshes;
- volatile functions including `INDIRECT`, `OFFSET`, `NOW`, `TODAY`, `RAND`, and `RANDBETWEEN`;
- cycles, missing cells, unsupported syntax/functions, oversized packages, or timeouts.

## Data handling

All bundled workbooks and identifiers are synthetic. The local UI binds only to `127.0.0.1` by default. It accepts a benchmark case ID and reviewer label, not arbitrary uploads. Download paths use an allowlist and normalized filenames. Sealed evaluation stages only public inputs for each repair process and installs a file-capability guard that denies ordinary reads outside those inputs and the run directory.

## Original-workbook protection

Safety inspection precedes every read. Repair output is a separate OOXML package. Each patch carries the expected old formula and fails if it no longer matches. Evaluation re-hashes the source after the run.

## Known limitation

The worker is an allowlisted interpreter plus process-local file-capability boundary, not a hostile-code kernel sandbox. The repair workers execute fixed FormulaWitness code, not workbook-supplied Python. On platforms that require protection from a malicious repair implementation itself, run it as a non-root container with only staged public inputs mounted, a read-only filesystem, resource caps, and `--network none`.
