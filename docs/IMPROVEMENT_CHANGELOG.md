# Improvement Changelog

Every row below records an actual implementation stage preserved in Git history. Correctness
figures use End-to-End Semantic Repair Rate (E2E-SRR); a repair counts only when all 48 sealed
vectors pass, the source remains unchanged, and the formula diff is minimal. Revision 1 and
revision 2 are different frozen benchmarks, so their scores are historical checkpoints rather
than a causal comparison across revisions.

| Stage | What we tried and why | Evidence | Decision / learning |
|---|---|---|---|
| Baseline (`d44e78c`, benchmark v1) | A direct agent scanned formulas once and applied at most one textual policy substitution. This represented the simplest plausible automated audit. | 50.0% E2E-SRR (6/12), 100% clean preservation, 0% on H01. Historical evidence is stored in `d44e78c:evals/results.json`. | Established the starting point, but later review found that its substitution table encoded benchmark-specific defect fragments. |
| Iteration 1 (`d44e78c`, benchmark v1) | Added cited typed rules, policy-derived boundary cases, a fail-closed formula worker, dependency/Ochiai localization, constrained repair, approval, and sealed replay. | 100% E2E-SRR (12/12), 100% clean preservation, 100% on H01: +50 percentage points over the v1 baseline. | Kept the staged witness workflow. The perfect result triggered an adversarial audit of the benchmark and evaluator rather than an immediate completion claim. |
| Iteration 2 (`be16d1e`, benchmark v2) | Rebuilt lookup mutants around real ordered `LOOKUP`, corrected proportional proration, and made all 48 held-out inputs disjoint from visible inputs. This tested whether the result survived a more realistic benchmark. | FormulaWitness remained at 100% E2E-SRR and 100% clean preservation; the direct baseline fell to 33.3%. `artifacts/benchmark-validation.json` proves every mutant is killed and the split is disjoint. | Kept benchmark v2. The lower baseline score is not presented as an agent improvement; it is evidence that v1 was too forgiving. |
| Iteration 3 (`be16d1e`, benchmark v2) | Removed benchmark-specific substitution logic and gold-formula filtering, moved the oracle and held-out cases to `evals/sealed`, and ran each agent with a file-capability guard. | Hardened result: 33.3% baseline versus 100% FormulaWitness (+66.7 pp), both with 100% clean preservation. `tests/evaluation/test_oracle_isolation.py` proves the repair workers cannot import or read evaluator-only data. | Kept. Evaluation integrity mattered more than preserving the earlier baseline score. |
| Iteration 4 (`5a66c74`, benchmark v2) | Made trajectories judge-readable, bound approval to repaired workbook bytes, made new OOXML entries deterministic, and visually fixed formula overflow in the UI. | 33 tests pass; trajectories contain instructions, tools, responses, feedback, retries, and checkpoints; independent approved runs produce the same workbook and approval hash; all 17 workbooks pass the renderer. E2E-SRR stayed 100%. | Kept. These changes improved reproducibility and end-to-end quality without changing the scored outcome. |
| Final | Combined the hardened witness workflow, sealed evaluator, human approval, reproducible artifacts, and explicit limitations. | 33.3% baseline versus 100% FormulaWitness (+66.7 pp), 100% clean preservation, and H01 improved from 0% to 100%. | The main contribution is not formula generation alone; it is the reviewable chain from cited policy to counterexample, localization, minimal patch, approval, and independent replay. |
| Agent rebuild (unscored) | Replaced fixed role-labelled stages with an OpenAI-compatible model-controlled manager, generic tools, fresh-context falsifier, raw traces, budgets, and separate approval. | Scripted behavior tests prove falsifier feedback can force a second candidate. A live NIM GPT-OSS smoke produced a proposal after 17 manager turns, 10 falsifier turns, 27 tool calls, and six sandbox executions. | Kept. This establishes real agent mechanics, but no blind agent benchmark has been run; the earlier 33.3%/100% figures remain legacy deterministic results only. |
| Provider hardening (unscored) | Stress-tested live providers and fixed premature token/tool exhaustion, oversized parallel observations, empty terminal streams, lost citation handles after compaction, ignored mandatory tool choice, empty chat completions, and ignored serial-tool settings. | Offline transport/loop tests cover each failure class. OpenCode free-model runs reached up to 33 tool calls but none completed candidate staging and falsification; the traces ended in bounded `ABSTAIN` states. | Kept the provider-neutral fixes. A compatibility run is not a repeated benchmark, and the tested OpenCode free endpoints are not a production recommendation. |

## Removed experiment: benchmark-specific substitutions and gold-formula localization

The first baseline contained a fixed table of formula fragments such as `H6<=0.95` and
`J6>1`, while the first localizer discarded cells whose formulas already matched a compiler-built
reference. Those shortcuts made the benchmark easier by encoding knowledge of how its mutants
were constructed. They were removed rather than optimized.

After removal, the hardened baseline scored 33.3% on benchmark v2 while the advanced workflow
still scored 100%. The v1 and v2 figures are not directly comparable because the benchmark also
changed; the decisive evidence is structural: current repair processes cannot import evaluator
modules, hidden cases, mutation descriptions, or pristine formulas. This experiment taught us
that a high score is not credible if localization or the baseline can recognize the test generator.

## Challenging case: H01

H01 combines three defects that interact downstream: ordered tier lookup (`N6`), waiver scope
(`P6`), and cap order (`S6`). The direct baseline returned `NO_CHANGE`, passed only 9 of 48 sealed
vectors, and failed first at H10. FormulaWitness used 140 of its 160 allowed case executions,
changed exactly `N6`, `P6`, and `S6`, passed all 48 sealed vectors, preserved the source, and
changed no unrelated formula.

H01 revealed that a one-shot edit can appear locally reasonable while leaving interacting faults
hidden. The useful orchestration is sequential evidence-driven repair with complete replay after
each accepted candidate, bounded by a strict change and execution budget.

## Main failure mode and hot take

The main failure mode is ambiguous or conflicting policy language. FormulaWitness must abstain
until a qualified reviewer supplies an interpretation, because generating an expected result would
otherwise fabricate certainty. See [FAILURE_MODE.md](FAILURE_MODE.md).

**A spreadsheet returning a number is not evidence that it implements the policy.** The evidence
is the full witness chain: cited rule, discriminating input, observed divergence, dependency path,
minimal patch, accountable approval, and independent replay.
