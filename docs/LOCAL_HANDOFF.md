# Local handoff: work a cloud session could not finish

Cloud sessions have no Starsector install, no test rig, no Windows, and no access to
`In operation/`. Whatever they build that needs one of those is listed here, newest first, so a
local session can pick it up. Each entry says what to run, what "done" looks like, and which
roadmap item it closes. Delete an entry once it is done (the roadmap keeps the history).

## From 2026-09-24

### 1. Rebuild the probe jar, then one live run of `content-ids` (ROADMAP P14 item 31)
The probe's source moved to 0.2.2 but the committed `probe-mod/jars/bridgeforge-probe.jar` is
still 0.2.1: it can only be built against RC8's `starfarer.api.jar`.
```powershell
python -m bridgeforge build-probe-mod --jdk "In operation\_rig\jdk-25.0.4.1+1" --core $core --install-release
python -m bridgeforge.test_guard     # tests/test_probe_mod_build.py runs only on a machine with the rig
python -m bridgeforge probe-config "<mod_dir>" --runtime $rig --install
```
Then New Game, wait a day, and run `log-triage`. Done when the log shows
`BF-PROBE|0.2.2|content-ids|OK|all-content|checked=N failed=0 ...` for a known-good mod, and a
deliberately broken variant id (a copy of a mod with one weapon id misspelled in a `.variant`)
shows a `content-ids|FAIL|variant:<id>|...` line naming the game's error. Record both in item 31,
then commit the rebuilt jar and release copy.
- Worth adding if `javap` confirms the methods (not verified from the cloud): direct
  hull/weapon/hull-mod lookups, and a check that a built fleet member's hull is the variant's own
  hull rather than a substitute (the PRB-FIGHTER-01 Nebula). Candidates to look for:
  `javap -cp starfarer.api.jar com.fs.starfarer.api.SettingsAPI | findstr /i "HullSpec WeaponSpec HullModSpec"`
  and `javap -cp starfarer.api.jar com.fs.starfarer.api.fleet.FleetMemberAPI | findstr /i Hull`.

### 2. Build the real API-drift catalogue (ROADMAP P14 item 29)
```powershell
python -m bridgeforge api-diff "<0.9a reference rig>\starsector-core" $core --output "In operation\_reference\api-diff-0.9a-to-rc8.json"
python -m bridgeforge compile-check "<a queued mod>" --vanilla-core $core --api-diff "In operation\_reference\api-diff-0.9a-to-rc8.json"
```
Done when the catalogue exists and at least one queued mod's `compile-check` shows `API CHANGE`
lines. Check that `SectorAPI.addMessage` lists `CampaignUIAPI.addMessage` as a candidate and
`SectorAPI.createFleet` has none; if not, the catalogue logic needs a fix. Every removal it
finds that the scanner does not flag yet is a candidate check or fixer.

### 2b. Build the removed-content catalogue (ROADMAP P14 item 8)
```powershell
python -m bridgeforge content-diff "<0.9a reference rig>\starsector-core" $core --output "In operation\_reference\removed-content-0.9a-to-rc8.json"
```
Done when `weapon:thruster_fighter_sm` and `hullmod:shields_formshield` appear as removed (the two
cases this item was written for). Then rescan Vacuum's and Rebal's originals with
`--removed-content` and check both show up as `content-reference-removed-in-vanilla`.

### 3. Confirm `revenantlib_contract` on the real rig (ROADMAP P14 item 30)
```powershell
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector"
python -m bridgeforge revenantlib-check "In operation\RevenantLib"
```
Done when both show the three `bf.*` methods as PASS.

### 4. Validate `diff-data` on the Rebal files it was designed for (ROADMAP P14 item 19)
Run it on a few of Rebal's shadowed vanilla files against the 0.9a reference copy and against
RC8's copy. Done when the output matches what E11's hand-built rebuild plan found for those files.
That result is the input item 21 (`rebuild-from-reference`) needs.

### 5. Try `rebuild-from-reference` on Rebal (ROADMAP P14 item 21)
```powershell
python -m bridgeforge rebuild-from-reference "In operation\Xenoargh-Rebal\working" --reference-core "<0.9a reference rig>\starsector-core" --vanilla-core $core --class wpn --output "In operation\Xenoargh-Rebal\scratch\rebuilt-wpn"
```
Done when, for the files E11 rebuilt by hand, the MERGED output matches E11's result (compare with
`diff-data`), and every CONFLICT is a genuine both-sides edit. Then repeat for `ship`, `variant`,
`skin`, `system`. If a file class needs different merge rules, record it in item 21.

### 6. Build the Downloads index (ROADMAP P14 item 18)
```powershell
python -m bridgeforge corpus-index build "C:\Users\exxec\Downloads"
python -m bridgeforge corpus-index search shieldbypass
```
Done when the search finds `Ship and Weapon Pack/data/hullmods/hull_mods.csv` (the 2026-09-20
false negative). Note the build time and index size in item 18, and check the `NOT searched` line:
if many mods sit in `.7z`/`.rar` archives, reading them needs a new dependency, so decide whether to
add one or extract them once.

### 7. RevenantLib line endings
Merge `claude/confident-archimedes-e2qv1v` in `Exxec/RevenantLib` (`.gitattributes`
`original/** -text`; all 24 `PROVENANCE.md` hashes match on a fresh clone). Afterwards,
`git status` in your local RevenantLib copy should be clean.

### 8. Local-only tooling the repo cannot carry
- `.githooks/pre-commit` is gitignored: add `ruff check .` so lint failures stop before CI.
- `AGENTS.md` is gitignored: keep it consistent with `CLAUDE.md` (the committed copy cloud
  sessions read).
