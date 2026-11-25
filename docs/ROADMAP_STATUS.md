# Current roadmap view

Reconciled 2026-10-17 for the owner-approved planning update; items 89-97 added 2026-11-17. This is a compact index into the authoritative
`ROADMAP-3.md`, not a replacement history. Historical test/run claims below are attributed to their recorded evidence;
this documentation pass did not rerun the suite, launch the game or requalify releases.

**Update 2026-11-25.** Revivals target 0.98.5a-RC9, the hotfix (ROADMAP-3 item 98): RC7 -> RC9 leaves 346 of 350 archives CLEAN, and four need a hand port.

**Update 2026-11-23.** The G series is in progress: 94.G1 is done (WP1 to WP6, 2026-11-19), 94.G2 is done (2026-11-23: slices 1 to 24, all four pilots proven on both boot halves), and 94.G3, the gene bank, has started (slice 1 done 2026-11-23: the pilots banked, one ROOT on White_Legion and Test1). The probe on `main` is 0.3.6 (#225); the package is 0.4.2. The rows below that predate this update are history: where one says an item is open, ROADMAP-3 decides. Items it now marks Done or closed: 95.4 and 95.5 (Done 2026-11-19), 95.14 (Done 2026-11-19), 95.6 (closed as covered 2026-11-22), 92.40 (remainder closed 2026-11-22) and 97.3 (closed 2026-11-19, superseded by 93.30 and 95.11). Items 79.7, 80.1 to 80.8, 81.1 to 81.5 and 82.1, 82.2, 82.7 to 82.9 were verified as built against the code on 2026-11-23 (see their entries). This pass did not rerun the suite or the game.

Source/GitHub documentation audit 2026-10-18: current source/default branch is `3342654d`, package 0.3.0 then (0.4.0 on 2026-10-21); latest
published tool is v0.2.0 pre-release (re-checked 2026-10-21; v0.4.0 since 2026-11-17, below). Proposed S1-S4 strategy remains unimplemented. DOC-001 (`archive --refresh`
deleted the old archive) was fixed 2026-10-18; see `BUGS.md` and [the audit](archive/DOCS_AUDIT_2026-10-18.md). Neither is a
fresh live acceptance.

**Items 89-96, 2026-11-15 to 2026-11-17: the move to 0.98.5a.** As ROADMAP-3 records them on 2026-11-17; tests are offline
unless a run is named. Revivals target 0.98.5a-RC7 (`target show`); RC8 is the previous target (QUALIFIED) and the
reference. The checkout is package 0.4.2 with probe 0.3.3. v0.4.0 was published as a pre-release on 2026-11-17
([receipt](RELEASE_0_4_0.md)), and v0.4.1, which fixes its four security problems, the same evening; the owner then made
v0.4.1 a full release, marked Latest
([receipt](RELEASE_0_4_1.md)). v0.4.2 followed on 2026-11-18 as a full release marked Latest ([receipt](RELEASE_0_4_2.md)); later changes wait as `changelog.d/` fragments until they are assembled under the next version.

| Item | Implementation | Validation / shipping evidence | Next step |
|---|---|---|---|
| 89 0.98.5a as the target | `target-impact` with a worklist, gated rules and fixers (`rc8-signature-changed`, `jar-call-signature-changed`, `forwarding-class-method-missing`), parameter renames in `api-diff`, `revive --target` from the core; 89.8, 89.9 and 89.11-89.13 Done 2026-11-15 | `tests/test_target_impact.py`, `test_api_sources.py`, `test_game_version.py`, `test_jar_call_rewrites.py`, `test_forwarding_methods.py` | 89.7: hand ports, and whether a `rules.csv` row overriding a vanilla id behaves as on RC8 under the new `rules` list (live) |
| 90 game-build registry | 90.1-90.3 Done 2026-11-15: `target show/set/export`, `@target`, `target-bump`, `retarget` | `tests/test_target_bump.py` | 90.4 dormant-call verdict and 90.5 per-build behaviour facts open |
| 91 side by side | 91.1-91.4 Done 2026-11-15: `vanilla-migration`, `touches`, `new-vanilla-id-collision`, `vanilla-now-provides` | `tests/test_target_delta.py` and the tests named in 91 | None open |
| 92 the six-mod batch on RC7 | Done 2026-11-16/17 except 92.20 and 92.40; parts left open in 92.8 (`--watch-dir` attribution), 92.9 (finding texts that say "RC8") and 92.25 (sources built in a platform encoding) | Tests named per sub-item; all six mods reached UNATTENDED_DONE | 92.20 OP-trim audit on Test1 (LOCAL_HANDOFF); 92.40's remainder (name checks for copies) was closed as covered 2026-11-22 |
| 93 rigs, probe targets, libraries | Done: 93.1, 93.2, 93.25, 93.26, 93.28 (code), 93.33, 93.36, 93.37 (start check and retry; the cause is not shown), 93.38 (code), 93.39 (probe 0.3.3: every combat round fights its own hulls), 93.40 (a screenshot when a battle never ends), 93.41 (code: Prepatcher's own log is not drift), 93.44 (tooling: the audit reads fixer runs in the escalation ledger), 93.45-93.48 (security: what a mod ships can no longer steer javap, javac, cmd.exe, PowerShell or src-to-jar's writes); live-validated with G1R and SR5 on 2026-11-17. Open: 93.42 (FR + Prepatcher built in), 93.49 (a probe battle can stall), 93.50 (a vanished window ends a live run with an exception), 93.51 (two lower-risk review leads), 93.43 (JDK 27: set up on Test1, not yet the default), Bultach's re-run and archive (after 93.41 and 93.44) | Tests named per sub-item; the batch's four groups reached LIVE_DONE on Test1's 0.98.5a rig (2026-11-17) through local wrappers | 93.28's first live run; 93.3-93.24 (93.21's direct start proven only through the wrappers), 93.27, 93.29-93.32, 93.34, 93.35, 93.37 open |
| 94 feature genome | Approved strategy (GD-1). Queued 2026-11-17, resumed 2026-11-19 ("then begin G series after that"): 94.G1 done (WP1 to WP6, 2026-11-19); 94.G2 done 2026-11-23 (pilots P1 to P4 proven) | [FEATURE_GENOME_ROADMAP.md](FEATURE_GENOME_ROADMAP.md) section 14; ROADMAP-3 item 94 | 94.G3 slice 3 (lineage, licence report, atlas); slices 1 and 2 done (2026-11-23, 2026-11-25; the bank's home is Test1, on RC7); 94.G4 to 94.G7 not started |
| 95 faster re-validation | Done 2026-11-17: 95.10, 95.12(i), 95.13, 95.15 (code) | Tests named per sub-item; the RC8 -> RC7 `target-impact` catalogue of `Done/` (175 archives: CLEAN 167, BREAKS 4, RELINK 3, REVIEW 1) | Since 2026-11-17 Done: 95.4, 95.5, 95.12(a), (g), (h), 95.14; 95.6 closed as covered; 95.1, 95.2, 95.7-95.9 and 95.11 kept queued after the G series (owner 2026-11-22); see ROADMAP-3 for 95.3 and 95.12(b)-(f) (Nightcross closed on Test1 2026-11-17) |
| 96 skills, ports, docs, release | 96.0 owner decisions recorded; 96.1 Done 2026-11-17 (`.claude/skills/`); 96.3 Done 2026-11-17 (docs pass); 96.4 Done 2026-11-17: v0.4.0 published as a pre-release ([receipt](RELEASE_0_4_0.md)); 96.5 A1 and P6 Done, C3's first half done; 96.6 Done; 96.7 Done 2026-11-17: v0.4.1, the security release, published, then made a full release marked Latest on the owner's word ([receipt](RELEASE_0_4_1.md)) | `checks.sh` passed every step; an independent review per batch of diffs; 96.4 and 96.7: full suite and main CI on the tagged commit, asset hashes checked after download | The rest of 96.5's small items, in the handoff order ([FEATURE_GENOME_ROADMAP](FEATURE_GENOME_ROADMAP.md) section 14); P1 is next. 96.2's ports wait on live testing (LOCAL_HANDOFF) |
| 97 S series re-queued | Owner 2026-11-17: S4 parked; S2 and S3 no longer gates | ROADMAP-3 item 97 lists what remains from S_SERIES_IMPLEMENTATION_PLAN.md | 97.1 copied-save pilot (approved 2026-11-01), 97.2 the owner's look at one `data-file-not-utf8` case, 97.3 closed 2026-11-19 (superseded by 93.30 and 95.11), 97.4 closed (measure only with a speed-up claim) |

The table below is the 2026-10-17/18 reconciliation of items 61-75.

| Item | Implementation | Validation / shipping evidence | Next step |
|---|---|---|---|
| 61 Java/launcher matrix | Built; later fixes recorded | ROADMAP 70 continuation records first live use on 2026-10-12; `tests/test_java_matrix.py` | Preserve run identities under 75 R1; do not retain the old "no live run yet" headline |
| 62 mass environment testing | Built | ROADMAP 70 records the 150-mod 2026-10-12 pass: 137 SCREEN_PASS, 13 NEEDS_LUNALIB; boot evidence, not full gameplay acceptance | R1 provenance and environment-based retest selection |
| 63 AoTD/launcher compatibility | Partly implemented | `java_matrix.py`, `env_check.py`, compat sets, scanner checks and `tests/test_aotd_compat.py`; dated observations in `AOTD_COMPAT_PLAN.md` | Fork-specific behavior/requalification remains distinct from helper existence |
| 64 machine migration | Inventory/relocation/verification and snapshot tools implemented | `move_machine.py`, `state_snapshot.py` and their tests | Actual machine transfer/isolated restore qualification not established by this audit |
| 67 Mod Atlas | Index/forecast and refinement tooling implemented; broader phases partial | `atlas*.py`, `tests/test_atlas*.py`, root roadmap's dated local results | Forecasts remain PREDICTED; no whole-design completion inferred |
| 70 hardening | Partly implemented; remaining work open | ROADMAP 70 dated sub-items; safeio, baseline/archive checks, CLI/scanner split, snapshot and evidence tooling have existing implementations; this is not a claim all H1-H5 gates passed | Audit remaining sub-items individually under R7; use R1/R2/R8 for strengthened requirements |
| 72 lost-feature detection/recreation | E4 `port-dropped-feature` (REVIEW, `scan_port.py`, `PORT_SOURCE.json` format) and the `recreation` packet skeleton implemented 2026-10-18; E3 not built | `tests/test_scan_port.py`; Templars 0.9.8f `PORT_SOURCE.json` written and rescanned 2026-10-20 (local scan `scratch/bf-scan-20261020`): 3 port-dropped-feature findings (15 classes, event `tem_crusade`, 15 report stages), all the Crusade, already re-created as TEM_Crusade (TEMPLAR_CRUSADE_PLAN 5a). Owner accepted all three 2026-10-20 (baseline keys plus reason in the workspace `reports/ESCALATION_REVIEW.md`; no tool accepts a non-packet finding, so the keys were added with `baseline.finding_dict_baseline_key`). TEM_Radiated (Irradiated World condition) and TEM_MarketPlugin (Requisitions submarket) checked: unrelated to the Crusade, removed upstream in 0.9.9e with their data rows | Scheduled recreation work: C4 player reputation (`player_participated_*`/`player_protected_*`) and the `TEM_TriggerCrusade` console command; Crusade live run (plan 4.3, LOCAL_HANDOFF 0b item 13); E3 waits for the live event-advancement proof |
| 73 less hand work | Implemented offline 2026-10-18 except E3: A3, A4, B1, B4-B7, C1-C4, D1-D3, E1/E2 (report-only), E4, F1-F6, G1-G6, H1, H3; B2 added no rule (no RC8 member involved, reason in `signature_rewrites.py`); A2 superseded by R2, H2 by R5 | Merged suite 2026-10-18 (see 75); per-item tests named in each commit; F sweeps over all 316 workspaces in the commit bodies; A1 fresh scan 2026-10-14 (`bridgeforge-state/finding-stats/2026-10-14`, local): 100/316 unattended | Live and real-queue runs in LOCAL_HANDOFF 0b; `revive` reaching code/decision-tier fixers is an open owner decision; B6 drafting has no command yet |
| 74 Zorg/EPTA | Working revisions implemented | `docs/OWNER_MOD_FOLLOWUP_2026-10-17.md`: Zorg 119 proxy assertions + package audit; EPTA scoped audit + static scan | LIVE PENDING: copied-save upgrade/reload and campaign visuals; new revisions not archived |
| 75 trust refinements | R1-R6 and R8 implemented offline 2026-10-18, DOC-001 fixed; every live gate pending | Merged suite 2026-10-18: 2211 tests, only the known `test_locks` intermittent failing (see commit `Fix item 73 merge`); no rig run | LOCAL_HANDOFF 0b, R1 first |

Items 79.7 and 80-81 (ROADMAP-3), merged to `main` 2026-10-21 as PRs #41-#53, offline only (tests, no rig run): 79.7 one launcher path
(`launch.py`, `window_watch.py`); 80.1 changelog fragments and `merge-train`; 80.2 and 80.6 `gates.json` and `board --live-pending`;
80.3 archive gate; 80.4 `decision apply`; 80.7 `escalation triage`; 80.8 `hygiene`; 81.1-81.5 atlas census, migrations and exemplars.
80.5 (Salvor pin autopilot) lives in the Salvor repo (Project-Salvor PR #7); it has run: the bot's pin-bump PRs #23 (2026-11-19) and #24 (2026-11-23) were merged. The probe is now 0.3.5 on `main`. Item 82 is no longer only a proposal: 82.1, 82.2 and 82.7 to 82.9 are built (`bridgeforge/research/`), 82.5 was closed as already built.

Item 75 work contracts:

| Work | State | Dependency / acceptance boundary |
|---|---|---|
| R1 run-input provenance | IMPLEMENTED, LIVE PENDING: `run_manifest.py` (`run-manifest prepare/release/check`), one evaluator for group and standalone acceptance; legacy runs read as provenance UNKNOWN; `accept` now needs `--rig` and a manifest. Startup-marker echo of the manifest id not built | `tests/test_run_manifest.py` (22) and updated acceptance tests; live positive/negative proof in LOCAL_HANDOFF 0b |
| R2 scan registration/freshness | IMPLEMENTED: `scan_registry.py`, CURRENT/STALE/UNKNOWN/INCOMPLETE, registration-based discovery | `tests/test_scan_registry.py` (16); real queue reads UNKNOWN until `finding-stats --rescan-stale` registers it |
| R3 auto-accept policy | IMPLEMENTED REPORT-ONLY: `escalation_policy.py` gates with PASS/FAIL/INCOMPLETE/NOT_APPLICABLE; `--auto-accept` refuses (`ENABLED = False`); application path tested behind the refusal | `tests/test_escalation_auto_accept.py` (20); enable only after R1/R2/R4 live evidence and an `AUTO_ACCEPT_POLICY.json` |
| R4 semantic rulings/fixer refusals | IMPLEMENTED for C1, B1, B4, B5, B6, D3 | Rulings need a versioned predicate from three independent mods; proposals never edit mod data; stale approvals refused |
| R5 revision lifecycle | IMPLEMENTED, LIVE PENDING: `revise prepare/finalize/status/migration` with a journal; never edits tested bytes; no push | `tests/test_revise.py` (14); finalize twice on a live-qualified candidate (LOCAL_HANDOFF 0b) |
| R6 save-upgrade scenarios | IMPLEMENTED OFFLINE: `save-upgrade plan/evaluate`, eight cases, PROXY_ONLY and LIVE_PENDING distinct from VERIFIED | `tests/test_save_upgrade.py` (13); no in-game evidence emitter yet; Zorg bf.9 to bf.10 live run pending. Owner decision 2026-10-20: the Zorg bf.9 to bf.10 run may use manual evidence (screenshots plus logged steps), recorded as MANUAL, never VERIFIED; the in-game emitter is deferred to S3. |
| R7 detailed status reconciliation | This table, updated 2026-10-18 for items 72, 73, 75 | Per-sub-item audit of item 70 still open |
| R8 restore exercise | IMPLEMENTED OFFLINE: `snapshot-restore-check`, best verdict RESTORED_OFFLINE, `recoverable` stays false without the rig step | `tests/test_snapshot_restore.py` (8); real restore to a new folder and rig scenario pending |
| DOC-001 archive refresh | FIXED 2026-10-18: refresh moves the old archive to `Done/_replaced-<date>/`, restores it on a failed write | `tests/test_archive_preserves.py` (5) plus the group-path assertion; not yet exercised on a real `Done/` archive |

Cross-project follow-ups found 2026-10-18 (individual status below):
- Translation schema alignment implemented offline 2026-10-19: `text-line`, loose `class` and validated role/group metadata,
  with byte-identical shared extension fixtures. BridgeForge stages linked copies and refuses linked in-place application;
  it consumes declared roles rather than implementing Go's classifier. See `fixtures/translation-conformance/SCHEMA_V1_EXTENSIONS.md`.
  Runtime, real-mod acceptance and Project Go P8.10 remain open.
- Implemented 2026-10-20: public `save_doctor.installed_mods` (Salvor's provider contract; `_installed` kept as an alias);
  Salvor pinned in its provider contract test.
- Runtime context fields implemented offline 2026-10-19: `run_manifest` observes selected Java version and `write_run_record`
  stores an explicit exit code or null; synthetic producer/Go-consumer fixtures cover both. Existing interactive callers
  do not observe a natural Java exit, so real runtime qualification remains NOT_TESTED. No clean-log-to-zero inference.
- Natural-exit observation implemented offline 2026-10-20, live pending: `probe-group live --natural-exit` waits (bounded) for
  the operator to quit the game and writes `<TESTID>.exit.json` (NATURAL + code, or KILLED + null); `record --observe-exit`
  puts it in the run record (`process_exit_code`, `process_exit_observed`). Tested with fakes only (`tests/test_exit_observation.py`).
- `tests/test_locks.py::test_own_open_file_inside_target_is_found` can hang on this machine (psutil `open_files()`,
  observed 2026-10-18 with no CPU for 25+ minutes; twelve orphaned suite processes from that morning were found stalled).
  Checked 2026-10-20: already bounded. The probe runs in a subprocess via `_bounded_process_paths` with `timeout=30`, so a hang fails instead of stalling; no change needed.

Update this index when implementations or evidence change. Record source, compile, static, package, dependency/API,
save compatibility, live acceptance and shipping separately; use UNKNOWN/INCOMPLETE/NOT_APPLICABLE where appropriate.
An implemented command does not prove its live acceptance criterion. Local-only reports must be labeled as such.
The detailed per-sub-item status audit and any machine-readable status/lint extension remain R7 work.

Item 83 B3 implementation checkpoint 2026-10-23: all prefix families implemented and validated locally;
review/merge pending. See [completion evidence](REFACTOR_B3_COMPLETION.md). This does not complete item 83, B4-B6,
or any live/release gate.

B4 report implemented locally, 2026-10-23: [command-reference audit](REFACTOR_B4_COMMAND_AUDIT.md), based on B3 tip `6a843117`. Report only; owner grouping/deprecation decision and review/merge pending. No command behavior changed.

Owner decision 2026-10-23: retain the current CLI; B4 grouping/deprecations declined. B5 implemented locally: measured unittest fast/slow CI partitions, full suite and coverage preserved. See [B5 evidence](REFACTOR_B5_TEST_SPEED.md). Owner review/merge and hosted CI pending; B6 remains open.

B6 architecture/handoff documentation implemented locally, 2026-10-23: [close-out evidence](REFACTOR_B6_CLOSEOUT.md). Item 83 stays open pending the stack review/merge and applicable cross-repository obligations. Research #73 is merged; other B3 family merges are pending at this checkpoint.

Publication checkpoint 2026-10-23: the eleven B3-B5 branch tips are pushed with green hosted push CI (run links in [the stack ledger](REFACTOR_STACK.md)). B6 full local suite: 2,619 tests, 12 unchanged skips, hermeticity PASS. Draft PR creation awaits explicit owner approval; review/merge and item 83 completion remain open.

Strategic implementation checkpoint 2026-10-24: owner authorized S-series planning and S1 start. The compatibility/policy map is recorded and a read-only workspace adapter is implemented for both dialects; [plan](S_SERIES_IMPLEMENTATION_PLAN.md), [progress](S1_PROGRESS.md). S1 case/candidate/receipt persistence, qualification integration, finalization and operational pilot remain unimplemented; S1 is IN_PROGRESS, not accepted. S2-S4 remain planned. No existing live, archive or auto-acceptance gate is closed.

S1 initial slice validated 2026-10-24: 2,635 tests, 12 unchanged skips, hermeticity PASS; branch coverage 83.1451218%; installed-wheel Salvor 208 tests/4 skips PASS. Existing runtime/payload bytes and CLI golden unchanged; only the read-only adapter is added. S1 remains IN_PROGRESS; [evidence and next slice](S1_PROGRESS.md).

Owner goal 2026-10-24: implement/validate all S1-S4 in dependency order; automated live tests authorized when needed on the dedicated isolated rig under existing ownership/evidence/safety rules. S1.3 is next. Operational and human acceptance gates remain explicit; no live run was performed by this goal-activation checkpoint.

S1.3 checkpoint 2026-10-24: case/candidate/receipt identities and append-only store implemented offline; exact payload/context binding, drift/refusal/replay/retry/lock tests pass. Generic receipts are RECORDED_NOT_VERIFIED; qualification adapters and active profile remain S1.4 work. [Contracts](S1_CASE_RECORDS.md), [validation/handoff](S1_PROGRESS.md).

S1.3 validated 2026-10-24: 2,660 full-suite tests, 12 unchanged skips, hermeticity PASS, coverage 83.1940548%; installed-wheel Salvor 208 tests/4 skips PASS. Next S1.4: qualification obligations and independently verified evidence adapters. S1-S4 goal remains active; operational/live/owner gates are not closed.
