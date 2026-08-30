# Security and trust boundaries

## Accepted

- calculation-focused `.xlsx` packages below the configured size/entry limits, containing only
  UTF-8 XML parts compressed with ZIP store/deflate;
- case-insensitively unique worksheet/part names and an explicit allowlist of passive workbook,
  worksheet, style, string, theme, calculation-chain, and document-property relationships/types;
- direct or qualified references and ascending ranges in the benchmark calculator;
- arithmetic, comparisons, bounded references/ranges, and `IF`, `AND`, `OR`, `MAX`, `MIN`,
  `ROUND`, ordered `LOOKUP`, and equality `COUNTIF`.

## Rejected

- `.xls`, `.xlsm`, VBA, macro projects, ActiveX, OLE embeddings;
- encrypted/duplicate ZIP parts, defined names, macro/dialog sheets, shared/array/data-table
  formulas, unsupported compression methods, and multiple sheet names targeting one worksheet part;
- external relationships, external workbook links, connections, QueryTables, and Power Query;
- DDE and network refreshes;
- volatile functions including `INDIRECT`, `OFFSET`, `NOW`, `TODAY`, `RAND`, and `RANDBETWEEN`;
- cycles, missing worksheet references, unsupported syntax/functions, oversized packages, or
  timeouts;
- drawings, comments, controls, charts, media, hyperlinks, and other relationships outside the
  calculation-focused allowlist.
- conditional formatting, data validation, worksheet extension lists, and any other formula-bearing
  worksheet context the deterministic evaluator does not execute;

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

The default local UI binds only to loopback and requires a loopback Host header. Its private upload
mode requires both a workbook and matching policy, uses raw size-bounded bodies and server-generated
paths, rejects unsupported OOXML/formulas and a failing initial calculation before a model call, and
stores files/runs in an isolated
OS-temporary runtime instead of the repository. A consent gate states that selected evidence is sent
to the configured provider and retained in traces. Each upload can start only one audit. Pending and
repair-review inputs expire after 30 minutes. Deletion is attempted earlier after a non-repair result
or approval; an operating-system deletion failure is disclosed in the response and queued for
bounded retries. Stopping the server removes its complete temporary runtime.

The explicit public
demo mode must sit behind an HTTPS reverse proxy and match its configured Host and modifying-request
Origin. It accepts only bundled synthetic benchmark case IDs—never arbitrary uploads—limits JSON
request size and audit frequency, serializes expensive operations, uses unguessable job IDs, and
allowlists downloadable filenames. Audits run asynchronously so one long model call does not hold
the HTTP request open. Public browser approval is disabled; an approval call additionally requires a
server-side bearer token. Error details stay in server logs rather than public JSON responses.

Every accepted package part is parsed through the UTF-8 XML gate; `DOCTYPE` and `ENTITY`
declarations are rejected even in optional style, theme, property, or calculation-chain parts.
Worksheet,
cell, shared-string, formula, range, package-entry, compressed-byte, and uncompressed-byte bounds
limit parser and dependency amplification. PDF extraction runs in a disposable subprocess with a
20-second wall-clock limit, 15-second CPU limit, and 512 MiB process-memory/address-space limit. POSIX
uses resource limits; Windows attaches a kill-on-close Job Object before sending the PDF request and
fails closed if that boundary cannot be established. The anonymous public deployment accepts no
uploads. These gates reduce risk but do not turn the local server into a hostile multi-tenant
document service.

Policy search uses ordered literal scans rather than a wildcard regex, keeping retrieval linear in
the bounded extracted text even for repeated adversarial query terms.

The experiment sandbox recalculates one selected formula sheet. It accepts sheet-qualified raw input
overrides, but uploaded workbooks containing cross-sheet formula-to-formula dependencies are rejected
before the model runs so cached values cannot become false evidence.

Public rate limits, jobs, and locks are process-local, so the demo must run as one instance. The
container runs as an unprivileged user and writes transient artifacts below `/tmp`. Local/private
trajectories can retain policy quotes, workbook observations, formulas, and model/tool messages;
treat a configured persistent artifact directory as confidential, apply host filesystem controls,
and delete it according to the data owner's retention policy. FormulaWitness does not encrypt
artifacts at rest.

Sealed evaluation invokes the oracle only after each model run and never places reference formulas,
held-out cases, or oracle output in an agent request.

## Original-workbook protection

Safety inspection precedes every read. Repair output is a separate OOXML package. Each patch carries
the expected old formula and fails if it no longer matches. Approval takes immutable source and
policy snapshots, revalidates citations and proposal-bound experiments, replays the candidate,
uses an exclusive cross-process lock, stages output/report files, and publishes `approval.json` last
as the transaction commit marker. The UI serves the repaired workbook/report only when that marker's
hash is valid and its recorded repaired hash matches the exact bytes. Formula caches are cleared and
Excel full recalculation is forced.

## Known limitation

The worker is an allowlisted interpreter plus process-local file-capability boundary, not a
hostile-code kernel sandbox. The repair workers execute fixed FormulaWitness code, not
workbook-supplied Python. The public mode has no user accounts, tenant isolation, distributed rate
limiter, durable queue, or durable artifact store. The JSONL hash chain is anchored into the reviewed
proposal and approval, but it is not a digital signature or substitute for immutable external log
storage. On platforms that require protection from a malicious repair implementation itself, run
workers as a non-root container with only staged inputs mounted, a read-only filesystem, resource
caps, and `--network none`.
