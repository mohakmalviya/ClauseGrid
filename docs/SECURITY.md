# Security and trust boundaries

## Accepted

- ordinary `.xlsx` packages below the configured size/entry limits;
- case-insensitively unique worksheet/part names and ordinary worksheet relationships;
- direct or qualified references and ascending ranges in the benchmark calculator;
- arithmetic, comparisons, and `IF`, `AND`, `OR`, `MAX`, `MIN`, `ROUND`, `LOOKUP`.

## Rejected

- `.xls`, `.xlsm`, VBA, macro projects, ActiveX, OLE embeddings;
- encrypted/duplicate ZIP parts, defined names, macro/dialog sheets, shared/array/data-table
  formulas, and multiple sheet names targeting one worksheet part;
- external relationships, external workbook links, connections, QueryTables, and Power Query;
- DDE and network refreshes;
- volatile functions including `INDIRECT`, `OFFSET`, `NOW`, `TODAY`, `RAND`, and `RANDBETWEEN`;
- cycles, missing cells, unsupported syntax/functions, oversized packages, or timeouts.

## Data handling

All bundled workbooks and identifiers are synthetic. Model-directed runs send selected workbook
regions, formulas, policy passages, tool schemas, and prior tool results to the configured external
model provider. They therefore require explicit external-processing consent at startup. Provider
credentials are read from one named process environment variable, are never accepted in browser or
CLI value arguments, and are redacted from errors and traces.
Provider presets select only endpoint metadata and the environment-variable name. Model IDs remain
explicit. `--base-url` rejects embedded credentials, query strings, fragments, and non-TLS remote
URLs. HTTP is allowed only for loopback development. The Anthropic adapter refuses redirects and
bounds response bodies before JSON decoding.

The local UI binds only to loopback, requires a loopback Host header, accepts a benchmark case ID
and reviewer label rather than arbitrary uploads, limits JSON request size, serializes expensive
operations, and allowlists downloadable filenames. It is not a multi-user or internet-facing
service. Trajectories intentionally retain policy quotes, workbook observations, formulas, and
model/tool messages under the configured artifact directory. Treat that directory as confidential,
apply host filesystem access controls, and delete it according to the data owner's retention policy.
FormulaWitness does not currently encrypt artifacts at rest.

Sealed evaluation invokes the oracle only after each model run and never places reference formulas,
held-out cases, or oracle output in an agent request.

## Original-workbook protection

Safety inspection precedes every read. Repair output is a separate OOXML package. Each patch carries
the expected old formula and fails if it no longer matches. Approval takes immutable source and
policy snapshots, revalidates citations and proposal-bound experiments, replays the candidate,
uses an exclusive cross-process lock, stages output/report files, and publishes `approval.json` last
as the transaction commit marker. Formula caches are cleared and Excel full recalculation is forced.

## Known limitation

The worker is an allowlisted interpreter plus process-local file-capability boundary, not a
hostile-code kernel sandbox. The repair workers execute fixed FormulaWitness code, not
workbook-supplied Python. The local UI has no account authentication, tenant isolation, durable job
queue, or TLS and must remain on loopback. The JSONL hash chain is anchored into the reviewed
proposal and approval, but it is not a digital signature or substitute for immutable external log
storage. On platforms that require protection from a malicious repair implementation itself, run
workers as a non-root container with only staged inputs mounted, a read-only filesystem, resource
caps, and `--network none`.
