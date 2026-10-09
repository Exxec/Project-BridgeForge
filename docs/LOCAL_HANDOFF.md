# Local handoff: work a cloud session could not finish

Cloud sessions have no Starsector install, no test rig, no Windows, and no access to
`In operation/`. Whatever they build that needs one of those is listed here, most useful first, so a
local session can pick it up. Each entry says what to run, what "done" looks like, and which
roadmap item it closes. Delete an entry once it is done (the roadmap keeps the history).

Rewritten 2026-09-27 after the local and cloud histories merged. Closed and removed: the MOVES.log
shadowing audit (P14 item 27, done locally in `0183ab3`) and the Maelstrom dependency-jar check
(E8, resolved in P14 item 44). Several local runs used commands that were then folded into one
version each (P15 item 5: `diff-data`, `rebuild-from-reference`, `corpus-index`, `provider-index
build`, `dependency-graph`, `strip-plan`); the kept versions have not yet run on real data, so those
runs are repeated below (R1-R4). In the commands, `$core` is the RC8 `starsector-core` and `$rig`
the test rig; reference installs sit beside RC8 under `C:\Program Files (x86)\Fractal Softworks\`
(`Starsector8.1`, `Starsector9a`, `Starsector9.5.1a`, ...).

Updated 2026-09-27 after the first local pass (ROADMAP P15 item 13): P1, R2, G4 and the local
tooling entries are done and removed; G2's content expectation and R2's BDS command were wrong.
Every long command now prints `[n/total]` progress and resumes if interrupted (P15 item 12).

## 0. Resume here: where the 2026-10-06 live-test session stopped

**State.** Every mod `probe-group plan` knew about is live-validated and archived in `Done/`; the plan lists
nothing left. Archived this session: Ironclads, Kadur Remnant, Free Stars Union, Metelson Industries,
Glinthawk Operations, Tritachyon, yunruhullmods, yunruworlds, Magellan Protectorate, Pegasus Belt Council,
Stardust Merchant Coalition, Sylphon RnD, The Nomads, yunrucore (workspace `YunruCore-2025`), Nightcross,
Omega Trauma (re-archived), Zorg18 V18+bf.7. Code is committed up to `d363e49e` (ROADMAP items 55i, 55j). The
owner's `.gitignore` edit and the untracked folders (`.goal-transfer/`, `fixtures/`, `ac8-save-editor-research/`,
...) are deliberately not committed. Probe is 0.2.22. Last full suite: 1553 tests, one failure that also fails on a clean
HEAD here: `tests/test_locks.py::test_child_with_cwd_inside_target_is_found` (process cwd lookup; environmental).

**Open, in the order to take them (the owner decides the first four; do not decide for them):**
1. Ironclads (`Done/Ironclads`): review the nine replaced vanilla faction files, the new-game character-point
   conversion (manual option = 6 points, three skills dropped) and the removed vanilla worlds (black site, Limbo, gate
   hauler, Nameless Rock; `data/scripts/plugins/IroncladsCoreLifecyclePlugin.java`).
2. Hiver Swarm: its Nexerelin condition lines were dropped from `rules.csv` (review).
3. Accepted probe finding: Magellan's hidden `magellan_startigers` builds no patrol at any size in RC8's
   `FleetFactoryV3` (cause not found; nothing in the mod spawns its fleets). Recorded in the workspace's
   `working/reports/probe_accepted.json` as a session decision. Delete the entry to reopen it.
4. Zorg18's three revive findings (cosmetic design-type column, missing `zorg.faction` known lists, jar `initStar` call)
   were put in `working/reports/baseline.json` as accepted (unchanged from the archived +bf.6); yunrucore's six
   description-less weapons and five manufacturer colours likewise. Remove the baseline keys to reopen.
5. Combat-Misc-Utils 0.4.1 (`In operation/Combat-Misc-Utils`): imported, status ASSESSMENT_REQUIRED, never revived.
   `revive` it, then `probe-group plan`.
6. Not written: a scanner check for an industry or content id that a newer installed library renamed (Tritachyon asked
   for `BOGGLED_AI_STATION`, TASC 10.0.9 calls it `BOGGLED_REMNANT_STATION`; fixed by hand, jar rebuilt).
7. Gated roadmap items 39 and 45 are unchanged.
8. **Paused by the owner (2026-10-06): ROADMAP item 60 (60a-60e)**, five proposed automation and gap-coverage entries,
   nothing started; item 6 above is 60d. Ask the owner which to start; the recommended order is 60a, 60b, 60c, 60d, 60e.

**How a live run works.** Close Starsector first, then from the repo root:
```powershell
python -m bridgeforge probe-group plan --no-auto-solo [--solo <Workspace>]   # writes In operation\PROBE_GROUPS.json
python -m bridgeforge probe-group install 1 --stage-providers
Set-ExecutionPolicy -Scope Process Bypass; .\tools\bf-test.ps1 launch GRP<N><letter>-<yyyymmdd>   # blocks until the game closes
python -m bridgeforge probe-group report "In operation\_rig\logs\<TESTID>.stdout.log"
python -m bridgeforge probe-group record <TESTID> --archive
```
A person must play: New Game, a career all the way through, one in-game day, the combat mission to its last round, quit.
A launch that dies at startup ends by itself in seconds (read `<TESTID>.triage.txt` and `<TESTID>.windows.txt`). `record`
reads the probe config the last `install` wrote, so record before installing the next group. If the audit blocks an archive,
`bridgeforge audit-shipped "In operation\<Ws>"` lists each UNEXPLAINED difference; explain with `audit-explain <Ws> <files>
--reason "<evidence>"` (`--auto` first). Recording writes `MOD_CHANGELOG.md` and `bridgeforge/release_policy.json`: do not run
the test suite while it does (hermeticity check), then commit them.

**Traps found this session.**
- `git commit`'s hook runs `python -m ruff`; the project `.venv` Python has no ruff. Put
  `C:\Users\exxec\AppData\Local\Python\pythoncore-3.14-64` first on `PATH` for the commit.
- Workspaces get locked to non-admin sessions (twice: `Done\` zips and 14 workspaces; cause unknown). If `probe-group plan` says
  "Access is denied", run `tools\unlock-workspaces.ps1 -Apply` from an Administrator PowerShell (dry run without `-Apply`).
- A mod that already has an archive in `Done/` collides on `record --archive`: move the old folder to
  `Done\_replaced-<date>\` (never delete an archive without the owner's word), then record again.
- Edit code with the Write/Edit tools: `\n`, `\\` and `\"` inside shell heredoc Python are unescaped and corrupted files again
  and again. Run `python -m bridgeforge docs-index` after adding a check, and do not edit tracked files while the suite runs.
- Provider sources: `probe-group plan` with `--provider-source` set to the real install stages MagicLib 1.5.6 over the rig's 1.5.7
  and the installer refuses; use the default sources.

## 0a. Java/launcher matrix: first live use (ROADMAP item 61)

Set up 2026-10-09, not yet run. Do this when live testing resumes:

1. `python -m bridgeforge java-matrix discover --rig "In operation/_rig"` (found here: Java 8 jre, 25, 27, 28; **no Java 17**: add one with `--jdk-root`).
2. `python -m bridgeforge java-matrix setup "In operation/_rig"` writes `run-j25-direct.bat`, `run-j25-fr.bat`, ... (Java 8 is skipped unless `--java 8`).
3. Check the `fr` bats by hand once: the rig's `starsector-core` junction must expose `fr.vmparams` (and `PatchLibAgent.jar` if used); confirm the log lands in `_rig/logs`, not the real install.
4. `python -m bridgeforge java-matrix run "In operation/_rig" --mods <ids> --repeats 3` in the background; read its progress lines. "Done" = a pass-rate table per variant. If Java 28 + `fr` fails and `direct` passes, Fast Rendering is the cause; add a row to `docs/RC8_BEHAVIOUR.md`.
5. For a tester's report: `java-matrix describe-log <their starsector.log>` shows their Java and whether Fast Rendering was loaded.

Parallel (owner 2026-10-09, max 3): `java-matrix run RIG --mods <ids> --preset compare` boots vanilla (Java 25), FR, Java 28 and FR + Java 28, three at once, each in `RIG/instances/<variant>/` (linked mods and core, own logs/saves). `java-matrix instances RIG` shows state. Serial (`--parallel 1`) stays the reference: parallel load changes timing, which matters for a race. `--skip-known` reuses a recorded all-pass (`bridgeforge-state/java-matrix-ledger.json`) for the same variant, Java build and mod set, so only new mods boot everywhere. Check RAM (about 4 GB each) before the first parallel run.

Known limit: the stale-process check only sees java.exe under the rig, and these JDKs live outside it; the run kills the launcher's process tree on timeout.

## 1. Measure and try the unattended pipeline (ROADMAP P15)

### P2. First real `revive` and agent run (P15 items 2-3, 8-9)
ClearCommands reached UNATTENDED_DONE, passed its probe run and is archived in `Done/ClearCommands`
(local-only, 2026-09-27). For the agent half: done 2026-09-27 on Yunru's Unpack Blueprints (P15 item 21, VERIFIED in 61 s). Give it the probe run;
for more agent runs, pick a mod with a `code` packet from `In operation/FINDING_STATS.md`. The command below
needs `claude` on PATH; otherwise pass the VS Code extension's `claude.exe` path:
```powershell
python -m bridgeforge revive "In operation\<Mod>" --vanilla-core $core                                   # dry run
python -m bridgeforge revive "In operation\<Mod>" --vanilla-core $core --apply --draft-report
python -m bridgeforge escalation list "In operation\<Mod>"
python -m bridgeforge escalation run "In operation\<Mod>" <packet> --agent "claude -p --permission-mode acceptEdits --allowedTools Read,Edit,Write,Grep,Glob"
```
Done when one agent packet ends VERIFIED (then rerun with `--apply`) and the mod passes the usual
probe run. Record in ROADMAP P15 how long the agent took, whether the packet had enough context,
and anything it had to go looking for; that decides what packets carry next. Also open one
`content-reference-unresolved` packet from any mod and check its Options section (substitute,
vendor, strip) matches what you would decide by hand. Fixers you want applied everywhere go once in
`In operation\AUTOMATION_POLICY.json`:
```json
{"approved_fixers": {"mod-info-game-version-inexact": {"reason": "every revival targets RC8", "recorded_on": "2026-09-27"}}}
```

## 2. Re-run with the kept commands (P15 item 5)

### R3. Done 2026-09-27 (P15 item 26): 69 min, `shieldbypass` found. Removed.

### R4. `strip-plan` and `vendor-copy --plan` on a real case (P14 item 4, P15 item 7)
```powershell
python -m bridgeforge strip-plan "In operation\<a STRIP_FROM_MOD mod>\working" --vanilla-core $core
python -m bridgeforge vendor-plan "In operation\<provider>" --id hullmod:<id> --json > plan.json
python -m bridgeforge vendor-copy --plan plan.json --to "In operation\RevenantLib"
```
Done 2026-09-27 (P15 items 13, 17): the strip plan matches, and the vendor conflict is RevenantLib's own
deliberate copy of `shields_formshield` (see its PROVENANCE.md), so nothing is left here.

### G0. Probe the 63 finished mods in 8 group sessions (P15 item 24)
The plan is in `In operation\PROBE_GROUPS.json` (rebuild with `python -m bridgeforge probe-group plan`). Per group N:
```powershell
python -m bridgeforge probe-group install N
.\tools\bf-test.ps1 launch GRP-N-<date>
# New Game, wait one in-game day, open Missions -> BridgeForge Probe: Combat briefly, quit
python -m bridgeforge probe-group report "In operation\_rig\logs\GRP-N-<date>.stdout.log"
```
Done when every member reads PASS. FAIL names the mod and id; UNCLEAR means a crash no member's jar owns, so
run that group's members alone with `bf-test.ps1 probe <folder>`. Record each PASS in the mod's report.

## 3. Needs the game

### G1. Probe follow-ups (P14 item 49, P15 item 18)
`content-ids` passed on SEEKER 2026-09-27 (checked=40, failed=0); a missing weapon in a variant is an RC8
New Game fatal and a missing hull mod is dropped silently, so neither reaches the probe (the scanner flags
both). Left:
1. Confirm the window watcher records dialog text: next time any run shows an error dialog, check that
   `<TESTID>.windows.txt` has a `dialog:` line and triage lists it as FATAL.
2. Hull check done: CID-HULL-20260927 passed on probe 0.2.4 (checked=40, failed=0).

### G2. Removed-content catalogue follow-up (P14 items 47, 8)
Catalogues for 0.8.1a, 0.9a and 0.95.1a to RC8 are in `In operation\_reference\` (2026-09-27), and
the API check passed against 0.8.1a (P15 item 13). Left: review each `removed-content-*.json` for
removals the scanner does not flag yet (candidate checks or fixers). The old expectation that
`weapon:thruster_fighter_sm` and `hullmod:shields_formshield` appear was wrong: they are mod ids.

### G3. Confirm `revenantlib_contract` on the real rig (P14 item 48)
```powershell
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector"
python -m bridgeforge revenantlib-check "In operation\RevenantLib"
```
`revenantlib-check` PASS 2026-09-27; `rig-doctor` has nothing to check until RevenantLib is installed in
the rig (`prepare-test`). Done when `rig-doctor` shows `revenantlib_contract` PASS.
