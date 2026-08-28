# Hot take

> **A spreadsheet returning a number is not evidence that it implements the policy.**

Spreadsheet correctness is not a linting problem. A formula can be syntactically valid, internally consistent, and still be wrong because the real specification lives in policy prose, exception emails, and human judgment.

The useful unit of assurance is therefore not “formula changed.” It is a **witness**: a cited rule, a discriminating input, an observed divergence, a dependency path, a minimal patch, and an accountable approval. FormulaWitness makes that chain executable and reviewable.
