# Main failure mode

FormulaWitness is only as sound as the approved interpretation of the written policy.

The synthetic benchmark is deliberately unambiguous. Real policies often omit units, disagree across amendments, use undefined terms, or leave boundary/precedence behavior implicit. Generating a deterministic expected result in those cases would turn uncertainty into a fabricated oracle.

Required production behavior:

1. mark the rule `AMBIGUOUS` or `CONFLICT`;
2. preserve all competing source spans;
3. generate a review question and distinguishing examples;
4. block executable tests and repair for that rule;
5. resume only after a reviewer selects and signs an interpretation.

The MVP exposes the status field and fail-closed architecture but ships only an exact synthetic policy. General ambiguity extraction is the next major validation target.
