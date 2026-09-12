# Revival assurance plan (design, 2026-09-11)

**End goal:** revived mods reach players with as few bugs as possible, using as little human testing as possible.

This is a design plan to be turned into roadmap entries. Each phase lists its deliverables, acceptance criteria, dependencies and rough effort, so it can be lifted into `ROADMAP.md` directly.

## 1. Principles

1. **Evidence tiers, cheapest first.** Every issue should be caught at the lowest tier that can catch it:
   | Tier | What it is | Cost |
   |---|---|---|
   | T0 | Static scan | free, seconds |
   | T1 | Automated rig boot | minutes, no human |
   | T2 | In-game probe | one click |
   | T3 | Human play | expensive |

   Human time goes only to what needs judgment: visuals, balance, feel.
2. **Every live bug becomes a permanent check.** No live finding is closed until a scanner check, probe assertion or test covers its bug class, or a written reason says why it can't.
3. **Division of labour:** BridgeForge dissects (exhaustive, deterministic, cheap), the agent judges (semantics, root cause, fix design), and BridgeForge verifies (re-scan, `jar-audit`, `copy-drift`, `boot-test`, build tag).
4. **SPW stays a sibling, not a dependency.** SPW (performance) and BridgeForge (correctness) share no code by design. Both are GPL-3.0, so small helpers and patterns may be ported with attribution. Integration is file-level: one tool reads the other's JSON artifacts.

## 2. What already exists (don't rebuild)

| Capability | Where | Status |
|---|---|---|
| Scan → plan → apply (SAFE-gated) → compile → review → validate pipeline | BridgeForge V0.1–V1.0 | done |
| ~40 RC8 static checks from live testing (procgen rows, known lists, carrier-rework symptoms, sandbox reflection, bundled/duplicated classes, data→class references, orbit periods, module/spawned-captain personality, hard-coded coordinates, design-type column, triage banners, …) | BridgeForge `scanner.py` | done, with 265+ tests |
| Full org.json legacy-JSON dialect | BridgeForge (ported from SPW `lenient_json`) | done |
| `log-triage`, `copy-drift`, `jar-audit`, `build-tag`, scan baselines | BridgeForge | done |
| Generic `runtime smoke` (command + log markers) | BridgeForge `runtime.py` | exists; can't drive Starsector |
| `review-bundle` (plan + compile-feedback handoff) | BridgeForge `review.py` | exists; too narrow for triage |
| `fix` (SAFE fixers), `prepare-test`, `boot-test`, variant validity, description/asset checks | BridgeForge | **in progress (2026-09-11)** |
| In-game helper mod pattern (public `EveryFrameScript`/`ModPlugin`, built `--release 17` against `starfarer.api.jar`) | SPW Tick Marker | done, live-validated in the real game |
| JFR capture/analysis, CPU attribution per mod, startup analysis, benchmark scenarios, `hs_err` crash logs, HTML viewer | SPW | done, live-validated on the ~154-mod install |
| Isolated test rigs (junctioned `starsector-core`, JDK 25, quoted-bat launch) | `In operation/*-rc8-runtime` | done |

## 3. Phases

### P1: Finish the in-flight tooling (S, now)
- **Deliverables:**
  - Merge `fix` / `prepare-test` / `boot-test` / variant validity / description and asset checks.
  - Resolve vanilla loose scripts under all of `data/**` in `data-class-reference-missing`.
  - Re-validate every check on the real mods **with `--vanilla-core`**.
  - Write a baseline file per mod, so accepted findings such as Broken Star's safe orbit stay quiet.
- **Acceptance:**
  - Full suite green.
  - `boot-test` passes against a fake runtime, then one real rig run with owner approval.
  - Each mod's baseline is committed next to its working copy.

### P2: Agent dossier, a review-bundle v2 (S–M)
- **Size cap: split, never truncate (owner decision, 2026-09-11).**
  - A small **index** (`dossier.json`/`.md`) holds the identity, inventory summary, all open questions, artifact summaries and a manifest of parts.
  - **Numbered parts** (`dossier.part-NN.json`/`.md`) are each ≤ the cap (default 40 KB), filled MANUAL → REVIEW → UNKNOWN → SAFE, then by severity, grouped by file.
  - A single finding is never split. An oversized one gets its snippet trimmed, and the trim is recorded.
  - A reviewer reads the index plus usually part-01.
- **Deliverable:** `bridgeforge dossier <mod_dir> [--baseline] [--rig ...] [--log ...]` writes that index and those parts, containing:
  - an inventory: hulls, weapons, wings, factions, systems, jar classes, dependencies, build tag
  - findings **new since the baseline**, each with file:line, ±5 lines of context, evidence, classification, and whether a `fix` fixer exists
  - `jar-audit` versus the original, `copy-drift` versus the rig, and the latest `log-triage` summary
  - "open questions": only the REVIEW/MANUAL items needing judgment
- **Acceptance:** an agent can triage a mod from the dossier plus ≤ 5 targeted file reads. Measure the token use against this week's manual sweeps.
- **Depends on:** P1 baselines.

### P3: In-game probe mod, `bridgeforge-probe` (M–L), the largest cut in human testing
A small Starsector mod enabled only on test rigs. It uses only the public API (the same pattern as SPW's Tick Marker). It writes machine-readable `BF-PROBE` lines to `starsector.log`, and `log-triage` parses them.
- **Campaign probe** (runs `onNewGameAfterTimePass`/`onGameLoad`, then every N days):
  - every ring band and orbit has finite period and radius
  - every non-vanilla faction has non-empty known lists
  - each market's submarkets stock ships and weapons after an update
  - patrol and fleet presence per faction
  - custom-entity movement snapshots (e.g. Avesta's position/waypoint over time)
  - procgen and spec lookups for every custom planet and star type
  - uncaught script exceptions, captured with the owning mod
- **Combat probe:** a mission that spawns every hull of the mod under test on both sides under AI for N seconds, logging any exception with the hull id. It covers ship-system activation, weapons firing, module detach, fighter launch and missile teleport paths.
- **Save round-trip:** spike first. Saving is UI-driven; check whether Console Commands can script save and load. If not, the probe marks it `MANUAL` and T3 keeps it.
- **Would have caught this week:** EX-NEWGAME-02/03, EX-MARKET-01, FLX-KNOWN-01, EX-REFLECT-01 (combat), SK-13 (with AI Tweaks), the ring non-finite crash, and Avesta's route.
- **Human role:** click New Game (and Missions → Probe) once.
- **Acceptance:**
  - The probe reproduces 3 of this week's bugs against their pre-fix backups.
  - It stays silent on vanilla plus the fixed mods.
- **Depends on:** P1 `boot-test`. Reuse SPW's build and release recipe.
- **Implemented (2026-09-11):** `probe-mod/` (id `bridgeforge_probe`, no
  dependencies) built and jar-verified sandbox-clean, but **not yet run
  inside Starsector** — see "still needs a live rig run" below.
  - `RigGate` (`SettingsAPI.fileExistsInCommon("bf_probe_rig")`) gates every
    hook; absent marker logs one line and does nothing else.
  - Campaign probe: `CampaignProbeScript` (`EveryFrameScript`), added from
    both `BaseModPlugin.onGameLoad` and `.onNewGameAfterTimePass`, guarded by
    `SectorAPI.hasTransientScript`. Scheduling uses
    `CampaignClockAPI.getTimestamp()`/`getElapsedDaysSince(long)` rather than
    accumulating `advance(float)`'s seconds (which does not track in-game
    days under time compression): first run after `getElapsedDaysSince >= 1`,
    then every `campaign_interval_days` from `bf_probe_config`. Checks (each
    wrapped in try/catch(Throwable), one broken check never stops the rest):
    rings/orbits (`OrbitAPI.getOrbitalPeriod()`; `RingBandAPI` via
    `LocationAPI.getEntities(RingBandAPI.class)` for `getMiddleRadius()`/
    `getBandWidthInEngine()`/`getOrbitDays()` — **`CircularOrbitAPI` is not
    public in this build**, `javap` reports class-not-found), faction known
    lists (`FactionAPI.getKnownShips/Weapons/Fighters`, for factions owning a
    market), submarket stock (`SubmarketPlugin.updateCargoPrePlayerInteraction()`
    then `SubmarketAPI.getCargo().getMothballedShips().getNumMembers()` /
    `.getWeapons().size()`, WARN on 0 for an open/military/black market of a
    non-vanilla faction), fleet presence per faction
    (`LocationAPI.getFleets()` across `SectorAPI.getAllLocations()`), tracked
    custom-entity positions (`SectorAPI.getEntityById`, always INFO so
    movement is comparable run to run), and planet spec resolution — **this
    deviates from the plan's `StarGenDataSpec`/`PlanetGenDataSpec`, neither
    of which exists in the public API for this build** (`javap` class-not-
    found for both); implemented instead against the public `PlanetSpecAPI`
    via `Global.getSettings().getSpec(PlanetSpecAPI.class, planet.getTypeId(),
    true)` for every planet (a safe superset of "non-vanilla only", since the
    public API has no direct vanilla/non-vanilla query).
  - Combat probe: mission `bfprobe_combat`, a **loose**
    `data/missions/bfprobe_combat/MissionDefinition.java` compiled by the
    game itself (same convention as vanilla's `hornetsnest` etc.), which
    reads `bf_probe_config`, alternates the target mod's hulls onto both
    sides up to `combat_cap_per_side` (default 12, skips logged), and adds
    `BfProbeCombatPlugin` (`EveryFrameCombatPlugin`) via
    `MissionDefinitionAPI.addPlugin`. The plugin logs per-ship hull id, WARNs
    when a ship's captain is non-null but `PersonAPI.getPersonalityAPI()` is
    null (the SK-13 class), then calls `CombatEngineAPI.endCombat(0f)` once
    `getTotalElapsedTime(false) >= combat_seconds`.
  - Output: every result is both a
    `BF-PROBE|<version>|<check>|<status>|<subject>|<detail>` log line
    (`Global.getLogger(...).info(...)`) and a JSON line appended to
    `bf_probe_report`. `log-triage` (`bridgeforge/log_triage.py`) now parses
    `BF-PROBE` lines (always log4j level INFO, regardless of probe status)
    into a `probe` section: counts by status/check, the FAIL/WARN list, and
    whether START/END markers were seen.
  - Build: `bridgeforge/probe_mod_build.py` (`bridgeforge build-probe-mod
    --jdk <jdk> --core <core> [--install-release]`) compiles with `javac
    --release 17` against `starfarer.api.jar` plus `json.jar` (org.json is
    not bundled in `starfarer.api.jar`), `log4j-1.2.9.jar`
    (`Global.getLogger()`'s return type), `lwjgl.jar`/`lwjgl_util.jar`
    (`Vector2f`) — no `starfarer_obf.jar` classes referenced. The jar is
    packed with Python's `zipfile` (fixed per-entry timestamp, sorted
    entries) instead of the `jar` tool, so two builds from identical sources
    are byte-identical (verified in `tests/test_probe_mod_build.py`, which
    also reuses `bridgeforge/jar_audit.py`'s own class-file parser to prove
    none of the 13 compiled classes reference `java.lang.reflect`,
    `java.io.File`, or `java.nio.file`).
  - Rig install: `bridgeforge probe-config <mod_dir> --runtime <rig_dir>
    [--seconds N] [--track ENTITY ...] [--install] [--dry-run]`
    (`bridgeforge/probe_config.py`) builds the config from the mod's own
    `ship_data.csv`/`.variant` inventory (hulls minus MODULE/FIGHTER hints,
    one variant per hull), refuses unless `<rig_dir>/starsector-core` is a
    junction/symlink (reusing `boot_test`'s check), and writes
    `bf_probe_config`/`bf_probe_rig` into `<rig_dir>/saves/common/` (no
    extension appended by the common-file API).
  - `bridgeforge scan probe-mod --vanilla-core ...` is clean of MANUAL
    findings (one accepted REVIEW: `duplicate-source-layout` between
    `data/missions/bfprobe_combat/MissionDefinition.java` and its intentional
    copy under `releases/bridgeforge-probe/`).
  - **Save round-trip spike result:** no save/load trigger exists in the
    public API (`Global`/`SectorAPI` expose none) or in Console Commands
    4.0.9 (`commands.csv` has no save/load command; its jar has no
    `org/lazywizard/console/commands/*Save*`/`*Load*` class). **Stays
    MANUAL/T3** — see `probe-mod/README.md` for detail.
  - **Still needs a live rig run** (nothing above has executed inside
    Starsector): build the release copy, install it plus a config onto a
    real rig, launch, click New Game then Missions → the probe mission, and
    confirm the probe reproduces at least 3 of this week's pre-fix bugs while
    staying silent on vanilla/fixed mods (the plan's acceptance bar).

### P3b: Test-oriented save tooling (S–M; owner-approved 2026-09-11; owner will expand later)
Not a general save editor. `campaign.xml` is ~10 MB of XStream XML with `z=`/`ref=` object links and class aliases (`cl="Sstm"`, mod classes as simple-name elements such as `<ExipiratedAvestaMovement z="…">`). A hand edit can produce a state the game never could, which makes tests meaningless, or an unloadable save. So the tooling **reads** saves, and **state changes happen inside the game** through the probe.
- **B. `save-compat <save> <mod>` (first, DONE — `bridgeforge/save_compat.py`, `check_save_compat`/`compare_builds`):** enumerates the mod classes a save references (resolving aliases, including inner-class forms like `ExipiratedAvestaMovementWaypoint`) and checks each against the build's loaded jars. Output: `LOADS` / `WILL_FAIL` (+ missing classes) / `UNKNOWN`. Real motivation: rebuilding Arkgneisis from its bundled `src/` would have dropped jar-only classes and broken existing saves. Pairs with `jar-audit` ("removed classes that saves reference"), via `compare_builds`.
  - **Verified alias rules** (read against real rig saves, `In operation/_rig/saves/`): a class can appear (1) as an **element tag** — the mod's simple name when it registered an alias that way (`<ExipiratedAvestaMovement>`), the **outer+inner concatenation with no separator** for an aliased inner class (`<ExipiratedAvestaMovementWaypoint>` for `ExipiratedAvestaMovement$Waypoint`), or the **dotted FQN with `$` escaped as `_-`** when unaliased (confirmed on vanilla's own `com.fs.starfarer.api.impl.campaign.shared.WormholeManager_-WormholeData`); or (2) as a **`cl="..."` attribute** on a field whose declared and actual types differ — a short cryptic vanilla alias (`cl="Sstm"`, `cl="Plnt"`, `cl="CCEnt"`, ...; never decodable without a curated table and never treated as belonging to a mod), the mod's own simple name (`cl="ExipiratedAvestaSubmarketPlugin"`), or the dotted FQN **with a literal `$`** when unaliased (`cl="com.fs.starfarer.campaign.util.CollectionView$1"`, `cl="lunalib.backend.scripts.LunaCampaignRendererEntity"`). Anonymous inner classes (`Outer$1`) only ever get the two FQN forms. Attribution to "this mod" is by exact alias match against the build's own class index, or (for classes the build removed entirely) by dotted-package-prefix match against the mod's *surviving* classes; anything else goes to `limitations`, never a guessed pass/fail.
  - **Validation:** `save_FourthAnderson_*` against `Exigency-0.7.2-assessment` → `LOADS`, 14 referenced classes, 0 missing, 0 ambiguous. The same save against a temp copy with `EXI.jar.pre-route-fix.bak` swapped in → still `LOADS` (route/reflection fix kept class names, as expected). A SEEKER save (`save_TrangThisbe_*`) against `Done/SEEKER-0.98a` with `vanilla_core` set → `UNKNOWN`: grepping the raw save confirms Seeker's own footprint there is plain **text content** (`<st>ART_organicHull</st>`, `<modPluginClassName>data.scripts.SKR_modPlugin</modPluginClassName>`), not live object-graph class references — correctly out of scope for a class-reference tool, and correctly reported as "can't tell" rather than a guess.
- **A. `save-inspect <save> [--diff <save2>] [--track ENTITY|CLASS …]`:** a streaming read of tracked state: entity locations and script fields (Avesta's `waypoint`/`progress`/`loitering`), faction known-list sizes, market submarket stock, fleet members' and modules' hull/armour. `--diff` compares two saves, e.g. before and after 30 days.
- **D. `save-snapshot {tag|list|restore}`:** copies rig saves under `<rig>/saves/` tagged by build tag; restore stays within the rig. Refuses a non-junction rig.
- **C. Probe setups (extends P3):** `probe-config --setup rep:<faction>=<level> --setup credits:N --setup ship:<variant> --setup spawn-fleet:<faction>:<fp> --setup jump:<system>`, applied once via the public API when the rig marker is present.
- **Closes most of the save-round-trip gap P3 can't automate:** the probe applies a setup, a human saves and quits (the one manual step), `save-inspect`/`save-compat` verify persistence, and `save-snapshot` keeps the starting point.
- **Excluded:** direct XML editing. At most a last resort on copies, validated by a rig load test.
- **Order:** B → A → D → C.

### P4: Standard compatibility pack (S)
- **Deliverable:**
  - A named mod set for every boot and probe run: AI Tweaks, Nexerelin with MagicLib, LunaLib, GraphicsLib, plus 3–5 popular content mods.
  - `boot-test --pack standard` runs each revived mod alone and then with the pack.
  - A matrix report.
- **Why:** both of 2026-09-11's crashes only appeared alongside other mods.
- **Acceptance:** the SK-13 NPE reproduces, or is ruled out, automatically.
- **Implemented (2026-09-11):**
  - `bridgeforge/compat_sets/standard.json` (data, not code) declares two named sets, resolved by
    `bridgeforge/compat_sets.py`'s `resolve_set` (`standard` `extends: ["libs"]`, its own entries win on
    conflict):
    - `libs`: `lw_lazylib` (LazyLib), `MagicLib`, `lunalib` (LunaLib), `shaderLib` (mod id of "zz
      GraphicsLib" — GraphicsLib's actual `mod_info.json` id in the owner's real install).
    - `standard` (libs plus): `aitweaks` (AI Tweaks — the SK-13 repro target), `nexerelin` (records
      `required_by`: MagicLib, needed to reach new-game sector generation — the real RingBand-crash
      finding this week), and four content mods actually present in the owner's real install at RC8 or
      a compatible generic `0.98a`: `swp` (Ship/Weapon Pack, RC8), `IndEvo` (Industrial.Evolution,
      `0.98a`), `US` (Unknown Skies, RC8), `tahlan` (Tahlan Shipworks, `0.98a`). Diable Avionics was a
      candidate but its installed copy declares `gameVersion: 0.98a-RC5`, so it was excluded rather than
      assumed compatible.
  - `bridgeforge compat-set install <set> --runtime <rig> --source-mods <dir> [--dry-run] [--json]`
    resolves each set id to a folder in `--source-mods` by reading `mod_info.json` ids with the same
    lenient reader as the scanner (`scanner._load_lenient_json_file`), refuses unless
    `<rig>/starsector-core` is a junction/symlink (`boot_test._is_link`), and only ever copies
    source → rig. A mod already byte-identical in the rig (`copy_drift.compare_copies`, status `PASS`)
    is skipped; a drifted or partially-present mod copies only its missing/different files, never
    touching rig-only extras; a wholly absent mod is copied in full. It warns (never blocks) when a
    source mod's declared `gameVersion` doesn't exactly match the rig's inferred RC (there is no single
    canonical version file inside an isolated rig, so the rig's RC is inferred as the most common
    `0.98a-RCn` already found in the rig's own `mods/*/mod_info.json`).
  - **Dry-run plan against the real rig** (`In operation/_rig`, real install's `mods/` as
    source, 2026-09-11): the rig already carries LazyLib, MagicLib, LunaLib, GraphicsLib, AI Tweaks and
    Nexerelin byte-identical to the real install (all reported `skipped_identical`), and would copy in
    the four content mods it doesn't have yet — Industrial.Evolution, Unknown Skies, Ship/Weapon Pack,
    Tahlan Shipworks. It also warned (correctly) that MagicLib/LunaLib/LazyLib/IndEvo/Tahlan declare an
    older or generic `gameVersion` than the rig's inferred `0.98a-RC8`; nothing was written (dry-run).
  - `boot_test.run_boot_matrix(runtime_dir, target_mods, pack, timeout=240, log_name=None,
    compat_sets_path=None)` (new; `run_boot_test`'s own signature is unchanged and still used directly
    by every other caller) runs two sequential `run_boot_test` calls: **(a) "alone"** — the target mods
    plus only the pack's `role: "lib"` members the target actually declares as a dependency in its own
    `mod_info.json` (read from the rig's `mods/`; falls back to every lib in the pack if the target's
    `mod_info.json` can't be found, so this stays a safe default rather than silently dropping a needed
    library) — and **(b) "with_pack"** — the target plus every id in the resolved pack. Each
    `run_boot_test` call restores `enabled_mods.json` itself, so the rig's `enabled_mods.json` is back to
    its original content once the matrix returns (verified by a test). The overall verdict is `PASS`
    (both boots reach the main-menu marker), `FAIL_ALONE` (the target itself doesn't boot — not a pack
    problem), `FAIL_WITH_PACK_ONLY` (passes alone, fails with the pack — the interesting interaction
    bug class this phase exists for), or `SUSPECT_FATAL_DIALOG` (either run is stuck alive past timeout
    with no marker, propagated as-is since a Fatal Error dialog is never provable from a redirected
    log). Wired into the CLI as `bridgeforge boot-test <runtime_dir> --mods ... --pack standard`
    (`--pack` is optional; omitting it keeps today's single-run `boot-test` behaviour unchanged).
  - Tests: `tests/test_compat_sets.py` (set resolution/`extends`, refusal on a non-junction rig,
    dry-run plan, real copy vs. skip-identical, source directory never written to, `gameVersion`
    mismatch warnings, a CLI dry-run smoke test) and `tests/test_boot_test.py`'s new
    `BootMatrixTests` (a fake rig + fake launcher that reads `mods/enabled_mods.json` and only writes
    the main-menu marker when a pack-only id is absent, proving `FAIL_WITH_PACK_ONLY`; a pass/pass case;
    a `FAIL_ALONE` short-circuit case; `enabled_mods.json` restoration after the matrix).
  - **SK-13 repro, next steps (not yet run — no Starsector launch performed by this phase's own tests):**
    1. `bridgeforge compat-set install standard --runtime <rig> --source-mods "<real install>\mods"`
       (drop `--dry-run` once the plan above is reviewed) to bring the rig's copies up to date.
    2. `bridgeforge boot-test <rig> --mods SEEKER --pack standard` — this proves SEEKER boots alone and
       boots (or doesn't) with the full standard pack enabled. It does **not** reproduce SK-13's
       combat NPE by itself: SK-13 is a `CombatFleetManager.deployAll` NPE that needs a live combat
       deployment of a captained SEEKER hull (Betelgeuse), which a boot-to-main-menu test never
       triggers. The actual combat repro needs the P3 combat probe mission
       (`bridgeforge probe-config SEEKER --runtime <rig> --install`) run with SEEKER plus the standard
       pack enabled, so `BfProbeCombatPlugin`'s existing null-personality WARN check
       (`docs/REVIVAL_ASSURANCE_PLAN.md` §P3) fires against a rig that actually has AI Tweaks loaded.

### P5: Change-impact test selection (M)
- **Deliverable:** `bridgeforge test-plan <mod> --since <build-tag>`:
  - diffs the working copy against the file hashes recorded at that tag
  - maps changed files to features (faction file → markets and fleets; `.system` → ship system; worldgen class → new game)
  - outputs the minimal `LIVE_TEST_INSTRUCTIONS` IDs plus the probe assertions to re-run
- **Acceptance:** for this week's fixes it selects the same tests a human chose, and nothing that's clearly unrelated.
- **Depends on:** `build-tag` recording a per-tag hash manifest (a small extension).

### P6: SPW performance gate (S, file-level integration)
- **Deliverable:**
  - After a mod passes correctness, run SPW `diagnose --level STANDARD` on the rig with the mod enabled.
  - BridgeForge `dossier` ingests SPW's `performance-report.json`, covering per-mod CPU share, heavy every-frame scripts and startup time.
  - It also ingests `log-triage`'s log-spam counts, e.g. Arkgneisis logs `loa_awacs_order_manager … advance called with null engine` every frame.
- **Acceptance:**
  - A regression threshold is agreed with the owner.
  - No code dependency between the repos.

### P7: Bug-class registry and knowledge capture (S, ongoing)
- **Deliverable:** `docs/BUG_CLASSES.md`, one row per live-found class, giving its symptom, root cause, the BridgeForge check or probe assertion, a test, and the first mod it hit.
- Move the durable conventions out of `In operation/STATUS.md` into `docs/`.
- Add the rule from Principle 2 to `AGENTS.md`.
- **Acceptance:** every 2026-09-08..11 finding maps to a row.

### P8: Release pipeline (M)
- **Deliverable:** `bridgeforge release <mod>`, which:
  - requires a clean scan against the baseline, `jar-audit` versus the original (no library or vanilla classes, class count explained) and the final build tag
  - builds a forward-slash zip
  - produces the `Done/` layout with source and backups excluded
  - applies a licence gate (e.g. Exigency: **local only, never packaged for release**)
  - writes a release note from the build-tag deltas
- **Acceptance:** re-packaging SEEKER reproduces today's `Done/SEEKER/SEEKER-0.98a.zip` layout.

## 4. Suggested order and effort

P1 (now) → P2 → P3 (spike the save round-trip first) → P4 → P7 (in parallel, cheap) → P5 → P6 → P8.

The biggest payoff for the least effort is P2 then P3. P2 cuts agent cost per mod; P3 turns most of the T3 matrix into T2.

## 5. Risks and limits

- **Static and probe checks can't prove behaviour** that depends on the player's eye. The nebula placement and the black-hole look still need T3.
- **The probe mod runs inside the game,** so it must never ship to players or be enabled outside a rig. Give it a distinct id and refuse to run without a rig marker file.
- **New-game creation is UI-driven.** Full automation may be impossible without Console Commands, so plan for one human click.
- **Keep SPW and BridgeForge separately useful.** Integrate only through artifacts.
