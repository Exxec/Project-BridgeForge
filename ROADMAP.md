# Project Bridgeforge roadmap

Bridgeforge follows the project charter in `docs/PROJECT_CHARTER.md`: understand first, modify second, validate always. The original mod is never changed in place.

## Revival assurance track (2026-09-11)

Goal: revived mods reach players with the fewest bugs for the least human testing. The full design is in `docs/REVIVAL_ASSURANCE_PLAN.md`. **How to use the tools: `docs/BRIDGEFORGE_REVIVAL_GUIDE.md`.** Further P3b save-tooling ideas for review: `docs/P3B_SAVE_TOOLING_RECOMMENDATIONS.md`. **P2 polish is done (2026-09-11):** noise-free, collapsed open questions; readable Markdown; a real location for `external-mod-api-import`; the Arkgneisis index went from 25.5 KB and 62 questions to 16.0 KB and 21. Evidence tiers, cheapest first: static scan → automated rig boot → in-game probe → human play. Every live-found bug becomes a permanent check. SPW (`Exxec/SPW`, performance) stays a separate program and integrates through artifacts only.

Order: P1 → P2 → P3 (spike the save round-trip first) → P3b (save tooling: B → A → D → C) → P4 → P7 (in parallel) → P5 → P6 → P8. **All implemented as of 2026-09-11; next is the first live run.** Then P3c (ease-of-use setup: profiles → Console Commands → LunaLib).

1. **P1: Finish the in-flight tooling.** `fix` (SAFE fixers only, dry-run by default), `prepare-test`, `boot-test` (quoted-bat launch, main-menu marker, flags a suspected Fatal dialog), variant validity (OP budget, wings vs bays, weapon slots), `description-missing` / `asset-reference-missing`, vanilla loose-script resolution under all of `data/**`, and per-mod scan baselines.
   Acceptance: suite green; real-mod validation with `--vanilla-core`; one owner-approved real rig boot.
   **Status: implemented 2026-09-11 (329 tests green).** `fix` (8 SAFE fixers), `prepare-test`, `boot-test` (CLI and module verified end to end on the save-isolation refusal path, without launching), the variant validity checks, `description-missing`/`asset-reference-missing`, and vanilla loose-script resolution have landed, together with the earlier data→class references, hard-coded coordinates/grid, baselines, orbit-period and captain-personality checks, triage banners, `build-tag` and comment-aware source checks.
   **Remaining:** one owner-approved real rig `boot-test` run; per-mod baseline files; triage of the new variant/description findings (table in `In operation/STATUS.md`).
2. **P2: Agent dossier (review-bundle v2).** `bridgeforge dossier <mod>`: size-capped JSON + Markdown covering the inventory, findings new since the baseline (with code context and available fixers), `jar-audit`, `copy-drift`, the latest `log-triage`, and the open judgment questions.
   Acceptance: a mod can be triaged from the dossier plus ≤5 file reads.
   **Status: implemented and accepted 2026-09-11 (340 tests green).** Acceptance passed: Legacy of Arkgneisis was triaged from its dossier index plus 3 targeted reads, finding one real bug (LOA-VAR-01, a Vulcan in an ENERGY slot) and two check gaps. The gaps were fixed: `mountTypeOverride`, and bays added by hull mods. Validation dossiers: Arkgneisis index 25.5 KB + 2 parts; Exigency 16.5 KB + 1; SEEKER 10.2 KB + 2; every part under the 40 KB cap, nothing dropped.
   **Polish follow-ups (from real use):**
   - Keep SAFE-ish "retain unchanged" notes (e.g. `non-strict-json-trailing-comma`) out of `open_questions`.
   - Collapse a finding id repeated across many files into one line with a count and a file list.
   - Render inventory and artifact dicts as readable Markdown, not Python reprs.
   - Give `external-mod-api-import` a real file location, not "unknown location".

   These would also shrink the 25 KB Arkgneisis index.
   Earlier progress note (started 2026-09-11): `bridgeforge dossier` is being built (versioned JSON + Markdown, baseline-filtered findings with context snippets and fixer availability, `jar-audit`/`copy-drift`/`log-triage` summaries, open questions). **Size cap splits rather than truncates (owner decision):** a small index (identity, inventory summary, all open questions, and a manifest of parts), plus numbered parts each under the cap. MANUAL findings are in part-01, findings are grouped by file, and nothing is dropped. Acceptance test: triage Legacy of Arkgneisis's open variant findings from its dossier.
3. **P3: In-game probe mod (`bridgeforge-probe`).** Public API only, reusing SPW's Tick Marker build recipe. It emits `BF-PROBE` log lines that `log-triage` parses.
   - Campaign probe: finite ring/orbit values, faction known lists, market stock, patrol presence, entity movement, procgen spec lookups, script exceptions.
   - Combat probe mission: every mod hull under AI.
   - Save round-trip: spike needed.
   - Rig-only, behind a marker file.

   Acceptance: reproduces ≥3 of this week's bugs from pre-fix backups, and is silent on vanilla plus the fixed mods.
   **Status: implemented and statically verified 2026-09-11; live rig run pending.**
   - `probe-mod/`: 13-class jar, deterministic build, zero reflection/file-API references (checked independently); BridgeForge scan: 0 findings.
   - CLI: `bridgeforge build-probe-mod` and `probe-config --install`; `log-triage` gained a `probe` section. Suite: 360 green.
   - API facts: `CircularOrbitAPI` and `StarGenDataSpec`/`PlanetGenDataSpec` are not public in RC8 (it uses `OrbitAPI.getOrbitalPeriod`, `RingBandAPI` and `PlanetSpecAPI` instead).
   - Save round-trip: no public API or Console Commands trigger exists, so it stays manual (T3).
   Design decisions:
   - Vanilla API only (no reflection or file APIs, which the RC8 sandbox forbids).
   - A rig-only gate via a `bf_probe_rig` marker read through Starsector's common-file API (`saves/common`, inside the isolated rig), so it does nothing on a player's install.
   - `bridgeforge probe-config` writes the target hulls, variants and tracked entities from the dossier inventory.
   - Results go to `BF-PROBE|…` log lines, parsed by `log-triage`, plus a `bf_probe_report` common file.
   - Built the way SPW's Tick Marker is.
   - Save round-trip: spike only. Console Commands 4.0.9's command list shows no save or load command.
3b. **P3b: Test-oriented save tooling (owner-approved 2026-09-11; owner will expand later).** Not a general save editor. Saves are ~10 MB XStream XML with `z=`/`ref=` object links and class aliases, and hand edits can create states the game can't produce, so tests against them prove nothing. Mostly read-only; state changes happen inside the game.
   - **B. `bridgeforge save-compat <save> <mod>`** (read-only, FIRST): lists every mod class a save references and checks it against the build's jar. Answers "will this build load existing saves?" and catches the Arkgneisis "rebuild drops classes → `CannotResolveClassException`" trap; pairs with `jar-audit`. Needs research: saves reference mod classes by alias (e.g. `<ExipiratedAvestaMovement z="…">`, and `ExipiratedAvestaMovementWaypoint` for an inner class), so aliases must map back to jar FQNs.
   - **A. `bridgeforge save-inspect <save> [--diff <save2>]`** (read-only): streams the save and reports tracked mod state (entity positions and script fields such as Avesta's `waypoint`/`progress`/`loitering`; faction known lists; market stock; fleet members' and modules' hull/armour), with a diff across two saves.
   - **D. `bridgeforge save-snapshot`** (rig-only file copies): tag, list and restore rig saves by build tag, giving reusable test starting points.
   - **C. In-game test setups via the P3 probe** (`probe-config --setup …`): reputation, credits, ships, a nearby enemy fleet, a player jump. Applied through the public API so every state is game-valid; removes setup grind (EX-5 rep gating, SK-6c damaged modules).
   - **Expansion (owner-approved 2026-09-11, from `docs/P3B_SAVE_TOOLING_RECOMMENDATIONS.md`):**
     - E. `save-content`: data ids stored as strings (hulls, variants, weapons, wings, hull mods, factions, commodities, industries, conditions, special items), checked against the build plus vanilla.
     - F. `save-scripts`: a duplicate-script and listener audit (scripts re-added on every load).
     - G. `save-growth`: per-mod object and size growth across a save chain.
     - H. `save-provenance`: which mod versions and BF build tags made the save, against the current working copies.
     - I. `save-removal`: "can this mod be removed mid-campaign?" (internal only).
     - J. Dossier `--save` runtime footprint.
     - K. Named scenarios, each with expected results (`scenario plan|check`).
     - L. `save-summary`: a redacted, shareable bug-report summary with no player data (local file only).
     - M. A save corpus under `In operation/save_corpus/<mod-id>/` (local only), re-checked as a release gate (P8).
   - Order: B → E → A → F → H → D → C → K → G → I → J → L → M. Direct XML editing is excluded; at most a last resort on copies, validated by a rig load test.
   **Status: B implemented 2026-09-11** (`bridgeforge save-compat`, `bridgeforge/save_compat.py`, 8 tests). Alias rules were verified on real rig saves: simple-name tags, outer+inner concatenation, dotted FQNs with `_-`/`$`, and vanilla short `cl=` aliases excluded. Real Exigency save: `LOADS`, CLI exit 0.
   **Status: A, C, D, E, F, G, H, I, K and L implemented 2026-09-11** (CLI wired; validated read-only on real rig saves).
   - A: `save-inspect` and `save-diff` (objects matched by path, since XStream `z=` ids aren't stable).
   - F: `save-scripts`.
   - G: `save-growth`.
   - H: `save-provenance` (Exigency save: `STALE_BUILD`, recorded `0.7.2` against the working copy's `0.7.2+bf.1`).
   - E: `save-content` (SEEKER: `LOADS`).
   - I: `save-removal` (internal only).
   - L: `save-summary`.
   - D: `save-snapshot`.
   - C: `probe-config --setup`, with `ProbeSetup` in a 15-class sandbox-clean jar. RC8 has no public `FleetFactoryV3`.
   - K: `scenario list/plan/check`.
   J (dossier `--save`) and M (corpus gate) ship with P6/P8. C and K still need their first live rig run.
3c. **P3c: Ease-of-use test setup (owner-approved 2026-09-11).** Three front ends to the same `ProbeSetup` engine (P3b-C), so every path applies state through the public API only. A desktop GUI for all of BridgeForge was considered and dropped (owner, 2026-09-11).
   **Order: 1 → 2 → 3, each after the previous one's first live run confirms `ProbeSetup` works.**
   **Status: step 1 (profiles) implemented 2026-09-11, ahead of the live run at the owner's request.**
   - `probe-config --profile`, bundled profiles, and the Java `ProbeProfile` parser (16-class jar, sandbox-clean).
   - The rig file `saves/common/bf_probe_profile` replaces the setups; a leftover one is retired to `.prev` when a later run has no profile.
   - Steps 2 and 3 wait for the first live run.
   1. **Editable setup profiles (text files).**
      - A commented, Notepad-friendly file with one setup per line, e.g. `rep exipirated = FRIENDLY`, `credits = 500000`, `ship ART_dimention_manipulator x1`, `spawn pirates 120`, `jump Corvus`, plus `# comments`.
      - Profiles live in `bridgeforge/probe_profiles/*.txt` (bundled examples: one per scenario), or any path you give.
      - `probe-config --profile <file>` validates the file with the existing `validate_setup_spec` (a line number with each error) and writes it into the rig's `saves/common`.
      - The probe also re-reads a rig-side `bf_probe_profile` common file at every new game, so you can edit it and start a new game with no CLI step.
      - Options per profile: `apply = once-per-save | every-load`, and `enabled = true/false` per line.
      - Sandbox: `SettingsAPI.readTextFileFromCommon` only, with no file APIs.
      - Tests: the parser, line-numbered errors, and a round trip against `--setup`.
   2. **In-game commands through Console Commands** (soft dependency; `lw_console` 4.0.9 is in the rig).
      - The probe mod ships `data/console/commands.csv` (header `command,class,tags,syntax,help`; Exigency and Void-Tec use the same format) with classes implementing `org.lazywizard.console.BaseCommand`.
      - Commands, available any time in the campaign and not just once per save:
        - `bfsetup <spec>`, e.g. `bfsetup rep exipirated FRIENDLY`
        - `bfprofile <name>` (apply a profile)
        - `bfprobe run` (run the campaign probe now)
        - `bfprobe status` (what was applied and when)
      - Build: compile the command classes against `lw_Console.jar`. Console Commands loads them only when present, so the probe still runs without it. Verify this with a rig boot that has Console Commands disabled.
      - Every command logs `BF-PROBE|…|setup|…` as usual, so `log-triage` and `scenario check` work unchanged.
   3. **In-game settings screen through LunaLib (optional)** (soft dependency; LunaLib 2.0.5 is in the rig).
      - A `data/config/LunaSettings.csv` (header `fieldID,fieldName,fieldType,defaultValue,secondaryValue,fieldDescription,minValue,maxValue,tab`) for simple values:
        - on/off toggles: probe enabled, campaign probe, combat log detail, apply the profile at new game
        - numbers: probe interval in days, combat seconds, combat cap
        - a `Radio` or `String` field choosing the active profile
      - Lists (ships, reputation for several factions) stay in profiles (1), because LunaLib fits them poorly.
      - Values are read through LunaLib's settings API only when `lunalib` is enabled; otherwise `bf_probe_config` still governs.
      - Verify the exact LunaLib method names with javap against `LunaLib.jar` before building.
   - **Guardrails (all three):**
     - Still rig-gated by the `bf_probe_rig` marker, so none of it does anything on a player install.
     - Nothing writes saves directly.
     - Each command, profile line and setting maps 1:1 onto an existing `--setup` spec, so there is one validation path.
     - The jar must stay sandbox-clean (constant-pool scan in its tests).
4. **P4: Standard compatibility pack.** `boot-test --pack standard` runs each mod alone and then with AI Tweaks, Nexerelin+MagicLib, LunaLib, GraphicsLib and a few popular content mods, producing a matrix report.
   Acceptance: the SK-13 AI Tweaks NPE is reproduced or ruled out automatically.
   **Status: implemented 2026-09-11 (376 tests green).** `bridgeforge/compat_sets/standard.json` (data)
   + `bridgeforge/compat_sets.py`: `libs` (`lw_lazylib`, `MagicLib`, `lunalib`, `shaderLib`/GraphicsLib)
   and `standard` (`extends` libs, plus `aitweaks`, `nexerelin`, and four content mods verified present
   in the owner's real install at RC8 or a compatible `0.98a`: `swp`, `IndEvo`, `US`, `tahlan`; Diable
   Avionics excluded, its installed copy is RC5). `bridgeforge compat-set install <set> --runtime <rig>
   --source-mods <dir> [--dry-run] [--json]` copies only what's missing/drifted (never rig → source),
   refuses off a non-junction rig, warns (doesn't block) on a `gameVersion` mismatch. Dry-run against
   the real rig (`In operation/_rig`): libs/AI Tweaks/Nexerelin already identical, would
   add Industrial.Evolution/Unknown Skies/Ship_Weapon Pack/Tahlan Shipworks. `boot_test.run_boot_matrix`
   (new; `run_boot_test`'s signature unchanged) runs the target alone with the libs it declares, then
   with the whole pack, restoring `enabled_mods.json` after each leg; verdict `PASS` /
   `FAIL_ALONE` / `FAIL_WITH_PACK_ONLY` / `SUSPECT_FATAL_DIALOG`. Wired as `boot-test <rig> --mods ...
   --pack standard`. **SK-13 next step:** `compat-set install standard` then `boot-test <rig> --mods
   SEEKER --pack standard` proves the boot; the combat NPE itself still needs the P3 combat probe run
   with SEEKER plus the pack (a boot-to-main-menu test never deploys a hull into combat).
5. **P5: Change-impact test selection.** `bridgeforge test-plan <mod> --since <build-tag>` maps changed files to features and returns the minimal live-test IDs and probe assertions. It needs `build-tag` to record a per-tag hash manifest.
   **Status: implemented 2026-09-11.**
   - `bridgeforge/test_plan.py` (data-driven rules table) is wired as `test-plan <mod> --since rN`.
   - `build-tag` and `prepare-test --bump` record manifests by default, stored outside the mod in `bridgeforge-state/build-manifests/`.
   - Validated on a copied Arkgneisis tree: a touched faction file mapped to markets and fleets.
   - Manifests start with the next `build-tag`. Tags made earlier have no manifest to diff against.
6. **P6: SPW performance gate.** Run SPW `diagnose --level STANDARD` on the rig after correctness passes; the dossier ingests SPW's `performance-report.json` and log-spam counts.
   Acceptance: an owner-agreed regression threshold.
   **Status: implemented 2026-09-11 (file-level only).**
   - `bridgeforge/spw_bridge.py` is wired as `perf-gate`; the dossier gains `--perf`.
   - It is report-only until the owner sets thresholds. The report reader is schema-tolerant because SPW's report schema is still only a design document.
   - Acceptance still needs owner-agreed thresholds and a real SPW report.
7. **P7: Bug-class registry.** `docs/BUG_CLASSES.md` gives one row per live-found class (symptom, cause, check or probe assertion, test, first mod). Durable conventions move from `In operation/STATUS.md` into `docs/`, and the "no live finding closes without a check" rule goes into `AGENTS.md`.
   **Status: implemented 2026-09-11.**
   - `docs/BUG_CLASSES.md` has 14 rows, 2 of them with a written "no check yet" reason.
   - `tests/test_bug_class_registry.py` asserts every listed id exists.
   - The closure rule is now in `AGENTS.md`.
   - Moving the durable conventions out of `STATUS.md` remains incremental.
8. **P8: Release pipeline.** `bridgeforge release <mod>`:
   - Gates: a clean scan against the baseline, `jar-audit` against the original, the final build tag.
   - Output: a forward-slash zip and the `Done/` layout, with source and backups excluded.
   - Licence gates (Exigency stays local-only).
   - A release note built from the build-tag deltas.

   **Status: implemented 2026-09-11** (`bridgeforge/release.py`, `release_policy.json`, wired as `release`), including the P3b-M save-corpus gate.
   - It is a dry run by default; `--apply` writes only when every gate passes.
   - Validation: a dry run on Arkgneisis correctly returned BLOCKED on the scan gate (no reviewed baseline yet) and wrote nothing.
   - Before the first real release, each mod needs a reviewed baseline (`scan --write-baseline`) and a save corpus.

9. **P9: Discovery first (owner-approved 2026-09-11).** Discovery moves ahead of test design, following an external review.
   Today the flow is: design tests → modernize → something breaks → BridgeForge finds the hidden behaviour. It flips to: BridgeForge archaeology → architecture map + risk register → tests designed to falsify each risk → modernize → compare against a baseline.
   **Principle: the tool does the crawl and models do the reasoning.** Exhaustive discovery is search and bytecode work, which BridgeForge does completely and repeatably. A model's claim that something is "missing", "unused" or "dead" is a hypothesis until BridgeForge confirms it: a Haiku sweep once flagged 16 vanilla ids in Vacuum as missing.
   - **P9-0. Standing rule (done 2026-09-11):** `AGENTS.md` "Never infer dead code". No code is dead, redundant or safe to refactor until textual, data-file, rules.csv, reflection, serialization, event-registration and runtime references are checked. Precedents:
     - SEEKER's `SensorDroneStats`, loaded by vanilla from a data path
     - mod `rulecmd` classes, called by name from rules.csv
     - SEEKER's bundled source, which differed from its shipped jar
   - **P9-1. `bridgeforge archaeology <mod>` → `ARCHITECTURE_MAP.json` + `.md`** (deterministic, read-only). It reuses the scanner, bytecode and save-compat pieces, and every entry carries file:line evidence, lifecycle, API age and confidence. Sections:
     - **Entry points:** mod plugin hooks (`onApplicationLoad`, `onNewGame`, `onNewGameAfterEconomyLoad`, `onGameLoad`, `beforeGameSave`/`afterGameSave`), `settings.json` plugins, and missions.
     - **Scripts and listeners:** each registration paired with its removal and its `hasScript`/`hasListener` guard. An unguarded add in `onGameLoad` means a duplicate on every load, which pairs with `save-scripts`.
     - **Memory keys and `$variables`:** across Java and rules.csv, including keys read but never written (and the reverse), plus persistent-data keys.
     - **`Global.getSector()` touchpoints by area:** economy (markets, submarkets, industries, conditions), fleets (spawn and despawn), factions and reputation, intel and bar events, hyperspace and terrain, combat plugins.
     - **Cross-file id graph:** CSV, `.ship`, `.variant`, `.wpn`, `.faction`, rules.csv, `settings.json` and Java string literals, with dangling and unused ids. Unused ids are only reported after every source has been checked (P9-0).
     - **String and reflective class references:** data files, `Class.forName`, and the ones the RC8 sandbox forbids.
     - **Serialization-sensitive classes:** everything that lands in saves (script, listener and intel fields, statically, plus `save-compat` on real saves). Renaming or removing any of them breaks existing saves.
     - **External mod APIs and load-order assumptions:** hard versus soft dependencies, `isModEnabled` guards, and `onApplicationLoad` ordering.
     - **API age:** bytecode linkage against the RC8 API, covering removed and changed methods.
     - **Stat modifier ids:** `modify*` paired with `unmodify*`. A missing `unmodify` is a permanent buff or debuff leak.
     - **Timing and state machines:** `IntervalUtil`, day math, and enum or int state fields in scripts.
   - **P9-2. `RISK_REGISTER.md`, seeded automatically from the map.**
     - A data-driven table maps each risky entry kind to a risk template and a detection method: probe assertion, `save-inspect` check, census diff, scenario or scan check.
     - Ids are stable across runs (`RISK-<mod>-nnn`, derived from kind plus evidence key), with statuses OPEN / TESTED / ACCEPTED / CLOSED.
     - A model then refines each risk's failure mode and confidence.
     - `release` gets a gate: no OPEN high-severity risks. `test-plan` maps changed files → risks touched → tests.
   - **P9-3. Breadcrumbs.** Each change cites its risk and test ids (`RISK-EXI-014`, `TEST-T22`) through `build-tag --note` (stored in the build manifest) and a commit-message convention. The release note lists the risks addressed, giving a trail from discovered behaviour → risk → test → change.
   - **P9-4. Static map diff, original versus working copy (the practical baseline).** The originals usually can't run on RC8, which is why they're being revived. So compare `archaeology` output for the original against the working copy: a listener dropped, a memory key renamed, an id orphaned, a save-sensitive class renamed, a lifecycle hook moved. It catches behavioural drift without running anything, and runs in `release` and `test-plan`.
   - **P9-5. Probe census + `census-diff` (runtime snapshot testing).**
     - At fixed points (day 1, day N, after combat) the probe dumps the mod's live state to a census file:
       - registered scripts and listeners by class
       - memory keys with the mod's prefix (type plus value hash)
       - mod entities (id and location)
       - markets and submarkets (industries, conditions, stock counts)
       - fleets per faction (count and fleet points)
       - persistent-data keys
       - stat modifier ids on the player fleet
     - The baseline is the first build that boots (`r1`), stored per tag and scenario under `bridgeforge-state/census/`.
     - The diff is structural, with tolerance bands, because campaign RNG makes exact counts meaningless.
     - It pairs with scenarios (P3b-K) so the same scenario is captured on every build.
   - **P9-6. Discovery-first workflow and model routing (`docs/DISCOVERY_FIRST_WORKFLOW.md`).** Five stages:
     1. **Discovery:** `archaeology`, `dossier` and `scan`. Deterministic, no edits.
     2. **Risk extraction:** a local model (Qwen/Hermes) reads the map plus source and writes the risk narratives. No edits.
     3. **Test design:** Opus/Sol designs tests that try to falsify each risk, not happy paths.
     4. **Modernization:** the implementer changes code, and every change cites its RISK and TEST ids.
     5. **Compare:** `census-diff`, the map diff, the save tools and scenarios.

     The document includes a fixed audit template and prompts per stage, so every mod gets the same map, register, dependency graph and test candidates. Data-era gap checks (procgen rows, known lists, carrier rework, wing roles) stay mandatory: most live bugs so far were data-format gaps, not Java behaviour.
   - **Related recommendations:**
     - Run `archaeology` automatically at intake, alongside `scan` and `dossier`, once the folder reorganisation adds `bridgeforge intake`.
     - Store the map and register in each mod's `reports/`, and let a future `bridgeforge board` show open risks per mod.
     - Feed the save-sensitive class list into `save-compat --compare-old/--compare-new` and the `release` jar gate, so a renamed class without a migration path blocks the release.
     - Each confirmed risk that bites live becomes a `BUG_CLASSES.md` row and a check (P7 closure rule).

   **Order:** P9-0 now; then the folder reorganisation and the first offline live session; then P9-1 → P9-2/3 → P9-4 → P9-5 → P9-6. **Status: P9-0 done; the rest planned.**

   **P9 v2: BridgeForge becomes a behaviour-discovery engine (second review, 2026-09-11; D0-D6 tooling implemented).**
   The review's diagnosis: BridgeForge is strong at catching known bug classes, but nothing in it discovers unknown behaviour before modernization starts. Discovery currently happens only after something breaks. The fix is not more bespoke detectors: BridgeForge assembles the facts it already extracts into a behaviour model *before* any change. Stages are named D0–D6 so they don't clash with P1–P8. Existing pieces are reused, not rebuilt:
   - scanner and bytecode checks
   - dossier
   - `save-compat` aliases and `save-inspect`
   - probe and scenarios
   - `release-evaluate`, `test-plan` and `BUG_CLASSES`

   | Stage | Command(s) | Output | Built from |
   |---|---|---|---|
   | **D0 Archaeology** (read-only, deterministic) | `archaeology` | `archaeology/architecture.json` + `ARCHITECTURE_MAP.md`, `cross_reference.json` | P9-1 plus the items below |
   | **D1 Behaviour model** | `behavior-map`, `risk-register`, `hypotheses` | `behavior.json` + `BEHAVIOR_MAP.md`, `risks.json` + `RISK_REGISTER.md`, `hypotheses.json`, `UNKNOWN_BEHAVIORS.md`, `coverage_seed.json` | D0 |
   | **D2 Runtime baseline** | `probe-baseline` | `baseline-<build>-<scenario>.json` (records what happened, no verdicts) | probe census (P9-5) + scenarios |
   | **D3 Test synthesis** | `hypotheses --tests` | proposed tests per hypothesis; Opus/Sol make them adversarial | D1 |
   | **D4 Modernization** | (existing tools) | every change cites RISK/HYP/TEST ids (P9-3) | — |
   | **D5 Differential validation** | `behavior-diff`, `release-behavior-evaluate` | delta report per behaviour | D2 on both builds + map diff (P9-4) |
   | **D6 Coverage and residual human testing** | `coverage` | coverage matrix; human tests only for what stays uncovered | D1 + D2 + D5 |

   - **D0 additions beyond P9-1:**
     - **A real cross-reference graph, not grep.** Nodes: Java, bytecode, CSV, JSON, `.faction`, `.variant`, `.ship`, `.wpn`, rules.csv, `mod_info.json`, jar resources, save aliases. Edges: "can make X relevant" paths, e.g. `rules.csv` command → class, or hullmod id → variant → fleet.
     - **"No known reference" instead of a dead-code verdict.** BridgeForge never says "dead code". It reports `NO KNOWN REFERENCE (confidence 0.72)` with two explicit lists: **Checked** (source, bytecode, CSV, JSON, faction data, variants, rules.csv, reflection-shaped strings) and **Not verified** (runtime registration, generated references, external mod integration). This enforces P9-0.
     - **Lifecycle graph.** Every hook (`onApplicationLoad`, `onNewGame`, `onNewGameAfterProcGen`, `onNewGameAfterEconomyLoad`, `onNewGameAfterTimePass`, `onGameLoad`) and every registration (`addScript`, `addTransientScript`, `addListener`, `ListenerManager`, combat plugins) is drawn as a tree. A script or listener reachable from more than one route with no visible guard is flagged as a possible duplicate registration. This is the pre-runtime version of `save-scripts`.
     - **Persistent-state map:** classes and fields that land in saves, confirmed by `save-compat` aliases on real saves.
     - **Source ↔ bytecode divergence:** bundled source that doesn't match the shipped jar, as SEEKER's didn't.
   - **D1 details:**
     - Each **behaviour** entry has: subsystem, entry point, trigger, Java classes, data files, ids consumed and produced, persistent state, external APIs, other mods involved, lifecycle, side effects, confidence and evidence. The review's worked example is the Avesta movement, already partly proven by `save-inspect`.
     - **Hypotheses (HYP-nnn).** These are generated, not hand-written. Example: "FooMovement is persistent and moves an entity; unknowns: survives save/load? registered once? position continuous after load? destination kept? exactly one instance per new game?" Each unknown comes with the observations that would answer it (script count before and after a load, entity position at T0/T+1d/T+5d, waypoint state across a load). This bridges archaeology and testing: Opus/Sol get concrete hypotheses instead of inventing what might matter.
     - **Unknown-behaviours ledger (UNK-nnn).** Statuses: `EXPLAINED`, `LIKELY INTENTIONAL`, `LIKELY DEFECT`, `UNKNOWN`, `RUNTIME TEST REQUIRED`, `PRESERVE UNTIL EXPLAINED`. A modernization agent must not "clean up" anything in the last status.
     - Hypotheses and unknowns sit alongside the P9-2 risk register, sharing its stable ids and statuses.
   - **D2 details:**
     - `probe-baseline` is a no-verdict mode of the probe. It records entities, scripts, markets, factions, fleets and tracked state per scenario: new game, day 5, save/load, progression, combat, and compat-set environments.
     - **The reference build is the hard part, since originals usually can't run on RC8.** In order of preference:
       - (a) An older game version, where you have one, installed as a second isolated rig, running the **original** mod. This is the true oracle.
       - (b) The first bootable revived build (`r1`).
       - (c) Whatever the original does manage to run before it fails.
       - (d) The static map diff (P9-4) as the floor.
   - **D5 details:** `behavior-diff` sorts every observation into one of five categories:
     - `UNCHANGED`
     - `EXPECTED_CHANGE`, matched against a declared-changes file written alongside each change
     - `UNEXPLAINED_CHANGE`
     - `MISSING_OBSERVATION`
     - `NEW_BEHAVIOR`

     `release-behavior-evaluate` extends `release-evaluate` to consume this runtime evidence. That's the step `release-evaluate` deliberately refuses today without such evidence.
   - **D6 coverage matrix:** one row per behaviour, with columns static, runtime, save/load, compat and human, and a status of `COVERED` or `OPEN`.
     - **It reports counts only** (owner decision, 2026-09-11), e.g. "37 known behaviours: 31 covered, 4 need runtime evidence, 2 need human judgment; 7 unknowns open".
     - There is no percentage: a share of the *known* behaviours says nothing about the unknown ones, which is why the unknowns ledger is counted alongside.
   - **The dossier becomes the presentation layer:**
     - The index adds ARCHITECTURE, BEHAVIOUR, RISKS, UNKNOWNS, COVERAGE and RECOMMENDED TESTS sections.
     - It keeps split-never-truncate and "triage in ≤5 reads".
     - It's the packet handed to Qwen/Hermes or Opus.
   - **New release gate:** "scan, compile, boot and probe clean" is no longer enough.
     - No HIGH-risk behaviour may remain `UNKNOWN` or `PRESERVE UNTIL EXPLAINED` without a written decision.
     - Every observed delta between the reference and the revived build must be explained, explicitly approved or covered by a test.
     - It joins the P8 gates, after P9-2's risk gate.
   - **Workflow and model routing:**
     1. BridgeForge archaeology (deterministic) plus a Qwen exhaustive *review* of its output, plus the reference baseline, produce the map, risks, unknowns and hypotheses.
     2. Opus/Sol design adversarial tests.
     3. Qwen/Hermes implement the modernization.
     4. BridgeForge runs the differential validation.
     5. Opus/Sol review only the unexplained deltas.

     Qwen's role is reviewing and annotating the archaeology output, not replacing the deterministic crawl (principle above).
   - **Order (after the offline live session):** D0 (archaeology + cross-reference + lifecycle) → D1 (behaviour, risks, hypotheses, unknowns) → dossier integration → D2 `probe-baseline` (with P9-5 census) → D5 `behavior-diff` → D6 coverage + release gate → D3 test synthesis. D4 is the existing tools plus the breadcrumbs.
   - **Pilot:** run D0/D1 on Exigency and SEEKER first. Their live bugs are already known, so they measure how many of this week's surprises archaeology would have predicted, which is the acceptance test.
   - **Owner decisions (2026-09-11):**
     1. **Reference rig:** yes. The owner will install older versions (see P10).
     2. **Coverage:** counts only.
     3. **Qwen/Hermes:** optional, still in testing. Every stage must work without it. Its D1 review is an extra pass whose output is a file dropped into `reports/` for BridgeForge to merge.
     4. **Expected-changes format:** designed in `docs/EXPECTED_CHANGES_FORMAT.md`.
        - One lenient-JSON file per mod, at `In operation/<Mod>/reports/expected-changes.json`.
        - Entries have ids (`EXP-<MOD>-nnn`) and are tagged with the build that made the change.
        - Matchers are typed; statuses run PROPOSED → APPROVED → RETIRED.
        - `behavior-diff` sorts every observed change into EXPECTED / UNEXPLAINED / EXPECTED_BUT_ABSENT.
        - The release gate counts only APPROVED entries.
   - **Implementation (2026-09-11):**
     - D0 `archaeology` writes deterministic architecture, cross-reference,
       lifecycle, registration, persistence-candidate, source/package authority,
       scanner-finding and `NO_KNOWN_REFERENCE` evidence. Java/data/JAR and
       constant-pool references are joined without loading mod classes.
     - D1 `behavior-map`/`risk-register` write stable behavior, risk,
       hypothesis, unknown and coverage-seed artifacts without requiring a
       model. Scanner findings and data-selected local classes become explicit
       behavior/risk entries.
     - D2 `probe-baseline` imports hash-bound observations in a no-verdict
       schema. It does not launch a game; reference-rig capture remains an
       explicit live step.
     - D3 `hypotheses --tests` emits proposed adversarial tests with acceptance
       and stop conditions.
     - D4 `expect add|approve|retire|check` implements the expected-change
       lifecycle, requires RISK/HYP/TEST breadcrumbs and keeps a last-edit
       backup.
     - D5 `behavior-diff` compares runtime baselines and optional original/new
       static maps, including `EXPECTED_BUT_ABSENT`; the standalone and normal
       release gates reject unresolved deltas and open HIGH/unknown behavior.
     - D6 `coverage` emits the counts-only matrix and residual test list. The
       dossier presents all six discovery views, and approved expected changes
       are grouped by build in release notes.
     - Exigency and SEEKER D0/D1 pilot evidence is generated under ignored
       `artifacts/d-series-pilot/`; no source mod or known-good release was
       modified. Reference baselines and live D2/D5/D6 closure remain dependent
       on the isolated old/current game sessions described in P10.

10. **P10: Reference rigs on older game versions (the D2 oracle).** The owner can install older Starsector versions, so each original mod can run on the game it was built for.
    - **Needed versions,** read from the untouched originals' `mod_info.json`:

      | Game version | Mods |
      |---|---|
      | **0.8.1a** | FlowerGod, Flu-X |
      | **0.7.2a** | Exigency |
      | **0.97a-RC11** | Omega Trauma |
      | 0.65.2a | SEEKER |
      | 0.62a | Vacuum |

      Arkgneisis and Broken Star already target 0.98a. Edmund's Church and Void-Tec have no untouched original here.
    - **`rig-create --game-version <v> --install <dir>`:** registers an old install as an isolated reference rig. Old versions keep saves inside their own install, so each version needs its own folder, never the real install. It records the bundled Java version and the run command, and `rig-doctor` learns about reference rigs.
    - **Era compat sets:** `era-0.8.1a`, `era-0.7.2a` and so on. Old mods need old LazyLib, MagicLib and GraphicsLib, and finding those builds is part of the setup. Missing libraries are the most likely blocker.
    - **Observation without the probe:** the probe is compiled against the RC8 API, so it won't run on old versions. The cheap oracle is the **old game's saves**, since they're XStream too: `save-inspect` and `save-content` read a save from the original mod on its own game, as the D2 baseline. A per-era `probe-legacy` build comes later, only if saves prove too thin.
    - **Pilot:** Exigency on 0.7.2a, comparing the Avesta movement, markets and known lists against the revived build. Then FlowerGod and Flu-X on 0.8.1a (one install covers both).
    - **Offline tooling implemented (2026-09-12):** `rig-create` records a hash-bound historical-install manifest (core API, bundled Java metadata, run command and saves path); `rig-doctor --reference-manifest` verifies drift and the era base version while skipping the incompatible RC8 probe. Five `era-*` sets represent the original mods and known dependencies without inventing exact historical library versions. `save-baseline` converts selected old-save state into D2's no-verdict schema. No old install was available, so the Exigency/FlowerGod/Flu-X runtime pilots remain `LIVE VALIDATION REQUIRED`; see `docs/P10_REFERENCE_RIG_STATUS.md`.
11. **P11: Tool hygiene** (found 2026-09-11 while reorganising).
    - **Stale processes:** 22 `tail -f`/`grep` log watchers from the Sep 9 boot tests were still running two days later and locking the rig.
      - `rig-doctor` gains a lock check: open files via Restart Manager, stale watchers, and processes whose current folder is inside the rig.
      - Every monitor BridgeForge or `bf-test.ps1` starts must stop its children.
      - A new `bridgeforge who-locks <path>` names the process holding a path. That diagnosis took several steps by hand.
    - **Test hermeticity:** a test deleted the real `probe-mod/releases` copy on every run; now fixed.
      - A CI or suite guard should fail when a test changes anything outside temp dirs: check that `git status` and the ignored release copy are unchanged before and after the run.
      - A shared test helper should resolve temp paths, because GitHub's Windows runners use 8.3 short paths (`RUNNER~1`).
    - **CI upkeep:** move `actions/checkout` and `actions/setup-python` off Node 20, which GitHub has deprecated. Keep the Linux and Windows matrix, with Windows-only features (junctions, `.bat` launch) skipped on Linux.
    - **Implemented/locally verified (2026-09-12):** read-only `who-locks`, rig
      process-path checks with explicit visibility limits, session-scoped monitor
      interruption cleanup (`tools/bf-test.ps1`), shared resolved-temp fixtures,
      guarded CI and minimal Node24 action upgrades. The guarded local suite passed
      601 tests (one skip); Windows Restart Manager identified an exclusive temp
      file owner. No live game was launched. Exact-SHA CI is the publication gate;
      see `docs/ROADMAP_COMPLETION_LOG.md` for evidence and remaining scope.
12. **P12: Workflow tooling for the new layout.**
    - **`bridgeforge intake <archive>`:** creates `In operation\<Mod>\{original,working,reports,builds,scratch}` from a download (keeping the archive in `original\`), then runs `scan`, `dossier` and, later, `archaeology`.
    - **`bridgeforge board`:** generates the status table from each mod's folder (stage, build tag, last test, open risks), so `STATUS.md` stops being hand-maintained.
    - **`rig-doctor` layout check:** flags strays at the `In operation\` root and working copies outside the convention.
    - **`bridgeforge promote <mod>`:** runs `release --apply` into `Done\<Mod>\`, keeping the previous release as `builds\`.
    - **Finish Vacuum's move** once its folder is free.
    - **Release hygiene:** tag `v0.2.0` in git, with GitHub release notes taken from the CHANGELOG.
    - **P12A implemented (2026-09-12):** source-preserving `intake` with explicit
      root selection, scan/dossier and optional archaeology; deterministic declared
      evidence `board` with optional STATUS.generated files; read-only rig-doctor
      layout warnings. Existing originals/manual STATUS/builds are not replaced.
      Promotion, Vacuum movement and release hygiene remain pending; see
      `docs/P12_LAYOUT_TOOLING.md` and the completion log for exact validation gates.
    - **P12B promotion implemented (2026-09-12):** dry-run-default promotion with
      audited plan/report and D5 release gates, exact staged package identity,
      prior-release retention, per-release evidence and rollback. Bundled release
      policy is installed and missing/invalid policy blocks distribution. Full
      guarded suite: 630 tests, one skip, no checkout/probe drift. No actual mod
      promotion or new live test; Vacuum movement and release hygiene remain open.
      See `docs/P12_PROMOTION.md` and `docs/ROADMAP_COMPLETION_LOG.md`.
    - **P12C Vacuum layout completed (2026-09-12):** active copy at
      `Vacuum/working`, earlier attempt preserved under scratch, pre-carrier ZIP
      retained under builds, rig at `_rig-vacuum`. Before/after byte inventories
      match; only launcher JDK path and working-copy junction were corrected.
      No source/gameplay changes or new live test. Probe/report/live gates remain
      explicit; release hygiene is next. See `docs/P12_VACUUM_LAYOUT.md`.
    - **P12D release hygiene completed (2026-09-12):** public `v0.2.0` tool
      release at `e98522109a00c27dbe73e2bb1cffcd5978427ea8`; six source CI and
      six tag CI jobs passed. Exact-source packages and fresh public downloads
      verified, with changelog notes and SHA256 receipts. P12 is complete;
      live/manual/research acceptance gates are not. See `docs/RELEASE_0_2_0.md`.
13. **P13: Non-English intake (from the 2026-09-13 Chinese mods: Nightcross, Mirfak Parcel Service, Blackrock CN).**
    - **Implemented now, because these mods needed it:**
      - `translate-export` / `translate-apply` / `translate-check` (`bridgeforge/translation.py`). Stable ids for CSV cells, JSON-like strings and keys, loose Janino scripts and jar string constants. Prefill from a zh/en record (`--record`) or an English copy (`--reference`: CSV row+column, JSON path, jar constants when the class layout matches). Apply is hash-guarded, span-exact and structure-verified.
      - `_parse_json` gained the remaining org.json leniencies: leading-zero and leading-dot numbers, and data after the root value. There's a new `json-content-after-root` (REVIEW) for keys the game never loads.
      - `csv-row-extra-columns` now separates spilled content (MANUAL/high) from empty padding (SAFE/low).
      - Spec ids come from the file, not its name (`.wpn`/`.variant`/`.ship`). `undeclared-library-dependency` sees `isModEnabled` guards in bytecode. New `loose-script-shadowed-by-jar` (SAFE): the game never compiles a loose script whose class is in the jar, so its Janino risks are dropped. A local `.wpn` that overrides a vanilla-registered weapon is no longer also reported as unregistered.
      - **Done 2026-09-13 (second pass):**
        - `jar-entry-unreadable`: CRC and corrupt-entry check. The rest of the jar is still scanned.
        - OS/VCS litter is excluded from releases and copy-drift (`.idea/`, `.vscode/`, `.git/`, `__MACOSX/`, Thumbs.db…). `shippable-work-file` lists editor and design files that would ship (`.psd`, `.sai2`, `.docx`, `.iml`, `.orig`…).
        - `player-text-non-english`: CJK in data files outside comments.
        - `design-type-color-duplicate-key` / `-unused` / `design-type-without-color`: designTypeColors keys against the tech/manufacturer text, counting vanilla's keys.
      - **Done 2026-09-14:**
        - `non-ascii-identifier` and `non-ascii-file-path`.
        - `data-file-not-utf8`, with the likely encoding.
        - `csv-fullwidth-number`.
        - `shippable-work-file` now also covers archives and `.lnk`/`.url` shortcuts.
        - First sweep of these checks: Arkgneisis has a GBK `rules OLD.csv`; Omega-Trauma ships a `.rar` and three `.lnk` shortcuts.
    - **Planned:**
      - **Decompile dumps and translator working folders** (`_u0001_cmp`, translator `ai/`). They sit outside the shipped folders in the mods seen so far; add globs when one turns up inside `data/`/`graphics/`.
      - **CSV narrower-row check:** rows shorter than the header; tolerated by the game, rejected by strict tools.
      - **Non-ASCII path safety** for every external tool BridgeForge drives (JDK tools, launchers, Project Go): use ASCII staging copies automatically.
      - **Translation memory across mods:** reuse approved zh→en pairs, such as shared faction or ship-class terms. Glossary files are per mod for now.
    - **Handed to Project Go's maintainer:** non-ASCII paths in `ssmt-cli.bat`; strict CSV/JSON; the missing cause in "Could not create localization project"; JSON keys not extracted; incomplete CSV and jar coverage (861 Nightcross strings missed).

## P14: Dependency intelligence and queue throughput (planned 2026-09-14)

Starting point:
- The 2026-09-14 queue of 25 older mods showed that the hard cases are dependencies, not syntax. Add-ons of dead mods (Communist Clouds → Vayra's Sector), abandoned library families (Xenoargh's FX Core and EZ Damage), and removed campaign APIs (0.6's `SectorAPI.createFleet(faction, fleetType)`, used by BaseSpawnPoint spawners) block more mods than any data problem. `BaseSpawnPoint` itself still ships as an RC8 loose script (corrected 2026-09-14).
- `dependency-substitutes` and `dependency_successors.json` are the first step.
  - `dependency-substitutes` finds the smallest set of visible mods that provides what a mod needs. Each provider in the set is current, revivable (a workspace here with 15 MANUAL or fewer) or heavy.
  - It recommends SWAP, REVIVE_DEPENDENCY, STRIP_FROM_MOD or ESCALATE, per `docs/DEPENDENCY_STRATEGY.md`.

**Working order (owner, 2026-09-15; live testing deferred until more comes to light):**
1. Loose-script compile check (item 11). **Done 2026-09-15** (wired into `scan`/`scan_mod`; the standalone `compile-check` command was task A9).
2. Carrier-bay fixer (item 6). **Done 2026-09-15.**
3. Jar rebuild command (item 7). **Done 2026-09-14/15 (task A9).**
4. Fold-in workflow (item 10), then fold FX Core into RevenantLib.
5. Strip/vendor planner (item 4), with Rebal phase 2.
6. Provider index and dependency graph (items 2–3).
7. Licence-aware revival (item 9).
8. The Ironclads queue, last.

Items 1 and 3 share a Java-toolchain module and are built together (task A9).

Progression, each stage feeding the next:

1. **Done 2026-09-14.**
   - `dependency-substitutes`, the evidenced successor file and the strategy guide.
   - Scanner checks: `content-reference-unresolved`, `source-import-unresolved`, `legacy-vanilla-class-import`, `library-import-unused-in-jar`, `console-command-optional`, `carrier-bays-proposal`.
   - Fixers: `target-interface-method-missing`, `wing-data-missing-role-desc-column`.
2. **Provider index as a corpus artefact.** Store each visible mod's "provides" set beside the novelty fingerprints (`bridgeforge-state/`, gitignored), so a lookup is instant and works when the provider isn't installed. Record game version and mod version.
3. **Dependency graph across the queue.** Build a graph of which queued mods need which missing mods, and order revival by unblocking value. As of 2026-09-14: FX Core (10 MANUAL) unblocks FX Example and part of Rebal; AI Overhaul (12 MANUAL) the rest of Rebal. EZ Damage is already revived (r1). Show it in `board`.
4. **Strip and vendor plans.** For STRIP_FROM_MOD, generate the exact edit list: which variant, `.ship` and faction lines lose which ids, plus proposed vanilla substitutes of the same slot type and size. Also generate the matching PROPOSED expected changes, so approval goes through `expect` as usual. Where the licence allows, offer vendoring as an alternative: copy the one missing piece (for example Rebal's `shields_formshield` into Explorer Society) instead of reviving a heavy provider.
5. **Spawn-point fleet port kit.** RC8 keeps `BaseSpawnPoint` and `addSpawnPoint`, but not `SectorAPI.createFleet(faction, fleetType)`, which 0.6 spawners use to build fleets from old faction fleet definitions. The kit is:
   - a helper that builds the equivalent fleet with FleetFactoryV3, following Zorg18 r1's spawner;
   - a scanner check for the removed call.

   It is proposed per mod, never auto-applied, because fleet composition changes. Six queued mods need it (ESCALATIONS E6).
6. **Carrier-bay fixer.** Apply the approved `carrier-bays-proposal` counts, adding the `fighter bays` column where the file predates it, with per-hull approval (`--hull ID=N`).
   **Done 2026-09-15.** `fix <mod> --finding carrier-bays-proposal --hull ID=N [--hull ID=N ...] --apply` (`bridgeforge/fixers.py` `_fix_carrier_bays_proposal`). `--hull` is repeatable and required; an id with no ship_data.csv row is refused, and a count must be 0-6 (vanilla's own maximum, the Astral, read from RC8's own `ship_data.csv`). The column is added, blank for untouched hulls, the same way `wing-data-missing-role-desc-column` adds `role desc`, if the file predates it. `_scan_carrier_bays_proposal` no longer proposes a hull whose `fighter bays` is already set, so a partial approval correctly narrows what's still proposed. Tests: `tests/test_fixers.py` (`CarrierBaysProposalFixerTests`, 12 cases incl. CLI wiring), `tests/test_batch_lessons.py` (already-set hulls are skipped).
7. **Jar class rebuild for missing interface methods.** For classes compiled into a jar (AI-War), patch just those classes from source after a class-by-class diff, following the Arkgneisis precedent.
   **Done 2026-09-14/15 (task A9).** `rebuild-jar <mod> --sources DIR --jar JAR` (`bridgeforge/rebuild_jar.py`, sharing `java_toolchain` with the compile check below): rebuilds from source, packages a jar keeping the original manifest/resources, and diffs it against the original class-by-class and member-by-member, normalizing known compiler-only differences (class-file version bump, `synchronized`-only change, Lombok lock fields, synthetic `access$`/`lambda$` members). PASS/REVIEW/FAIL, with `--install` moving the previous jar to `scratch/moved-<date>/` and installing only on PASS.
8. **Removed-vanilla-content catalogue.** Record ids and classes vanilla dropped between versions (the `thruster_fighter_sm` / `shields_formshield` kind), with evidence and successors, so "defined nowhere" becomes "removed in 0.9x; use X".
9. **Licence-aware revival of dependencies.** Before REVIVE_DEPENDENCY, check `release_policy.json` so a revived library is marked local-only when its licence doesn't allow redistribution.
11. **Loose-script compile check.** Removed APIs keep turning up one method at a time: `SectorAPI.createFleet`, then `SectorAPI.addMessage` (RC8 moved it to `CampaignUIAPI`), found only by task A5's compile check of Cobalt-Arms and Independant-Mining-Faction. When the rig JDK is available, compile every loose `data/**.java` against the core jars plus the declared dependencies' jars, and report each javac error as a MANUAL finding with its file and line. That catches every removed or changed API in one pass; per-method `removed-api-call` entries then serve only as fixer rules.
    **Done 2026-09-15.** The standalone `compile-check <mod>` command (task A9) is now also reachable from a plain scan: `scan_mod(..., compile_check=True)` and `scan --compile-check` call `bridgeforge.compile_check.compile_loose_scripts` when `--vanilla-core` is given, emitting `loose-script-compile-error` (MANUAL, grouped one finding per failing file, up to 5 errors' line/message/symbol as evidence) or `loose-script-compile-unavailable` (UNKNOWN, no JDK or no core). Off by default so a plain scan stays fast and hermetic. Real cases (2026-09-15): Renis-Imperium, AI-War, Argamede-Union and EZFaction were each marked ready by every other check and failed only this one. Janino version check: RC8 ships Janino 2.7.8 (`starsector-core/janino.jar` manifest); its own changelog dates the diamond operator/try-with-resources/multi-catch/lambdas all to the 3.0.x line, well after 2.7.8, so `janino_gap_warnings` keeps flagging every construct it already flagged. Tests: `tests/test_scanner.py` (`CompileCheckScanIntegrationTests`).
10. **Fold-in workflow (owner policy 2026-09-14).** Discontinued library-like mods are folded into RevenantLib (`revenantlib`), per `docs/DEPENDENCY_STRATEGY.md`. The workflow has four parts:
    - a `fold` command that copies a library into RevenantLib, keeping its ids and class names and adding a provenance section;
    - a fixer that rewrites dependents' dependency ids;
    - a `dependency_successors.json` entry per folded mod;
    - a check that warns when an original mod and RevenantLib are enabled together.

    **Tooling done 2026-09-20 (task A12).** `fold <source> <target>` (`bridgeforge/fold.py`) copies the
    source mod byte-for-byte into `<target>/original/<source name>/`, records a provenance section
    (source path, mod id, name, author, version, `gameVersion`, licence-file evidence, per-file SHA-256)
    in `<target>/reports/PROVENANCE.md`, and appends a `dependency_successors.json` entry (kind
    `folded-into-revenantlib`) so `dependency-substitutes` proposes the swap. `--dry-run` writes nothing;
    an existing `original/<name>/` is refused without `--overwrite`; a file that already exists with
    different content is a conflict that stops the whole run, reported rather than resolved. New scanner
    check `revenantlib-fold-conflict` (MANUAL) fires when a mod declares both `revenantlib` and a folded
    original id; `fix <mod> --finding revenantlib-fold-conflict --apply` drops the redundant original
    entry, reusing `_add_revenantlib_dependency`. Source/target are always explicit arguments; nothing
    under "In operation" was touched by this task, and folding FX Core itself is still the coordinator's
    next step, not done here. Tests: `tests/test_fold.py`, `tests/test_fixers.py`
    (`RevenantlibFoldConflictFixerTests`).

12. **Cross-mod loose-script shadowing.** `loose-script-shadowed-by-jar` only compares a mod's loose
    `data/**.java` against **its own** jars. A mod that overrides a *dependency's* loose script is
    therefore misreported: the scanner raises `loose-script-janino-risk` on a file the game never
    compiles, because all mod jars share one classloader and the dependency's jar already supplies the
    class ("already loaded (perhaps from jar file) ... skipping compilation"). Worse, the override
    itself silently does nothing, which is a defect in the mod that no check currently reports.
    Found 2026-09-20 on Maelstrom Interstellar Imperium Unofficial Expansion (escalation E8): its two
    Titan scripts are shadowed by base Interstellar Imperium's `II.jar`. Needs the provider jars that
    `compile_check`/`substitutes.provider_index` already assemble, plus a new finding
    (`loose-script-shadowed-by-dependency-jar`, MANUAL: the edit has no effect) and a scanner test.

## Post-1.0 research and gated automation

### Deferred migration findings from the 0.98a corpus audit

These are scanner-supported, review-gated migration tracks. They are intentionally
not automatic fixes: the audit establishes candidates, not authorial intent.

1. **Runtime placeholders:** classify reachable `UnsupportedOperationException`
   and equivalent stub paths, then require a source-level replacement and compile
   validation before proposing a migration.
2. **Configured class integrity:** reconcile configured plugin/script class names
   with the packaged JAR and source layout; distinguish obsolete configuration from
   an accidentally omitted class.
3. **Campaign spawn registration:** inspect disabled or commented-out registration
   paths and propose restoration only after validating lifecycle timing, campaign
   conditions, and duplicate-spawn safeguards.
4. **Target-bytecode compatibility:** detect classes beyond the selected Java/
   Starsector profile and provide a working-copy rebuild plan using the appropriate
   source and dependency evidence.
5. **Campaign-state coupling:** review persisted live objects, external memory
   keys, and hard-coded system/entity identifiers; propose resilient lookup or
   compatibility strategies only where the mod's intended content contract is
   evidenced.
6. **Target interface contracts:** detect active source implementing known
   target-engine interfaces while missing newly mandatory methods. Require a
   source-level implementation and compile validation; never generate behavior
   automatically from the signature alone.
   **Status: initial 0.98a `LevelupPlugin` contract check implemented after
   reproducing Edmund's Church 2.5's Janino load failure.**

### Audit-derived capability gaps

The 2026-09-01 archive and installed-mod corpus audits showed that several
existing signals need stronger context before they can drive a useful migration
plan.

1. **Reachability-aware finding triage:** correlate source and bytecode findings
   with configured entry points, plugin registration, and known campaign/mission
   callbacks. Rank likely-reachable stubs and obsolete APIs above dead code,
   examples, and inactive sources, while retaining the raw evidence.
   **Status: configured-entry-point and bounded unambiguous local-call evidence
   implemented; full call-graph analysis remains research.**
2. **Packaged-versus-source reconciliation:** classify a missing configured class
   as absent from the packaged JAR, present only in source, supplied by a
   dependency, or genuinely unresolved. Generate a rebuild/package diagnosis
   rather than treating every mismatch as the same defect.
   **Status: source-only, packaged, and unresolved classification implemented;
   explicit local API inventories can now attribute configured classes without
   asserting that unselected dependencies are absent.**
3. **Content-identifier ownership and resolution:** build a mod-local/vanilla/
   external identifier index for systems, entities, variants, factions, and
   memory namespaces. Use it to distinguish intentional self-references from
   brittle cross-mod or vanilla assumptions, and detect unresolved references.
   **Status: source-defined and mod-prefix attribution implemented for campaign
   system/entity lookups, with an optional explicit registry workflow; no global
   vanilla or external-mod registry is assumed.**
4. **Mission assembly validation:** statically resolve mission fleet/member,
   variant, ship, weapon, and map references across both historical mission
   layouts. Flag missing local members separately from references supplied by a
   dependency; add an opt-in mission smoke scenario where runtime support exists.
   **Status: local ship/fighter-wing, mission-variant hull, and mission-variant
   weapon resolution implemented; maps and runtime launch remain future work.**
5. **Dependency compatibility matrix:** extend external API-import evidence with
   declared dependency versions, bundled-library ownership, and verified local
   API inventories. Report version skew and unavailable API symbols without
   proposing substitutions unless a migration-pack contract exists.
   **Status: declared dependency versus direct API-import evidence plus opt-in
   local class and unambiguous method-name inventory checks implemented;
   overload, runtime, and load-order verification remain gated.**
6. **Scenario-based runtime smoke profiles:** add opt-in, user-authored profiles
   for campaign load, mission launch, and custom-UI interaction markers. They
   must execute only in a staged working copy and must never claim runtime health
   from static analysis alone.
   **Status: scenario labels, per-scenario log assertions, and stale staged-mod
   protection implemented; game launch orchestration remains explicitly
   user-authored and opt-in.**

### Current completion map (priority order)

1. **Transactional recovery fault injection:** simulate a failure during a later migration write and prove that every earlier write is restored.
2. **Legacy JSON policy:** verify target-engine behavior for trailing commas and other observed historical syntax before changing classification or normalization behavior; retain `MANUAL` findings until the evidence exists.
3. **Cross-platform CI matrix:** run install and unit tests on Windows and Ubuntu with supported Python versions and Java 17.
4. **Opt-in corpus comparison runner:** scan user-approved local mod corpora and compare only aggregate results to sanitized baselines; keep paths and mod content out of Git and CI.
5. **Verified migration-pack contracts:** require provenance, before/after fixtures, compile validation, idempotence, conflict checks, and save-risk assessment for every MagicLib, LazyLib, or AshLib mapping.
6. **Containment and symlink security coverage:** test altered plans/manifests, symlink escapes, and archive member traversal names.
7. **Archive-intake coverage:** add bounded handling/tests for wrapper-directory layouts, corrupt archives, entry-count and compression-ratio limits, and missing metadata.
8. **Deterministic provenance coverage:** prove hashes are stable for unchanged inputs and change only with relevant content.
9. **Deferred test-suite hygiene:** split `tests/test_scanner.py` by concern only when it becomes a demonstrated maintenance burden; this must not displace product work.

- **Completion definition:** all items above have deterministic tests, documentation, and machine-readable artifacts where applicable. Research tracks below remain gated until their stated evidence and safety prerequisites are met.

**Current status: completed 2026-08-31.** The test-suite split was assessed and deliberately deferred under its documented maintenance threshold; all other completion-map items are implemented and covered by local and cross-platform CI verification.

### Corpus expansion strategy

- **Legacy campaign/code specimens:** prioritize Vayra's Sector, then one of Blackrock Drive Yards or Dassault-Mikoyan Engineering. Use them for analysis and evidence quality, never automatic migration.
- **Modern controls:** maintain known-working current specimens (starting with Nexerelin and a library-dependent modern mod) to measure false-positive rates and confirm Bridgeforge can recognize health.
- **Version lineage:** collect old/current releases of a maintained mod such as Ship/Weapon Pack or Nexerelin. Treat maintainer-driven differences as evidence for what changed, what remained intentional, and which scanner assumptions are false.
- **Dependency archaeology:** compare historical/current LazyLib, MagicLib, and optionally GraphicsLib releases. Library migration rules may use this evidence only through the verified migration-pack contract.
- **Library usage attribution:** report whether each known library is declared, bundled, imported, source-called, or bytecode-referenced; flag declared-but-unreferenced dependencies for review. This is evidence only: it must not remove, upgrade, or migrate a library without verified API-specific examples and compile/runtime validation.
- **Binary-only restraint specimen:** retain one source-less, old-bytecode mod to verify package/class inventory, dependency evidence, and graceful `UNKNOWN` handling without decompilation or speculative reconstruction.

### Evidence intake (2026-08-31)

- **Vayra's Sector archive:** a 492-file legacy campaign specimen with a JAR, non-UTF-8 CSVs, verified trailing-comma cases, and other parser-tolerance ambiguity. It is evidence for intake classification, not a migration source.
- **Ship/Weapon Pack source lineage:** the public master branch is reachable and its source tree places `mod_info.json` under `src/`; use old/current maintainer releases to distinguish source-checkout layout from a distributable mod layout.
- **Nexerelin modern control:** the public repository provides maintained 0.12.2-series tags and a large current source/data tree. Use it to measure modern false positives, especially historically loose JSON syntax.
- **LazyLib and MagicLib dependency archaeology:** both public repositories are source/build layouts, not generic migration templates. LazyLib keeps its distributable metadata below `mod/`; MagicLib contains built artifacts as well as source. Keep scans attributable to the selected root and require release-specific before/after evidence for every pack rule.

These sources are retained as external, user-approved evidence only. Bridgeforge does not vendor them, execute their code, or infer transformations from apparent API similarity.

- **Cross-mod analyzer:** construct a read-only dependency and API-use graph across a selected set of mods, including duplicate libraries, package/class ownership, declared dependencies, and version-skew findings. Reports must remain attributable to each source mod and machine-readable.
  **Status: explicit-set dependency, duplicate-class, and campaign-ID ownership graph implemented; global discovery and runtime load-order analysis remain out of scope.**
- **Bytecode rewriting:** investigate narrowly scoped, reversible bytecode transformations in working copies only. Every transform must be deterministic, generate a class-level patch/provenance record, retain the original class, and require explicit review/approval before it can be applied.
- **Decompiler integration:** add an optional local decompiler adapter for review artifacts when source is absent. Decompiled output is evidence only: it must never be treated as authoritative source or automatically recompiled/replaced without an explicit user workflow.
  **Status: hash-bound, explicit-execution adapter plan implemented; output is retained as untrusted review-only evidence.**
- **MagicLib/AshLib adoption:** develop evidence-backed migration packs for manual and review-gated adoption of MagicLib, LazyLib, and AshLib. Do **not** add transformations merely because APIs appear equivalent: every mapping must come from verified examples and documented behavioral evidence. Automatic adoption is a later, opt-in research track and may proceed only for a small allowlisted set of semantics-preserving mappings with compile, conflict, and save-risk validation; all other adoption remains recommendation-only.

## Product boundary

Bridgeforge modernizes legacy mods. It does not profile performance. The related, independent **Starsector Performance Workbench** is specified in [docs/PERFORMANCE_WORKBENCH_DESIGN.md](docs/PERFORMANCE_WORKBENCH_DESIGN.md); the only planned interchange is a small set of versioned JSON schemas.

## Void-Tec working-tree evidence tranche

1. **Working-tree layout classification:** distinguish generated and backup
   candidates from source/content candidates without suppressing any files.
   **Status: implemented as read-only `working-tree-layout` evidence.**
2. **Source-authority selection:** require an explicit source-root manifest when
   a working tree contains multiple non-generated Java roots.
   **Status: implemented as output-only `source-authority`.**
3. **Build-input manifests:** expose Lombok/annotation-processing imports,
   local processor JAR hints, and build metadata without assuming a processor
   version or attempting a rebuild. **Status: implemented.**
4. **Optional-integration scenarios:** translate direct optional API imports,
   external campaign-memory access, and UI injection into review-only staged
   runtime prompts. **Status: implemented; no runtime health claim is made.**
5. **Generated-artifact-aware release deltas:** report build/log/class and
   backup candidate deltas separately from normal content deltas. **Status:
   implemented; candidates are never ignored automatically.**

## First 10 implementation phases — V0.1 scanner

1. **CLI and target profile** — accept a mod directory and explicit Starsector/Java targets.
2. **Safe intake** — validate the input directory and scan it read-only.
3. **File inventory** — record files, sizes, and relevant layout areas.
4. **Metadata analysis** — parse `mod_info.json` and declared dependencies.
5. **JAR/bytecode analysis** — inspect archives and class-file major versions without loading code.
6. **Dependency analysis** — identify bundled libraries, duplicates, and likely obsolete runtime copies.
7. **Source inspection** — collect imports and flag a small, data-driven set of known legacy APIs.
8. **Asset/config validation** — check JSON and CSV structure in Starsector data areas.
9. **Environment inference** — estimate source Starsector and Java eras with recorded evidence.
10. **Artifacts and reporting** — emit `MODERNIZATION_REPORT.md` and `bridgeforge.compat.json`.

**Status: implemented locally.** The V0.1 scanner is deliberately read-only and has no automatic migration, bytecode rewrite, or AI dependency.

## Subsequent releases

- **V0.2:** working-copy generation, safe deterministic metadata/config fixes, checkpoints, and patch manifests. **Status: initial workspace, plan, approval, patch, and rollback foundation implemented; migration-pack coverage remains deliberately minimal.**
- **V0.3:** AST-based Java source migrations; no regex source rewrites. **Status: parse-only JDK AST import/method evidence and review-gated, AST-confirmed import replacement foundation implemented.**
- **V0.4:** JDK/dependency selection and compile validation. **Status: JDK-profile capture, command preview, controlled `javac` execution, diagnostic classification, non-applying compile feedback, and deterministic output-copy JAR packaging implemented.**
- **V0.5:** scoped agent handoff bundles for ambiguity only; Bridgeforge remains the planner and validator. **Status: bounded review-bundle artifact generation implemented.**
- **V0.6:** runtime smoke validation and log collection. **Status: reference-integrity, structural, and compile-result validation are implemented; runtime execution remains opt-in and can require configured log markers inside the selected working directory.**
- **V0.7:** ~~save-risk analysis.~~ **Closed:** save compatibility is not a Bridgeforge compatibility target across Starsector patches. The existing static identifier-diff report remains optional review context only; it must not be presented as a path to save migration or compatibility.
- **V0.8:** migration-pack/plugin ecosystem, including separate library-migration and library-adoption recommendations. **Status: discoverable, validated bundled pack registry and pack-selectable planning implemented; ecosystem rules remain deliberately empty until evidence-backed mappings are added.**
- **V0.9:** modernization-opportunity analysis; no automatic adoption. **Status: static, report-only adoption candidates implemented with explicit high behavioral risk and no automatic change path.**
- **V1.0:** repeatable scan → diagnose → plan → apply → compile → review → validate → report pipeline. **Status: orchestration command and final workspace modernization report implemented.**
