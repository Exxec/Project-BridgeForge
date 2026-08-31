# Verified library migration-pack contract

Bridgeforge will not accept a MagicLib, LazyLib, or AshLib migration rule
without a non-empty `evidence` object containing every field below:

- `provenance`: a verified example and behavioral source reference;
- `before_fixture` and `after_fixture`: sanitized regression-fixture IDs;
- `compile_validation`: the explicit compile evidence or procedure;
- `idempotence`: proof that rerunning the rule makes no additional change;
- `conflict_review`: the conflict-detection result or review record; and
- `save_risk_assessment`: the save-compatibility assessment.

This is a load-time contract, not documentation-only guidance. It deliberately
does not establish that any particular API transformation is correct; a mapping
may be added only after the listed evidence is independently verified.
