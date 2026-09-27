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

## 1. Measure and try the unattended pipeline (ROADMAP P15)

### P2. First real `revive` and agent run (P15 items 2-3, 8-9)
ClearCommands reached UNATTENDED_DONE 2026-09-27 (P15 item 14): give it the usual probe run. For the agent
half, pick a mod with a `code` packet from `In operation/FINDING_STATS.md`:
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
Done 2026-09-27 (P15 items 13, 17): the strip plan matches, and the vendor conflict is RevenantLib's own
deliberate copy of `shields_formshield` (see its PROVENANCE.md), so nothing is left here.

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
