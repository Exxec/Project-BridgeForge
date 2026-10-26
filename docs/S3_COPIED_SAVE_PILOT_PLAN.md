# S3 copied-save healthy-control pilot plan

Status 2026-10-25: approval for this exact synthetic pilot was requested in the active thread and is pending. No save load, copy-back, migration or live trial is recorded here. This plan is not authority to start the run.

## Exact immutable seed

The self-owned S3 generation healthy control produced `healthy/rig/saves/save_UraniaMoktar_980645493355580262/` under the preserved `s3-generation-controls-20261025-a1` private root in the older S-series worktree. Seed bytes checked on 2026-10-25: `campaign.xml` 9,576,255 bytes, SHA256 `abed81eebe2160461aeaac6be717b0f80a4bbc02f3efe257caae274ba186838b`; `descriptor.xml` 3,122 bytes, SHA256 `974d40dfde6561c9383fb0275b468b70af876fb5ae0a488f337214043bd14a36`. The seed, original worktree, primary game and primary saves remain read-only. Any working save lives only in a new isolated rig and is hash-checked against this seed before launch.

The subject is `bf_s3_generation_control`, a self-owned synthetic mod. It is a healthy no-migration control, not an approved real-mod save upgrade or a historical repair. Candidate version/identity differences must be exact and disclosed before a run; they cannot silently introduce gameplay, persistent-state, or feature changes. Both full candidate shipped sets need independent static, compile, API, dependency and named-run checks before considering live evidence.

## Evidence required before calling a stage observed

1. Fresh current-engine case/candidate and R1 manifests bind the copied rig, exact seed, staged mod, core/JDK and run IDs. Prepare `save_upgrade.plan_upgrade` for its `healthy-control` case with distinct input and result slots. A same-slot `cmdSave()` cannot meet the separate-slot requirement.
2. Before launch, rehash the seed and rig input copy. Record process ownership and exact loaded save slot from a game log or in-game probe. Menu enumeration alone is not a load.
3. Observe `load_old_with_new`, no-migration state/ownership/identity invariants, and a real save to a separately named rig slot. The existing `ExistingSaveReloadStage` uses `cmdSave()` on its current slot, so it does not by itself satisfy this stage. An observer must prove a separate copy/save operation and the actual resulting files; API signatures alone do not prove behavior.
4. Restart the game, load the result slot, repeat, and compare state and identity snapshots. Preserve logs, manifests, copied save hashes and natural/forced exit classification. Run `evaluate_upgrade` only on verified stage-specific evidence. A hand-authored JSON object with plausible fields is not proof of those stages.
5. Rehash seed and original worktree after the test; report every static, compile, API, package, save and live result separately. Failure or missing evidence stays FAIL/INCOMPLETE/LIVE_PENDING. The pilot cannot qualify S3's real-mod persistent case or all scenario families.

The current source has no complete in-game separate-slot evidence emitter or current S3 case adapter for the R6 pure evaluator. Implementing one requires direct evidence of RC8 save-copy behavior and review under the HIGH persistent-state routing rule in `docs/REVIVAL_WORKFLOW.md`; no undocumented call is assumed. The plan remains useful if approval arrives before that adapter is ready: build and review the observer first, then run only after its exact inputs and state effects are known.
