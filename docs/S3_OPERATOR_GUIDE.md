# S3 operator notes: implemented library surfaces

Owner-approved representative scope is S3_COHORT_PROPOSAL.md. Current evidence, exact input locations and gaps are in S3_PROGRESS.md. This is a guide to initial library surfaces, not a completed one-command qualification flow or support promise. No saved-campaign upgrade execution is implemented/authorized by these notes.

## Inventory and scenario binding

Use the existing S1 CaseStore and current candidate context, including explicit core, dependencies, running Python/JDK, rules and policy. plan_behavior_obligations(store, case_id, candidate_id) freshly inventories original/candidate static hypotheses and returns a content-bound plan. All features initially remain unknown, and original-only hypotheses remain visible. Review discovery completeness and proposed critical features; a plan does not decide behavior preservation.

A case-specific scenario may live in a private external catalog. Its JSON needs schema_version 1, exact name, supported family, nonempty behavior_ids from the plan, exact subject_mod/mods/extra_mods and nonempty scoped probe assertions with a positive observation. Save/setup/tracking/compat-set expansion still refuses in this adapter. Bind the actual file path under inputs["rules"]["scenario." + name] before capturing the next candidate with explicit predecessor, then regenerate its plan. Neither a filename nor a copied PASS report is authority.

## Observe a completed named run

Only run an eligible candidate after current full qualification has resolved every applicable non-live dimension and rig/runtime ownership/context is exact. Cohort selection does not waive the static/compile/source/dependency/review/rights gates. Keep isolated writable state and one game/UI owner; preserve existing saves, archives and prior runs.

The existing live_run library accepts scenario=NAME and forwards it to R1 launch preparation; its default stays "probe-group live". The manifest must have been prepared for that same scenario name, candidate and runtime. This forwarding is not a prelaunch eligibility adapter. Do not relabel an old generic run, edit a completed manifest or bypass preparation to make a name match. Full S3 operator preparation integration remains open.

For an already completed exact named run:

```python
from bridgeforge.behavior_obligations import plan_behavior_obligations
from bridgeforge.behavior_observations import observe_behavior_scenario

plan = plan_behavior_obligations(store, case_id, candidate_id)
observation = observe_behavior_scenario(
    store, case_id, candidate_id, plan,
    scenario=name, rig=rig, run_id=run_id,
    definition_directory=private_catalog,
)
```

Omit definition_directory only for the packaged catalog. The definition must be explicitly bound even there. Fresh case/plan, artifact identity, R1 echo/closure/milestones and scenario assertions are rechecked. ASSERTIONS_OBSERVED covers only those candidate assertions. It is not feature equivalence, reference-runtime evidence, deviation approval, family support or whole-case qualification. REGRESSION_DETECTED identifies failed assertions; REFUSED/INCOMPLETE preserves identity/evidence gaps. Keep residual human tests and unavailable reference evidence visible. New-game observations never prove existing-save load/migration/save/restart/reload/repeat semantics.
