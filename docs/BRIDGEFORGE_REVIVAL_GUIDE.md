# BridgeForge revival toolkit: how to use it

This guide covers the commands built for reviving old Starsector mods on 0.98a-RC8: what each one does, when to use it, and the workflows that chain them together. For the design behind them, see `docs/REVIVAL_ASSURANCE_PLAN.md`. For progress, see `ROADMAP.md`.

All commands run from the repo root:

```powershell
.venv\Scripts\python.exe -m bridgeforge <command> ...
```

Two shorthands used below, adjust to your machine:

```powershell
$core = "C:\Program Files (x86)\Fractal Softworks\Starsector\starsector-core"   # vanilla game data, read-only
$rig  = "C:\Users\exxec\Documents\Project BridgeForge\In operation\_rig"  # isolated test rig
```

## 0. Safety rules (read once)

- **Your real Starsector install is read-only.** BridgeForge only ever reads it (`--vanilla-core`, `--source-mods`).
- **Test rigs must be isolated.** A rig is a folder with `run-java25.bat`, `mods/`, `logs/`, `saves/` and a `starsector-core` **junction** to the real install. The junction is what keeps saves inside the rig. `boot-test`, `probe-config` and `compat-set` refuse to run when it's missing.
- **Work on working copies** under `In operation/`. Never edit a mod's original archive. Finished mods go to `Done/` only after a passing live test.
- **Every command that changes files keeps backups** (`*.pre-*.bak`), or previews first (`fix` and `build-tag --dry-run`).
- A Starsector **Fatal error shows only as a dialog box**, never in the log. If the game is still running but no main menu appears, suspect that dialog.

## 0b. Before every test session: rig-doctor

```powershell
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector" [--write-saves-baseline]   # first time: record the baseline
python -m bridgeforge rig-doctor $rig --real-install "C:\Program Files (x86)\Fractal Softworks\Starsector"                           # every session
```

Checks, each with its fix command:
- the rig is isolated (junction)
- no rig game is running
- the probe is installed and matches its release copy
- every enabled mod resolves, with its dependencies and a matching base `gameVersion`
- every known working copy matches its rig copy (`--working ID=PATH` adds more)
- your real install's saves haven't changed since the recorded baseline
- if RevenantLib is installed, it still provides every `bf.*` method `fix --finding removed-api-call` rewrites calls to (`revenantlib-check` runs the same check on any RevenantLib folder or jar, and also catches a jar missing a class for one of its source files)

Exit code 1 means a FAIL: fix it before testing.

## 1. Look at a mod: scan and dossier

**`scan`** runs every static check (about 60) and writes a report.

```powershell
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --output .\scan-out
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --write-baseline .\baselines\<mod>.json   # accept the current findings
python -m bridgeforge scan "<mod_dir>" --vanilla-core $core --baseline .\baselines\<mod>.json         # later: show only new ones
```

Always pass `--vanilla-core`. Without it, checks that need vanilla data report `UNKNOWN`, not a verdict. Keep baselines **outside** the mod folder so they never end up in a package.

**`dossier`** is the triage packet, for a person or an agent.

```powershell
python -m bridgeforge dossier "<mod_dir>" --vanilla-core $core --output .\dossier-out\<mod> `
    [--baseline .\baselines\<mod>.json] [--original-jar "<original.jar or .bak>"] [--rig "$rig\mods\<mod>"] [--log "$rig\logs\<run>.stdout.log"]
```

- `dossier.md` is the index: identity and build tag, inventory, the open questions (your to-do list), artifact summaries, and a table of parts.
- `dossier.part-01.md`, `-02`, … hold the findings with code context. The most serious are in part 1. Nothing is ever cut; the output splits into more parts instead.
- **Typical use:** read the index, open part 1, and read only the files a question points at.

Classifications: **MANUAL** means likely broken, act on it. **REVIEW** needs judgment. **UNKNOWN** means BridgeForge can't tell. **SAFE** is informational or has a mechanical fix.

## 1b. Which API changed? api-diff

```powershell
python -m bridgeforge api-diff "<old install>\starsector-core" $core --output "In operation\_reference\api-diff-0.9a-to-rc8.json"
python -m bridgeforge compile-check "<mod_dir>" --vanilla-core $core --api-diff "In operation\_reference\api-diff-0.9a-to-rc8.json"
```

`api-diff` compares two `starfarer.api.jar`s (a jar, or the `starsector-core` folder holding one) once,
and lists every public class, method and field the newer one removed or changed. For each removed method
it names the new overloads in the same class and other classes that now declare the same name and
signature (the `SectorAPI.addMessage` -> `CampaignUIAPI.addMessage` kind). With `--api-diff`,
`compile-check` prints those leads under each javac error they explain (`API CHANGE ...`). They are
leads to verify, not rewrites. The catalogue holds only API names; keep the game jars themselves out of
the repository.

## 1c. What did the mod actually change? diff-data

```powershell
python -m bridgeforge diff-data "<mod_dir>\data\weapons\lightmg.wpn" "$core\data\weapons\lightmg.wpn"
python -m bridgeforge diff-data "<mod_dir>\data\weapons\weapon_data.csv" "$core\data\weapons\weapon_data.csv"
```

Compares by value: key, row and column order, comments, trailing commas and `10` vs `10.0` never
show up. `~` changed, `+` only in the second file, `-` only in the first, `^` the same list values in
another order. Exit code 1 means they differ.

**Many shadowed vanilla files? rebuild-from-reference.** When a mod ships edited copies of vanilla
files (the `vanilla-path-shadowing` finding) and you have the install it was made for:

```powershell
python -m bridgeforge rebuild-from-reference "<mod_dir>" --reference-core "<old install>\starsector-core" --vanilla-core $core --class wpn --output "In operation\<Mod>\scratch\rebuilt-wpn"
```

Per file: **MERGED** (RC8's version plus the mod's edits, written to `--output`), **CONFLICT** (the mod
and RC8 changed the same value; RC8's is kept and the path listed for you to decide),
**UNCHANGED_COPY** (the mod never edited it: delete it from the mod). Review the merged files with
`diff-data`, then copy them into the working copy yourself. Repeat per `--class`.

## 2. Fix the mechanical things: fix

```powershell
python -m bridgeforge fix "<mod_dir>" --finding <id>            # preview (diff only)
python -m bridgeforge fix "<mod_dir>" --finding <id> --apply    # write + backup + re-scan
```

Only SAFE, mechanical fixes are supported. Any other id is refused, with the list:

| Finding | Extra options |
|---|---|
| `wing-role-assault-removed` | none |
| `mod-info-game-version-inexact` | `--target-game-version 0.98a-RC8` |
| `csv-row-extra-columns` | none (refuses if any extra field has content) |
| `csv-missing-design-type-column` | `--design-type NAME --id-prefix P [--id-prefix P2] --design-color R,G,B` |
| `procgen-planet-row-missing` / `procgen-star-row-missing` | `--vanilla-core $core --type-id <custom_type> --from-vanilla-id <closest_vanilla_type>` (clones vanilla's row with spawn frequency 0) |
| `faction-known-lists-missing` | `--vanilla-core $core --faction-file <data/world/factions/x.faction>`; refuses if any id is unresolved |
| `mod-info-triage-banner` | none |

Anything else (REVIEW or MANUAL) needs a human or agent decision. Use the dossier.

## 3. Build numbers: build-tag

```powershell
python -m bridgeforge build-tag "<mod_dir>" [--dry-run]    # "Mod" -> "Mod [BF r1]", version -> "+bf.1"; next run r2, …
```

Bump on every change you want tested, so the launcher shows which build is running. It edits only `name` and `version` in `mod_info.json`, never the `id` (saves depend on it) and never `.version` files. `--set N` forces a number.

## 4. Get a change into the test rig: prepare-test and copy-drift

```powershell
python -m bridgeforge copy-drift "<working_mod_dir>" "$rig\mods\<mod>"                   # are they identical?
python -m bridgeforge prepare-test "<working_mod_dir>" "$rig\mods\<mod>" --bump --sync   # tag, then copy the changes to the rig
```

`prepare-test` copies only working → rig, never the reverse. It never deletes files in the rig (it lists extras), and it requires 0 drift afterwards. A rig mod folder that's a junction to the working copy is reported as "same folder" (e.g. Flu-X, Vacuum).

## 5. Does it boot? boot-test

```powershell
python -m bridgeforge boot-test $rig --mods lw_lazylib MagicLib <mod_id> [--timeout 240] [--log-name EX-1] [--keep-mods]
```

It sets `enabled_mods.json`, launches the rig, waits for the main menu, closes the game and triages the log. Results:

| Result | Meaning |
|---|---|
| **PASS** | Reached the main menu. |
| **FAIL** | The process exited before the menu. |
| **SUSPECT_FATAL_DIALOG** | The game is still running but no menu appeared. Look at the screen for an error dialog. |
| **REFUSED** | The rig isn't isolated, or a rig game is already running. |

`enabled_mods.json` is restored afterwards unless you pass `--keep-mods`. With a companion pack (P4), see §9.

## 6. Test inside the game: probe-config and the probe mod

The **probe mod** (`bridgeforge-probe`) runs checks inside the game and logs the results. It does nothing unless the rig marker exists, so it can't affect a normal install.

```powershell
python -m bridgeforge build-probe-mod --jdk "$rig\jdk-25.0.4.1+1" --core $core --install-release   # only after editing probe-mod/
python -m bridgeforge probe-config "<mod_dir>" --runtime $rig --install [--track <entity_id>] [--seconds 60] [--combat-cap 12]
```

Then:

1. Enable `bridgeforge_probe` together with the mod under test and launch the rig (e.g. `boot-test … --keep-mods`, then start the game yourself).
2. **New Game.** Wait about 1 in-game day. The campaign probe checks rings and orbits, faction known lists, market stock, fleet presence, custom planet specs and tracked entity positions. It re-runs every few in-game days. Once per session it also asks the game to resolve every variant and wing id the mod defines, and builds each of the mod's own ship variants as a fleet member (`content-ids`); a FAIL there names the id and the game's own error.
3. **Missions → BridgeForge Probe: Combat.** The mod's ships fight under AI. It logs every ship deployed and flags any captain with no personality.
4. Run `log-triage` (§7) and check its **probe** section.

Save and load can't be scripted. Saving and reloading remains a manual step.

**Skip the setup grind with `--setup`** (repeatable; applied once per save, a day after New Game, through the public API only):

```powershell
python -m bridgeforge probe-config "<mod_dir>" --runtime $rig --install `
    --setup "rep:exipirated=FRIENDLY" --setup "credits:500000" --setup "ship:ART_dimention_manipulator:1" `
    --setup "spawn-fleet:pirates:120" --setup "jump:Corvus"
```

| Spec | Effect |
|---|---|
| `rep:<faction>=<RepLevel or -1..1>` | Sets your reputation with a faction (e.g. `FRIENDLY`, `0.5`). |
| `credits:<N>` | Adds credits. |
| `ship:<variant_id>[:<count>]` | Adds ships to your fleet. |
| `spawn-fleet:<faction>:<fleet_points>` | Spawns a hostile fleet next to you (built from that faction's ship list). |
| `jump:<star_system_name>` | Moves your fleet into a star system. |

Each setup logs `BF-PROBE|…|setup|OK/FAIL|<spec>`, which `log-triage` shows.

**Setup profiles (P3c-1).** Instead of `--setup` flags, keep setups in a plain-text file:

```
# my Exigency test
apply = once-per-save          # or every-load
rep exipirated = FRIENDLY
credits = 500000
ship ART_dimention_manipulator x1
spawn pirates 120
-jump Corvus                   # a leading '-' switches a line off
```

- **Using it:** `probe-config … --profile exigency-rep` (bundled: `exigency-rep`, `seeker-betelgeuse`, `flux-basic`) or `--profile C:\path\my.txt`.
- **Editing in the rig:** the profile is copied to the rig as `saves\common\bf_probe_profile.data`. Starsector adds `.data` to every file a mod keeps there. Edit that file in Notepad and start a New Game; no command needed. When a profile is present it replaces the `--setup` list.
- **Leftover profiles:** running `probe-config` without `--profile` retires an old rig profile to `bf_probe_profile.data.prev`.

**Snapshots.** Keep good starting points and reuse them. Snapshots stay inside the rig; restoring never overwrites a save unless you pass `--replace`:

```powershell
python -m bridgeforge save-snapshot tag $rig <save_folder_name> exigency-r7-avesta   # copy + hash manifest + build tags
python -m bridgeforge save-snapshot list $rig
python -m bridgeforge save-snapshot restore $rig exigency-r7-avesta [--as-name <new_folder>] [--replace]
```

**Scenarios.** A scenario is a named test: the mods, setups, snapshot and **expected results**. The bundled ones are `avesta-near`, `betelgeuse-damaged` and `nex-corvus-day1`.

```powershell
python -m bridgeforge scenario list
python -m bridgeforge scenario plan avesta-near $rig --mod "exigency=<mod_dir>"      # what to enable and run (writes nothing)
python -m bridgeforge scenario check avesta-near "$rig\logs\<run>.stdout.log" [--save "<save dir>"]   # PASS/FAIL per expectation
```

## 7. Read a log: log-triage

```powershell
python -m bridgeforge log-triage "$rig\logs\<run>.stdout.log" [--mod-prefix <mod package or id>] [--json]
```

Add `--mods-dir "$rig\mods"` to **name the culprit**. Each exception gets:
- `suspect`: the mod whose code threw
- `involved`: every mod on its stack

For example, an NPE thrown inside AI Tweaks with SEEKER's ship on the stack lists AI Tweaks as the suspect and SEEKER as involved. For a log from another mod list (e.g. a player's modpack), point `--mods-dir` at that pack's `mods` folder and add `--all-mods`.

It sorts the log into **FATAL**, **MOD-ERROR** (with the mod's own stack frame), **KNOWN-NOISE** (harmless, each with a reason) and OTHER. It also reports milestones (main menu reached, real campaign loads, saves) and the probe results. The exit code is 1 when there's a FATAL.

## 8. Check jars and saves: jar-audit and save-compat

```powershell
python -m bridgeforge jar-audit "<rebuilt.jar>" --original "<original.jar | archive.zip | *.bak>"
python -m bridgeforge save-compat "<rig save dir or campaign.xml>" "<mod_dir>" [--vanilla-core $core]
python -m bridgeforge save-compat "<save>" "<mod_dir>" --compare-old "<old jar or mod>" --compare-new "<new jar or mod>"
```

- **jar-audit** compares a rebuilt jar with the original: class counts, removed classes, library or vanilla classes that slipped in (this is how Exigency's 40 stray GraphicsLib classes were found), and any use of reflection or file APIs.
- **save-compat** answers "will this build load this save?": `LOADS`, `WILL_FAIL` (lists the missing classes) or `UNKNOWN`. Run it before handing anyone a rebuilt jar.

## 9. Test alongside other mods: compat sets (P4)

Some bugs only appear alongside other mods: this project's SEEKER crash needed AI Tweaks, and Nexerelin needs MagicLib to generate a new game. A **compat set** is a named list of popular mods to test with, defined in `bridgeforge/compat_sets/standard.json`:

| Set | Mods |
|---|---|
| `libs` | LazyLib (`lw_lazylib`), MagicLib, LunaLib (`lunalib`), GraphicsLib (`shaderLib`) |
| `standard` | `libs` + AI Tweaks (`aitweaks`), Nexerelin, Ship/Weapon Pack (`swp`), Industrial Evolution (`IndEvo`), Unknown Skies (`US`), Tahlan Shipworks (`tahlan`) |

```powershell
# Copy the set's mods from your real install into the rig (your install is only read; --dry-run shows the plan first)
python -m bridgeforge compat-set install standard --runtime $rig --source-mods "C:\Program Files (x86)\Fractal Softworks\Starsector\mods" --dry-run
python -m bridgeforge compat-set install standard --runtime $rig --source-mods "C:\Program Files (x86)\Fractal Softworks\Starsector\mods"

# Boot the mod alone (with its libs), then with the whole set
python -m bridgeforge boot-test $rig --mods <mod_id> --pack standard
```

| Verdict | Meaning |
|---|---|
| **PASS** | Boots both alone and with the set. |
| **FAIL_ALONE** | Broken on its own. |
| **FAIL_WITH_PACK_ONLY** | Boots alone but breaks with the set: **an interaction bug.** Check the log for which mod's code is on the stack. |
| **SUSPECT_FATAL_DIALOG** | The game is still running but no menu appeared. Look for an error dialog. |

A boot only reaches the main menu. Combat interactions such as the AI Tweaks crash need the probe's combat mission (§6) run with the set enabled.

## 9b. Test only what changed: test-plan

```powershell
python -m bridgeforge test-plan "<mod_dir>" --since r3
```

Every `build-tag` (and `prepare-test --bump`) records a hash manifest of the mod's files, stored in `bridgeforge-state/build-manifests/`, outside the mod. `test-plan` compares the working copy with that tag's manifest and tells you:
- which features the changes touch
- which probe assertions to check
- which test IDs in `LIVE_TEST_INSTRUCTIONS.md` to re-run

For example, a faction file edit means re-checking markets and fleets, while a description edit only needs a text check. Files it can't classify are listed for you to review by hand.

## 9c. Performance: perf-gate and dossier --perf

```powershell
python -m bridgeforge perf-gate --perf-report "<SPW performance-report.json>" --log "$rig\logs\<run>.stdout.log" --mod-prefix loa_ [--thresholds perf.json]
```

It summarises SPW's report (CPU share per mod and startup time) and counts log spam (the same line repeated by a mod, e.g. Arkgneisis's `advance called with null engine`).

Without `--thresholds` it only reports. A thresholds file looks like `{"spam_count": {"warn": 100, "fail": 1000}, "startup_ms": {"warn": 60000}}`. `dossier … --perf <report> --log <log> --perf-mod-prefix <p>` adds the same summary to a dossier, and `dossier … --save <save>` adds the mod's footprint in a save.

## 9d. Release: release

```powershell
python -m bridgeforge release "<mod_dir>" --original "<original.jar>" --baseline .\baselines\<mod>.json --out-dir .\release-out `
    --vanilla-core $core [--rig "$rig\mods\<mod>"] [--corpus-dir "In operation\save_corpus\<mod-id>"]   # dry run
python -m bridgeforge release … --apply                                                                   # write, only if every gate passes
```

| Gate | Blocks when |
|---|---|
| scan | Any new MANUAL finding against the reviewed baseline. |
| jar-audit | Library or vanilla classes are bundled, or original classes are missing. |
| build tag | No `[BF rN]` tag. |
| copy-drift | The rig copy differs (only checked with `--rig`). |
| save corpus | A kept save would no longer load (`save-compat` / `save-content`). |
| licence | `bridgeforge/release_policy.json` marks the mod `local_only` (Exigency). |

`--apply` writes a forward-slash zip and the `Done/`-style folder (no source, no backups, and no jars that `mod_info.json` doesn't load) to `--out-dir`, plus a release note from the build manifests. Save good test saves into `In operation/save_corpus/<mod-id>/`; every one of them is re-checked at each release.

## 10. Workflows

**A. First look at a new mod**

`scan` (with `--vanilla-core`) → `dossier` → triage the open questions → `fix` for the SAFE ones → write the rest into the mod's `reports/REVIVAL_PLAN.md` → `scan --write-baseline` once reviewed.

**B. Every change you want tested**

1. Edit the working copy.
2. `scan --baseline …` (no new MANUAL findings?).
3. `prepare-test … --bump --sync`.
4. `boot-test`.
5. `probe-config … --install` → play (New Game plus the probe mission) → `log-triage`.
6. Save, quit and reload by hand; then run `save-compat` on that save.

**C. Before calling a mod done**

- Every live-test item in `In operation/LIVE_TEST_INSTRUCTIONS.md` passes. Use `test-plan --since <last tested tag>` to re-run only what changed.
- Copy good test saves into `In operation/save_corpus/<mod-id>/`.
- `release` (dry run) shows every gate passing. It covers the baseline scan, jar-audit, the build tag, copy-drift, the save corpus and the licence.
- Then run `release … --apply`. Exigency is refused by the licence gate (local-only).

## 11. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `boot-test` says REFUSED | The rig's `starsector-core` isn't a junction, or a rig game is already running. |
| A process is detected, but no game window | That can be VS Code's Java language server (also `java.exe`). BridgeForge matches by the executable path under the rig, not by name. |
| Game "crashed" but the log is clean | A Fatal error dialog. Look at the screen; the log never shows it. |
| `UNKNOWN` everywhere | You forgot `--vanilla-core`. |
| A mod unchecked itself in the launcher | Its `gameVersion` targets a different **base** version (e.g. `0.97a`). An older RC of `0.98a`, such as `0.98a-RC5`, is accepted. Use `fix --finding mod-info-game-version-inexact --target-game-version 0.98a-RC8`. |
| Launching the bat fails with "not recognized" | The path has spaces. BridgeForge quotes it; if you launch by hand, quote the full bat path. |
