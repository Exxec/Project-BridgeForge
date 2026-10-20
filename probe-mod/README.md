# bridgeforge-probe

Roadmap P3 (`docs/REVIVAL_ASSURANCE_PLAN.md` §P3): an in-game evidence-tier-T2 probe mod, enabled
only on BridgeForge test rigs. It uses only the public, documented Starsector modding API
(`com.fs.starfarer.api.*`), the same pattern SPW's Tick Marker uses
(`Starsector project workbench/spw/agent-mod/`, GPL-3.0, small patterns ported here with
attribution — both projects are GPL-3.0 and stay separate by design).

**Never enabled by accident.** At startup the mod checks for a rig marker common-file
(`bf_probe_rig`, via `SettingsAPI.fileExistsInCommon`). If it is absent, every hook logs one line
(`BF-PROBE disabled: no rig marker`) and does nothing else. `bridgeforge probe-config` is what
writes that marker, only into an isolated rig whose `starsector-core` is a junction/symlink.

## Layout

- `mod_info.json` — id `bridgeforge_probe`, `gameVersion` `0.98a-RC8`, no dependencies.
- `src/com/bridgeforge/probe/*.java` — the compiled mod: `BfProbeModPlugin` (entry point),
  `RigGate`, `ProbeFiles`, `ProbeLog`, `ProbeConfig`, `CampaignProbeScript`, `BfProbeCombatPlugin`.
- `jars/bridgeforge-probe.jar` — built output (regenerate with the build command below; not
  committed by hand-edit).
- `data/missions/bfprobe_combat/` — the combat probe mission: `descriptor.json` plus a **loose**
  `MissionDefinition.java`. Vanilla missions (e.g. `data/missions/hornetsnest/`) ship the same way:
  a loose `data.missions.<id>.MissionDefinition` class the game compiles itself (via the bundled
  Janino compiler) when the mission loads. That means it is **not** part of the jar; it is
  separately test-compiled (see below) against the
  jar's classes to catch API mistakes before a rig run, then shipped as source, same as vanilla.
- `data/missions/mission_list.csv` — this mod's own copy (`mission,` header + `bfprobe_combat,`),
  merged with vanilla's by the game at load, never edits the base game's file.
- `releases/bridgeforge-probe/` — runtime-only release copy (`mod_info.json` + `jars/` + `data/`,
  no `src/`, no build scratch), assembled by `bridgeforge build-probe-mod --install-release`.

## Build

```
.venv\Scripts\python.exe -m bridgeforge build-probe-mod ^
    --jdk "In operation\_rig\jdk-25.0.4.1+1" ^
    --core "C:\Program Files (x86)\Fractal Softworks\Starsector\starsector-core" ^
    --install-release
```

This (`bridgeforge/probe_mod_build.py`):

1. Compiles `probe-mod/src/**/*.java` with `javac --release 17` against `starfarer.api.jar` plus
   the sibling jars whose types the public API surface reaches into (`json.jar` for `org.json.*`,
   `log4j-1.2.9.jar` for `Global.getLogger()`'s return type, `lwjgl.jar`/`lwjgl_util.jar` for
   `Vector2f`) — no obfuscated `starfarer_obf.jar` classes are referenced anywhere.
2. Packs the compiled classes into `jars/bridgeforge-probe.jar` itself, via Python's `zipfile`
   with a fixed per-entry timestamp and sorted entry order, rather than shelling out to the `jar`
   tool — this is what makes two builds from identical sources byte-identical (verified in
   `tests/test_probe_mod_build.py`).
3. Test-compiles the loose mission source against the freshly built classes (catches an API break
   without needing a live rig), but never includes the resulting `.class` in the jar.
4. `--install-release` assembles `releases/bridgeforge-probe/` (runtime-only).

To push it onto a rig: `bridgeforge probe-config <mod_dir> --runtime <rig_dir> --install` (see the
main `README.md` / `docs/REVIVAL_ASSURANCE_PLAN.md` for the full command).

## API facts verified against `starfarer.api.jar` (RC8) via `javap`

- Common-file I/O (never `java.io.File`/`java.nio.file`, both forbidden at class-load by RC8's
  script sandbox): `SettingsAPI.readTextFileFromCommon(String)`, `.writeTextFileToCommon(String,
  String)`, `.fileExistsInCommon(String)`. No extension is appended by the API, so
  `ProbeFiles.RIG_MARKER`/`CONFIG`/`REPORT` (`bf_probe_rig`, `bf_probe_config`, `bf_probe_report`)
  are the literal on-disk file names under the rig's `saves/common/`.
- `org.json.JSONObject`/`JSONArray` (from `json.jar`, not bundled inside `starfarer.api.jar`) are
  on the mod classpath and usable from mod code; `SettingsAPI.loadJSON`/`getSettingsJSON` etc.
  already return them.
- Orbits/rings: `OrbitAPI.getOrbitalPeriod()` is the only public radius/period-shaped getter on
  `OrbitAPI` itself (there is **no public `CircularOrbitAPI`** in this build — `javap` reports
  "class not found" for it). Ring-specific finite values come from `RingBandAPI.getMiddleRadius()`,
  `.getBandWidthInEngine()`, `.getOrbitDays()`. Ring bands are fetched via
  `LocationAPI.getEntities(RingBandAPI.class)` on each `StarSystemAPI`.
- Custom planet/star specs: **`StarGenDataSpec`/`PlanetGenDataSpec` do not exist in the public
  API** for this build (`javap` "class not found" for both). The plan's intent — FAIL when a
  planet's generation spec doesn't resolve — is implemented instead against the public
  `PlanetSpecAPI`, via `Global.getSettings().getSpec(PlanetSpecAPI.class, planet.getTypeId(),
  true)` (the nullable 3-arg form), checked for every planet in every system (vanilla planets
  always resolve, so this is a safe superset rather than the harder "is this type non-vanilla"
  query the public API has no direct way to answer).
- Submarkets: `SubmarketPlugin.updateCargoPrePlayerInteraction()`, `.isOpenMarket()`,
  `.isMilitaryMarket()`, `.isBlackMarket()`; ship/weapon counts via
  `SubmarketAPI.getCargo().getMothballedShips().getNumMembers()` and `.getWeapons().size()`.
- Fleet presence: `LocationAPI.getFleets()` across `SectorAPI.getAllLocations()`,
  `CampaignFleetAPI.getFaction()`.
- Faction known lists: `FactionAPI.getKnownShips()/getKnownWeapons()/getKnownFighters()`.
- Content ids (`content-ids`, probe 0.2.2): `SettingsAPI.doesVariantExist(String)` (boolean) and
  `SettingsAPI.getFighterWingSpec(String)`, both called from RevenantLib 1.2.0+bf.1's RC8-built jar
  (constant-pool Methodrefs, read 2026-09-24; the latter null-checked there, and also wrapped in
  try/catch here in case a missing id throws); `Global.getFactory().createFleetMember(
  FleetMemberType.SHIP, String)`, as `ProbeSetup` already calls it. Building the member resolves the variant's hull,
  weapons and hull mods, so no hull/weapon/hull-mod lookup method is relied on. The ids come from
  `probe-config`'s `content_variants` (`ship`: built; `other`: fighter/module/wreck or non-mod hulls,
  existence only) and `content_wings`.
- Content parity (`content-parity`, 77.17; javap RC8, 2026-10-20): `SettingsAPI.getHullSpec/getWeaponSpec/getFighterWingSpec/getHullModSpec/getIndustrySpec/getMarketConditionSpec(String)`, `getAllSubmarketSpecs()`, `getAllPlanetSpecs()`, `getMergedSpreadsheetData(String idColumn, String path)` (rules.csv ids). `getMergedSpreadsheetDataForMod(String, String, String)` exists, but whether its rows carry a per-row source (`fs_rowSource`) cannot be read from the public interface (that string is only in `starfarer_obf.jar`), so rules are matched by the ids the mod's own rules.csv defines, not by source. Hull, weapon, wing, hull mod, industry, condition and planet specs extend `WithSourceMod.getSourceMod()` (`ModSpecAPI.getId()`), used for the `src_*` counts; `SubmarketSpecAPI` does not.
- Tracked entities: `SectorAPI.getEntityById(String)`, `SectorEntityToken.getLocation()`
  (`org.lwjgl.util.vector.Vector2f`).
- Combat probe: `MissionDefinitionAPI.addToFleet(FleetSide, String variantId, FleetMemberType,
  String name, boolean)` returns `FleetMemberAPI`; `MissionDefinitionAPI.addPlugin
  (EveryFrameCombatPlugin)`; `EveryFrameCombatPlugin`/`BaseEveryFrameCombatPlugin.init
  (CombatEngineAPI)`; `CombatEngineAPI.getShips()`, `.getTotalElapsedTime(boolean)`,
  `.endCombat(float)`, `.isPaused()`; `ShipAPI.getCaptain()` returns `PersonAPI`;
  `PersonAPI.getPersonalityAPI()` (the SK-13 class: captain non-null, personality null).
- Campaign scheduling: `CampaignClockAPI.getTimestamp()`/`getElapsedDaysSince(long)` (used instead
  of accumulating `advance(float)`'s seconds argument, which does not track in-game days under
  time compression); hooked from both `BaseModPlugin.onGameLoad(boolean)` and
  `.onNewGameAfterTimePass()`, guarded by `SectorAPI.hasTransientScript(Class)` so a new game
  never double-registers the script.

No `java.lang.reflect.*`, `java.io.File*`, or `java.nio.file.*` symbol is referenced anywhere in
the compiled jar — verified mechanically in `tests/test_probe_mod_build.py` by reusing
`bridgeforge/jar_audit.py`'s own class-file constant-pool parser (the same one `jar-audit`
already trusts) against the built jar's 13 classes.

## Save round-trip: spike result (MANUAL, stays T3)

Checked whether any public API method or a Console Commands command could trigger a save or a
load programmatically:

- `com.fs.starfarer.api.Global` and `SectorAPI` expose no save/load method anywhere in
  `starfarer.api.jar` (`javap -p` over both interfaces lists none).
- Console Commands 4.0.9's own command registry
  (`In operation/_rig/mods/Console Commands-4.0.9/data/console/commands.csv`) has no
  save- or load-related command; its jar (`jars/*.jar`) has no class under
  `org/lazywizard/console/commands/` whose name references saving or loading a game — the only
  `*Save*`/`*Load*`-named class in the jar is `ConsoleFont$FontLoader`, a font resource loader
  unrelated to campaign saves.

**Conclusion: save/load is UI-driven only** (the Save/Load screens), with no public or
Console-Commands-scripted trigger found. Per the plan, this stays `MANUAL`/T3: a human still
clicks Save and Load once per revived mod. Nothing about this blocks P3's campaign/combat probes,
which never need a save round-trip themselves.

## Save-and-reload fingerprint (opt-in, next probe version, not yet bumped, ROADMAP 75 R6)

`save_reload: {"after_days": N, "slot_note": "..."}` in `bf_probe_config` (written by `probe-group install --save-reload-after-days N
[--save-reload-note ...]`; 0 or absent = off). Classes: `SaveReloadStage` (EveryFrameScript + the after-load hook, one registration line in
`BfProbeModPlugin.onGameLoad`), `FingerprintSections` (canonical text and 64-bit FNV-1a; no `java.security`). At in-game day N it logs
`fingerprint|INFO|phase=before|section=<s>;count=;len=;fnv=` for `markets systems rings fleets player cargo mod totals`, calls
`CampaignUIAPI.cmdSave()` (RC8-30), logs `fingerprint|INFO|save|cmdSave returned true;ts=` and writes `bf_probe_fingerprint` (digests plus
each section's text up to 40,000 chars). On a later load whose campaign clock timestamp equals the stored one it logs the stored digests
(`phase=before`, `source=file`), `phase=after`, `fingerprint|WARN|diff|section=;only_before=;only_after=` per differing section and
`fingerprint|INFO|compare|equal=true;diff=;sections=8` (`FAIL` when not equal). Verified with javap on RC8: `MarketAPI.getId/getFactionId/
getSize/getConditions/getIndustries/getSubmarketsCopy`, `MarketConditionAPI.getId`, `Industry.getId`, `SubmarketAPI.getSpecId`,
`EconomyAPI.getMarketsCopy`, `SectorAPI.getStarSystems/getAllLocations/getPlayerFleet`, `LocationAPI.getFleets/getPlanets/getAllEntities/
getEntities(Class)`, `RingBandAPI.getBandIndex/getMiddleRadius/getBandWidthInEngine/getOrbitDays`, `CampaignFleetAPI.getFleetData().
getMembersListCopy/getCargo`, `FleetMemberAPI.getHullId/getVariant/getStatus/getRepairTracker().getCR`, `ShipVariantAPI.getModuleSlots/
getModuleVariant/getHullVariantId`, `FleetMemberStatusAPI.getHullFraction()/getHullFraction(int)/getNumStatuses/getArmorDamageTaken`,
`CargoAPI.getMaxCapacity/getMaxFuel/getMaxPersonnel/getSpaceUsed/getFuel/getCrew/getSupplies`. **Not exposed to campaign code:** a module's
armor grid (cells or average) - only its hull fraction and the member's one aggregate `getArmorDamageTaken()` are recorded. "Per mod" is
attributed only through the config's own factions, patched factions and `mod_systems` (the `mod` section); there is no API for the owning mod
of an arbitrary market or fleet.

Harness: `probe-group live <ID> --save-reload` plays the normal live run (the drive also waits for the `fingerprint|save` line), then starts the
game a second time under manifest `<ID>-reload`, clicks Continue (RC8-29) and waits for the compare line (`bridgeforge/save_reload_run.py`).
Manual fallback if the click path fails: start the rig game yourself, press Continue (or Load Game and pick the newest save), then run
`run-manifest evaluate` on that log; `milestones.reload_after_save` is read from the log, never set by hand. The campaign is paused after a
load (RC8-28), which does not matter here: the compare runs in `onGameLoad`, before any tick.

## What still needs a live rig run

Everything above compiles and self-checks outside the game (`javac`, deterministic jar packing,
sandbox-clean bytecode scan, `probe-config` writing into a junctioned fixture rig). None of it has
run inside Starsector yet. See the main repo's final report for the exact command sequence.

## Raid scenario mod (`raid-mod/bf_raid`, ROADMAP item 73 G6)

A rig-only loose-script mod, like `capacity-mod` and `duel-mod`, and the only one allowed Nexerelin classes (it depends on `nexerelin`).
It creates one `NexRaidIntel` against the market named in `data/config/bf_raid.json` (inert as shipped) and logs `BF-RAID|raid-start|...`
and `BF-RAID|raid-end|...`. `bridgeforge.raid_run.install_raid_mod(rig, target_market, attacker_faction=...)` copies it into a rig and writes
the config. There is no jar to build; the game compiles the scripts with Janino. To test-compile them against RC8 core and Nexerelin's jar
(read-only, from the install's mods folder): `raid_run.check_raid_mod(jdk, core, raid_run.nexerelin_jar(mods_dir), work_dir)`; 2026-10-14
against Nexerelin 0.12.2d: javac PASS, Janino PASS. Not yet run in the game.
