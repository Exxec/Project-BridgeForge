# Changelog

## Unreleased

- New `preset-check <bf-test.ps1>`: checks every test preset against the rig's installed mods. Errors: the preset's own mod or a dependency it declares isn't enabled, an enabled id isn't installed, or the folder has no mod_info. Warning: an enabled library that no enabled non-library mod needs, either through declared dependencies (followed transitively) or by referencing its package in sources or jar classes. That keeps optional LunaLib use quiet when a mod really uses it. First run: the `flux` preset still enabled the LazyLib and MagicLib that Flu-X r3 dropped (fixed); five other presets carry a possibly deliberate extra library.
- New `docs-index` command (with `--check`). It regenerates `docs/CHECKS.md` and a new `docs/COMMANDS.md`, which covers every command and nested subcommand with its arguments, notes and help, taken from the real argument parser. `docs/CHECKS.md` gains a *Bug classes* column linking each finding to the `docs/BUG_CLASSES.md` rows that cite it. A ratchet (`tests/untested_checks_baseline.json`, 23 ids today) fails when a new finding id has no test naming it, and when a baselined id gains one, so the list can only shrink. `docs/CHECKS.md` is built from the source with `ast`:
  - every scan finding id (including table-driven ones like `LEGACY_API_RULES` and computed `bundled-{...}` ids), with its classifications and severities (both branches of a conditional), the `module:function` that emits it, the first sentence of its explanation, and the test modules that name it;
  - every `revival-audit` issue id;
  - an index of `scanner.py`'s private helpers with signatures, to reuse instead of re-deriving.

  `tests/test_checks_index.py` fails when either file is stale, so neither can drift. The first index shows which finding ids no test names; for example, the lenient-JSON findings are only tested through the parser's tolerance list.
- Fix: `revival-audit` no longer reads "NOT PERFORMED" as a completed validation. It had reported `plan-validation-state-stale` for honestly unticked plan items (Zorg18 r1).
- Scanner, from Zorg18:
  - New `campaign-fleet-reference-missing` (MANUAL). Campaign spawners that keep variant and wing ids in arrays and pick one at run time are now checked. In any source that uses `FleetMemberType`, a mod-prefixed `..._wing` literal must be a wing, and a literal starting with one of the mod's hull ids must be a variant. Missions keep their own check.
  - `faction-known-lists-missing` drops to low when the faction has no shipRoles and no market evidence: no econ JSON, no Nexerelin faction config, and no `setFactionId`/`createMarket`/`addMarket` beside the faction id in the sources or in the jar's bytecode. It stays high when compiled code without sources could create markets. First sweep: only helper factions dropped (Exigency `mysterious_contact`, FlowerGod `copyplayer`, Zorg18 `zorg`).
  - New `system-generation-unguarded` (REVIEW): `createStarSystem("X")` with no null check on `getStarSystem("X")` anywhere and no memory-flag check around the generator. It rates medium when the generator is named in a ModPlugin's `onGameLoad` (the system is duplicated on every load) and low otherwise. Total conversions and `SectorGeneratorPlugin` replacements are exempt. Zorg18 r2 now has both guards.
  - New `core-campaign-plugin-reregistered` (REVIEW/low): a mod that registers vanilla's `CoreCampaignPluginImpl`, which vanilla's SectorGen already registers (RC8 `SectorGen.java:168`), so each new game keeps a duplicate core plugin in its save. It's a 0.6-era template line. Total conversions and `SectorGeneratorPlugin` replacements (Vacuum) are exempt. First sweep: Zorg18 only.
  - `hard-coded-campaign-system-reference` is SAFE/low when the lookup is null-checked, inline or through the variable it is assigned to (Flu-X `radikius`, Zorg18 `askonia`, Arkgneisis `Anargaia`, Broken-Star `Danai`). Unguarded lookups stay REVIEW/medium.
- Fix: `translate-apply --out` makes its own copy writable. `copytree` kept the read-only attribute of Mirfak's source files, so writing the translation failed half-way. The source keeps its attributes.
- Scanner (P13), three more checks from the Chinese mods:
  - `non-ascii-identifier` flags spec ids (CSV `id`, `hullId`, `skinHullId`, `variantId`, `.wpn`/`.proj`/`.faction`/`.system` `id`) with non-ASCII characters. Prose spilled into an id column is left to `csv-row-extra-columns`.
  - `non-ascii-file-path` flags shipped file names with non-ASCII characters.
  - `data-file-not-utf8` flags data files that aren't valid UTF-8, with the line and the likely encoding (GB18030 or CP-1252).
  - `csv-fullwidth-number` (SAFE) flags CSV cells that are numbers written with full-width digits or punctuation (`１５００`, `0。5`); prose with Chinese punctuation is ignored.
  - `shippable-work-file` now also lists archives (`.rar`, `.7z`, `.zip`) and Windows shortcuts (`.lnk`, `.url`); Omega-Trauma ships both.

- New `behavior-decide <discovery_dir> <decisions.json>`: applies written decisions (select by risk/unknown/behavior ids, lifecycle, subsystem or entry-point prefix; status, why, evidence, by, on) and writes `risks.decided.json` / `unknowns.decided.json` for `release-behavior-evaluate`. The generated maps are never edited. A decision that selects nothing is refused as stale, so regenerating the maps can't silently drop one. Exit 1 while HIGH risks or unknowns are still open. First used on Flu-X: 38 of 42 unknowns decided; the 4 mission-plugin unknowns and 4 HIGH risks wait for the mission live test.
- Scanner: `rules-condition-merged-lines` flags a rules.csv condition where two lines were glued together (`$faction.id == infected$faction.hostileToPlayer`), so the rule never fires. Vanilla RC8 has 0 such rules in 11,107. `rules-condition-unknown-faction` (needs `--vanilla-core`) flags `$faction.id ==` naming a faction neither vanilla nor the mod defines. Found in the original Flu-X greetings, including one copied from Templars.
- Fix: archaeology no longer reads class declarations out of comments. Flu-X's `// Only class allowed to import exerelin.*` produced a fake class `allowed`. The scanner's own-class index had the same bug.
- Fix: `archaeology --output <discovery>/archaeology` no longer nests a second `archaeology/` folder, which had left the old maps in place and stale (Flu-X). The discovery folder is still the documented argument.
- Scanner: `jar-entry-unreadable` names jar entries that fail their CRC or can't be decompressed, and the rest of the jar is still scanned. Previously a single bad entry turned the whole jar into `unreadable-jar` (the Chinese Nightcross jar). Every entry is now read, so resource files are checked too.
- `revival-audit`: new WARNING `dependency-claim-stale` when the report's DEPENDENCY CHECK calls a library (LazyLib, MagicLib, GraphicsLib, Nexerelin, LunaLib) declared but mod_info.json doesn't declare it. Clauses that call a library optional are ignored. Found on Flu-X after its unused libraries were dropped.
- Releases and copy-drift never include OS/VCS litter: `Thumbs.db`, `desktop.ini`, `.DS_Store`, `__MACOSX/`, `.git/`, `.svn/`, `.idea/`, `.vscode/`. New scanner check `shippable-work-file` (REVIEW) lists editor and work files that would ship (`.psd`, `.xcf`, `.kra`, `.blend`, `.tmp`, `.orig`, `.old`, `.log`, `*~`, `.swp`, `.rej`, `.diff`, `.patch`).
- Scanner (P13): `player-text-non-english` counts CJK text in data files outside comments, per file; `translate-check` also covers jar strings. `design-type-color-duplicate-key`, `design-type-color-unused` and `design-type-without-color` (the last needs `--vanilla-core`) check that designTypeColors keys match the tech/manufacturer text exactly, counting vanilla's keys. Starsector's `#` comments are honoured.

- New `translate-export` / `translate-apply` / `translate-check` commands (`bridgeforge/translation.py`) for mods whose player-visible text isn't English. They read Starsector's own lenient formats directly, with no input normalisation:
  - CSV cells by raw span
  - JSON-like strings and keys, with their paths, through `#` and `//` comments, single quotes and barewords
  - loose Janino `.java` scripts outside `src/`
  - jar string constants (CONSTANT_String → Utf8)
  - prefill from a zh/en translator record (`--record`) or an English copy of the mod (`--reference`: CSV row+column, JSON path, and jar constants when the class layout matches)
  - apply refuses changed sources, checks placeholders (`%s`, `$vars`, `\u0001`), edits only each value's span, and re-verifies CSV shape, JSON parsing and class parsing
  - `translate-check` reports leftover CJK and designTypeColors keys that no tech/manufacturer uses
  - jar entries with bad CRCs are reported, not fatal
  - `translate-tm` writes a translation layer as Project Go (SSMT) translation memory, for `ssmt tm import <db> json <file>`. English recovered from the original author is marked `AUTHOR_LOCALIZATION`; our translations are `AI_TRANSLATED`. Verified on Nightcross: 1,035 entries imported into a Project Go database, passed `tm integrity`, and exported back identical.
  - `$variable` placeholders are ASCII-only. Python's `\w` also matches CJK, so a memory key glued to Chinese text (`$LTHS_Person1标记的NPC…`, Mirfak's rules notes) had swallowed the sentence into one "placeholder" that no translation could keep.
  Built for the 2026-09-13 Chinese intake (Nightcross, Mirfak Parcel Service, Blackrock CN), where Project Go's strict parsers and partial coverage fell short.
- `_parse_json` now accepts the remaining org.json leniencies seen in that intake: leading-zero and leading-dot numbers (`098`, `.7`), and data after the root value, taking the first value as the game does. New findings:
  - `json-lenient-number` (SAFE)
  - `json-trailing-brackets` (SAFE)
  - `json-content-after-root` (REVIEW): keys after an early closing brace never load; Blackrock's `br_consortium.faction` loses its `factionDoctrine`
  All 19 Mirfak and Blackrock files that failed to parse now parse.
- Scanner false positives fixed:
  - `.wpn` / `.variant` / `.ship` specs are keyed by their declared id, not their filename. Nightcross's `naai_mare_center.wpn` declares `naai_mare_deco`, which is registered.
  - `csv-row-extra-columns` now separates spilled content (MANUAL/high) from empty spreadsheet padding (SAFE/low).
  - `undeclared-library-dependency` recognises `isModEnabled` guards in bytecode, for jar-only mods, not just in source.
  - `loose-script-janino-risk` skips loose scripts whose class is also in a loaded jar. The game never compiles those ("already loaded (perhaps from jar file) ... skipping compilation"). They are reported once as the new `loose-script-shadowed-by-jar` (SAFE): Mirfak ships most of its hullmods both ways.
  - With `--vanilla-core`, a local `.wpn` that overrides a vanilla-registered weapon (Blackrock's `blinker_green`) is no longer also reported as `local-weapon-spec-unregistered`; `vanilla-path-shadowing` already reports the override.
  - `external-mod-api-import` ignores imports of the mod's own classes, even in a library-named package. Blackrock ships its own `data.scripts.util.AnamorphicFlare` / `BRDYMulti`, and `data.scripts.util` is MagicLib's legacy prefix.
- `scan --output` help now says it is an output folder.
- Nightcross (English mod shipped as a Chinese re-translation): English fully restored into `working` from the translator's own record, via Project Go plus a finishing pass (861 more strings: 530 jar constants, 331 data values). Its three required libraries are now declared in `mod_info.json`. Build tag Nightcross Armory [BF r1]; synced to the rig. `bf-test.ps1` presets `nightcross` / `nightcross-nex`.

- Live run EX-7c confirmed EXI-EVENT-01 fixed on Exigency [BF r3]. Flying an Exigency destroyer past an Exigency fleet showed the "caught" message and "Relationship with ExigencyCorp reduced by 20 (hostile)". Exigency EX-7 now passes, along with EX-B5 (Nex Corvus, scenario PASS) and EX-B6 (Nex random sector, clean).
- Live run EX-7b confirmed EXI-FLEET-01 fixed. Exigency fleets spawn from the Tasserus anomaly, and probe 0.2.1 counted 21-23 of them.
- Exigency fix for EXI-EVENT-01 (live run EX-7b). The illegal-tech event detected Exigency hardware in the player's fleet but applied its reputation penalty inside a `reportEventStage` delivery script, and that call does nothing in 0.98a. The penalty now runs directly, with a campaign message ("An ExigencyCorp fleet has identified restricted Exigency technology in your fleet."); RC8's reputation plugin posts its own notice of the change. The recompile kept the jar's class names (`$1`/`$2`/`$3`/`$Offense`). Backup `EXI.jar.pre-event-fix.bak`. Build tag Exigency [BF r3].
- New check `legacy-event-report-noop` (MANUAL) flags calls to `SectorAPI.reportEventStage` in jars and source. A sweep found Exigency's event and FlowerGod's `FG_PersonBountyEvent`; FlowerGod's is still to be reviewed.
- Probe 0.2.1: the known-lists and fleet-count checks now include the tested mod's own factions even when they own no markets (PRB-FACTION-01). `probe-config` writes a new `factions` config key, read from the mod's `data/world/factions/*.faction`. Those counts are logged as INFO, because contact or story factions may field no fleets. Market-owning factions keep WARN at 0 fleets. The stock check also skips each market's storage tab, which is always empty for the player (PRB-STORAGE-01).
- Exigency fix for EXI-FLEET-01, "no fleets in Tasserus" (live run EX-7). Exigency's attack and defense fleet managers, and its random missions, build fleets from a bare `createMarket()` market. RC8's `FleetFactoryV3` scales fleet size by that market's combat fleet-size stat, which is 0 on a bare market, so every fleet came out empty and vanished, with no error. The shared revival adapter `exigency_FleetParamsCompat` now gives such markets what vanilla gives its own no-market fallback: fleet-size multiplier 1 and quality 0.5. Real markets such as Avesta are untouched. Only that one class changed in `jars/EXI.jar` (backup `EXI.jar.pre-fleetsize-fix.bak`). Build tag Exigency [BF r2].
- New check `fleet-source-bare-market` (REVIEW) flags fleets built from a bare `createMarket()` source when the same tier (jar or source) never sets the fleet-size multiplier. It flags the pre-fix Exigency jar (4 classes) and passes the fixed one. It also flags FlowerGod's vendored `FleetFactoryV2_FG`, which is still to be reviewed.
- The probe mission's `icon.jpg` is vanilla art (Fractal Softworks), so the public repo no longer carries it. Both copies are gitignored. `build-probe-mod --install-release` copies it from `--core` (`data/missions/afistfulofcredits/icon.jpg`), and without it the release fails with a clear error instead of shipping a mission that Fatals at startup.
- Live run SK13-1e confirmed SEEKER-PERSONALITY-01 fixed on Seeker [BF r3]: triage FATAL=0, MOD-ERROR=0, no `getPersonality` NPE. Live runs FLX-R4b (Nexerelin Corvus: Radikius generated once, Infected fleets normal) and FLX-R5 passed, so Flu-X has now passed FLX-R1..R5.
- `log-triage` now files RC8's own `Weapon [lightmortar_fighter] from weapon_data.csv not found in store` warning as known noise. Vanilla keeps a `#`-named row with no `.wpn` file, so every run logged it and it showed up as an unexplained OTHER event.
- SEEKER fix for SEEKER-PERSONALITY-01, a Fatal on deploy in five SEEKER missions (live run SK13-1d). The missions gave enemy captains the 0.6-era personalities "suicidal"/"fearless", which RC8 lacks, so the personality stayed null and the ship AI crashed. The five `MissionDefinition` classes now use "reckless", changed by a same-length constant-pool edit in `jar/SEEKER.jar` with no recompile; the other 122 jar entries are byte-identical. Build tag Seeker [BF r3].
- New check `personality-id-unknown` (MANUAL) flags `setPersonality` ids RC8 doesn't define, in jars and in source. Ids a mod adds in its own `data/characters/personalities.csv` count as valid (Vacuum). A sweep of every working copy found SEEKER's 5 classes and nothing else. Flu-X's "The infected are fearless" briefing line is correctly ignored.
- `log-triage` names this crash: new FATAL rule "Null officer personality (unknown personality id)".
- `bf-test.ps1` gains a `flux-nex` preset (Flu-X plus Nexerelin) for FLX-R4. Live runs FLX-R1..R3 passed with no issues.

- The probe combat mission no longer deploys wreck-only hulls (PRB-DEBRIS-01): hulls whose `ship_data.csv` designation is Debris, Wreck, Hulk or Fragment. SEEKER's 13 "Debris" hulks were disabled on arrival and pushed real hulls (ART_armor, SKR_clipper, CIV_titanic) out of the battle.
- Live run SK13-1c confirmed SEEKER-DEATH-01 fixed (the Betelgeuse shatters once, with no slowdown) and the pirate spawn sized correctly (12 ships, ~120 FP).

- SEEKER fix for SEEKER-DEATH-01, the Betelgeuse death slowdown (live run SK13-1b). `ART_organicHull` ran its death effect every frame on the persisting wreck, spawning 3 debris ships and 15 projectiles each frame. It now runs once per ship, guarded by the ship's custom data. The class was patched into `jar/SEEKER.jar` the same way as SEEKER-STATIC-01.
- New check `hullmod-instance-state` (REVIEW) flags hull mods that keep mutable instance fields, which are shared across every ship with that hull mod. It works on jars or source.
- Fix the probe's `spawn-fleet` sizing (PRB-FLEET-02). It stops at the requested fleet points via `getFleetPoints()`; before, 120 FP produced a 40-ship fleet.

- Fix `copy_drift` ignoring jars outside `jars/` (BF-DRIFT-01). It now also collects every jar `mod_info.json` declares. SEEKER's `jar/SEEKER.jar` had never been compared or synced, so drift reported PASS while the rig ran an old jar, and a `release` would have shipped SEEKER without its code.

- SEEKER fix for SEEKER-STATIC-01, the first real mod crash found by a live run (SK13-1).
  - `ART_thrusterRotation` and `ART_shockwave_weaponGlow` kept per-weapon state in `static` fields shared across every copy in a battle. Vector-cruiser debris spawned mid-battle overwrote them, and a living cruiser then read a ship with no system, which was a Fatal NPE.
  - The fields are now instance fields, `getSystem()` is null-checked, and the glow effect skips ships lacking their gun or beam.
  - The two classes were recompiled from the jar's own decompiled source and swapped into `jar/SEEKER.jar` surgically; all other entries are unchanged, and the pre-patch jar is kept as `SEEKER.jar.pre-static-fix.bak`.

- Fix the Vacuum bounty-board dialog lock (VAC-DIALOG-01, player report). The revival's station options re-populated the menu with `FireBest PopulateOptions`, so only one options rule ran and Leave could disappear. Both rows now use `FireAll PopulateOptions`, as vanilla does everywhere. Vacuum's build tag is bumped.
  - New check `rules-firebest-populate-options` (MANUAL) flags this in any mod's `rules.csv`; Vacuum was the only mod affected.
- SEEKER and Flu-X pulled back from `Done/` for re-processing (owner, 2026-09-13), logged in `In operation/_REORG_2026-09-13_done-pullback.json`. SEEKER's working copy is now `In operation/SEEKER/working`.

- New check `weapon-effect-static-combat-state` (MANUAL) from live run SK13-1, SEEKER's first real crash found by a live run.
  - It flags per-weapon plugin classes (`EveryFrameWeaponEffectPlugin`, `OnFire`/`OnHit` effects) that keep a ship, weapon, engine controller, system or projectile in a `static` field, in loaded jars or in source.
  - SEEKER's `ART_thrusterRotation` shares `static ShipAPI ship` across every weapon copy, so Vector-cruiser debris spawned mid-battle made a living cruiser read a ship with no system, which is a Fatal NPE.
  - The class-file parser now records the superclass, interfaces and field flags.
- `log-triage` classifies an exception escaping `CombatMain` as FATAL ("Combat loop exception"). It had shown as MOD-ERROR, although the game shows a Fatal dialog.
- Fix the probe's `spawn-fleet` setup (PRB-FLEET-01). It asked factions for role `"combat"`, which doesn't exist, and now tries `combatSmall`/`Medium`/`Large`/`Capital`.

- Fix `save-content` false failures found by live run PRB-2: 50+ false "missing" ids on a healthy Exigency save.
  - Wing ids now come from `wing_data.csv`, not variant file names.
  - Faction relation keys (`exigency_hegemony`…) are skipped.
  - A mod-prefixed string counts as MISSING only inside real data-id lists: known lists, hullmods, wings, fleet-member variants. Elsewhere, for example runtime-created market ids, it goes to a new `unattributed_prefix_matches` list and doesn't fail the check.
- Fix `save-diff campaign.xml campaign.xml.bak` comparing a file with itself. An explicit `campaign.xml*` path is now used as given.

- Fix the probe's planet check reporting every planet as a failure (PRB-PLANET-01). It looked types up with `getSpec(PlanetSpecAPI.class, …)`, which never resolves them. It now checks each planet's type against `getAllPlanetSpecs()`, logs FAIL only for genuinely unresolved types, and ends with one summary line instead of one line per planet.
- First fully working live run (PRB-1c): the campaign checks ran, 12 real Exigency ships deployed with no Nebulas, and the `avesta-near` scenario passed. The clock timestamp was logged as `-55661260032000`, confirming PRB-CAMPAIGN-01's negative-timestamp cause.

- Fix fighter hulls being deployed as ships in the probe combat mission (PRB-FIGHTER-01). Exigency's Tarujan, Azata and Naxos have blank `ship_data.csv` hints, so the probe treated them as ships, and the game swapped in a vanilla Nebula starliner. The probe's hull list now also excludes any hull whose `.ship` file declares `hullSize: FIGHTER`.

- Fix the probe's combat logging (PRB-COMBAT-01). The first successful run logged only START and END: ships spawn after the plugin's `init()`, so the deployment and captain-personality checks saw no ships.
  - Each ship is now logged the first time a combat frame sees it, with a `combat-summary` count at the end.
  - The campaign script logs `campaign-armed` on its first tick, so a log shows whether the check window was ever reached.
- Fix the campaign probe never running its checks (PRB-CAMPAIGN-01). It used `startTimestamp < 0` as "not started", but campaign clock timestamps can be negative, so it re-armed every frame (1,519 `campaign-armed` lines in one session). It now uses a boolean, and the heartbeat records the clock timestamp.

- Fix the third live-run failure (PRB-COMMON-01): the probe stayed switched off because Starsector appends `.data` to common-file names.
  - `probe-config` now writes `bf_probe_rig.data`, `bf_probe_config.data` and `bf_probe_profile.data`.
  - A new test pins each on-disk name to its Java `ProbeFiles` name plus `.data`.

- Fix the second live-run crash (PRB-MISSION-02). The game compiles loose scripts with Janino, which ignores generics, so the probe mission's for-each over `Map.Entry<String, String>` failed as Object → String.
  - The mission now iterates with a raw iterator and explicit casts, the way vanilla loose scripts do.
  - A new scanner check, `loose-script-janino-risk` (REVIEW), flags typed for-each loops, diamonds and lambdas in loose `data/**/*.java` files.
  - `log-triage` now classifies Janino compile errors and `Error loading [class]` failures as FATAL; before, they showed as FATAL=0.

- Fix the first live-run crash (PRB-MISSION-01). The probe's combat mission shipped without `mission_text.txt` and an icon, which is a Fatal dialog before the main menu.
  - The mission now ships all four files every vanilla mission has.
  - A new scanner check, `mission-required-file-missing`, flags any listed mission missing a required file or its declared icon.
- `rig-doctor` no longer compares the revived working copies with a historical reference rig. It had suggested a `prepare-test --sync` that would overwrite the original mod there. By default it now compares only the mods installed in the rig being checked (Vacuum has its own rig), and explicit `--working` entries are still always checked.

No changes yet.

## 0.2.0 — 2026-09-12

Everything landed since the `v0.1.0-alpha.1` tag. The tool and
`bridgeforge-probe` report version `0.2.0`. This tool release does not certify
individual mod revivals, historical runtime behavior, or save compatibility.

- Complete P12C Vacuum layout migration with before/after byte and link evidence.
  Retain the earlier modified attempt and pre-carrier ZIP, correct only the rig
  JDK path and working-copy junction, and keep probe/report/live gates explicit.

- Implement P12B dry-run-first guarded `promote`, staged package identity checks,
  per-release reports, recoverable prior-release retention, and publication rollback.
  Preserve declared live-test requirements. Bundle release policy in installed
  packages and fail closed on missing or malformed policies.

- Implement P12A source-preserving ZIP `intake`, deterministic declared-evidence
  `board`, optional generated status files, and read-only rig-doctor layout warnings.
  Intake never replaces existing mod folders or approves a revival plan; unknown
  test/risk evidence remains explicit. Harden portable ZIP paths/collisions and
  retain empty upstream directories. Promotion/release hygiene remain separate.

- Implement P11 tool hygiene: read-only `who-locks` and rig-doctor process-path
  checks, Windows Restart Manager diagnostics, declared psutil dependency, and
  PID/start-time-scoped interruption cleanup in the versioned `tools/bf-test.ps1`.
- Guard the six-job CI suite against checkout/probe-release end-state drift;
  add resolved-temp-path fixtures and move checkout/setup-python to Node24.

- Implement the offline portion of roadmap P10 reference rigs.
  - Add `rig-create` manifests with core/JRE hashes, bundled Java metadata, run command, save location, and an explicit unprovable-isolation limitation.
  - Teach `rig-doctor --reference-manifest` to validate historical rig identity/version while skipping the incompatible RC8 probe.
  - Add five evidence-gated `era-*` compatibility sets; their installer accepts a verified `--reference-manifest` without weakening the normal junction guard. Add `save-baseline` conversion of old-game saves into D2 no-verdict observations.
  - Keep the Exigency and 0.8.1a live pilots separately gated on dedicated-install identity, authoritative dependencies, and observed runtime evidence.

- Implement roadmap P9 v2 stages D0-D6 as an interruption-safe behavior-discovery pipeline.
  - Add deterministic `archaeology`, `behavior-map`/`risk-register`, no-verdict `probe-baseline`, `hypotheses --tests`, `behavior-diff`, `release-behavior-evaluate`, and counts-only `coverage` commands.
  - Add the `expect add|approve|retire|check` decision lifecycle with required RISK/HYP/TEST breadcrumbs and recoverable last-edit backups.
  - Dossier presentation now includes architecture, behavior, risk, unknown, coverage, and recommended-test sections.
  - CLI release packaging now requires D5 behavior evidence and can block on unresolved deltas, open HIGH risks, preserved unknowns, or invalid expected changes; approved changes are grouped by build in release notes.
  - Exigency and SEEKER D0/D1 pilots are kept under ignored artifact storage; they do not modify source mods or completed releases.
  - Align runtime `bridgeforge.__version__` with the `0.2.0` package metadata so generated evidence records the correct tool version.

- Fix the CI failures of the 0.2.0 push.
  - `test_prepare_test` imported the Windows-only `_winapi` unguarded, which broke Linux.
  - The boot-test launch and matrix tests are now Windows-only, since they launch a `.bat`.
  - Five tests now resolve their temp dirs, because GitHub's Windows runners use 8.3 short paths (`RUNNER~1`).
- `test_probe_mod_build` no longer deletes the real `probe-mod/releases/bridgeforge-probe` copy that `probe-config --install` ships. It parks and restores it.
- `rig-doctor` finds working copies by the folder convention (`In operation/<Mod>/working`, then `Done/<Mod>/<release>`) instead of a hard-coded list. The test rig is now `In operation/_rig`.

The probe gained `ProbeSetup` and `ProbeProfile`. Its `BF-PROBE|0.2.0|…` lines
show which probe build produced a log.

- `log-triage --mods-dir <mods>` (with `--all-mods` for a log from another mod list) names the mod whose loaded jar threw each exception.
  - Each exception gets `suspect`, the mod closest to the throw, and `involved`, every mod on the stack. The attribution summary counts exceptions per suspect.
  - Built for the SEEKER/AI Tweaks NPE (SK-13) and for foreign modpack logs.
  - The package fallback uses only a class's own package, only when a single mod owns it, and never the shared `data.*` loose-script packages, which misattributed Exigency frames to SEEKER.
- Add `bootstrap <mod_dir>… --vanilla-core <core>`: writes a scan baseline (`bridgeforge-state/baselines/<mod-id>.json`, kept unless `--overwrite`) and records the current build manifest for each mod, so `test-plan` and `release` work immediately. Nothing is written inside mods.
  - `build-tag --record-only` records the manifest for the current build (`r0` if untagged) without bumping.
- Add editable probe setup profiles (P3c-1): Notepad-friendly `.txt` files.
  - Line forms: `rep F = L`, `credits = N`, `ship V xN`, `spawn F FP`, `jump S` and `apply = once-per-save|every-load`, with `#` comments and a leading `-` to disable a line.
  - Wired as `probe-config --profile NAME|PATH`, with bundled `exigency-rep`, `seeker-betelgeuse` and `flux-basic`.
  - The profile is written to the rig as `saves/common/bf_probe_profile`. The probe re-reads it at every campaign load, and when present it replaces the config's setups.
  - A leftover profile is retired to `bf_probe_profile.prev` when a later `probe-config` has none, so it can't silently override that run's `--setup` list.
  - The probe jar now has 16 classes and remains sandbox-clean.

- Add `rig-doctor <rig>`: pre-flight checks before a test session. Each problem comes with the command that fixes it, and it exits 1 on any FAIL.
  - Checks: the `starsector-core` junction, no rig game running, the probe installed and matching its release copy, every enabled mod resolving (dependencies and base `gameVersion`), and working-copy drift for the 9 known mods (from `default_working_copies`).
  - `--real-install` confirms the real install's saves are untouched, compared with a listing recorded once by `--write-saves-baseline` in the gitignored `bridgeforge-state/`.

- Add `test-plan <mod> --since rN` (P5): lists the features and minimal live tests to re-run for what changed since a build tag.
  - Changed files map to features (markets and fleets, ship systems, new game, refit, combat, scripted, text, launcher) through a data-driven rules table.
  - It returns the matching probe assertions and `LIVE_TEST_INSTRUCTIONS.md` test IDs.
  - `build-tag` and `prepare-test --bump` now record a per-tag file hash manifest by default (`--no-manifest` to skip). Manifests are stored outside the mod, in `bridgeforge-state/build-manifests/` (gitignored).
- Add `perf-gate` (P6): ingests SPW's `performance-report.json` at file level, counts log spam per mod, and gates against owner thresholds. It is report-only until thresholds are set.
- Dossier gains `--save` (runtime footprint: live classes, scripts, factions and markets; P3b-J) and `--perf` / `--perf-mod-prefix`.
- Add `docs/BUG_CLASSES.md` (P7): 14 live-found bug classes, each with its check, probe assertion or test.
  - A registry test fails if a listed check id stops existing.
  - `AGENTS.md` now requires every live finding to close with a check, a probe assertion, a test or a written reason.
- Add `release` (P8, plus the P3b-M save-corpus gate). It is a dry run by default; `--apply` writes only when every gate passes.
  - Gates: no new MANUAL findings against the baseline, jar-audit against the original, a build tag present, copy-drift, a save-corpus re-check and a licence policy (`bridgeforge/release_policy.json`; Exigency is `local_only`).
  - Output: a forward-slash zip and the `Done/` layout, with a release note built from the build manifests.
  - Jars in `jars/` that `mod_info.json` doesn't load are listed (`excluded_unlisted_jars`) and never shipped. This was found in Omega-Trauma, whose `jars/` holds three unloaded `Omega_Psychasthenia_old*.jar` leftovers.

- Add read-only save tools (roadmap P3b A/E/F/G/H/I/L).
  - `save-inspect`/`save-diff`: tracked mod state (e.g. Avesta's `waypoint`/`progress`/`loitering`), known-list sizes and per-mod object counts, compared across two saves. The diff matches objects by path, because XStream's `z=` ids are not stable between saves.
  - `save-scripts`: flags a mod script or listener registered more than once on the same holder.
  - `save-growth`: object and size growth across a save chain.
  - `save-provenance`: which mod versions and BF build tags made a save, compared with the working copies (`STALE_BUILD`).
  - `save-content`: the data ids a save stores as strings, checked against the build plus vanilla.
  - `save-removal`: internal only.
  - `save-summary`: a redacted, shareable summary with no player data.
  - Shared streaming reader: `bridgeforge/save_reader.py`.
  - Validated on real Exigency and SEEKER rig saves.
- Add `save-snapshot {tag,list,restore}` (P3b-D): rig-only save copies with a hash and build-tag manifest. Restore never overwrites without `--replace`, and never touches `saves/common`.
- Add `probe-config --setup` (P3b-C): `rep:`, `credits:`, `ship:`, `spawn-fleet:` and `jump:`.
  - The probe mod's new `ProbeSetup` applies each setup once per save through the public API.
  - RC8 has no public `FleetFactoryV3`, so fleets are built with `createEmptyFleet` plus `pickShipAndAddToFleet`.
  - The probe jar now has 15 classes and remains sandbox-clean.
- Add `scenario {list,plan,check}` (P3b-K), with bundled scenarios `avesta-near`, `betelgeuse-damaged` and `nex-corvus-day1`, each listing its expected probe and save results.

- Correct the `gameVersion` rule. The Starsector launcher matches on the
  **base** version (`0.98a`), not the release candidate: LazyLib, LunaLib
  and Console Commands (`0.98a-RC5`) and MagicLib (`0.98a-RC7`) all loaded
  and ran in an RC8 test rig.
  - `mod-info-game-version-inexact` now fires only when the base version
    differs (e.g. `0.97a` against an RC8 target), at high severity with an
    accurate explanation. An older RC of the same version is no longer
    flagged.
  - `compat-set install`'s gameVersion warning follows the same rule.
  - This replaces the earlier "exact RC match or the launcher silently
    unchecks the mod" assumption.
- Add the standard compatibility pack (roadmap P4).
  - `bridgeforge compat-set install <set> --runtime <rig> --source-mods <dir>
    [--dry-run] [--json]` installs a named mod set from
    `bridgeforge/compat_sets/standard.json` into an isolated rig:
    - `libs`: LazyLib, MagicLib, LunaLib, GraphicsLib (`shaderLib`).
    - `standard`: the libs plus AI Tweaks, Nexerelin (recorded as needing
      MagicLib for new-game generation), Ship/Weapon Pack, Industrial
      Evolution, Unknown Skies and Tahlan Shipworks.

    It copies only missing or drifted files, never copies rig → source, and
    refuses a rig without a junction.
  - `bridgeforge boot-test --mods … --pack standard` runs a two-leg matrix
    (the target with its libs, then the target plus the whole set) through
    `boot_test.run_boot_matrix`. The verdict is `PASS`, `FAIL_ALONE`,
    `FAIL_WITH_PACK_ONLY` (the interaction class behind this week's
    SEEKER/AI Tweaks and Nexerelin/MagicLib crashes) or `SUSPECT_FATAL_DIALOG`.
- Polish `bridgeforge dossier`:
  - `open_questions` leaves out retain-unchanged and informational findings
    (SAFE or info severity, plus a documented noise-id set such as
    `non-strict-json-trailing-comma`), which stay in the parts.
  - A finding id repeated across ≥3 files collapses to one line with a count
    and a file sample.
  - The index Markdown renders as readable prose and tables, not Python
    reprs.
  - `external-mod-api-import` now carries the real importing file and line,
    not "unknown location".
  - Real effect on Legacy of Arkgneisis: index 25.5 KB → 16.0 KB, open
    questions 62 → 21.
- Add `bridgeforge save-compat <save> <mod_dir> [--vanilla-core] [--compare-old
  X --compare-new Y] [--json]` (roadmap P3b-B, `bridgeforge/save_compat.py`).
  It checks whether an existing save's referenced mod classes are present in
  the build's loaded jars (`LOADS`/`WILL_FAIL`/`UNKNOWN`), reading the save as
  a stream. It resolves XStream's forms verified against real rig saves:
  simple-name element tags, outer+inner concatenation for aliased inner
  classes, and dotted FQNs with `_-` or a literal `$`. Vanilla's short `cl=`
  aliases are never attributed to a mod. `compare_builds` narrows
  `jar-audit`'s removed-class list to the classes a specific save needs. On a
  real Exigency save it reports `LOADS` (14 classes referenced, 0 missing).
- Add `bridgeforge-probe` (roadmap P3): a rig-only in-game evidence-tier-T2
  probe mod (`probe-mod/`), public API only, built with SPW's Tick Marker
  recipe (`javac --release 17` against `starfarer.api.jar`). It does nothing
  unless a `bf_probe_rig` common-file marker is present. The campaign probe
  (an `EveryFrameScript` added from both `onGameLoad` and
  `onNewGameAfterTimePass`, first run after ~1 in-game day via
  `CampaignClockAPI.getElapsedDaysSince`, then every `campaign_interval_days`)
  checks ring-band/orbit finiteness, faction known-list emptiness, submarket
  stock after `updateCargoPrePlayerInteraction()`, per-faction fleet
  presence, tracked custom-entity positions, and planet spec resolution
  (`PlanetSpecAPI` — `StarGenDataSpec`/`PlanetGenDataSpec` are not public in
  this build). The combat probe is a mission (`bfprobe_combat`, a loose
  `MissionDefinition.java` compiled by the game like a vanilla mission) that
  deploys the target mod's hulls alternating on both sides up to a cap, logs
  deployment and a captain-personality WARN (the SK-13 class), lets AI fight
  for a configured duration, then calls `CombatEngineAPI.endCombat`. Every
  result is both a `BF-PROBE|<version>|<check>|<status>|<subject>|<detail>`
  log line and a JSON line appended to a `bf_probe_report` common-file; every
  check is wrapped in try/catch(Throwable) so one broken check never stops
  the rest. `bridgeforge/probe_mod_build.py` compiles and packs the jar
  deterministically (fixed-timestamp `zipfile`, no `jar` tool); a jar-audit
  reuse in `tests/test_probe_mod_build.py` proves it references no
  `java.lang.reflect`/`java.io.File`/`java.nio.file` symbol. `bridgeforge
  probe-config <mod_dir> --runtime <rig_dir> [--install]` builds the config
  from the mod's hull/variant inventory and writes it plus the rig marker
  into `<rig_dir>/saves/common/`, refusing unless `starsector-core` is a
  junction/symlink. `log-triage` now parses `BF-PROBE` lines into a `probe`
  section (counts by status/check, plus the FAIL/WARN list). The save-round-trip
  spike found no public API or Console Commands trigger for a save/load;
  that stays `MANUAL`/T3 (see `probe-mod/README.md`).

- Variant checks now honour a weapon's `.wpn` `mountTypeOverride` (e.g. an
  ENERGY weapon with `HYBRID` fits BALLISTIC slots), and count fighter bays
  added by hull mods (`converted_hangar` +1, whether built in or installed by
  the variant). Found by triaging Legacy of Arkgneisis from its dossier: 16
  false slot mismatches (`loa_flashlight`) and 4 false wings-exceed-bays
  (`loamtp_thatcher`) disappeared, leaving the one real bug (a Vulcan in an
  ENERGY slot on `loa_buffalo_ars_basic`).
- Add `bridgeforge dossier <mod_dir>` (roadmap P2): a deterministic,
  size-capped triage packet for a reviewing agent. It writes a small index
  (`dossier.json`/`.md`) with identity and build tag, an inventory (hulls,
  weapons, wings, systems, factions with known-list sizes, custom planet/star
  types, created star systems, jar classes), all open questions, optional
  `jar-audit`/`copy-drift`/`log-triage` summaries, and a manifest. Findings go
  into numbered parts (`dossier.part-NN.json`/`.md`), each under `--max-kb`.
  Parts are ordered MANUAL > REVIEW > UNKNOWN > SAFE, grouped by file, and
  carry context snippets and whether a `bridgeforge fix` fixer exists. The
  size cap **splits, never truncates**; only a single oversized finding's
  snippet is trimmed, and that is recorded. `--baseline` limits the dossier to
  new findings. It refuses to write its default output into `In operation`
  or `Done`.
- Fix `data-class-reference-missing` for `rules.csv` commands: vanilla keeps
  rule commands in `rulecmd` sub-packages too (e.g.
  `rulecmd.salvage.AddBarEvent`), so a bare command now resolves by simple
  name against any vanilla class under a `.rulecmd.` package. Real false
  positive: Legacy of Arkgneisis's `AddBarEvent`.
- Add `bridgeforge/boot_test.py` (`run_boot_test`), a headless boot test for
  an isolated Starsector rig. It refuses when `starsector-core` isn't a
  junction or symlink (save isolation; NTFS junctions are detected via the
  reparse-point attribute), or when a java.exe under the rig is already
  running (matched by executable path, not name). It backs up and restores
  `enabled_mods.json`, launches through a fully quoted `cmd /c` bat path, and
  polls for the main-menu marker. The result is PASS, FAIL, or
  `SUSPECT_FATAL_DIALOG` (process alive, no menu, since Fatal errors show only
  as a modal dialog). It then terminates the process tree and runs
  `log-triage`.
- Add variant validity checks with skin-aware hull resolution, skipping
  fighter-size hulls: `variant-wings-exceed-bays`, `variant-op-over-budget`
  (tolerance `max(3, 5% of OP)`), and `variant-weapon-slot-mismatch`.
- Add `description-missing` (falls back to vanilla's `descriptions.csv`, read
  leniently because it isn't valid UTF-8) and `asset-reference-missing`.
- Fix `data-class-reference-missing` so it resolves vanilla loose scripts
  under all of `data/**` (not only `data/scripts`), using each file's own
  `package` line when present.
- Add `bridgeforge fix <mod_dir> --finding ID [--apply] [--json]`
  (`bridgeforge/fixers.py`): SAFE, mechanical, surgical-text fixers for eight
  finding ids (`wing-role-assault-removed`, `mod-info-game-version-inexact`,
  `csv-row-extra-columns`, `csv-missing-design-type-column`,
  `procgen-planet-row-missing`/`procgen-star-row-missing`,
  `faction-known-lists-missing`, `mod-info-triage-banner`); any other id is
  refused with the supported list. Dry-run (default) prints a unified diff
  per file and never writes; `--apply` writes the change, keeps a
  `<file>.pre-bf-fix-<id>.bak` backup per pre-existing file (numbered instead
  of clobbering an existing backup), then re-runs `scan_mod` and reports
  whether the finding is gone. `csv-row-extra-columns` only drops trailing
  *empty* extra fields and refuses outright if any extra field is non-empty;
  validated read-only against a copy of FlowerGod's real
  `descriptions.csv.pre-row64-trim.bak` (10-field row), which correctly
  refuses. `faction-known-lists-missing` derives `knownShips`/`knownWeapons`/
  `knownFighters` from the faction's own `shipRoles` variant keys and refuses
  if any resolved hull/weapon/wing id doesn't validate against mod+vanilla
  data (never adds `knownHullMods`).
- Add `bridgeforge prepare-test <working_dir> <rig_mod_dir> [--sync] [--bump]
  [--label BF] [--boot RUNTIME_DIR --mods ID...] [--json]`
  (`bridgeforge/prepare_test.py`): detects a same-folder junction/symlink rig
  ("same folder (junction), nothing to sync"); `--bump` runs
  `apply_build_tag` on the working copy first; runs `copy_drift.compare_copies`
  and, with `--sync`, copies only drifted/missing working -> rig files (never
  the reverse, never deletes rig extras -- it lists them), then requires 0
  drift afterward. `--boot` lazily calls `boot_test.run_boot_test` and
  reports "boot-test module unavailable" instead of crashing if that module
  isn't present. Validated read-only against real rigs: `Flu-X-0.98a` vs its
  `Flu-X-rc8-runtime` junction correctly reports "same folder"; `Done/
  SEEKER-0.98a-workspace` vs the `Flu-X-rc8-runtime` SEEKER rig copy compares
  cleanly in no-sync mode.
- Wire `bridgeforge boot-test <runtime_dir> --mods ID [ID...] [--timeout 240]
  [--log-name NAME] [--keep-mods] [--json]` in `cli.py`, calling
  `boot_test.run_boot_test` via a lazy import and printing its status,
  reason, log path, and triage counts.

- Add `data-class-reference-missing` (MANUAL, critical): every fully qualified
  class named in mod data (hull_mods.csv/ship_systems.csv/submarkets.csv
  `script`, industries.csv `plugin`, weapon_data.csv script-like columns,
  `.system` `statsScript`/`aiScript`, `.wpn`/`.proj` `onHitEffect`/
  `everyFrameEffect`/`onFireEffect`, `rules.csv` bare rule commands,
  `settings.json` `plugins`, and `mod_info.json` `modPlugin`) must resolve to
  a class in the mod's own loaded jars/sources or (when `--vanilla-core` is
  supplied) vanilla; a `com.fs.*` reference with no vanilla core supplied is
  reported UNKNOWN ("vanilla class, unverified") rather than guessed missing,
  and a known third-party library package (org.lazywizard, org.magiclib,
  data.scripts.util.Magic*, org.dark, lunalib, exerelin) is reported UNKNOWN
  ("external dependency, unverified") instead of MANUAL. A row/line commented
  out with `#` is skipped. Real validation: Exigency's disabled
  `combat_radar_plugins.csv` row correctly does not fire. Vanilla loose
  scripts anywhere under `data/**` (e.g. `data/shipsystems/scripts/`) resolve
  when `--vanilla-core` is supplied; without it such references are UNKNOWN,
  not MANUAL.
- Add `hardcoded-hyperspace-coordinates` (REVIEW, low): a hyperspace-touching
  class (`getHyperspace()`/`getLocationInHyperspace`/a waypoint-like list)
  hard-coding 3 or more literal `Vector2f`/`getLocation().set(...)` coordinate
  pairs. Real validation: fires once on Exigency's
  `ExipiratedAvestaMovement` (29 waypoints) and once on Legacy of
  Arkgneisis's `loa_anargaia`; does not fire on commented-out coordinates.
- Add `hardcoded-terrain-grid-size` (REVIEW, low): a literal grid size/mask
  used to index or divide near a `getTiles()` call; skipped entirely for a
  class that already calls `getTileCenter`. Real validation: correctly does
  NOT fire on Exigency's `Tasserus.removePNGFromNebula`, which was already
  fixed to use `getTileCenter` instead of the old 260-tile mask.
- Add `bridgeforge scan --baseline FILE` / `--write-baseline FILE`: writes or
  compares accepted finding keys (id + file + first evidence item) so a
  re-scan reports only new findings plus a count of previously accepted
  findings that are now resolved. Default scan output is unchanged when
  neither flag is given.
- Add scanner checks for a second wave of live-RC8 crash classes: a zero or
  unguarded-computed orbit period passed to `addRingBand`/`addAsteroidBelt`/
  `setCircularOrbit*` (`orbit-period-zero`, `orbit-period-computed-unguarded`
  — the next save throws a non-finite-number crash such as
  `RingBand.writeReplace`; real case: Legacy of Arkgneisis's
  `SpawnChampionRing`), a `SHIP_WITH_MODULES` hull or a `spawnShipOrWing`/
  `spawnFleetMember` call spawning a ship variant (not a wing) whose captain
  can have no personality and NPEs in `Ship.getPersonality()`
  (`module-captain-personality-risk`, `spawned-ship-captain-personality-risk`
  — real case: SEEKER's `ART_*_hulk*` debris spawns), and a `mod_info.json`
  name/description/author still carrying a pre-release triage banner
  (`mod-info-triage-banner`).
- Add `bridgeforge build-tag <mod_dir> [--label BF] [--set N] [--dry-run]
  [--json]` to iterate a visible build number in a revived mod's
  `mod_info.json` `name` (` [BF rN]`) and, when `version` is a string,
  `version` (`+bf.N`). Edits only those two string values in place by regex
  (honoring `"`/`'` quoting) and never re-serializes the file, so comments,
  trailing commas, key order, BOM, and line endings survive untouched; `id`
  and `.version` (version-checker) files are never touched. The result is
  re-parsed with the lenient JSON reader before being trusted.
- Source checks for orbit periods and spawned-ship captains now blank out Java
  `//` and `/* */` comments first (string literals preserved, line numbers
  kept), so commented-out code is no longer flagged. Real false positive: a
  disabled `setCircularOrbit` block in Legacy of Arkgneisis's procgen
  generator. `mod-info-triage-banner` now matches only banner forms (all-caps
  `BROKEN`, a parenthesised `(broken`, `BROEKN`, etc.), so an ordinary name
  such as "Broken Star" isn't flagged.
- Fix `jar-audit --original`/rebuilt-jar detection to sniff zip content (a
  `.class`-bearing zip is a jar; otherwise, a zip containing a `.jar` member
  is used) instead of trusting the file extension, so a real revival backup
  named e.g. `al_arkleg.jar.pre-ring-guard.bak` is accepted.
- Add live-RC8-testing static checks to the scanner: missing procgen
  star/planet rows for campaign-placed `planets.json` types
  (`procgen-star-row-missing`/`procgen-planet-row-missing`), factions missing
  `knownShips`/`knownWeapons`/`knownFighters` (`faction-known-lists-missing`),
  the 0.8a carrier-rework gap (`shiproles-wing-id`,
  `shiproles-obsolete-fighter-role`, `ship-data-missing-fighter-bays-column`,
  `wing-data-missing-role-desc-column`, `wing-role-assault-removed`,
  `wing-op-cost-blank`, `carrier-without-bays-or-wings`), black hole star
  types missing `isBlackHole` (`black-hole-type-missing-flag`), an inexact
  `mod_info.json` `gameVersion` against an RC target
  (`mod-info-game-version-inexact`), and mod files shadowing vanilla data at
  the same path with different bytes (`vanilla-path-shadowing`).
- Add an optional `vanilla_core` scan input (`scan_mod(..., vanilla_core=...)`,
  CLI `bridgeforge scan --vanilla-core`) so the new checks can exempt vanilla
  procgen rows, vanilla faction merge-fragments, and diff against vanilla
  data; every new check degrades gracefully (documented in finding evidence)
  when no vanilla core is supplied.
- Legacy-JSON parsing now also accepts a comma after the root object's closing
  brace (Exigency's shipped faction files end with `},`; Starsector loads them).
  A faction file BridgeForge still cannot parse is reported as
  `faction-file-unparsed` (UNKNOWN) instead of being skipped silently, so an
  unchecked file can no longer read as a clean one.
- `vanilla-path-shadowing` is downgraded to REVIEW/low for mods declaring
  `"totalConversion": true`, where vanilla overrides are expected.
- Add bytecode checks from live RC8 testing, built on a real class-file
  constant-pool parser: `script-sandbox-forbidden-api` (java.lang.reflect,
  java.io.File-family or java.nio.file references, which RC8's script
  classloader rejects at runtime, sometimes mid-combat),
  `bundled-library-classes` (GraphicsLib/LazyLib/MagicLib/LunaLib/Nexerelin
  classes compiled into a mod jar), `vanilla-class-duplicated-in-jar` (a mod
  copy of a vanilla class or loose script, MANUAL when it lacks vanilla public
  methods; new `rulecmd` classes are exempt), and `obfuscated-internal-api-use`.
  Also add `csv-missing-design-type-column` and
  `undeclared-library-dependency`, and extend `vanilla-path-shadowing` to
  loose `.java` scripts.
- Bytecode checks read only the jars Starsector loads: `mod_info.json`'s
  `jars` list, or every jar outside `build/`, `out/`, `tmp/` and `target/`.
  Compile-classpath caches and unloaded legacy jars are skipped.
- Legacy-JSON parsing now accepts Starsector's full org.json dialect:
  single-quoted strings, unquoted keys, bareword values, `//` comments and
  Java number suffixes (`0.5f`). Each accepted tolerance is reported as a SAFE
  informational finding.
- Add workflow commands: `bridgeforge log-triage` (classify a Starsector log
  into FATAL / mod errors / known noise, with the top mod stack frame and
  milestones), `bridgeforge copy-drift` (hash-compare a working copy with its
  deployed test-rig copy), and `bridgeforge jar-audit` (compare a rebuilt jar
  with the original: bundled library packages, removed classes, sandbox-banned
  references). `log-triage` counts a campaign load only from RC8's real
  `CampaignGameManager - Loading <path>` line (absolute paths with spaces
  included). Save-menu descriptor reads and startup mission-variant preloads
  are not treated as progress.
- Add a review-gated bytecode inspection, diff, plan, and apply workflow
  bounded to pinned-ASM class/JAR symbolic remaps written to a separate
  output copy (`bytecode-inspect`, `bytecode-diff`, `bytecode-plan`,
  `bytecode-apply`); see `docs/BYTECODE_BOUNDARY.md`.
- Add read-only ZIP archive intake (`archive-preflight`, `archive-stage`)
  that reports traversal, symlink, duplicate-member, and mod-root ambiguity
  evidence before any extraction, and never writes beside the input archive.
- Add read-only, budget-bounded multi-mod corpus auditing (`corpus-audit`)
  and two-directory release comparison (`release-evaluate`).
- Add local, review-only library API inventory/match research tooling
  (`library-api-inventory`, `library-api-match`) and an opt-in local
  library registry (`--library-registry`) that auto-resolves a mod's
  declared dependency IDs to local JARs for compile validation.
- Add deterministic output-copy JAR packaging after a successful compile
  (`package-jar`), with an input/output SHA-256 manifest confirming the
  source JAR was preserved.
- Bytecode rewriting is therefore no longer an alpha-1 limitation: it is
  available as a narrow, review-gated remap of exact same-descriptor
  symbols only. Library API *transformation* and cross-mod dependency
  graphing remain unimplemented; see the roadmap.

## 0.1.0 — Alpha 1 — 2026-08-31

First public alpha of the read-only Bridgeforge compatibility workflow.

- Scan Starsector mod folders without modifying them and emit Markdown plus
  JSON compatibility artifacts.
- Use evidence-aware JSON, encoding, metadata, archive, bytecode, source, and
  dependency findings; `UNKNOWN` is not a breakage verdict.
- Provide explicit working-copy planning, approval-gated application,
  provenance, conflict, compile, validation, save-risk, and review artifacts.
- Include Windows and Ubuntu CI on Python 3.10–3.12 with Java 17.

### Alpha limitations

- Migration packs are scaffolds only; no library API transformation is shipped.
- Runtime launching, decompilation, bytecode rewriting, and cross-mod analysis
  are not part of this alpha release.
- Scanner output is evidence for review, not proof that a mod will load or
  behave correctly.
