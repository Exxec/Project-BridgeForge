# Implementation handoff: trust before unattended mutation

ROADMAP item 75. Planned 2026-10-17; no R1-R8 implementation is claimed here.
Owner: "ok add/modify roadmap with these recommendations and if possible a plan on how to implement for other agent."
This authorizes roadmap/specification changes. It does not approve publishing, archiving untested revisions,
changing gameplay, editing real saves or widening the existing unattended-action policy.

Read `AGENTS.md`, `CLAUDE.md`, `docs/AUTOMATION_PLAN.md` and `docs/LOCAL_HANDOFF.md` section 0 first.
This handoff refines items 70 and 73 rather than creating replacement tools. Current code wins on existing API names;
the requirements below govern the new behavior. Inspect dirty files and preserve unrelated changes. New names here
are proposed, not commands the next agent can assume already exist.

## Current evidence and boundaries

The 2026-10-17 review found these concrete starting points:

- `live_accept.accept_run` calls `live_trust.write_run_record`, which hashes working files at acceptance time.
  A log plus the current hash alone does not prove that the run used those bytes. Extend all acceptance paths.
- `finding_stats._latest_scan` searches `reports/scan-*/bridgeforge.compat.json`. The EPTA follow-up scan was stored
  under `reports/owner-followup-scan-20261017/`; folder-name discovery misses it.
- Item 73 E2 is still a specification. Existing verifier/review functions provide scan/diff evidence, not a general
  proof of behavior. Missing checks must not become successful unattended acceptance.
- Item 73 H2's original bump-then-archive operation could require a live run for a version it had just created.
- Source audit 2026-10-18: DOC-001 in `BUGS.md` establishes that archive `refresh=True` deletes the prior artifact;
  it does not preserve it as policy requires. R5/S1 must correct preservation before relying on this path. Documentation
  and helper existence do not satisfy that acceptance criterion; do not refresh known-good archives meanwhile.
- Zorg bf.10 has a local executable 119-assertion migration harness and a package-entry audit. It has no observed
  campaign load/save/reload for these bytes. EPTA's data audit/full scan also do not establish visual acceptance.

Do not promote PREDICTED behavior into `docs/RC8_BEHAVIOUR.md`. A dated observed fact needs its run evidence.
Never commit mod/game files or saves; use synthetic fixtures. Local original-derived reproductions stay local.
Existing-save, lifecycle and architecture changes follow the model routing in `docs/REVIVAL_WORKFLOW.md`.

## R1. Bind every accepted run to staged inputs

Extends item 70 H1.6/H3.2 and item 73 G3/G5. Highest priority before trusting new unattended acceptance.

**Files:** `bridgeforge/live_trust.py`, `live_accept.py`, `probe_group.py`, `live_run.py`, `boot_test.py`,
`java_matrix.py`, `cmd_probe_group.py`, `tools/bf-test.ps1`; inspect their actual launch/record paths first.
Reuse `shipped_files`/`shipped_hash` and the existing `_live` records. Add a small shared manifest module if needed.

**Implementation slices:**

1. Define a versioned pre-launch manifest containing run id, rig identity, test kind, target/scenario, exact staged
   enabled-mod IDs/versions/file hashes (including transitive dependencies), corresponding candidate hashes, core
   baseline identity, Java executable/build, launcher/options/agents, probe/config hashes and expected milestones.
   Hash runtime configuration separately from shipped files. Pin the file-set algorithm version. Record the manifest
   atomically before launch; unreadable files or duplicate enabled IDs fail preparation.
2. Compute hashes from staged rig files, not only source working copies. Prevent BridgeForge staging edits while a
   run owns the rig; validate hashes at completion and again at acceptance. A pre/post comparison detects drift but
   is not a claim of tamper-proof execution. Tie log paths/digests and start/end boundaries to the run id; a startup
   marker should echo the manifest identity using existing sandbox-permitted probe mechanisms.
3. Group and standalone acceptance consume the same evidence evaluator. Require matching run/candidate/environment
   identities and actual expected milestones. A smoke boot can pass its boot scenario but cannot satisfy campaign,
   combat or save-upgrade requirements. Preserve per-member verdicts; an unrelated member's success is insufficient.
4. Store the manifest digest and log evidence in the versioned run record; update `live_status`, archive gates and
   ledger readers compatibly. Legacy runs remain readable with provenance UNKNOWN; never manufacture a launch manifest
   retrospectively or treat a supplied note as missing identity evidence. Fail closed for new exact-build acceptance.

**Tests:** extend `test_live_trust.py`, `test_live_accept.py`, `test_probe_group.py`, `test_live_run.py` and relevant
launcher tests. Cover unrelated/old logs, wrong run id, target absent, dependency-only drift, probe/launcher drift,
same version with different bytes, mutation between launch/record, concurrent staging, incomplete milestones,
unreadable inputs and legacy records. Add a passing synthetic full match. Keep game launches out of unit tests.

**Acceptance:** negative fixtures cannot become CURRENT/LIVE_VALIDATED. On the isolated rig, stage a small candidate,
run its prescribed scenario, accept exact bytes, then show that an edit after testing is refused. Record the test ids.
Offline implementation without that live proof is IMPLEMENTED with LIVE PENDING, not fully accepted.

## R2. Register scans and compare content, not timestamps

Replaces item 73 A2's freshness definition. Depends on a stable fingerprint schema, not R1's live driver.

**Files:** `bridgeforge/finding_stats.py`, `cmd_scan.py`, `scanner.py` and the report writer reached from `cmd_scan`;
new `bridgeforge/scan_registry.py` if needed; `tests/test_finding_stats.py` and new registry tests.

**Behavior:** write a workspace-local index of successful scans with schema version, output artifact path/digest and
analysis-input fingerprint. Include actual source/data/jar inputs (the scanner set may differ from the shipped set),
selected dependency/core content, target, options, scanner code/rules and relevant external tool versions. Separate
accepted-baseline/policy filtering identity from raw scan identity so a changed waiver cannot silently reuse an old
filtered conclusion. Use relative workspace paths where possible; reject index paths escaping the workspace or
registered artifact root. Publish the index entry only after the report is complete.

Define exact exclusions for generated reports, backups and build debris. Exclusion changes bump the schema/rule version.
Do not exclude a runtime input just because its directory is conventionally generated. Avoid reading all core files
repeatedly: cache digests, but content verification remains required before claiming CURRENT.

States: CURRENT = complete report with matching inputs/context; STALE = known mismatch; UNKNOWN = missing fingerprints
or tool identity; INCOMPLETE = required input/report unreadable or scan interrupted. Timestamps are diagnostics only.
Discover new reports through registration regardless of output name. Keep legacy glob discovery as historical fallback,
then rescan for trust; do not use a new mtime to bless legacy contents. Checkpoint reuse must match the same fingerprint.

**Tests/acceptance:** edits retaining mtime, same-version jar changes, dependency/check/options changes, relocated output,
stale/tampered index, absent legacy hashes, report self-exclusion, interrupted publication and selective rescan. A local
smoke check must discover the EPTA follow-up artifact without renaming it; its legacy provenance may still be UNKNOWN.
Only then run authoritative A1 measurement in the background with progress/checkpoints. Report freshness buckets.

## R3. Make auto-acceptance an explicit validation policy

Refines item 73 E1/E2. Implement report-only eligibility first; do not enable E2 while its prerequisites are incomplete.

**Files:** `bridgeforge/escalation.py`, `escalation_review.py`, `revive.py`, their command modules, and corresponding
`tests/test_escalation*.py`/`test_revive.py`; new shared policy evaluator if the existing modules would grow too large.

**Behavior:** retain every original E2 gate and add explicit scope and applicability records. Reject unattended application
of MANUAL/UNKNOWN, save migrations, gameplay decisions, maintained third-party edits and unresolved high-risk lifecycle
work. Approval applies to a bounded kind of change, not arbitrary files merely present in `allowed_files`.

Each check records PASS, FAIL, INCOMPLETE or NOT_APPLICABLE, its reason, tool identity, input/output hashes and evidence.
Skipped compiler, missing dependency/core, timeout, parser failure and missing regression fixture are INCOMPLETE.
Data-only compilation can be NOT_APPLICABLE with a checked scope reason. For code, run applicable compiler and meaningful
regression checks against the final candidate, including packaged classes where jar shadowing applies. Compare before
and after under the same tool/environment; pre-existing failures need explicit bounded handling, not a blanket waiver.

Immediately before applying, recheck packet/attempt/working/policy hashes under a workspace lock. Prepare backups and
stage all changes before committing them; journal enough to recover or roll back multi-file failures. Fail closed on
concurrent edits, deletion races, out-of-scope changes, path escapes or evidence changes. Preserve the review sheet for
anything ineligible. Keep auto-applied status distinct from live acceptance and publication.

**Tests/acceptance:** each gate failing alone blocks auto-application; missing tools cannot pass; changed attempt after
verification and changed working files before application are refused; partial writes recover; policy/classification
boundaries cannot be bypassed by tier `none` or regex silence. Run a synthetic candidate batch with eligible/ineligible
changes and inspect its ledger. E2 activation depends on R1, R2 and R4, not on passing line-count checks alone.

## R4. Preserve semantic conditions in fixers and standing approvals

Refines item 73 B1/B4/B5/B6/C1/D3. No new approval of balance or save changes.

**Files:** `bridgeforge/escalation_queue.py`, `fixers.py`, `scan_campaign.py`, existing preset/shadowing checks;
the planned fixer/proposal modules in item 73. Reuse ruling storage, do not create a competing approval database.

**Behavior:** normalized question/diff shapes aid grouping only. A reusable ruling needs a versioned semantic predicate:
finding/check revision, target API/provider, relevant field/value constraints, operation, intent and risk exclusions.
Count independent prior mods, not repeated runs of one mod. Conflicting/revoked/expired or incomplete evidence prevents
standing application. Store source ruling ids and hashes; invalidation must propagate to derived approvals. Test unknown
predicate fields as refusal, not wildcard. Historical free-text rulings can be shown as precedent without automatic reuse.

For each proposed fixer, define supported shapes and refusal cases before adding it to the registry:

- Generation guards cannot skip unrelated initialization; ambiguous multi-system/multi-purpose methods are refused.
- Orbit expressions need proven finiteness and an evidenced lower bound. Test NaN, infinities, zero, negatives and side
  effects. A positive clamp alone is not a nonfinite-value repair; unknown formulas stay escalated.
- Preset field restoration and old-vanilla override removal require field-specific intent review and three-way evidence.
  Preserve unapproved overrides, including byte-identical copies of older vanilla.
- Weapon/wing/bay numbers remain proposals unless an exact evidenced source or owner-approved value exists. Drafts do
  not modify mod data; stale row approvals cannot apply. Same type/size alone is not sufficient balance evidence.

**Tests/acceptance:** superficially similar questions with different provider/value/intent do not share approval; three
independent matches can reuse a permitted ruling; conflicts/revocations stop reuse. Exercise every refusal above and
approved idempotent span edits. Sample real workspaces read-only to measure false positives before enabling a fixer.
Update tiers only for evidenced coverage; do not confuse a third successful compile with behavior proof.

## R5. Prepare, test, finalize a revision without changing tested bytes

Replaces item 73 H2; depends on R1 and existing archive/baseline/save gates.

**Files:** proposed `bridgeforge/revise.py` and command module; reuse `archive.py`, `mod_changelog.py`,
`live_trust.py`, baseline/save compatibility helpers and `state_snapshot.py`.

**Proposed flow:** `revise prepare WORKSPACE "reason"` -> existing rig/scenario commands ->
`revise finalize WORKSPACE --revision ID --test-id ID`. Do not advertise CLI support until implemented.

Prepare records previous archive/version, source identity, authorized scope and new version once, then candidate manifest.
Repeated prepare of the same candidate returns its pending revision; changed files require explicit candidate refresh
with old evidence invalidated, not another accidental version bump. Finalize checks the matching accepted run and all
release gates, records any required publication authorization, and never changes shipped bytes or version. If a report
is part of the shipped set, write it before testing or store acceptance annotations externally; do not exclude executable
or game-consumed files just to make hashes match.

Journal states: PREPARED -> LIVE_ACCEPTED -> ARCHIVED -> SNAPSHOTTED/COMPLETE, with FAILED_STEP and recovery information.
Revalidate live identity rather than trusting a user-edited state label. Use atomic state writes and workspace locks.
Archive replacement preserves the old archive. Recovery reconciles recorded artifact hashes, avoids duplicate changelog
lines, and resumes only incomplete work. A failed snapshot after archiving reports that exact partial state. Keep local
archive finalization separate from Git push or external publication, which needs its own authorization.

**Tests/acceptance:** version formats, retries, concurrent prepare, stale candidates, mutation after testing, missing
authorization and injected failures at archive/changelog/snapshot boundaries. On a live-qualified local candidate,
finalize twice and prove archive bytes match tested bytes, the old archive survives and logs are not duplicated.

## R6. Reusable save-upgrade scenarios

Extends item 73 H3 and the existing scenario/save-corpus work; introduces no general save editor.

**Files:** `bridgeforge/scenarios.py`, `save_snapshot.py`, `save_inspect.py`, `save_compat.py`, `live_run.py`,
`probe-mod/` public-API assertions; `tests/test_scenarios.py`, `test_save_snapshot.py`, new upgrade-scenario tests.
Use Zorg's local `scratch/bf10/ZorgColonyRepairTest.java` as a logic example only; do not commit mod source or saves.

Define scenario inputs as exact old/new candidate manifests plus a copied rig-save identity. Assert preconditions, load
the old campaign with the new candidate, check migration, save to a separate rig slot, restart/load that result, then
repeat to verify idempotence. Record save lineage and each observed milestone. Cases: missing colonies, existing Zorg
colonies, captured/player ownership, removed colonies, missing registration and ID conflicts. Preserve unrelated state.
Include a no-migration healthy control. Only the in-game API performs state changes; original saves remain read-only.

**Tests/acceptance:** offline planner and evidence evaluator refuse missing/out-of-order stages and distinguish proxy
tests from real serialization. A local live run must verify actual trade/visibility, ownership preservation and repeat
save/reload; include negative cases and exact hashes. Without rig/corpus evidence, leave LIVE PENDING in the handoff.

## R7. One current status view, with historical evidence retained

**Files:** `ROADMAP.md`, `docs/HARDENING_PLAN.md`, `docs/LOCAL_HANDOFF.md`, proposed
`docs/ROADMAP_STATUS.md`; extend `bridgeforge/roadmap_lint.py` only if the status contract needs machine checks.

Create a compact table keyed by roadmap/sub-item ID: implementation state, source review, compile/static/package,
dependency/API, save compatibility, live acceptance, shipping state, evidence links/date and next blocker. Use UNKNOWN
and NOT_APPLICABLE explicitly. A local-only evidence link can support a status but must be labeled unavailable in a
clean checkout. Do not call draft automation "implemented" because a supporting CLI already exists.

Reconcile older headings such as items 61/62 against their later dated live results and item 70's built sub-items.
Preserve original measurements and dated history; point readers to current status instead of deleting provenance.
The initial reconciliation checks code, tests and recorded run artifacts; unavailable evidence remains unknown.
Later lint should catch new Done claims without evidence and impossible status combinations without equating a file
link or test count to live proof. Maintain one canonical status record, with summaries pointing to it.

**Acceptance:** every active item 70/72/73/74/75 sub-item has an evidence-backed state or explicit unknown/blocker;
current headings do not contradict later results. `roadmap-lint` passes without enlarging its tolerance baseline.
Metrics distinguish mechanical completion, review backlog, live-qualified candidates and shipped releases; report
human review time, false-positive/refusal rates and regressions separately from cleared-finding counts.

## R8. Prove snapshot recoverability

Extends item 70 H4 and item 64. Hash-complete copying is necessary, but restored usability needs a separate check.

**Files:** `bridgeforge/state_snapshot.py`, existing inventory/relocation/verification modules where present, and
the local-only `docs/MIGRATION_PLAN.md` if available; proposed isolated restore-check helper plus
`tests/test_state_snapshot.py` extensions. The requirements here are self-contained when that local plan is absent.

Write a restore manifest that names required state, omitted/unreadable files, snapshot identity and tool/schema versions.
Restore to a newly created isolated destination outside source/archive/real-install roots. Reject path traversal,
junction escapes, same-source targets and overwrite of an existing populated destination. Verify hashes, reconstruct
environment/junctions only through rig-safe setup, run CLI/status checks, then a bounded rig scenario where available.
Do not copy game binaries into Git or claim an incomplete snapshot is recoverable. Run after snapshot-format/restore
changes and before machine cutover; schedule further exercises only under an agreed local policy.

**Tests/acceptance:** corrupt/missing inputs, unreadable files, path/junction escape, wrong versions and safe successful
restore. Local acceptance records destination identity, verified hashes, regenerated environment, CLI check and rig
scenario verdict separately. Never replace the primary workspace as part of the exercise.

## Execution order and handoff requirements

1. Read current code/state; start R7 reconciliation and agree the common fingerprint/validation schemas in R1-R3.
2. Implement R2/A2, then run A1/A3 against trustworthy current inputs. R1 can proceed independently.
3. Implement R4 and R3/E1 report-only eligibility. Enable E2 only after R1-R4 gates and negative tests pass.
4. Continue D1/C1/C2 and measured A4/B work under the revised constraints. Drafting can proceed earlier without applying.
5. Implement R5 and R6 before treating revisions/migrations as unattended release work. Finish R8 before relying on
   snapshots for cutover. Keep raid/soak/lost-feature investigations in scope of their existing items, not this tranche.

For each bounded implementation: inspect dirty state, record scope/dependencies, implement focused tests (including
refusals), run focused checks, then the required `CLAUDE.md` lint/full suite/docs-index/lock checks as applicable before
commit. Do not edit tracked files while `test_guard` runs. CLI changes require reviewed golden updates. Long corpus,
restore and multi-item commands require progress/checkpoints and background execution. Follow normal commit rules;
this handoff does not itself authorize committing or pushing.

At handoff, list files changed, commands/results, validation levels, hashes/schema migrations, unresolved decisions,
and the next runnable step. Add local live tasks to `docs/LOCAL_HANDOFF.md`. Stop at actual owner decisions or missing
live evidence; continue unrelated SAFE work. Never mark a whole phase complete because its unit tests pass.
