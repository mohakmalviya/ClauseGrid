# Build dependencies

The committed policy PDF and 17 benchmark workbooks are runtime inputs; users do not need to regenerate them to run ClauseGrid or reproduce the evaluation.

The Python runtime, verification tools, pip, and Hatchling build backend are pinned in `requirements-lock.txt`. `scripts/setup.ps1` installs only those recorded distributions and then installs ClauseGrid without dependency or isolated-build re-resolution.

The workbook-authoring script uses `@oai/artifact-tool` version **2.8.52** from the Codex bundled workspace runtime. That package is not published on the public npm registry, so a fabricated public lockfile would not be reproducible. The generated `.xlsx` files, build script, mutation validation, and strict workbook-import verification are committed instead. The policy PDF generator uses the pinned ReportLab version.
