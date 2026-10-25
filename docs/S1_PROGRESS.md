# S1 progress and resume instructions

Latest checkpoint: real v2 cases qualified/archived/retried on both layouts; owned post-qualification drift is refused. Historical v1 refusal is preserved; remaining pilot/owner gates are open. See S1_PILOT_EVIDENCE.md and the final resume instructions below. S1-S4 remain the active goal.

2026-10-24. Branch `feat/s1-workspace-contracts`, parent `docs/b6-closeout` (`8736e13a`), worktree `C:/Users/exxec/Documents/bf-wt/s1-workspace-contracts`. Main and the published B stack are preserved. Helpers/logs belong in BridgeForge, not SpriteForge.

## Implemented

S1.1 compatibility/policy map: existing entry points and their different acceptance/side-effect semantics are source-reviewed in S1_CONTRACT_MAP.md. The initial qualification profile is a design, not active policy.

S1.2 initial library boundary: frozen `bridgeforge.case_workspace.WorkspaceView` returned by `open_workspace_view(Path(...), original_relative=...)`. It opens manifest-v1 and convention/intake-v1 layouts, references rather than relocates originals, identifies optional capabilities, and refuses malformed/ambiguous/unsafe paths. Selected intake roots come from supported records; nested legacy originals require explicit selection. Readability does not certify hashes, source/jar authority or acceptance; provenance is UNVERIFIED.

16 synthetic acceptance/refusal tests cover the existing workspace and intake APIs, unchanged trees, optional capabilities, explicit source selection, unsupported schemas/JSON, mixed dialects, overlap, traversal/drives/UNC and real junction/symlink boundaries. No private mod/game/save fixture is committed. No existing CLI, caller behavior, policy, dependency or public import changes.

## Validation

Focused adapter/resource/compatibility checks: 20 tests PASS; Ruff PASS.

- Full guarded suite: **2635 tests, OK (12 unchanged skips), 265.442s**; hermeticity PASS.
- Branch coverage: **83.1451218%**, up from B6/B5's 83.1122629%; adapter 98.56% (102/103 statements, 35/36 branches).
- Existing CLI golden unchanged; generated docs, gates lint (zero contradictions), whitespace and Ruff PASS.
- Wheel adds only `bridgeforge/case_workspace.py`; every existing runtime and non-code payload byte matches the validated B3 save wheel. Installed-module smoke resolves from the isolated environment.
- Installed-wheel Project Salvor suite: **208 tests, 4 unchanged skips, PASS**.
- Source inventory now has 335 Python files; nested source audits still pass. Existing APIs/commands and safety baselines are unchanged.

Raw suite/coverage/build/consumer logs and `s1-result.json` remain ignored in this worktree's `bridgeforge-state/`. No live test or real pilot was performed.

## Resume next

1. Read S_SERIES_IMPLEMENTATION_PLAN.md and S1_CONTRACT_MAP.md. Inspect current Git state and this evidence before editing.
2. Continue S1.6: integrate the minimal public operator flow and guide over the validated case/qualification/operation libraries. Read S1_CASE_RECORDS.md first; persisted result labels must never replace fresh qualification before finalization.
3. Review exact supported operator entry points/profile before S1.4 enforcement; preserve legacy caller distinctions and missing/unknown evidence.
4. Add interruption/stale-input/refusal tests before mutation/finalization integration. Candidate freezing must revalidate payload paths and concurrent changes; this read-only view checks selected boundaries only.
5. Select real P1-P6 pilots, permissions and rig/reviewer capacity with the owner before operational acceptance. Save-changing cases retain higher-capability/person routing. New-game proof cannot become save-upgrade proof.

S1 is IN_PROGRESS. S1.3 records are IMPLEMENTED OFFLINE and validated (evidence below); S1.4 read-only qualification is IMPLEMENTED OFFLINE; S1.5 operation adapters are IMPLEMENTED OFFLINE; S1.6 operator commands/guide are IMPLEMENTED OFFLINE; real pilot/acceptance remain OPEN; S2-S4 are PLANNED. The B-series review/merge gates remain independent. This slice is local-only; no push, PR creation, main merge, archive or release is authorized by this checkpoint. LIVE TEST NOT PERFORMED.

## Try the library boundary

```python
from pathlib import Path
from bridgeforge.case_workspace import open_workspace_view

view = open_workspace_view(Path("path/to/workspace"))
# For a legacy nested original without an intake selection record:
# view = open_workspace_view(Path("path/to/workspace"), original_relative="ModName")
print(view.layout, view.original, view.working, view.unavailable, view.provenance)
```

This is a library slice; no `case` CLI command has been added or implied.


## Active S1-S4 goal (owner instruction, 2026-10-24)

"set goal for all S series, if need be run automated live test."

The active goal now covers implementation and validation of all S1-S4 in dependency order, not only S1. Automated live testing is authorized where required, using the dedicated isolated rig with its ownership, staged-input/run-manifest and existing policy checks. Inspect current rig/process ownership before staging; serialize GUI/live resources. Preserve originals, primary saves and prior archives. Ordinary implementation/verification may continue without per-slice confirmation; gameplay/save-content decisions, licence/publication, PR creation, main merges, second-operator evidence and owner support/acceptance commitments remain distinct gates. A synthetic/automated test does not impersonate an independent human operator.

Next: S1.3's content-bound candidate/receipt spine, followed by durable case records and qualification adapters. Reuse `copy_drift._collect`/`run_manifest.FILESET_ALGORITHM` for the shipped set only after validating physical payload boundaries. Retain scan-registry's broader analysis-input identity separately; generated reports must not invalidate shipped payload identity. Bind receipts to candidate AND explicit dependency/core/tool/rule/policy context; missing context/provenance cannot become acceptance. Keep decisions and evidence outside frozen payloads and test stale inputs, same-version drift, tampering, unsupported schemas, interruptions and retries before wiring mutations.

## S1.3 implementation checkpoint, 2026-10-24

Content-bound candidates and generic observation receipts plus atomic append-only `CaseStore` are implemented. [Contract and limits](S1_CASE_RECORDS.md) describe schema, exact payload/context binding, provenance and recovery. The shipped digest matches the existing run-manifest algorithm; broader analysis and generated-report exclusions retain their distinct semantics. Persisted input locations support revalidation without chat. No existing CLI, acceptance gate or mutation flow changed.

25 new identity/store tests pass; 47 focused identity/workspace/safety/compatibility/resource tests pass. Full guarded suite: **2660 tests, OK (12 unchanged skips), 268.643s**, hermeticity PASS. Branch coverage **83.1940548%** (previous slice 83.1451218%); case identity 85.75%, store 94.74%. Wheel adds only `case_identity.py` and `case_store.py`; all prior package bytes are identical. Installed-wheel import smoke and Salvor **208 tests/4 skips PASS**. Ruff, docs-index, gates lint and whitespace checks PASS. Raw evidence is ignored under `bridgeforge-state/s13-*`. No generic recorded receipt is qualified evidence yet. S1 remains IN_PROGRESS; next is S1.4's explicit profile and evidence adapters, not broad auto-acceptance.

### Next action: S1.4

Implement a shared, explicit obligation evaluator plus caller-specific evidence adapters. Start with a read-only local-new-game qualification view; do not mutate archive/release/accept callers until their compatibility obligations are proven. Required observations must include source authority/review, candidate/package, static, applicable compile, dependency/API, and bound applicable live scenarios. Missing/unsupported/legacy observations stay INCOMPLETE/UNKNOWN; recorded PASS labels alone never satisfy obligations. Re-evaluate candidate/context/artifact identity on every qualification, and retain separate per-dimension results. In particular, reuse `run_manifest.evaluate_run` plus the existing log/probe refusal checks; require the specific candidate/member and scenario scope, not an unrelated passing member or a clean startup log.


## S1.4 implementation checkpoint, 2026-10-24

Read-only `case_qualification.qualify_case` and isolated `case_evidence` scan/compile worker implement the local-new-game profile described in S1_CASE_RECORDS.md. No legacy command, archive/release policy or import changes. Exact candidate/context rechecks, explicit dependency closure, source/review authority, fresh static/API/compile observations, rights restrictions and exact bound R1 live evidence retain separate results. Generic receipts never become qualification; missing evidence stays INCOMPLETE. Matching manifest echo is required even where legacy evidence accepts older logs.

13 new tests pass, including actual fresh worker plus synthetic R1 integration, exact enabled closure mismatch, legacy echo refusal, post-test staged drift, concurrent working mutation, unsupported target schema, bound owner policy changes, missing declared jars and incomplete Janino/source coverage. Synthetic logs and dummy runtime fixtures are regression tests only, not real game observations.

Final full guarded suite: **2673 tests, OK (12 unchanged skips), 277.013s**; hermeticity PASS. Coverage **83.1173723%**, down 0.0766824 percentage points from S1.3, above the unchanged 80% ratchet. Qualification module 77.56%; isolated worker executes in a child process outside parent coverage collection (reported 0%, with real subprocess integration tests passing). No coverage threshold, safety baseline or test skips changed. Wheel adds only case_evidence.py/case_qualification.py; every existing runtime/payload byte matches S1.3. Installed-wheel Salvor **208 tests/4 skips PASS**. Ruff, docs-index, gates lint and whitespace PASS. Raw logs/coverage/wheel/consumer evidence: ignored `bridgeforge-state/s14-*`; initial intermediate suite also passed 2668/12 before the final additional tests. No live game, source mod/save mutation, archive, push, PR or main merge occurred.

### Resume S1.5 next

Inspect current branch/status and active goal, then design the minimal supported prepare/run/finalize library flow before public CLI integration. Reuse R1 rig ownership/manifests and R5 revise concepts where their convention-only paths and policy semantics match; do not silently wrap permissive archive primitives or change legacy release behavior. Keep operation records outside frozen payloads. Prepare fixes the bytes/version once; finalization must independently requalify, verify exact staged/archive bytes, preserve prior artifacts and handle interruption/retry/concurrency without duplicate writes. Synthetic success must not bypass owner review for real changes or create publication authority. Then implement the minimal operator flow and S1.6 real pilot positive/drift negative in an isolated rig instance. Dedicated rig discovered at `C:/Users/exxec/Documents/Project BridgeForge/In operation/_rig`; existing instances/configurations/saves are preserved, ownership must be checked before any staging. All S1-S4 work remains the active goal; S1 operational acceptance, S2-S4 and independent operator/support gates are still open.


## S1.5 implementation checkpoint, 2026-10-24

`case_operations.prepare_case`, `prepare_case_run` and `finalize_case` implement the supported local-new-game archive library flow. Exact API/schema/recovery semantics are in S1_CASE_RECORDS.md. Prepare freezes the existing chosen version and original/working inventories in a private convention-layout adapter for either input dialect. Run preparation binds an already staged isolated rig using R1 ownership/manifests and the same context predicate as qualification. Finalization independently requalifies on every attempt, uses existing archive gates without overrides, verifies the preserved original, exact mod tree and main ZIP entries, and publishes a new operation-specific directory once. Failed private attempts and prior archives remain intact. Matching journaled publication can reconcile a crash after the move; unknown collisions or changed artifacts refuse. No legacy command behavior, dependency or public import changes.

13 new operation tests pass, covering preparation idempotence/no version bump, both workspace forms, missing-live/stale-input/unsafe-path/schema/collision refusals, exact completed retries, prior archive/source preservation, private archive failure retention, crash after publication, run-manifest/receipt interruption, exclusive lock behavior, wrong staged bytes and unbound Java execution refusal. Existing 13 qualification tests remain green. These use synthetic mod/rig/log fixtures only; no real mod/game/save/archive is changed.

Final guarded suite: **2686 tests, OK (12 unchanged skips), 307.229s**, hermeticity PASS. Earlier intermediate suite: 2685/12 PASS before the additional Java preflight guard/test. Coverage **83.1075614%** (previous 83.1173723%; unchanged 80% threshold); operations 80.90%, qualification 78.00%. No baseline/threshold/skips weakened. Wheel adds only case_operations.py and changes only case_qualification.py for the shared context predicate extraction; every other existing runtime/payload byte is identical to S1.4. Installed-wheel Salvor **208 tests/4 skips PASS**. Ruff, generated docs, gates lint and whitespace PASS. Raw evidence is ignored under `bridgeforge-state/s15-*`. Local-only; no push, PR, merge or live game launch.

### Resume S1.6 next

Reinspect branch/status before editing. Add the smallest explicit `case` operator interface for opening/capturing, current status/qualification, preparation, run binding and local finalization; document JSON inputs, IDs, failure exits and the distinction between historical operation states and current qualification. CLI golden changes must add only this deliberately supported surface and the top-level listing; preserve all existing command names/options/semantics. Reuse the operation library rather than duplicating profile checks in handlers. Provide a resumable guide with no hidden chat/hardcoded paths and measure the P1-P6 operator baseline. Staging/execution currently use existing rig/probe commands; the run adapter does not launch or overwrite a rig. Before any real pilot, inspect ownership/processes, exact target/core/JDK/probe/launcher/provider context and pilot eligibility; use a fresh isolated rig instance and preserve existing configurations/saves. S1 needs a genuine applicable live positive plus drift negative and both-layout pilot evidence; synthetic fixture success does not close that gate. Owner review for real changes, save-upgrade, independent operator/support and publication gates stay separate. All S1-S4 remain the active goal, with S1 operational acceptance and S2-S4 still open.


## S1.6 operator checkpoint, 2026-10-24

Added the opt-in `case` namespace: open/capture/status/qualify/prepare/prepare-run/finalize, with JSON output and documented exit codes. [S1_OPERATOR_GUIDE.md](S1_OPERATOR_GUIDE.md) describes absolute context input records, IDs, scope, lineage, existing staging/launch commands, exact recovery and remaining evidence gates. `case status` revalidates candidate identities and lists historical operation IDs/checkpoints without implying current qualification. A failed/interrupted open reports its case ID for retry. Malformed/duplicate/relative/unsupported input records refuse. Existing commands are unchanged.

Integration review found and fixed the new run adapter's manifest mismatch with the real harness: it now uses `probe-group live`'s exact scenario/milestones (including content IDs) and requires staging state to select only this case candidate. The operator guide gives the concrete existing unattended launch command. A regression test calls the actual shared launch manifest preparation and proves it reuses the same ID; no game is launched in that test. CLI golden review verified exactly eight new namespace/help nodes and only the top-level command-list change; every existing command/option golden is identical. Generated COMMANDS.md is updated.

5 new CLI acceptance tests pass, including command dispatch, actual shared qualification/archive flow and exact retry, stale current identity, historical checkpoint semantics, malformed inputs before writes, paired rig/run arguments and real-harness manifest compatibility. Focused CLI/operation/golden run: 19 tests PASS; final CLI/golden/index run: 12 PASS. Full guarded suite: **2691 tests, OK (12 unchanged skips), 312.538s**, hermeticity PASS. Coverage **83.0915637%** (previous 83.1075614%; unchanged 80% threshold); cmd_case 78.06%, operations 80.72%. No baselines/thresholds/skips weakened. Wheel adds only cmd_case.py and changes only case_operations.py/cli_commands.py for operator/harness integration; every other prior runtime/payload byte is identical. Installed-wheel Salvor **208 tests/4 skips PASS**. Ruff, generated docs, gates lint and whitespace PASS. Raw evidence: ignored `bridgeforge-state/s16-*`. Local-only; no push, PR or merge.

### Resume next: S1.6 real pilot and measurements

S1 remains IN_PROGRESS; S1.6 is not operationally accepted. At the operator checkpoint no real live game test had been performed; the later pilot record below supersedes that status. Complete the real P1-P6 pilot matrix, both layouts, applicable live positive/drift negative and measured operator effort/independent handoff before claiming that outcome. The operator/library implementation is validated, not a substitute for that matrix. Then advance S2-S4 in dependency order while retaining their owner/save/support gates.

Read-only preflight found the dedicated rig at `C:/Users/exxec/Documents/Project BridgeForge/In operation/_rig`, with existing j25-direct/j25-fr/j28-direct/j28-fr instances. At that observation no Java/game process or run_owner.json was present; recheck live state before staging. All core junctions resolve to the primary installation's core, so do not treat a core junction alone as proof of complete runtime isolation. Preserve existing instances and primary files/saves; use a new unique instance, explicitly route save/mod/log/screenshot paths to its owned directories, and prefer a copied private core/reference if necessary to protect original installation files. Do not use make_instance_rig with an existing ID: it removes/rebuilds that instance; use a verified fresh ID only, or create a fresh owned setup directly. Avoid linking mutable test payloads to original sources.

A candidate P1 input is the existing data-only `In operation/Faction-Relationships-Uniquified/working`: current metadata RC8, no declared dependencies/JAR/modPlugin/Java, explicit local-only release-policy entry. It is already revived, so using an immutable copy as a baseline must be labeled as such; it is not new proof for the historical original-to-revival repairs. Inspect actual contents/current scan before selecting it. Real P2 repair/review continuity, P3 source-authority refusal, P4 provider refusal, P5 save/persistence routing and P6 post-qualification mutation still need their concrete evidence. Do not generate an owner approval or independent operator result merely to close a gate. Keep pilot payloads/logs/private sources under ignored BridgeForge state, never SpriteForge, and record exact context/commands/timing/results with evidence limits.


## Real pilot and prerequisite fixes checkpoint, 2026-10-24

[S1_PILOT_EVIDENCE.md](S1_PILOT_EVIDENCE.md) is authoritative for A1/B2/C1 observations, preservation, timings, packaging contamination/correction and current limitations. After the real-derived fresh-menu driver fix, C1 reached menu/campaign/combat with zero fatal/mod/probe/caught-exception failures and no staged drift. Natural exit is NOT_PROVEN (KILLED). Current profile v1 correctly remains REFUSED under its recorded requirements: campaign_load was absent in the new-game run. No local archive/finalization or case acceptance occurred. Primary core (5532 files), saves (93), and source mod (3) are byte-identical after the run.

The real build also exposed ignored namespace contamination missed by earlier subtree-only wheel checks. Explicit package discovery and an actual backend regression now exclude ignored state/lookalikes. Corrected complete wheel allowlist: PASS, 373 entries, 1.47 MB, zero foreign entries; all intended prior package bytes preserved except live/live_run.py. Old local S-series wheels are superseded and must not be distributed. Existing generated build caches were quarantined, not deleted. CI/development explicitly install the already-declared setuptools backend for the test; runtime dependencies and uv.lock are unchanged (offline lock check PASS).

Final combined guarded suite: **2694 tests, OK (12 unchanged skips), 340.419s**, hermeticity PASS; coverage **83.0928266%**, unchanged 80% floor. 44 focused driver/triage/fallback checks and real-backend packaging test PASS. Installed corrected-wheel Salvor **208 tests/4 skips PASS**. Ruff/generated docs/gates/whitespace/CLI goldens PASS. Local changes only; no S-series push, PR, merge or publication by this work.

### Resume: correct new-game qualification, then finish S1 pilot

Inspect Git status, the pilot evidence and private receipts before acting. Version the new-game campaign obligation explicitly; preserve old saved-load/reload semantics and v1 results. Require completed campaign probe observations with healthy/missing/failed controls rather than silently relabeling new-game as saved-campaign loading. Review the legacy new-game harness's expected-milestone list (it currently also asks for campaign_load), shared case profile, run preparation and evaluator/tests together. Prepare fresh evaluator-bound operations/run IDs after changes; never edit old manifests/qualification labels. The private staged rig-b2 and core/reference remain under bridgeforge-state/s1-pilot-20261024-a1; C1's ids/records are pilot-ids-c1.json, pilot-evaluation-c1.json and qualification-c1.json. Recheck ownership/processes and input identities before reuse. All helpers/logs remain in BridgeForge, never SpriteForge. Use existing probe install_release to include the local vanilla mission icon; copying tracked probe files alone is incomplete.

Then perform a true qualified positive and local finalization/retry, a changed-after-qualified negative, both workspace layouts and P2-P5 evidence as applicable; independent resume/owner acceptance remain open. Complete feasible S2-S4 work in dependency order without treating this driver success as S1 acceptance. Keep whole-wheel allowlisting in package verification; old build/lib caches can retain foreign packages even after configuration changes, so use verified fresh build outputs/quarantine and refuse contaminated artifacts.


## V2 qualified two-layout checkpoint, 2026-10-24

Versioned campaign_checks observations fix the actual new-game/saved-load mismatch without reclassifying old v1 evidence. See the D1/E1 section of S1_PILOT_EVIDENCE.md. D1 convention and E1 custom manifest layouts independently ran, qualified, archived and retried exactly. D1's owned-copy payload mutation then refused qualification/finalization while its archive stayed byte-identical. Primary core (5532 files), saves (93) and source mod (3) remain unchanged after both. Natural exit remains NOT_PROVEN (KILLED). Unique mod denominator is one, not two.

58 focused checks PASS; final guarded suite **2698 tests, OK (12 unchanged skips), 328.714s**, hermeticity PASS; coverage **83.0964043%**, unchanged 80% floor. Whole-wheel namespace audit and installed Salvor **208 tests/4 skips PASS**. New profile/milestone and default new-game driver expectations are source-tested together; only run-manifest prepare's additive milestone choice changes help goldens. No runtime dependency, baseline or skip weakening. Local-only; no push/PR/merge/publication.

### Resume remaining S1 pilot, then S2-S4

Current private evidence root is bridgeforge-state/s1-pilot-20261024-a1. D1 ids/result describe the convention positive and P6 negative; that working copy deliberately retains S1_DRIFT_CONTROL.txt and is stale. Do not reuse its historical COMPLETE label as current qualification. E1 ids/result/setup use workspace-manifest with reference/edit and rig-e1; its current case c has independent qualified/archive evidence. Both rigs use the private core and explicit owned paths; recheck processes/ownership/identities before any reuse. Do not edit old receipts/manifests or clean negative controls silently.

Finish P2's actual reviewed narrow loose-source repair/compile continuity; P3 source/jar authority refusal; P4 provider refusal; P5 higher-capability/person save routing; measured independent resume and owner acceptance. The actual automation policy at Project BridgeForge/In operation/AUTOMATION_POLICY.json contains dated approved_fixers (including target-interface-method-missing), so inspect existing standing authority rather than inventing approval or asking twice. MANUAL/UNKNOWN and unapproved semantic/save/balance changes still require a person; no agent auto-accept policy is enabled. Represent any derived mechanical authority honestly and verify its exact scope; do not write a new owner approval merely to close a gate.

S2's strategy explicitly requires an agreed training/holdout cohort before implementation/tuning and human approval of cohort scope. Prepare a concrete read-only cohort proposal and frozen denominators/authority boundaries for review, preserving holdouts and abstentions. Then continue the full S1-S4 objective in dependency order; these successful data-only layouts do not close remaining pilot, save, independent-operator, support or publication gates.


## Real-input pilot continuation, 2026-10-25

Branch remains feat/s1-workspace-contracts; product implementation remains the validated f6f1dabc tree. See S1_PILOT_EVIDENCE.md for newly completed real P3 mixed-authority refusal, P4 unresolved-provider observation and P5 unsupported-existing-save-scope routing. P2 Leon Heavy Industries received only the four proposed interface-parameter additions in its private working copy under the existing dated standing fixer approval. Exact delta, unchanged originals, byte-identical backups and idempotence are recorded. Targeted findings disappeared, but full javac remains FAIL (39 errors before, 31 after); Janino covers only six accepted sources. Whole case remains REFUSED, with candidate-bound review INCOMPLETE. No new live launch or archive occurred in this continuation.

No product code, baseline or test was changed by these pilot runs. The last full guarded regression remains 2698 tests/12 unchanged skips, coverage 83.0964043%, with wheel/consumer checks recorded above. Do not describe that earlier run as a new regression run. Current documentation checks are recorded in the commit receipt.

### Resume from this checkpoint

1. Inspect branch/status and active goal. Private pilot root is bridgeforge-state/s1-pilot-20261024-a1; repair-continuity-result.json under p2-investigation-leon is the terminal P2 result. Do not reapply that repair or reuse a pre-repair candidate. P2 has no live or archive authority; missing libraries/other findings require their own evidence and decisions.
2. Preserve D1's intentionally stale working copy and historical archive; E1 is the independent manifest-layout positive for the same one mod. P3/P4/P5 records show refusal/routing only. No saved-upgrade behavior has been tested.
3. S1 operational acceptance still needs independent maintainer resume/owner acceptance and an adequate reviewed loose-script compile pilot. A passing subset of Janino sources cannot close full compilation. A dated fixer ruling is not a fabricated per-case owner-review record.
4. S2_COHORT_PROPOSAL.md freezes a proposed 8-training/4-holdout cohort and limits. Two owner questions were submitted: approve/change that named read-only cohort, and authorize measurement-first with defaults unchanged or provide the worthwhile improvement threshold. Neither preselection nor elapsed time supplies approval. Do not start dependent S2 implementation/tuning until the response; continue unaffected S1 work. All S1-S4 remain the active goal, not completed.


### Follow-up provider and guide check, 2026-10-25

P2 explicit-provider diagnostic completed terminally: LazyLib search-root selection alone leaves the 39/31 original/repaired compile errors unchanged because it does not amend declared closure. Inputs/provider inventories match before/after; no metadata, classpath override or acceptance change. See the private provider-compile-observation.json and pilot evidence. Corrected an obsolete saved-load sentence in the operator guide to the actual v2 menu/campaign_checks/content_ids/combat contract; historical v1 remains unchanged. S2 cohort/threshold and independent owner/maintainer gates remain pending. Do not repeat this diagnostic expecting a different declared closure.
