# S3 real generation-control evidence: 2026-10-25

## Tested claim

Two self-authored synthetic development mods were executed in the actual game, serially, in separate fresh isolated rigs. This is real runtime control evidence, not fake logs or a real-mod feature-equivalence claim. Scope was authorized by the approved S3 cohort proposal's synthetic-control provision. None of the three held real-mod cases was launched or repaired.

The fixture extends the local API's BaseModPlugin and implements onNewGameAfterEconomyLoad. Its action emits one uniquely named s3-generation-callback event. The healthy implementation executes that action once; the planted implementation executes it twice. Both use the same specification and parsed scenario definition: exactly one matching OK event for bf_s3_generation_control, min_count=1/max_count=1. The distinctive control-1 event version identifies the development fixture; the actual BridgeForge probe separately emits manifest/milestone evidence. A duplicate action is the intentionally planted bug, not an expected deviation.

The callback signature was verified by javap against the selected private RC8 API before build. Own source was compiled with the existing javac helper's --release 17 flags, packaged as JAR-only runtime payloads, and bound alongside source/build provenance. The actual source, class files, jars and game payload remain private; no game/mod/save files are committed. Each case's original and working baseline initially matched; the two cases are a paired control experiment, not an existing-save upgrade lineage. Their shipped differences are control.jar and mod_info.json (version label); source/compiled-byte receipts retain the causal fixture delta.

## Actual observations

| Control | Run ID | Matching action events | Driver | S3 scenario result |
|---|---|---:|---|---|
| Healthy | S3-GEN-20261025-HEALTHY-A1 | 1 | LIVE_DONE | ASSERTIONS_OBSERVED |
| Planted duplicate action | S3-GEN-20261025-DUPLICATE-A1 | 2 | LIVE_DONE | REGRESSION_DETECTED |

Both independently re-evaluated R1 results are ACCEPTABLE with matching manifest echo and exact selected candidate/runtime closure. Main menu, campaign_checks, content_ids, combat and a new private save were observed. Campaign_load and reload_after_save were not observed. Each run completed one combat round. Both process exits were KILLED with unknown exit code: natural exit is not proven. Driver times: 225.332/223.698 seconds; these are diagnostic waits, not a throughput claim or human-review measurement.

Independent verification rechecked raw observation IDs/artifact hashes, current candidate/context identity before drift, named scenario assertions and R1 evaluation. Matching assertions do not establish original/reference equivalence, all generation behavior, whole-family support, real-mod feature preservation or saved-upgrade qualification. The bug's clean generic game sequence does not override the failing S3 assertion, and no archive/promotion was attempted.

## Isolation and preservation

Fresh before-inventories were compared byte-for-byte after each run and independently afterward: primary core 5532 files, primary saves 93 files, private reference core 5532 files and the reused probe source 8 files, all PASS. Primary and private core snapshots were evaluated separately. Fresh primary SHA256: 587ae1f0e1d8af9b06b80e7b114c5c1bbb84c440c586be8a76ddd1f7f1a9ecc6; primary saves cc35d53a32ab92145bca009a52b45f2516609028bc377c939c9963bd9ae2256f. Original/working payload and context integrity were also rechecked by current-candidate validation before intentional drift. Captured launcher resolution/fullscreen preferences were restored. Owned Java stopped after both runs; final process audit found no remaining Java/game process.

Both launchers bind absolute saves/mods/logs/screenshots paths to their own rigs and junction their core to the existing private reference, not the primary install. An old private-rig descriptor was enumerated at the menu; actual process arguments and new-save paths were checked. No saved-campaign load was observed, and new campaign saves went into the new owned rigs. Descriptor enumeration is not relabeled as campaign loading or upgrade proof. No primary/player save was loaded or migrated.

## Changed-rule negative control

After both games stopped and their observations were verified, the healthy fixture's exact scenario definition was copied to scenario-definition-before-drift.json, then one whitespace newline was appended only to its owned catalog copy. Parsed assertion semantics stay identical, but content identity changes. Healthy current candidate became STALE and observation reuse raised "Behavior planning requires current candidate and context inputs". Both historical observation files remained byte-identical; the unrelated duplicate case remained CURRENT and its failing assertion was not promoted. The healthy catalog is intentionally left changed. Historical healthy success is not current qualification of that changed context.

This proves conservative reopening on changed rule bytes for this exercised path. It does not prove general selective impact analysis, every provider interaction, copied-save lineage or all maintained-qualification obligations.

## Artifacts and resume

Ignored root: bridgeforge-state/s3-generation-controls-20261025-a1. paired-control-result.json is the terminal independent summary. scope.json/protected-before.json and BaseModPlugin-javap.txt bind scope/input/API evidence; each healthy/duplicate subdirectory retains source/compile receipts, original/working copies, bound plan, named catalog and its fresh rig. run-a1 contains prelaunch qualification, driver, observation, preservation, result and independent-r1-evaluation JSON. Rigs retain exact manifests/completions/logs/screenshots/exit records. Full primary inventories and private assets stay ignored.

Main BridgeForge scratch helpers: s3-generation-setup.py, s3-generation-run.py LABEL, s3-generation-verify.py. Their logs are this worktree's bridgeforge-state/s3-generation-setup.log, -healthy.log, -duplicate.log and -verify.log. Setup, both execution sessions and verifier are terminal exit 0. Do not rerun them blindly: roots/attempts/baselines already exist, and healthy rule drift is intentional. Choose fresh owned contexts/runs after any relevant source/rule/provider change; preserve prior artifacts.

Current production source is the already validated 9f0d55c2 tree. No product source changed in this evidence slice; its guarded 2717-test/12-skip, 83.1289257% coverage and package/consumer results remain the last full regression, not a newly rerun suite. Current documentation checks are recorded separately. No hosted CI, push, PR, merge, publication, save-upgrade or independent human operator trial occurred. S3 remains IN_PROGRESS: real cohort feature observations, reference/deviation handling, broader healthy/known-bug families, full maintained qualification and authorized upgrade lineage remain open, as do prior S1/S2 acceptance gates.
