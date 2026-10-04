# Live-test trust: design (ROADMAP item 36, 2026-10-04)

**Built 2026-10-04:** all eleven parts (see ROADMAP item 36). Left for a live session: recording the RC8 core
baseline (`bf-test.ps1 doctor` once with `rig-doctor --write-core-baseline`) and the first run records.

Live runs are the only proof of runtime behaviour, so a run is worth only as much as our certainty about what
was tested. Five owner priorities close the gaps between "the probe passed" and "this mod, in this package,
on vanilla RC8, with this save, works". Each section gives what exists today, the design, the refusal rules
and the tests. Statuses use the project's words: a check that cannot decide says `UNKNOWN`/`SKIPPED`, never `PASS`.

Order of work: 2 and 4 first (built in part on 2026-10-04), then 1 (unblocks four mods now), then 3 (gates
archive), then 5 (needs save parsing shared with Salvor).

## 1. Missing rig providers in `probe-group plan` (was 34.19)

**Today.** `probe_group.plan` puts a mod in `unplaced` with "dependencies not in the rig: X" (SCY Nation Utility,
Yunru's Glinthawk and Old School, MUDA on 2026-10-04). The fix is a manual copy.

**Design.**
- For each missing dependency id, look for a provider among the queue's workspaces: a `working/mod_info.json`
  declaring that id whose revive status is `READY_FOR_LIVE_TEST`/`UNATTENDED_DONE` (not ESCALATED, not closed
  as SUPERSEDED). More than one candidate is an error naming them; none leaves the mod unplaced as today.
- `plan` prints the staged copy per provider (`copy-drift --sync <workspace> <rig>/mods/<folder>`), and the
  plan JSON carries `providers_to_stage`. `probe-group install N --stage-providers` performs it.
- Identity check before the probe runs, after the copy: the rig folder's `mod_info.json` id and version equal
  the workspace's, and `copy_drift` reports zero drift between the two. A mismatch stops the install.
- A provider staged this way is enabled only for groups that need it; its own probe result is not claimed.

**Refusals.** Never copy from the real install, `original/` or an archive; never stage a provider whose own
revive is not ready; never overwrite a rig folder that `copy_drift` shows was edited in the rig.

**Tests.** Synthetic queue: a provider ready, one escalated, two claiming one id, a rig copy edited in place;
plan output, install staging and the identity refusal for each.

## 2. Rig core integrity in the launch preflight (35.11)

**Today (built 2026-10-04).** `rig-doctor` has `core_integrity`: SHA-256 of every `starsector-core/*.jar` and
`data/config/settings.json` against `bridgeforge-state/rig-core-baseline.json`, recorded with
`--write-core-baseline`. Missing baseline is `SKIPPED`; a changed or missing file is `FAIL`; a new file `WARN`.

**Still to do.**
- Record the baseline once from the real RC8 install (read-only hashing; the rig's core is a junction to it),
  with the game version from `starsector-core/starfarer.api.jar` manifest or the launcher log line, stored in
  the baseline so a later RC9 install is reported as a different build, not as drift.
- `bf-test.ps1 launch` runs `rig-doctor` first and stops on `FAIL` (today `doctor` is a separate command).
  `-Force` is not offered: drift is fixed by restoring the core, not by skipping the check.
- The probe result and `log-triage` output record the baseline's hash, so a report says which core it ran on.

**Tests.** Built: record, match, changed jar, no baseline. To add: different build named, preflight stop.

## 3. Shipped-copy audit before archive and release (35.13)

**Today.** `archive`/`release` package `working/` through `copy_drift`'s file set. Nothing checks that every
difference from `original/` was intended; a stray edit or a lost file shows only in a probe run.

**Design** (after Project Go's `TranslatedCloneAudit`).
- Build the shipped file set, and `original/<Mod>/` (the nested root, per CLAUDE.md).
- Every file is one of: identical; changed and explained; added and explained; removed and explained.
  Explained means named by a recorded change: a fixer `FileChange` backup/ledger entry, a `patch-jar-class`
  record (`scratch/jar-patch-*/PATCH-*.json`), a translation artifact, a `rebuild-from-reference` merge,
  a `mod-changelog` line naming the file, or an `escalation apply` ledger entry.
- Unexplained differences fail the archive with the file list. A person explains one by recording it
  (`bridgeforge audit-explain WS FILE --reason`), which writes to `reports/SHIPPED_CHANGES.json`.
- Generated files the tool always writes (the revival report pair, `mod_info` version bump) are declared once.

**Refusals.** Never pass with `original/` missing; never treat "the file compiles" as an explanation.

**Tests.** Identical copy; explained fixer edit; unexplained edit; deleted file; jar patched with and without
its record; translation in place.

## 4. JVM crash logs in `log-triage` (35.10)

**Today (built 2026-10-04).** `bridgeforge/crash_log.py` (ported from SPW): `hs_err_pid*.log` beside the log
is parsed (problem summary, header lines, Java frames, a fallback for native out-of-memory logs); frames are
attributed to mods with `class_owner_index`. A crash written after the log was created counts as `FATAL`
(`JVM crash (hs_err)`), older ones are listed under `jvm_crash_logs`. Fixture: the checkout's
`hs_err_pid35148.log` is BridgeForge's own AST helper running out of native memory on 2026-09-28, not the game.

**Still to do.**
- `bf-test.ps1` copies a new `hs_err_pid*.log` from the rig's working directory into `<TESTID>.hs_err.log`
  beside the session log, as it does for `windows.txt`, so a crash belongs to its test id.
- Where the creation time is unknown (Linux without birthtime), match on the hs_err `Time:` line against the
  log's session start instead of never counting it.
- `probe-group record` turns a JVM crash into the group's result, naming the nearest mod frame.

**Tests.** Built: parse, out-of-memory fallback, attribution, triage counting, CLI text. To add: test-id copy.

## 5. Save baselines bound to their mod set (35.17)

**Today.** `save-baseline` builds a D2 baseline from a save without recording which mods made it.

**Design.**
- From the save's `descriptor.xml` (and SPW's `save_fingerprint` approach): the game version and the mod
  list (id, version). Add, from the rig at probe time: each enabled mod's version and jar SHA-256.
- Store both in the baseline as `made_with` and in each probe run as `ran_with`.
- Before a behaviour comparison, compare them: same ids and versions -> comparable; a version or jar hash
  differs -> `REVIEW` with the list; a mod missing or extra -> `UNKNOWN` comparison, reported, never a pass.
- Salvor uses the same reader for its diagnose step (item 35.17).

**Refusals.** Never infer a mod version from a folder name; a descriptor without a mod list is `UNKNOWN`.

**Tests.** Synthetic descriptor with mods; version change; extra mod; missing list.

## Additional recommendations (36.6-36.11)

6. **One run record per live test.** `<queue>/_live/<TESTID>.json` (plus each member's `reports/live_runs.jsonl`) joins the inputs: group members and their
   versions/hashes, core baseline hash, probe config, save `made_with`, and outputs: triage counts, JVM
   crashes, dialogs, probe verdicts. Every later claim ("passed on 2026-10-05") cites this file.
7. **Stale-result detection.** A mod's live result is valid only while its shipped hash equals the one in its
   run record; `ready-list` and `archive` show "tested on an older build" when a fix lands after the test
   (the 37 jar ports today made every earlier result for those mods stale).
8. **Group bisection.** When a group fails before the main menu, `probe-group bisect N` writes the two halves
   as new groups, keeping dependency closure, so halving is a command, not hand editing.
9. **Known-noise budget per group.** Record each group's KNOWN-NOISE count; a jump between runs of the same
   group is a `REVIEW` even when nothing is FATAL.
10. **Rig fingerprint in triage output.** `log-triage` prints the rig's enabled mod set and core baseline id,
    so a pasted triage result is self-describing.
11. **Archive gate.** `archive` refuses a mod whose latest run record is stale (7) or whose shipped-copy audit
    (3) fails, unless the owner records why.
