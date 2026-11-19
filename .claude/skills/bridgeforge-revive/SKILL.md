---
name: bridgeforge-revive
description: Take one Starsector mod through BridgeForge from intake to an archived, live-validated revival on the current target build (0.98.5a-RC7). Covers intake, revive with approvals, input-tier fixes, jar rebuilds from source, the owner's decision sheet, acceptances with evidence, the report draft, live tests on the Test1 rig, record and archive, and re-archiving a changed mod with a +bf.N bump. Use it whenever the user names a mod to revive, port, retarget or re-test ("revive X next", "port the abandoned ones", "UAF works on RC8, why so many findings?"), even if they don't say "revive".
---

# Reviving one mod

The full command guide is `docs/BRIDGEFORGE_REVIVAL_GUIDE.md`. This is the order that worked, with the traps found
on 2026-11-16/17 (the six-mod batch, United Aurora Federation and Sunrider). The owner decides what is accepted or
archived: present findings with evidence and a recommendation, never accept or archive on their behalf.

## 1. Intake (a copy; the input mod is never edited)

```
bridgeforge intake "<mod folder or zip>" --repo-root "<repo>" --name <Workspace-Name> --strip-junk
```

## 2. Revive

```
bridgeforge revive "In operation/<Name>" --vanilla-core "<target starsector-core>" --apply --draft-report [--approve <fixer-id> ...]
```

- **Name the core path.** `@target` needs `bridgeforge-state/target.json`, which White_Legion does not have. There is no
  AUTOMATION_POLICY.json, so approvals are passed per run with `--approve`.
- **Input-tier fixers do not run in revive** (for example `rules-csv-curly-quote-unreadable`). Apply them with
  `bridgeforge fix "In operation/<Name>/working" --finding <id> --apply`.
- **A jar that ships its source** (`jars/src`, `src/`): edit the source and rebuild with
  `bridgeforge src-to-jar "<ws>" --jar jars/X.jar --vanilla-core <core> --source-root jars/src --lib <library jars>`. A proof
  must PASS before it installs. No source: bytecode packets, or an owner-approved patch.
- **Return-type-only linkage** (a call whose game method now returns a value): `bridgeforge relink "<ws>" --vanilla-core <core>`.
- **A call whose game method changed its parameters** (`target-impact` says `jar-call-signature-changed`) is not a scan
  finding, so `revive --approve jar-call-signature-changed` does nothing (Vayra's Sector, 2026-11-19; ROADMAP-3 96.11).
  Run the fixer directly, dry-run first, then check the rewritten call with `javap -c`:
  `bridgeforge fix "<ws>/working" --finding jar-call-signature-changed --vanilla-core <core> [--apply]`.
- **The report draft says BLOCKED on javac errors** that are only missing libraries: since 93.36, revive passes its own
  providers; with an older build, run `revival-report-draft <working> --vanilla-core <core> --providers <RC8 mods> --apply`.

## 3. The owner's decisions

Group the findings for the owner:
- **real:** fix now;
- **as authored:** accept, with the evidence;
- **setup-dependent:** for example an optional Nexerelin integration behind an `isModEnabled` guard;
- **already so on the previous build:** say this plainly. A mod that runs on RC8 still lists many findings that are
  identical there (93.34).

Recommend one option per group. After the owner rules, record each finding:

```
bridgeforge escalation accept "In operation/<Name>" <finding-or-packet> --reason "<evidence>; owner <date>: '<their words>'"
```

Quote the owner's words in the reason. Run `revive` again until it ends UNATTENDED_DONE, then check that the report draft
reads READY_FOR_LIVE_TEST; `probe-group plan` requires both.

## 4. Live test on Test1 (the 0.98.5a rig)

- **Copy the workspace to Test1** (the `test1-run` skill), keeping paths relative.
- **Plan and install:**
  `bridgeforge probe-group plan "In operation" --rig "In operation\_rig-0985a" --write <plan>`, then
  `probe-group install N --plan <plan> --rig ...`.
- **Libraries the mod declares** must be in the rig's `mods/`; AshLib was copied by hand for UAF. Run
  `rig-doctor` before a run: its `launcher_prefs` check fails when no licence key is stored.
- **Smoke, then live**, as one-off interactive scheduled tasks (`test1-run`). On Test1 start the game directly (95.4):
  `probe-group live TESTID --direct --client-top -200 --bat run-j25-frpp.bat` (smoke and `live-queue` take the same options).
  Leave Test1's mouse alone during a live run.
- **`probe-group report <log> --rig ...` before the next install.** The report reads the rig's current probe config (93.29).
- **Harmless report lines** (orphan CSV rows, conditional content): record the owner's ruling per id in
  `working/reports/probe_accepted.json` as `{"check", "subject": "<kind>:<id>", "reason"}`.
- **Never read, print or copy the licence key.**

## 5. Record and archive (on the owner's word only)

```
bridgeforge probe-group record <TESTID> --rig "In operation\_rig-0985a" --accept --archive --note "<the owner's words; what ran>"
```

`record` refuses when the run is not bound to its staged inputs, for example when the probe config changed since the
launch. Re-install that group's config, or run again.

To archive a mod that is already recorded LIVE_VALIDATED, run `bridgeforge archive "In operation/<Mod>"`. Like
`record --archive`, it first records:
- what the files prove (`audit-explain --auto`): the credits file, moved work files, rows only added, and translations whose
  records sit in `scratch/translation/` or a translate-batch work folder;
- the owner's standing LOCAL_ONLY licence decision (2026-09-27), when the mod has none.

If it still refuses, explain each remaining file only from a record that shows why it changed:
- the revival report;
- `reports/ESCALATION_REVIEW.md`;
- a ROADMAP item carrying the owner's decision;
- an earlier `SHIPPED_CHANGES.json`.

Check the diff matches the record before `audit-explain FILE... --reason`, and never guess a reason. A baseline gone stale
through an owner-ordered `+bf.N` bump is re-stamped with `baseline-accept --reason`, naming what carried over.

## 6. A mod changed after archiving

1. `bridgeforge restore-from-done "Done/<Mod>" --queue "In operation"`. It finds the shipped folder even when its name differs
   from the archive's (Station Augments). It refuses when a workspace of that name exists: look at it first.
   - **For a new game build** add `--for-retarget` (ROADMAP-3 96.10): an existing workspace moves to
     `In operation/_stale-<date>/` (never deleted), and the archived report and plan are kept as `*.previous-build.md`, so
     revive drafts the new build's report.
2. Fix it, then `bridgeforge bump-version "In operation/<Mod>" --note "<what changed>"` (`+bf.N`, MOD_CHANGELOG).
3. Revive until UNATTENDED_DONE; check that the report reads READY_FOR_LIVE_TEST. A workspace restored without
   `--for-retarget` keeps the old report, which blocks the draft: `revival-report-draft "<ws>/working" --vanilla-core <core>
   --providers <rig mods> --apply --force`.
4. Live-test it again, then `record --archive --refresh`. The old archive moves to `Done/_replaced-<date>/`.

Never edit Done/ in place.

## Owner rulings to apply without asking again

- Keep CSV rows that have no file and that nothing uses; ignore their warnings ("keep them and ignore warning if it doesn't
  affect anything").
- Over-budget variants that the reference build shares: accept as authored (ruling option 2).
- Mods that are active upstream are skipped (AoTD, 2026-11-17). Abandoned mods are ported, however hard the port.
