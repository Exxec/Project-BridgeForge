# Exact named behavior comparison

`case-behavior-compare` re-evaluates candidate and optional reference runs through the existing
S3 obligation/observation and R1 interfaces. Input is a schema-1 selection with `candidate` and
`reference` (or null). Each selector contains absolute `store` and `rig` paths, `case_id`,
`candidate_id`, `scenario`, `run_id` and optional absolute `definition_directory`. A stored PASS
object is not a selector. Both cases, scenario bindings, current inputs and observed artifacts
are checked afresh, with another source/artifact/engine check before the report is returned.

The comparison is restricted to the same mod identity, behavior IDs, scenario family and ordered
probe check/status/subject predicates. Its vectors retain expected bounds and actual matched
counts. Changed predicates need an explicit comparison design; similar text is not authority.
Missing reference remains `REFERENCE_UNAVAILABLE`. A failing candidate assertion remains
`REGRESSION_DETECTED`. `ASSERTION_VECTOR_MATCH` means only these vectors matched, not that the
whole feature, old game behavior or every scenario family is preserved. All reports retain
`qualification: NOT_EVALUATED`, unknown feature preservation and explicit save/family limits.

Two passing but different vectors yield `OBSERVED_DIFFERENCE` and an exact `subject_id`. An owner
may review that concrete difference and supply `--deviation FILE`, using schema_version 1,
scope `probe-assertion-vector/v1`, that subject ID, actor OWNER, decision
`APPROVE_EXACT_SCENARIO_DEVIATION`, and nonempty reason/owner_words. REVOKE reopens the difference.
The file is hashed and rechecked. It does not become a standing ruling or permission to edit
code/gameplay/save state. An approval cannot waive a failed candidate assertion, missing
reference or identity mismatch; those require resolving the underlying gate and fresh evidence.

The initial implementation is a comparison/reporting surface. Critical feature selection,
broader family controls, actual real-mod coverage, copied-save qualification and whole-case
acceptance remain separate. Historical named logs can be freshly re-evaluated against exact
current inputs; that must be reported as re-evaluation, not a new live execution. Source plans
and observations keep their original identities and dates.

Fresh production comparison of the preserved real generation controls passes: healthy count 1,
duplicate count 2, `REGRESSION_DETECTED` retained. New writable case records bind current rule
bytes; the old stale healthy case/plan and historical worktree were not changed. Both actual
named R1 observations were re-evaluated through current contracts. No new live execution,
feature-equivalence claim, save upgrade or whole-family qualification occurred. Private evidence:
`bridgeforge-state/s3-comparison-20261025-a1/selection.json`, `comparison.json`, `result.json` and
`recheck.log`. Focused tests separately cover matching/different vectors, exact owner decisions,
revocation, incomparable predicates, drift and missing/failed references using synthetic fixtures.
