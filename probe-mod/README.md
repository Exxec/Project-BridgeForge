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
  Janino compiler) when the mission loads. That means it is **not** part of the jar and is not
  javac'd by BridgeForge's build step — it is separately test-compiled (see below) against the
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

## What still needs a live rig run

Everything above compiles and self-checks outside the game (`javac`, deterministic jar packing,
sandbox-clean bytecode scan, `probe-config` writing into a junctioned fixture rig). None of it has
run inside Starsector yet. See the main repo's final report for the exact command sequence.
