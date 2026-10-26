# Local handoff: work a cloud session could not finish

**Owned qualification-worker checkpoint, 2026-10-25:** the S1 read-only evidence worker now uses the same gated, owned process-family launch as the S2 portfolio worker. Timeout or parent exit releases its Windows kill-on-close job (or POSIX session), including descendants. This closes the plain-launcher timeout gap noted in the older checkpoint below; qualification policy and dimensions are unchanged. Focused tests: 34 PASS. A restricted full run failed unrelated boot/Java process tests under sandbox permissions and was stopped with its log preserved. The elevated full guarded suite then passed 2,761 tests/12 unchanged skips with hermeticity PASS in 414.455s. A separate full coverage run passed 2,761 tests/12 unchanged skips, hermeticity PASS and 83.0760710% branch coverage against the unchanged 80% floor. The current kit and exact engine are in [S4_WORKSTATION_TRIAL.md](S4_WORKSTATION_TRIAL.md); the older engine/kit values below are historical. Both full logs, coverage report/JSON and kit smoke result are under ignored `bridgeforge-state/s34-validation-20261025-a1/`.

**Earlier S-series checkpoint, 2026-10-25:** S1 was complete only for the accepted RC8 local-new-game scope. The production S2 read-only portfolio passed three equal-input rounds, actual coordinator death/recovery and bounded worker ownership; [S2_PRODUCTION_PORTFOLIO.md](S2_PRODUCTION_PORTFOLIO.md) reports the measured 16.5% median end-to-end reduction and remaining recipe, owner-time and yield gates. S3's exact comparison re-evaluated preserved real-game callback controls but did not run a new game or establish feature/save equivalence; [S3_COMPARISON_GUIDE.md](S3_COMPARISON_GUIDE.md) records the limits. S4's source-backed code kit and private case exchange passed local checks; [S4_WORKSTATION_TRIAL.md](S4_WORKSTATION_TRIAL.md) gives the fresh-machine instructions. The owner has another workstation and will test there. The trial, independent-human operator, copied-save scope and support/publication decisions were open. At this earlier checkpoint the full guarded regression was 2,761 tests/12 unchanged skips, hermeticity PASS, 83.0735811% branch coverage and engine `8044d70868ab32863525e0e781b36d2c1184f3522f37fdf6ca8c8a995dfcd9ca`. The plain qualification-worker timeout gap at this checkpoint is closed by the later checkpoint above. Historical S2 evidence has an earlier engine and is not restamped.

**S2 continuation, 2026-10-25:** [S2_ANALYSIS_REUSE.md](S2_ANALYSIS_REUSE.md) records the opt-in
pure-parsing cache and three current-engine training rounds (96 identical complete responses;
all selected inputs preserved). First/repeated scan reductions approximately 8.9%/28.0%, peak
worker working set 181.918 -> 211.250 MiB. Owner: "Accept the opt-in tradeoff" (2026-10-25),
for this measured local parsing slice only. Defaults unchanged; portfolio acceptance is separate.
Current guarded coverage run: 2,723 tests/12 unchanged skips PASS, 357.800s, hermeticity PASS,
coverage 83.1469862%; isolated wheel payload/import smoke PASS. Raw current validation is
`bridgeforge-state/s2-reuse-20261025-a1/`, not the older S1 `last-suite.json`.
The [private bounded portfolio trial](S2_PORTFOLIO_TRIAL.md) subsequently passed three serial/
two-worker rounds and narrow cancel/crash/context/refusal controls, with 43.2% median elapsed
reduction and 255.660/460.605 MiB sampled family peaks. No production source changed; prior full
regression remains current by exact engine identity. Next: production read-only portfolio
ownership/resource/recovery integration and governed recipe evidence. Holdouts cannot choose
tuning. S2-S4 remain incomplete. No game/save/publication action this slice.

**S1 closeout continuation, 2026-10-25:** current review and resume artifacts are indexed in
[S1_COMPLETION_REVIEW.md](S1_COMPLETION_REVIEW.md) on `feat/s1-completion-20261025`, based on `ab680e57`.
The original S-series worktree is preserved. Main's duplicate implementation was preserved under ignored
`bridgeforge-state/s1-20261025/duplicate-implementation/` and main restored to its clean starting state.
Current full suite: 2,717 tests, zero failures/errors, 12 unchanged skips; hermeticity PASS. Independent resume,
current-evaluator archive/retry and P3-P6 refusals are verified. **S1 is complete for its bounded local-new-game scope.**
Owner: "Approve the controlled repair pilot"; "Accept the bounded S1 baseline"; review time "not measured".
Exact-subject P2 review and full javac/Janino (1/1) re-evaluated PASS; the full mod remains REFUSED on unrelated findings.
Do not repeat Leon's failed repair/old diagnostics, fabricate human-review timing, or treat this as save-upgrade,
publication, S2 default-change or S4 human/support approval.

Cloud sessions have no Starsector install, no test rig, no Windows, and no access to
`In operation/`. Whatever they build that needs one of those is listed here, most useful first, so a
local session can pick it up. Each entry says what to run, what "done" looks like, and which
roadmap item it closes. Delete an entry once it is done (the roadmap keeps the history).

## Current entry point (documentation audit, 2026-10-18)

Read [INDEX.md](INDEX.md), [ROADMAP_STATUS.md](ROADMAP_STATUS.md) and the strategic documents before selecting new work.
The 2026-10-12 snapshot below is dated history, not a fresh inventory or an instruction to repeat completed runs.
Zorg bf.10 and EPTA 2.1.3+bf.2 acceptance remains pending in the owner follow-up section; this audit performed no live test.
S1-S4 and item 75 extensions remain proposals/specifications unless separately evidenced.

**DOC-001 fixed 2026-10-18:** `archive --refresh` and group `--archive --refresh` now move the old archive to
`Done/_replaced-<date>/` and restore it if the new write fails (`tests/test_archive_preserves.py`). Not yet exercised on a
real `Done/` archive: the first real refresh is the check (old bytes under `_replaced-*`, new archive complete).

## Exotica 2.1.1-RC4 live test (ROADMAP item 87.7, 2026-10-26)

Build: `In operation/Exotica-Technologies-2.1.1-RC4/builds/ExoticaTechnologies-2.1.1-RC4.zip` (LazyLib, MagicLib, LunaLib;
Console Commands for `et_listmultimoduleships true`). Static checks done: bytecode diff (only the 8 delegated methods
changed), `-Xverify:all` load of every rewritten class, 11 offline tree checks (`scratch/rc4-check/`). LIVE TEST NOT PERFORMED.
Run the test plan in `In operation/Exotica-Technologies/reports/EXOTICA_2.1.1-RC3_MULTIMODULE_DIAGNOSIS.md` on RC4 and on
RC3-fix2 side by side: FullMetalSalvo on the last identical module (Trails of Tooth and Claw Drivershack, UAF Charlotte),
an exotic on the Flourish root then its undershield (Emergent Threats IX), 2-3 copies of one ship in combat, and the
AlphaSubcore count after install/uninstall on different identical modules. Done when RC4 shows no clobbering, anchoring or
bleed where RC3 does, and the log has no ModuleSlotFix "stock module variant" warning. Record the result in the workspace's
`reports/` and in item 87.7.

## 0b. Item 73 / 75 implementation: what still needs this machine (2026-10-18)

**Project Go follow-up 2026-10-19 (owner: "Repeat for all next phases if able").** Translation schema alignment is
implemented offline. Runtime manifests now record observed selected-Java version, and run records support an explicit
process exit or null. Current interactive runs terminate Java's process tree, so they do not supply a trusted natural
exit; do not insert zero or promote Go runtime gates on that basis. Shared fixtures test plumbing, not a live run.
FlowerGod's copied-source measurement found 908 policy-approved / 1,620 units and 712 review items; no real candidate was
built or archived. The refreshed GUI checklist has 10 automated passes and 5 manual rows, with all 15 owner statuses
NOT_TESTED. JSON-key consumer semantics/P8.10 are still open. Details and artifact locations are in Project Go's
`docs/REMAINING_PHASES_STATUS.md`. None of these static checks closes a live, owner-review or release gate.
**Project Go runtime gates (owner 2026-10-20):** deferred to the session after next; no translated Go candidate exists yet (FlowerGod is BLOCKED_REVIEW).

Built and unit-tested offline; nothing below has been run. Order matters: R1 first, because acceptance now needs it.

1. **R1 run binding (live proof).** `rig-up <rig> --mods <id> --probe-config`, then `probe-group live <TESTID>` (prepares and
   releases the run manifest), then `probe-group record <TESTID> --accept --note "..."`. Done: `live_status` CURRENT with
   provenance BOUND. Then edit one shipped file of the candidate: `live_status` must turn STALE and acceptance must refuse.
   Also check `tools/bf-test.ps1 launch` end to end, and that the `\|combat-round\|` milestone regex matches a real log.
   Note: a player ticking mods in the launcher changes `enabled_mods.json`, which the manifest reports as drift.
   Natural-exit step (implemented offline 2026-10-20, live pending): run `probe-group live <TESTID> --natural-exit` (optional
   `--exit-wait 180`); when it prints LIVE_DONE, quit the game yourself from the main menu (Esc, Exit) within the wait. It
   writes `<rig>/logs/<TESTID>.exit.json` (NATURAL + return code, or KILLED + null if the game was still up at the bound).
   Then `probe-group record <TESTID> --observe-exit ...` copies it into the run record's `process_exit_code` and
   `process_exit_observed`. Check the code is the launcher's (`cmd /c run-j25-direct.bat`): it equals Java's only if the bat ends
   on the java call; confirm that in the bat before Project Go treats it as Java's exit. `bf-test.ps1 launch` and `boot_test`
   still kill the tree and record nothing.
2. **R2 registry.** `finding-stats --rescan-stale --write bridgeforge-state/finding-stats/<date> --vanilla-core $core` in the
   background (every real workspace reads UNKNOWN until registered). Then `auto-open "In operation"` and
   `finding-stats --promotion <dir>`; put UNEXPLAINED cases and promotion shapes into ROADMAP 73. Check the EPTA follow-up scan
   in `reports/owner-followup-scan-20261017/` is discovered without renaming.
3. **R5 revise.** On a live-qualified candidate: `revise prepare`, the R1 run, `baseline-accept`, `revise finalize` twice
   (second reports complete). Done: archived bytes equal tested bytes, old archive in `Done/_replaced-*`, one changelog line.
4. **R6 save upgrade.** Zorg bf.9 to bf.10: a spec with both manifests and a hashed copied rig save; per case load old with new,
   save to a separate slot, restart, reload, repeat; `save-upgrade evaluate SPEC EVIDENCE --run-id ID --run-hash HASH` VERIFIED
   for all eight cases. Needs an in-game evidence emitter that does not exist yet. Owner decision 2026-10-20: the Zorg bf.9 to bf.10 run may use manual evidence (screenshots plus logged steps), recorded as MANUAL, never VERIFIED; the in-game emitter is deferred to S3.
5. **R8 restore.** `snapshot-restore-check <snapshot> --to <new empty folder outside the repo> --source-root <repo>`: expect
   RESTORED_OFFLINE; then rebuild rig junctions in the copy and run a bounded rig scenario there, never in the primary workspace.
6. **G1 New Game fallback.** `probe-group live` on Vacuum (`exerelin_vacuum`, the only other total conversion in the corpus); done when it reaches
   `campaign END` with a `new-game-generic(N pages)` stage; screenshots in `<TESTID>.stdout.log.newgame/`.
7. **G6 raid mod.** `raid_run.install_raid_mod(rig, 'exipirated_avestamarket', attacker_faction='hegemony')` in a group with
   Nexerelin; done: `check_raid_log` gives RAID_OBSERVED. Confirm Janino compiles the loose scripts against Nexerelin's classes.
8. **G2/G3.** One `probe-group regress --changed-since <commit>` after the next probe change (a regression writes
   `_regress/REGRESSION_HOLD.json` and blocks the next run); `rig-up` on the real `_rig`.
9. **E4 port record.** Write `In operation/Templars-0.9.8f/working/reports/PORT_SOURCE.json` with `old_tree` =
   `scratch/port-0.9.9e-code/before` and rescan; expect `port-dropped-feature` findings for the Crusade; accept with a reason or
   ask for a plan. Done 2026-10-20: written and rescanned; see the decision draft in the workspace `scratch/`.
10. **H1.** `audit-explain --auto` on Ironclads, Nightcross and the GRP6A mods from their pre-explanation state; report the
    fraction left for a person.
11. **B fixers on the real queue.** `revive` over the queue with `finding-stats` before and after; B1 applied to 5 mods in the
    read-only sample (Hegemony-Expeditionary-Auxiliary, Hiver-Swarm, Scion-Collective, Valhalla-Starworks, Valhalla-Starworks-2.0).
    Owner decision open: should `revive` try the REVIEW-only fixers (B1, B4) before packeting?
12. **F checks, optional live proof.** LTA and Tahlan's Legio siege base (`market-on-hyperspace-entity`) with Nexerelin; the
    `EptaTestMission` `wormhole*` planets (`mission-map-reference-missing`).
13. **Templar Crusade live run (owner 2026-10-20).** TEMPLAR_CRUSADE_PLAN section 4.3: `probe-group live` with Templars 0.9.8f
    (`+bf`, with `jars/TEM_Crusade.jar`) and Nexerelin, Corvus and a random sector, `debugStartInDays` and the short-stage mode set
    in `data/config/tem_crusade_settings.json`. Done: `BF-TEMCRUSADE|stage|...` lines for start, fleets, condition on and off, an
    ending with losses and unrest, and a save that reloads. Try `defenderMode` `response` and `military` once each.
14. **All the Domain Drones rules.csv (BUGS.md FIX-001).** The working copy's rules.csv is restored. `probe-group live` with the
    mod, open a drone interaction that only its rules.csv defines (a dialogue option from the mod's rules) and screenshot it;
    then `archive --refresh` (the 0.6 archive without rules.csv moves to `Done/_replaced-<date>/`) and correct the status.
15. **SEEKER Betelgeuse modules survive save and reload (SK-6c, owner 2026-10-20).** `probe-group live` with SEEKER, LazyLib and
    the probe; New Game with the Betelgeuse (`ART_dimention`) in the player fleet; destroy one module and damage another's hull
    and armor; log hull and armor fractions; 10 campaign days; save, reload, compare. Pass: values match and no
    `SEEKER.twig.*` class error. Needs the small `BF-SKRTWIG|...` logging hook from `In operation/SEEKER/working/reports/TWIG_RECREATION_PLAN.md`.
16. **Ironclads launcher matrix (owner 2026-10-22).** Owner reports a start-up crash on the archived v.11+bf.1 (no crash log
    found on this machine; the rig copy matches the release except `data/missions/mission_list.csv`). Run Ironclads alone with the
    probe on six launches: FR (Java 25), FR + Java 28 and Java 28 direct, each without and with the pre-patcher
    (`In operation/_rig/run-j25-fr.bat`, `run-j25-fr-prep.bat`, `run-j28-fr.bat`, `run-j28-fr-prep.bat`, `run-j28-direct.bat`,
    `run-j28-direct-prep.bat`). Pass: main menu, New Game reaches the campaign, no FATAL. Keep each `starsector.log`.
    **Result 2026-10-22 (batch IC-*-20261022, probe 0.3.1): all six PASS** - New Game reached the campaign, the probe's campaign
    day ended (`campaign|END`), FATAL 0. The live driver reported exit 1 only because Ironclads replaces `mission_list.csv`, which
    hides the probe's combat mission (combat NOT_TESTED). The owner's start-up crash does not reproduce with Ironclads alone;
    it needs the owner's own `starsector.log` and `enabled_mods.json`.
17. **EPTA 2.1.3+bf.2 (owner 2026-10-22).** Revision prepared (candidate d9940ba8af7d): version label 2.1.3 and the Proelefsi
    station back on its original sprite. **Done 2026-10-22:** run EPTA213BF2C-20261022 (probe 0.3.2) recorded: entity-state OK
    (original sprite), bounties Artifact 667 / Masamune / Sever OK; archived as `Epta-Consortium-2.1.3-2.1.3+bf.2.zip`.
18. **Zorg V18+bf.10 (owner 2026-10-22).** Revision prepared (candidate 1f1499141da6): Zeta I/II visible from the start, Zeta I
    a size-7 industrial market, Zeta II a size-6 mining market, Unimatrix the size-10 hub. Live run: New Game and an existing
    bf.9 save; check the planets show on the map and in the intel list, the three markets exist, and the BF-ZORG lines.
    **Done 2026-10-22 (New Game):** run ZORGBF10C-20261022 (probe 0.3.2) recorded: entity-state OK for both planets, no FAIL;
    archived as `Zorg18-V18+bf.10.zip`. Loading an existing bf.9 save stays untested.
19. **Straggler archives (owner 2026-10-22, queued).** A structural check of Done/ (2026-10-22) found three archives below the
    standard: (a) `Done/Station.Augments-2.4.3+bf.1/` is a hand-placed patched copy (the 2026-10-11 save-load fix) with no
    ARCHIVE_NOTE.md, original/, workspace/ or zip, so MASTER_LOG lists it only in the changelog; evidence: rig logs
    GRP-SA-PATCHED4-20261011 and LOAD-SA-NEWSAVE(2)-20261011, original `Downloads/Station.Augments.7z`; (b) ClearCommands
    [BF r1] 1.0.e+bf.1 and (c) RevenantLib 1.2.0+bf.1 were archived before any live run. BF-Legacy-Fleets has no original/ by
    design (BridgeForge's own mod). No LIVE_VALIDATED workspace lacks an archive; no prepared revision is unfinished. Gates
    bf-strag-*.

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
3. The older gating note is superseded by the 2026-10-12 roadmap decisions: P15 follow-up 39 (population-delta fixer)
   was closed **not built** with owner agreement; follow-up 45 (0.7 economy translators) remains deferred because its
   measured trigger was not met. These are distinct from other sections that reuse the same item numbers.

**How a live run works.** Close Starsector first, then from the repo root:
```powershell
python -m bridgeforge probe-group plan --no-auto-solo [--solo <Workspace>]   # writes In operation\PROBE_GROUPS.json
python -m bridgeforge probe-group install 1 --stage-providers
Set-ExecutionPolicy -Scope Process Bypass; .\tools\bf-test.ps1 launch GRP<N><letter>-<yyyymmdd>   # blocks until the game closes
python -m bridgeforge probe-group report "In operation\_rig\logs\<TESTID>.stdout.log"
python -m bridgeforge probe-group record <TESTID> --archive
```
The manual route requires New Game, a career all the way through, the campaign checks, the combat mission and quit.
The existing `probe-group live TESTID` driver can perform its supported default/Nexerelin flow with real clicks;
unsupported/custom UI flows and visual/gameplay judgments still require a person. A driver finishing is evidence only
for paths it actually observed, not every feature or an existing-save upgrade.
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
  `C:\Users\exxec\AppData\Local\Python\pythoncore-3.15-64` first on `PATH` for the commit.
- Workspaces get locked to non-admin sessions (twice: `Done\` zips and 14 workspaces; cause unknown). If `probe-group plan` says
  "Access is denied", run `tools\unlock-workspaces.ps1 -Apply` from an Administrator PowerShell (dry run without `-Apply`).
- Existing archive handling is path-specific: ordinary group `record --archive` calls the move-aside path;
  standalone `archive` refuses a collision unless a replacement mode is requested. `--refresh` now moves the old archive
  aside (DOC-001, fixed 2026-10-18; see the note at the top of this file), but its first use on a real `Done/` archive is still
  the check. Preserve earlier artifacts.
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
4. `python -m bridgeforge java-matrix run "In operation/_rig" --mods <ids> --repeats 3` in the background; read its progress lines. "Done" = a pass-rate table per variant. A variant-associated failure is a hypothesis, not proof of its cause; reproduce with controlled inputs and record only the bounded observed fact in `docs/RC8_BEHAVIOUR.md`.
5. For a tester's report: `java-matrix describe-log <their starsector.log>` shows their Java and whether Fast Rendering was loaded.

Parallel (owner 2026-10-09, max 3): `java-matrix run RIG --mods <ids> --preset compare` boots vanilla (Java 25), FR, Java 28 and FR + Java 28, three at once, each in `RIG/instances/<variant>/` (linked mods and core, own logs/saves). `java-matrix instances RIG` shows state. Serial (`--parallel 1`) stays the reference: parallel load changes timing, which matters for a race. `--skip-known` reuses a recorded all-pass (`bridgeforge-state/java-matrix-ledger.json`) for the same variant, Java build and mod set, so only new mods boot everywhere. Check RAM (about 4 GB each) before the first parallel run.

Mass test (item 62): `python -m bridgeforge java-matrix mass "In operation/_rig" --only Ironclads` first (one mod, see the table), then `--limit 20`, then the whole archive in the background. Read `bridgeforge-state/mass-test/MASS_TEST.md`; logs are kept under `bridgeforge-state/mass-test/logs/<mod>/`. Check `dropped_flags` in the JSON: a JDK that refuses a flag is itself an environment difference (JDK 28+13 refuses `-noverify` and `-XX:+UseVectorStubs`). Prepatcher setup support now exists (`java-matrix setup --prepatcher`); use `--help` for exact options and `AOTD_COMPAT_PLAN.md` for dated, bounded observations.

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
