# Changelog

## Unreleased

- Fix the CI failures of the 0.2.0 push.
  - `test_prepare_test` imported the Windows-only `_winapi` unguarded, which broke Linux.
  - The boot-test launch and matrix tests are now Windows-only, since they launch a `.bat`.
  - Five tests now resolve their temp dirs, because GitHub's Windows runners use 8.3 short paths (`RUNNER~1`).
- `test_probe_mod_build` no longer deletes the real `probe-mod/releases/bridgeforge-probe` copy that `probe-config --install` ships. It parks and restores it.
- `rig-doctor` finds working copies by the folder convention (`In operation/<Mod>/working`, then `Done/<Mod>/<release>`) instead of a hard-coded list. The test rig is now `In operation/_rig`.

## 0.2.0 — 2026-09-11

Everything landed since the `v0.1.0-alpha.1` tag. The package moves to `0.2.0`, and the
`bridgeforge-probe` mod to `0.2.0` (it gained `ProbeSetup` and `ProbeProfile`). Its `BF-PROBE|0.2.0|…` lines show which probe build produced a log.

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
