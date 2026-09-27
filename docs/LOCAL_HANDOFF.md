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
the test rig.

## 1. Measure and try the unattended pipeline (ROADMAP P15)

### P1. Measure the queue: `finding-stats` (P15 item 1)
```powershell
python -m bridgeforge finding-stats "In operation" --scan --vanilla-core $core --write "In operation"
```
(`--scan` rescans every `working/`; drop it to use each workspace's latest stored scan, which is
faster but may be stale.) Add the Ironclads queue folder as a second root if it lives elsewhere.
Findings a mod's baseline accepts (`working/reports/baseline*.json`) are left out. Done when
`In operation/FINDING_STATS.md` exists. Paste its top table and the first 20 rows of "What to automate
next" into a cloud session: those rows decide the next fixers. An id under "Not in
automation_tiers.json" means a check was added without a tier; the test suite should have caught
that, so report it.

### P2. First real `revive` and agent run (P15 items 2-3, 8-9)
Pick a small mod with few findings (from P1's `auto` or `mechanical` bucket):
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

### R1. Provider index and revival order (P14 items 2-3)
```powershell
python -m bridgeforge provider-index build --providers "In operation" --providers "In operation\_rig\mods"
python -m bridgeforge dependency-graph --vanilla-core $core --provider-index bridgeforge-state\provider-index.json --write
python -m bridgeforge board --write
```
(A folder cache written by the removed `provider-index-update`, `bridgeforge-state\provider-index\`,
still loads through `--provider-index`.) Done when `In operation\DEPENDENCY_GRAPH.md` exists and its
top entries match the local run's ranking. Every `licence UNRECORDED` entry needs a decision before
that mod is revived: `python -m bridgeforge release-policy set <mod id> --local-only|--releasable --reason "..."`.

### R2. `diff-data` and `rebuild-from-reference` on the files the local runs used (P14 items 19, 21)
Repeat the local item 19/21/45 runs (Rebal, Better-Deserving-Smods) with the kept commands:
```powershell
python -m bridgeforge diff-data "<mod copy of a vanilla file>" "<0.9a or 0.95.1a reference copy>"
python -m bridgeforge rebuild-from-reference "In operation\Better-Deserving-Smods\working" --reference-core "<0.95.1a rig>\starsector-core" --vanilla-core $core --class hullmod --output "In operation\Better-Deserving-Smods\scratch\rebuilt"
```
Done when the results agree with the local runs recorded in items 19, 21 and 45 (BDS: 260 reverted
lines, 10 deliberate removals). Any disagreement is a bug in the kept version: record it in P15 with
the file names.

### R3. Rebuild the Downloads index (P14 item 18)
```powershell
python -m pip install -e ".[archives]"          # once: lets the index read .7z archives
python -m bridgeforge corpus-index build "C:\Users\exxec\Downloads"
python -m bridgeforge corpus-index search shieldbypass
```
The local `archive-index` database is not readable by `corpus-index`. Done when the search finds
`Ship and Weapon Pack/data/hullmods/hull_mods.csv` (the 2026-09-20 false negative). Note the build
time and index size in item 18, and check the `NOT searched` line (`.rar` is not read).

### R4. `strip-plan` and `vendor-copy --plan` on a real case (P14 item 4, P15 item 7)
```powershell
python -m bridgeforge strip-plan "In operation\<a STRIP_FROM_MOD mod>\working" --vanilla-core $core
python -m bridgeforge vendor-plan "In operation\<provider>" --id hullmod:<id> --json > plan.json
python -m bridgeforge vendor-copy --plan plan.json --to "In operation\RevenantLib"
```
Done when the strip plan's edits match what the local `strip-plan` listed for the same mod, and the
`vendor-copy --plan` dry run lists the same files as `vendor-plan`. Note: `vendor-copy` refuses a
local-only provider (the same licence gate `release` uses), which includes Rebal; if RevenantLib
should be allowed to take from local-only mods because it is itself local-only, that is an owner
decision to record in P15.

## 3. Needs the game

### G1. Rebuild the probe jar, then one live run of `content-ids` (P14 item 49)
The probe's source is 0.2.2 but the committed `probe-mod/jars/bridgeforge-probe.jar` may still be
0.2.1: it can only be built against RC8's `starfarer.api.jar`.
```powershell
python -m bridgeforge build-probe-mod --jdk "In operation\_rig\jdk-25.0.4.1+1" --core $core --install-release
python -m bridgeforge.test_guard     # tests/test_probe_mod_build.py runs only on a machine with the rig
python -m bridgeforge probe-config "<mod_dir>" --runtime $rig --install
```
Then New Game, wait a day, and run `log-triage`. Done when the log shows
`BF-PROBE|0.2.2|content-ids|OK|all-content|checked=N failed=0 ...` for a known-good mod, and a
deliberately broken variant id (a copy of a mod with one weapon id misspelled in a `.variant`)
shows a `content-ids|FAIL|variant:<id>|...` line naming the game's error. Record both in item 49,
then commit the rebuilt jar and release copy.
- Worth adding if `javap` confirms the methods (not verified from the cloud): direct
  hull/weapon/hull-mod lookups, and a check that a built fleet member's hull is the variant's own
  hull rather than a substitute (the PRB-FIGHTER-01 Nebula). Candidates to look for:
  `javap -cp starfarer.api.jar com.fs.starfarer.api.SettingsAPI | findstr /i "HullSpec WeaponSpec HullModSpec"`
  and `javap -cp starfarer.api.jar com.fs.starfarer.api.fleet.FleetMemberAPI | findstr /i Hull`.

### G2. API-drift and removed-content catalogues (P14 items 47, 8)
```powershell
python -m bridgeforge api-diff "<0.9a reference rig>\starsector-core" $core --output "In operation\_reference\api-diff-0.9a-to-rc8.json"
python -m bridgeforge compile-check "<a queued mod>" --vanilla-core $core --api-diff "In operation\_reference\api-diff-0.9a-to-rc8.json"
python -m bridgeforge content-diff "<0.9a reference rig>\starsector-core" $core --output "In operation\_reference\removed-content-0.9a-to-rc8.json"
```
Done when `compile-check` shows `API CHANGE` lines for at least one queued mod, `SectorAPI.addMessage`
lists `CampaignUIAPI.addMessage` as a candidate while `SectorAPI.createFleet` has none, and the
content catalogue lists `weapon:thruster_fighter_sm` and `hullmod:shields_formshield` as removed.
Every removal the scanner does not flag yet is a candidate check or fixer. A 0.95.1a-to-RC8 pair is
worth building too, since 255 corpus mods declare a 0.95.x base (item 45).

### G3. Confirm `revenantlib_contract` on the real rig (P14 item 48)
```powershell
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector"
python -m bridgeforge revenantlib-check "In operation\RevenantLib"
```
Done when both show the three `bf.*` methods as PASS.

### G4. RevenantLib: first scripted jar build and the move log
In the `Exxec/RevenantLib` checkout:
- `python tools/build_jar.py --game-core "<Starsector>/starsector-core" --lazylib "<mods>/LazyLib/jars/LazyLib.jar"`
  (read-only against the install; writes `scratch/RevenantLib.built.jar`). Done when it compiles with
  0 errors and the comparison shows 0 added and 0 removed. `changed` classes are fine if your javac
  differs from the one that built the committed jar; if so, run it again with `--install` and commit the
  jar, so later builds compare byte for byte.
- Copy `scratch/MOVES.log` entries into `reports/MOVES.md` (the tracked log since 2026-09-25).
- `python tools/check.py` should print three PASS lines.

## 4. Local-only tooling the repo cannot carry
- `.githooks/pre-commit` is gitignored: add `ruff check .` so lint failures stop before CI.
- `AGENTS.md` is gitignored: keep it consistent with `CLAUDE.md` (the committed copy cloud
  sessions read).
