# S1.3 case, candidate and receipt contracts

2026-10-24. Implementation: `case_identity.py` (content/byte binding) and `case_store.py` (durable, append-only local records). This continues S1 on `feat/s1-workspace-contracts`; it does not activate a qualification profile or modify existing commands.

## Persisted records

Every record has a strict `bridgeforge.<kind>` schema/version-1 envelope, canonical JSON content and SHA-256 record ID. Case IDs are independent UUIDs and remain stable across candidates; the immutable case metadata records selected workspace paths, target profile and declared scope. Scope is always `DECLARED_NOT_APPROVED`, not permission to apply, archive or publish.

A candidate binds:

- Case ID, declared target profile and optional predecessor candidate.
- Original selected tree identity under `all-regular/1`.
- Exact shipped relative-path/file-SHA map and `copy_drift.collect+sha256/1` payload digest, matching the existing run-manifest/live-trust algorithm.
- A separate broader analysis digest using scan-registry exclusion version 1. Generated root reports do not change the candidate; an unshipped source edit still does.
- Explicit core, dependencies, tools, rules, policy, launcher and source-authority context groups. Each selected file/tree has a physical source location and byte digest; omitted groups stay visible in `missing_roles`. An explicit empty dependency group is a declaration of no selected providers, not a dependency-resolution proof.

Context locations are persisted for artifact-only resume and are part of context identity. Relocation/rebinding can therefore create a new candidate rather than silently making old environment evidence current. Context provenance is `BYTE_BOUND_NOT_QUALIFIED`: file readability and hashes do not prove semantic authority, closure, licensing or correct tool use.

Capture performs two complete observations and refuses changed file sets/content/context; per-file stat comparisons detect mutation during a read. It is a local pre/post integrity check, not a filesystem transaction or tamper-proof attestation. Revalidate immediately before qualification/finalization. Physical traversal refuses links/junctions, special files and case-colliding paths before the legacy collector is used. The initial supported cohort requires physical input trees, including otherwise excluded metadata paths; unsupported linked trees refuse rather than being silently truncated.

Receipts bind the case, exact candidate and context, observation kind, outcome, reason, explicit tool identity, timezone-aware timestamp/run ID and evidence file digests. PASS needs an artifact; NOT_APPLICABLE needs a reason. Schema/content forgeries, subject/context replay and unavailable/changed evidence refuse or remain UNKNOWN/INCOMPLETE/STALE. A current generic receipt remains `RECORDED_NOT_VERIFIED`; a supplied PASS label is not approval. S1.4 must use independently verified caller-specific evidence adapters and a complete obligation profile.

## Storage, recovery and concurrency

`CaseStore` lives outside the workspace/frozen inputs. Create with an optional caller-known case ID for idempotent retry, then `add_candidate`, `add_receipt` and load records by their IDs. State directories cannot be context trees; individual immutable state artifacts may be referenced. `assess_candidate` reloads the workspace and stored context paths to detect drift without chat-supplied paths.

One exclusively created, token-owned store lock serializes writes; immutable readers remain available. Atomic safeio publication prevents partial records from becoming accepted state. Identical retries return the same record; different content is never written over an existing immutable path. Interrupted/malformed records are preserved and refused. Failed pre-publication writes leave no accepted case and can retry. Abandoned/changed-owner locks are not automatically stolen/deleted: explicit recovery belongs to S1.5. No mutable latest-candidate index is authoritative and no timestamp chooses an accepted candidate.

Digests detect accidental changes, not a malicious author capable of rewriting records and recomputing hashes. Persisted records confer no trust/signature, owner approval, live provenance or mutation authority. Existing run-manifest, archive/acceptance and policy gates remain independent.

## Validation and next work

25 new identity/store tests cover existing shipped-hash equality, same-version and context drift, generated reports versus source changes, original/target binding, missing context, directory inputs, junctions, concurrent mutation, strict schemas, replay, evidence tampering, retry, lock conflicts, partial/foreign records, persisted-input resume and scope/provenance forgeries. Full suite: 2,660 tests, 12 unchanged skips, hermeticity PASS; branch coverage 83.1940548%. Wheel/installed consumer checks pass; detailed receipts and raw-log locations are in S1_PROGRESS.md.

Next is S1.4: profile/obligation evaluation and evidence adapters. Do not let generic receipt labels satisfy live/compile/owner obligations. No live test was needed for this pure identity/storage slice. LIVE TEST NOT PERFORMED.


## S1.4 read-only qualification boundary

`case_qualification.qualify_case(store, case_id, candidate_id, run_compile=False, live=None)` evaluates the declared `rc8-local-new-game/v1` or `/v2` profile. Its exact target dictionary is exported as `TARGET`; declared scope is `local-new-game`. The opt-in case commands and S1.5 operations use this evaluator; legacy archive/release gates retain their own contracts.

Required dimensions are candidate, context, target, review, source authority, dependencies, static, API, compile, rights and live. Any FAIL yields REFUSED; any INCOMPLETE yields INCOMPLETE; otherwise QUALIFIED_FOR_DECLARED_SCOPE. Existing-save upgrades stay outside the profile. The result is evidence evaluation, never release/publication approval or a signature. Generic stored receipts cannot satisfy these dimensions.

Context bindings: `core.starsector` is the physical core tree; `tools.python` is the running interpreter file; Java-bearing analysis requires `tools.jdk` to match the configured JDK tree. `policy.target` is an explicit local JSON reference with integer schema_version 1, target `0.98a-RC8`, and core_sha256 matching the selected tree. This reference is a declaration, not independent game-version observation. `policy.release` uses the existing release policy format and requires an explicit mod entry with boolean local_only and a reason; no default inference. Dependencies are an explicit exact metadata-ID transitive closure, with cycles, extras and unresolved version constraints left incomplete.

No edits require owner review when original and working analysis inputs are identical. Changed inputs require `source_authority.review`, an explicit local owner policy file with schema `bridgeforge.owner-review`, integer schema_version 1, actor `owner`, decision `APPROVE_FOR_DECLARED_NEW_GAME`, scope matching PROFILE_ID, subject_id from `review_subject(candidate)`, and a reason. Review subject excludes only the source-authority group to avoid a circular approval hash. Jar plus Java source also requires runtime_authority `packaged-bytes`. This is an operator-selected local policy decision, not authenticated human identity; imported/untrusted decisions must not automatically gain authority. Missing declared jars refuse rather than falling back to other jars. The evaluator never writes an owner approval for a real mod.

Static/API and optional full loose-source compilation run fresh in a separate Python process with a private temporary helper cache and bound Java PATH. No game/mod code runs in that worker. Compilation requires both javac and RC8 Janino PASS and exact active-source coverage; a legacy top-level PASS with unavailable Janino remains INCOMPLETE. Parent process environment is unchanged. Candidate/context and evaluator code/payload hashes are checked again after evaluation. No persistent analysis cache or generic PASS shortcut is used.

Live reference is `(rig_path, run_id)`. It requires the specific candidate target, current R1 manifest/completion/log, matching manifest echo, all main-menu/campaign-load/combat milestones, no fatal/mod/probe/caught-exception failures, exact enabled candidate/dependency/probe bytes, bound core/runtime JDK, and matching launcher/VM/probe configuration. Optional `tools.probe` binds the probe mod tree; `launcher.game` binds the launcher file, all recorded VM-parameter files must also be bound file inputs in that group, and `launcher.probe_config` binds a recorded probe config. Legacy logs without an echo cannot qualify this profile even though the legacy evaluator retains its compatibility semantics. Hash checks are local integrity checks, not adversarial attestation. Log milestones do not establish feature coverage, save migration or independent operator acceptance.

Synthetic fixture runs exercise these adapters without launching a game. They are regression tests, never empirical live evidence. No finalization, version bump, archive refresh, release, public command, or game/save mutation is introduced by this slice.


## S1.5 local operation library

`case_operations.prepare_case(store, case_id, candidate_id, archive_root=...)` freezes an already selected final version without modifying or bumping the original/working mod. R5 `revise prepare` or an explicitly reviewed upstream build may choose a version before candidate capture; there is no finalization-time bump. Operation identity binds case, candidate, destination, current evaluator and local-new-game archive scope. Destination must be physically outside case state, workspace and all selected context inputs. A private normalized convention workspace copies the exact original and working inventories, allowing either input layout to use existing archive checks. Source, prepared copy and candidate identities are rechecked; links and unsupported records refuse. Partial preparation attempts are retained and retried in fresh directories.

`prepare_case_run(..., rig=..., run_id=..., run_compile=False)` requires an already staged isolated rig and complete non-live obligations. It reuses the same runtime-context predicate as qualification and R1 preparation/ownership/manifests, records a bound RUN_PREPARED receipt outside the payload, and supports interruption between manifest creation and receipt writing. It neither stages/overwrites mods nor launches the game. Existing rig/probe commands supply staging and execution; the operator integration remains S1.6 work. Wrong enabled/provider/launcher/core bytes refuse before a manifest is created. Launcher Java selection is checked against the bound external JDK before runtime observation may execute java -version. A different owner refuses; an unreadable owner record is not considered idle.

`finalize_case(..., live=(rig, run_id), run_compile=False)` independently qualifies current inputs every time, including retries. Unsupported or missing evidence returns REFUSED with the qualification details and no public archive. It calls existing `archive_mod` against private normalized inputs, preserving orphan/junk/content-loss/licence checks and keeping changelog/master-log side effects inside an attempt. No permissive archive override is supplied. Private attempts live under the selected archive root so final directory publication stays on the same filesystem. Prior archives and failed attempts are never refreshed, renamed or deleted.

Journal progression is PREPARED -> PACKAGED -> COMPLETE, atomically written in the case store. PACKAGED records exact full archive inventory and qualification identity before publication to `<archive_root>/<operation_id>`. The mod tree, preserved original and every main ZIP entry are verified against the candidate; ZIP sizes/streams are bounded by the actual tested files. Run artifacts, candidate/context and evaluator are rechecked before publication. Qualification/run/artifact changes after packaging cannot silently reuse an old bundle. Unknown destination collisions and damaged/missing completed output refuse; only a matching journaled move can reconcile an interruption after publication. Exclusive case-store writes serialize cooperating operations; local hashes/locks are integrity controls, not malicious-author authentication or a general filesystem transaction. An OS/process interruption can leave a PREPARED partial attempt or a PACKAGED move to reconcile. Preserve such files and retry the same API; never delete locks or partial outputs automatically. A stale evaluator/subject requires a newly prepared operation/candidate, not manual status edits.

The archive includes CASE_QUALIFICATION.json as separate evidence; tested mod bytes/version remain unchanged. This is local archive scope only, with existing licence/local-only restrictions in the archive note; publication and existing-save upgrades remain outside this API. S1 operational acceptance and the real pilot matrix are still open. No public CLI or legacy command policy is changed by this library slice.


## Versioned new-game obligation, v2 (2026-10-24)

New cases default to `rc8-local-new-game/v2` (`TARGET`). Historical `LEGACY_TARGET` v1 remains readable/evaluable with its original required menu/campaign_load/combat obligations; completed campaign checks never substitute for v1 saved-load evidence. No stored manifest or receipt is relabeled or migrated automatically.

V2 requires main_menu, campaign_checks, content_ids and combat. `campaign_checks` observes ordered probe INFO campaign START then END events; an isolated/reversed event, preload reference or FAIL event cannot substitute. It records completed campaign checks, not feature equivalence or save loading. Whole-log fatal/mod/probe/caught-exception refusals and exact subject/context/artifact checks still apply. Existing campaign_load, save and reload_after_save milestones retain their meanings. Saved-game upgrade support is still outside this profile.

The unattended driver actually creates a new game, so its default expected campaign milestone is now campaign_checks. Explicit run-manifest saved-load requirements are unchanged. Case run preparation follows that exact shared driver contract. V2 captures a new target/profile identity and operation; use a fresh case identity after upgrading from v1 rather than editing immutable records or retrying an old open with a different target. Existing v1 decisions remain scoped to their old subject/profile. Matching v2 owner authority is required where edits need review.

Implementation controls and independent real v2 runs for both workspace layouts pass, including local archival/retry and a post-qualification drift refusal. C1's historical v1 refusal remains intact. No operational acceptance is inferred merely from the new profile definition.
