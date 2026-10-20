# Current roadmap view

Reconciled 2026-10-17 for the owner-approved planning update. This is a compact index into the authoritative
`ROADMAP.md`, not a replacement history. Historical test/run claims below are attributed to their recorded evidence;
this documentation pass did not rerun the suite, launch the game or requalify releases.

Source/GitHub documentation audit 2026-10-18: current source/default branch is `3342654d`, package 0.3.0; latest
published tool is v0.2.0 pre-release. Proposed S1-S4 strategy remains unimplemented. DOC-001 (`archive --refresh`
deleted the old archive) was fixed 2026-10-18; see `BUGS.md` and [the audit](DOCS_AUDIT_2026-10-18.md). Neither is a
fresh live acceptance.

| Item | Implementation | Validation / shipping evidence | Next step |
|---|---|---|---|
| 61 Java/launcher matrix | Built; later fixes recorded | ROADMAP 70 continuation records first live use on 2026-10-12; `tests/test_java_matrix.py` | Preserve run identities under 75 R1; do not retain the old "no live run yet" headline |
| 62 mass environment testing | Built | ROADMAP 70 records the 150-mod 2026-10-12 pass: 137 SCREEN_PASS, 13 NEEDS_LUNALIB; boot evidence, not full gameplay acceptance | R1 provenance and environment-based retest selection |
| 63 AoTD/launcher compatibility | Partly implemented | `java_matrix.py`, `env_check.py`, compat sets, scanner checks and `tests/test_aotd_compat.py`; dated observations in `AOTD_COMPAT_PLAN.md` | Fork-specific behavior/requalification remains distinct from helper existence |
| 64 machine migration | Inventory/relocation/verification and snapshot tools implemented | `move_machine.py`, `state_snapshot.py` and their tests | Actual machine transfer/isolated restore qualification not established by this audit |
| 67 Mod Atlas | Index/forecast and refinement tooling implemented; broader phases partial | `atlas*.py`, `tests/test_atlas*.py`, root roadmap's dated local results | Forecasts remain PREDICTED; no whole-design completion inferred |
| 70 hardening | Partly implemented; remaining work open | ROADMAP 70 dated sub-items; safeio, baseline/archive checks, CLI/scanner split, snapshot and evidence tooling have existing implementations; this is not a claim all H1-H5 gates passed | Audit remaining sub-items individually under R7; use R1/R2/R8 for strengthened requirements |
| 72 lost-feature detection/recreation | E4 `port-dropped-feature` (REVIEW, `scan_port.py`, `PORT_SOURCE.json` format) and the `recreation` packet skeleton implemented 2026-10-18; E3 not built | `tests/test_scan_port.py`; Templars 0.9.8f `PORT_SOURCE.json` written and rescanned 2026-10-20 (local scan `scratch/bf-scan-20261020`): 3 port-dropped-feature findings (15 classes, event `tem_crusade`, 15 report stages), all the Crusade, already re-created as TEM_Crusade (TEMPLAR_CRUSADE_PLAN 5a) | Owner decision on the draft `In operation/Templars-0.9.8f/scratch/PORT_DROPPED_FEATURE_DECISION_DRAFT.md` (accept core with reason; keep C4 reputation, console command, TEM_Radiated/TEM_MarketPlugin check open); Crusade live run (plan 4.3); E3 waits for the live event-advancement proof |
| 73 less hand work | Implemented offline 2026-10-18 except E3: A3, A4, B1, B4-B7, C1-C4, D1-D3, E1/E2 (report-only), E4, F1-F6, G1-G6, H1, H3; B2 added no rule (no RC8 member involved, reason in `signature_rewrites.py`); A2 superseded by R2, H2 by R5 | Merged suite 2026-10-18 (see 75); per-item tests named in each commit; F sweeps over all 316 workspaces in the commit bodies; A1 fresh scan 2026-10-14 (`bridgeforge-state/finding-stats/2026-10-14`, local): 100/316 unattended | Live and real-queue runs in LOCAL_HANDOFF 0b; `revive` reaching code/decision-tier fixers is an open owner decision; B6 drafting has no command yet |
| 74 Zorg/EPTA | Working revisions implemented | `docs/OWNER_MOD_FOLLOWUP_2026-10-17.md`: Zorg 119 proxy assertions + package audit; EPTA scoped audit + static scan | LIVE PENDING: copied-save upgrade/reload and campaign visuals; new revisions not archived |
| 75 trust refinements | R1-R6 and R8 implemented offline 2026-10-18, DOC-001 fixed; every live gate pending | Merged suite 2026-10-18: 2211 tests, only the known `test_locks` intermittent failing (see commit `Fix item 73 merge`); no rig run | LOCAL_HANDOFF 0b, R1 first |

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
