# Tool and agent disclosure

## Build tools

- OpenAI Codex (GPT-5) was used as the coding agent to design, implement, test, and document this repository.
- `@oai/artifact-tool` 2.8.52 from the Codex bundled runtime authored and strictly re-imported the synthetic `.xlsx` fixtures. It is not a runtime dependency and is not published on the public npm registry.
- ReportLab generated the synthetic policy PDF; Poppler rendered it for visual QA.
- `pypdf` provides page-addressable policy text extraction.
- Desktop Microsoft Excel was used once for independent open/recalculate/save validation of the final repaired workbook; it is not a runtime dependency.
- Python standard-library OOXML, subprocess, HTTP, hashing, JSON, `Decimal`, and date modules implement the runtime.

No production or personal data, hidden hackathon test, external model API, or web service is used at runtime.

## Submitted trajectories

The advanced JSONL trajectory records `ingest-agent`, `rule-agent`, `counterexample-agent`, `localization-agent`, `repair-agent`, and `human-reviewer` transitions with stable input/output hashes and artifact references. A baseline trajectory is submitted separately. Hidden evaluator payloads are never written into either trajectory.
