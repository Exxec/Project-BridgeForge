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

## 0. Resume here: where the 2026-10-12 session stopped

**State (2026-10-12).** `probe-group plan` lists nothing left; `Done/` holds 153 archives (`Done/MASTER_LOG.md` is from 2026-10-11).
Probe is 0.2.27. A full regression pass (`probe-group regress`, 39 groups, REG-20261012) found three archived mods whose missions
named missing variants (Aivon Republic 0.0.4+bf.1, Sylphon RnD 1.0+bf.1, The Silent Armada vD 0.14+bf.2: fixed, live PASS,
re-archived) and two harness faults (mission-row count, scroll length), both fixed. Open from that pass: Vayra's Ship Pack
(`ii_*` variants) and Kadur Remnant (SWP and SEEKER variants) report missing mission variants that look like references to mods
not in their group (unconfirmed). The Java/launcher mass test (item 62) was re-run once the matrix learned to click the launcher;
results are in `bridgeforge-state/mass-test/MASS_TEST.md`. `state-snapshot --to DIR` keeps an append-only copy of the
irreplaceable state (first copy `C:\Users\exxec\BridgeForge-snapshots`; one file was unreadable, `Done/_previous/Fuel-Siphoning-1.2.2/Readme.txt`,
whose ACL lacks the owner). Old top-level zips of refreshed archives are in `Done/_replaced-2026-10-11/` (not deleted). The owner's
`.gitignore` edit and the untracked folders (`.goal-transfer/`, `everything-claude-code/`, `ac8-save-editor-research/`, ...)
are deliberately not committed.

**Unattended tools (2026-10-11):** `probe-group smoke` (boot to the menu, launcher clicked), `probe-group live TESTID` (whole live
run with real clicks; leave the PC alone), `probe-group duel TESTID` (rig-only duel missions with a frame/timer meter),
`probe-group plan --retest WORKSPACE`. Known weakness: menu and mission-list clicks are fixed fractions of the window (ROADMAP 65k).

**Open (owner decisions are marked):**
1. Owner: the review items (Ironclads' replaced vanilla faction files, character-point conversion and removed vanilla worlds;
   Hiver Swarm's dropped Nexerelin lines; Magellan's accepted `magellan_startigers`; Zorg18's and yunrucore's accepted findings)
   were checked on 2026-10-11 with the recommendation to keep them as they are; the owner asked for no change but has not
   explicitly approved each one.
2. The raw folder `In operation/Neutrino corp older` was deleted on 2026-10-11 at the owner's go-ahead: its files are identical to
   `Neutrino-Corporation-1.8.9/original/extracted/` (only git's index stat differed) and `Neutrino corp older.zip` stays in Downloads.
3. Gated roadmap items 39 and 45 are unchanged.

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
- **A live launch waits for a click.** `bf-test.ps1 launch` starts the game's launcher window; nothing runs, and no log is
  written, until the owner clicks "Play Starsector" there (owner, 2026-10-11). A launch that "never started" (GRP1A-20261010,
  stopped by hand) was this. Since 2026-10-11 `bf-test.ps1 launch` clicks it itself: it finds the launcher window, posts
  mouse messages at (50%, 68%) of the window, and falls back to a real cursor click 8 s later if the log still lacks "Running
  with the following mods" (proven on CLICKTEST-20261011: main menu reached with no manual click; the log is in
  `<id>.windows.txt`). `BF_NO_AUTOCLICK=1` turns it off. `probe-group live TESTID` (after `install N`) plays the whole live run unattended with real clicks (leave the mouse and keyboard alone for about five minutes; then `probe-group report` and `record --archive` on that log). `probe-group smoke` (after `install N`) does the same click from Python and boots to the main menu in about 12 s: run it before asking anyone to play. The mass boot test (`java-matrix`) starts java directly on fresh instance rigs and needs no click.
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

Set up 2026-10-09; first live run 2026-10-12 (a missing launcher click was fixed first). Result of the 150-mod mass test
(`--preset compare --bundle 4`, 6,148 s): no mod behaves differently on Java 25 vs 28 or with vs without Fast Rendering, except 13
mods that need LunaLib on the Fast Rendering variants (RC8-33). The Fast Rendering race hypothesis below is not supported by this run.
Do this when live testing resumes:

1. `python -m bridgeforge java-matrix discover --rig "In operation/_rig"` (found here: Java 8 jre, 25, 27, 28; **no Java 17**: add one with `--jdk-root`).
2. `python -m bridgeforge java-matrix setup "In operation/_rig"` writes `run-j25-direct.bat`, `run-j25-fr.bat`, ... (Java 8 is skipped unless `--java 8`).
3. Check the `fr` bats by hand once: the rig's `starsector-core` junction must expose `fr.vmparams` (and `PatchLibAgent.jar` if used); confirm the log lands in `_rig/logs`, not the real install.
4. `python -m bridgeforge java-matrix run "In operation/_rig" --mods <ids> --repeats 3` in the background; read its progress lines. "Done" = a pass-rate table per variant. If Java 28 + `fr` fails and `direct` passes, Fast Rendering is the cause; add a row to `docs/RC8_BEHAVIOUR.md`.
5. For a tester's report: `java-matrix describe-log <their starsector.log>` shows their Java and whether Fast Rendering was loaded.

Parallel (owner 2026-10-09, max 3): `java-matrix run RIG --mods <ids> --preset compare` boots vanilla (Java 25), FR, Java 28 and FR + Java 28, three at once, each in `RIG/instances/<variant>/` (linked mods and core, own logs/saves). `java-matrix instances RIG` shows state. Serial (`--parallel 1`) stays the reference: parallel load changes timing, which matters for a race. `--skip-known` reuses a recorded all-pass (`bridgeforge-state/java-matrix-ledger.json`) for the same variant, Java build and mod set, so only new mods boot everywhere. Check RAM (about 4 GB each) before the first parallel run.

Mass test (item 62): `python -m bridgeforge java-matrix mass "In operation/_rig" --only Ironclads` first (one mod, see the table), then `--limit 20`, then the whole archive in the background. Read `bridgeforge-state/mass-test/MASS_TEST.md`; logs are kept under `bridgeforge-state/mass-test/logs/<mod>/`. Check `dropped_flags` in the JSON: a JDK that refuses a flag is itself an environment difference (JDK 28+13 refuses `-noverify` and `-XX:+UseVectorStubs`). Prepatcher is not in the matrix yet (item 63 step 1).

Optimised mass run (item 62 addendum, 32 GB): `java-matrix mass "In operation/_rig" --preset compare --bundle 4` (vanilla, FR, Java 28, FR + Java 28, three at a time, 4 GB each, bundles of up to 4 unrelated mods). Your real launch: `--preset real` (Miko_Simple.txt copy on Java 28 with and without Prepatcher). Pass Prepatcher in `--mods` when testing the AoTD stack. Reports mark `bundle_conflict` and `dropped_flags`.

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

## Owner mod follow-up, 2026-10-17 (ROADMAP 74)

Acceptance steps: [Zorg18 and EPTA follow-up](OWNER_MOD_FOLLOWUP_2026-10-17.md). Test the working copies on the isolated rig, including a copied existing Zorg save with save/reload and an EPTA campaign-map visual check. LIVE TEST NOT PERFORMED; existing archives remain the previously shipped versions.

## Roadmap implementation handoff, 2026-10-17 (item 75)

Start with [current status](ROADMAP_STATUS.md) and [R1-R8 implementation contracts](ROADMAP_IMPLEMENTATION_HANDOFF.md).
These are specifications, not implemented CLI features. Next agent: inspect dirty state, define shared input/evidence
schemas, implement R2/A2 and R1, then R4/R3 eligibility reporting. E2 stays off until its prerequisites pass.
R1 needs a real rig positive/negative drift test; R6 needs copied-save load/save/reload; R8 needs an isolated restore.
Do not treat this document update or the proxy harness as completion of any of those live gates.
