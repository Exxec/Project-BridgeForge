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
4. Fold-in workflow (item 10), then fold FX Core into RevenantLib. **Done 2026-09-20** (tooling
   task A12; FX Core fold task A13).
5. Strip/vendor planner (item 4), with Rebal phase 2. **Tooling done 2026-09-21** (`strip-plan`/
   `vendor-copy` commands, picked up out of order at the owner's later direction, 2026-09-21:
   "pick those up and look for more tooling gaps"). **Rebal phase 2 itself still open** - the
   tooling exists; actually running it against Rebal's own remaining gaps is separate follow-up
   work, not done here.
6. Provider index and dependency graph (items 2–3). **Done 2026-09-21.**
7. Licence-aware revival (item 9). **Done 2026-09-21.**
8. The Ironclads queue, last. **Triage pass started 2026-09-21** (owner-directed scope, in
   preference to picking specific mods to revive or holding off): `corpus-recheck`/`dependency-graph`
   both gained a `--include-intake` flag widening their existing scope from "mods with a
   REVIVAL_REPORT.md" to "every mod with a `working/` copy" - the Ironclads queue's 265 workspaces
   share the identical layout, so no new discovery logic was needed, only a filter toggle. Full
   real corpus-wide compile-check results and a fresh roll-up (superseding the static, pre-this
   -session `In operation/QUEUE_IRONCLADS_2026-09-14.md`) land in `In
   operation/IRONCLADS_TRIAGE_2026-09-21.md` once the run completes. Tests: `tests/test_corpus_recheck.py`
   (`test_include_intake_widens_scope_to_report_less_mods`), `tests/test_substitutes.py`
   (`test_include_intake_widens_the_dependent_side_to_report_less_mods`).
   **Triage pass completed 2026-09-21.** 305 mods checked (0 scan errors). 157 (51%) already have
   0 MANUAL findings under every check landed this session - the original queue's cheapest-first
   ordering is still valid and now current. 148 have at least 1 MANUAL finding, 49 fail
   compile-check. Most common finding: `undeclared-library-dependency` (74 mods) - the item-16
   fixer already handles this mechanically, the single highest-leverage next step if/when revival
   work starts on this queue. Full detail: `In operation/IRONCLADS_TRIAGE_2026-09-21.md`. This
   pass is triage only, per the owner's explicit choice - no mod in the queue was fixed or revived.
   The bulk revival work itself (picking mods, reviving them one at a time) remains open; this
   roadmap item stays open until that work is actually done, not just made tractable.

Items 1 and 3 share a Java-toolchain module and are built together (task A9).

Progression, each stage feeding the next:

1. **Done 2026-09-14.**
   - `dependency-substitutes`, the evidenced successor file and the strategy guide.
   - Scanner checks: `content-reference-unresolved`, `source-import-unresolved`, `legacy-vanilla-class-import`, `library-import-unused-in-jar`, `console-command-optional`, `carrier-bays-proposal`.
   - Fixers: `target-interface-method-missing`, `wing-data-missing-role-desc-column`.
2. **Provider index as a corpus artefact.** Store each visible mod's "provides" set beside the novelty fingerprints (`bridgeforge-state/`, gitignored), so a lookup is instant and works when the provider isn't installed. Record game version and mod version.
    **Done 2026-09-21.** `Provider` gained a `version` field (was tracking `game_version` only).
    New `substitutes.update_provider_index`/`load_provider_index`, wired as `bridgeforge
    provider-index-update [--providers] [--output]`: one JSON file per mod id under
    `bridgeforge-state/provider-index/` (default), matching `novelty.py`'s own
    `corpus-fingerprints/` convention exactly (same directory shape, same `glob("*.json")` load).
    `load_provider_index` reads the cache back into real `Provider` objects with no dependency on
    the mod folder still existing - verified with a test that deletes the source folder entirely
    after caching and confirms the loaded provider is unaffected. Verified against the real repo:
    317 real providers cached from `<repo>/In operation` + its rig's mods in one run. Tests:
    `tests/test_substitutes.py` (`ProviderIndexCacheTests`, 4 cases: round-trip incl. version,
    survives the source folder's deletion, empty/missing cache dir, a changed provider's cache
    entry is overwritten on a second run).
3. **Dependency graph across the queue.** Build a graph of which queued mods need which missing mods, and order revival by unblocking value. As of 2026-09-14: FX Core (10 MANUAL) unblocks FX Example and part of Rebal; AI Overhaul (12 MANUAL) the rest of Rebal. EZ Damage is already revived (r1). Show it in `board`.
    **Done 2026-09-21.** New `bridgeforge/dependency_graph.py` (`build_dependency_graph`), wired as
    `bridgeforge dependency-graph [--repo-root] [--vanilla-core] [--provider-index]`. For every mod
    with real revival work recorded (via `project_board`, same discovery `corpus-recheck` uses), a
    scan's `content-reference-unresolved`/`source-import-unresolved` findings name what it needs
    (`substitutes.required_from_scan`); a need already covered by a live, currently-installed
    provider is not a blocker, but a need with no live coverage is checked against item 2's cached
    provider index for an unrevived candidate - crediting a provider even when it isn't installed
    anywhere live right now, which is exactly item 2's own reason for existing. Ranked by how many
    dependent mods each candidate provider would unblock.
    **Scope note:** deliberately its own command, not folded into `board` - `board`'s one-mod-per-row
    shape doesn't naturally hold a cross-mod graph, and the roadmap text's "show it in board" is
    served by this command's own readable summary output instead.
    Verified against the real corpus: the exact case this whole item's intro paragraph was written
    from (Communist Clouds needing `vayra_red_army`/`vayra_*` wings from Vayra's Sector) is real and
    confirmed present, and correctly does NOT appear as unresolved, because `Vayra-Merged` is a
    live, currently-installed provider in the real corpus - exactly the "not a blocker, already
    covered" case working as designed, confirmed by checking `provider_index` directly names
    `vayramerged`/`vayrasector` as covering `vayra_red_army`. Tests: `tests/test_substitutes.py`
    (`DependencyGraphTests`, 3 cases: an uninstalled cached provider is credited and ranked by
    unblock count, a need with no cached coverage anywhere is never a ranked blocker, CLI wiring
    for both new commands together).
4. **Strip and vendor plans.** For STRIP_FROM_MOD, generate the exact edit list: which variant, `.ship` and faction lines lose which ids, plus proposed vanilla substitutes of the same slot type and size. Also generate the matching PROPOSED expected changes, so approval goes through `expect` as usual. Where the licence allows, offer vendoring as an alternative: copy the one missing piece (for example Rebal's `shields_formshield` into Explorer Society) instead of reviving a heavy provider.
    **Done 2026-09-21.** New `bridgeforge/strip_plan.py`, wired as three commands:
    - `bridgeforge strip-plan <mod> [--providers] [--vanilla-core] [--ops] [--write-expected <path> --build <tag>]`
      computes `substitutes.hard_to_cover_ids` (genuinely uncovered, or covered only by a
      too-large-to-revive provider - the exact set `strategy()` already reasons about, extracted
      into a shared `classify_chosen_providers`/`hard_to_cover_ids` rather than a second
      implementation) and, for each hard id, the exact `.variant`/`.ship`/`.skin`/`.faction`
      file+field that references it (`find_content_references`, reading every candidate file
      itself, not trusting a scanner finding's id-only, capped evidence). For weapons only, real
      vanilla substitute candidates "of the same slot type and size": the slot a missing weapon
      occupies is resolved via `_resolve_variant_hull_and_slots` (extracted, behavior-preserving,
      from `_scan_variant_validity` - the same skin-override-aware resolution item 28 built), then
      matched against vanilla-only weapons using the scanner's own
      `_weapon_slot_type_compatible`/`_override_fits`/`WEAPON_SLOT_SIZE_RANK` - never invented,
      never a second fit-check implementation. Hullmods/wings have no comparable "slot type and
      size" concept, so those entries honestly propose removal only.
    - `--write-expected` turns each entry into a real `expect` PROPOSED entry
      (`behavior_discovery.add_expected_change`, the actual D4/D5 mechanism, not a new one), so
      approval goes through `expect` exactly as the item asked.
    - `bridgeforge vendor-copy hullmod <id> <from-provider> <to-mod> [--policy] [--apply]`: the
      vendoring alternative, scoped to hullmods (a CSV row plus its declared script is a single,
      well-defined unit to copy; a weapon/wing/hull involves sprite/balance data this command has
      no reliable way to locate or validate, so those kinds are refused outright rather than
      copied incompletely). Also copies any *same-mod* loose script the declared script's own
      source directly references (one hop, best-effort, always listed - not claimed exhaustive). A
      licence gate (`release._licence_gate`, the same one item 7 uses) refuses a local-only
      source. Dry-run by default; `--apply` required to write, matching `fold`'s own convention. A
      conflict (the target already declares the id, or already has different content at a target
      file path) refuses the whole copy rather than guessing which side is right.
    Verified against real data: `strip_plan` against a synthetic ENERGY/SMALL slot correctly
    proposes a real vanilla weapon of matching type/size (and correctly excludes a same-size
    BALLISTIC weapon and a larger ENERGY one); `vendor_copy` against Zorg18's real
    `zorg_zetaoverride` correctly reports its script as jar-only (not vendored, honestly flagged);
    against Batavia's real, loose `pb_batavianradar` it copies the CSV row and script end-to-end
    (dry-run then a real `--apply`, verified on disk); and against the exact real case this item's
    own text was written from (Rebal's `shields_formshield`), it correctly **refuses** vendoring,
    because Rebal is genuinely local-only per `release_policy.json` - the licence gate doing
    exactly its job on the item's own worked example.
    **A related gap found and fixed while building this:** `substitutes.required_from_scan`'s own
    `needed` set was silently capped (see item 33) - fixed first, since `strip_plan` is built
    directly on it.
    Tests: `tests/test_strip_plan.py` (28 cases: file/field reference-finding for all four kinds
    and the faction-known-lists case, weapon substitute matching including size/type/exclusion
    edge cases, a live provider correctly zeroing out the hard-id set, `write_expected_changes`
    producing a real PROPOSED entry with mod-id sanitization, and the full `vendor_copy` matrix -
    dry-run, apply, transitive same-mod dependency copying, jar-only scripts, not-found, both
    conflict shapes, identical-content is not a conflict, the licence refusal both synthetically
    and against the real Rebal case, kind restriction, and CLI wiring for both commands).
5. **Spawn-point fleet port kit.** RC8 keeps `BaseSpawnPoint` and `addSpawnPoint`, but not `SectorAPI.createFleet(faction, fleetType)`, which 0.6 spawners use to build fleets from old faction fleet definitions. The kit is:
   - a helper that builds the equivalent fleet with FleetFactoryV3, following Zorg18 r1's spawner;
   - a scanner check for the removed call.

   It is proposed per mod, never auto-applied, because fleet composition changes. Six queued mods need it (ESCALATIONS E6).
   **Done 2026-09-14/15 (found already complete 2026-09-21 - this item was simply never marked).**
   `REMOVED_API_CALLS[0]` in `scanner.py` detects `(Global.)getSector(API)?().createFleet(...)`
   (javap-confirmed absent from RC8's `SectorAPI`) as `removed-api-call` (MANUAL). The fixer
   (`fixers._rewrite_create_fleet_span`, keyed off that same table entry) rewrites the call to
   `bf.legacyfleets.LegacyFleets.createFleet(...)`, a real, complete FleetFactoryV3-based
   implementation in RevenantLib (`In operation/RevenantLib/working/src/bf/legacyfleets/
   LegacyFleets.java`) - not a stub or a per-mod proposal, but a genuinely shared library
   solution: it re-reads a faction's own `fleetCompositions` from its `.faction` file at runtime
   (the same schema RC8's own `player.faction` still ships), builds a fleet from that composition
   via `FleetFactoryV3`/`Global.getFactory().createFleetMember`, and falls back to RC8's own
   `FleetFactoryV3.createFleet(FleetParamsV3)` generator when a composition is missing or empty -
   never returns null, matching old callers that use the result unguarded. (This overshoots "never
   auto-applied, because fleet composition changes" - the fixer *is* auto-appliable here because
   the port is a runtime library call reading the mod's own real composition data, not a
   hand-authored guess at one; a per-mod scaffold was the more conservative original framing but
   turned out to be unnecessary once the composition data was proven readable from the `.faction`
   file directly.) Confirmed in real, current use: `Antediluvians`, `Batavia`, `Cobalt-Arms`,
   `Gekelonians`, `Independant-Mining-Faction` and `Qualljom` all currently call
   `bf.legacyfleets.LegacyFleets.createFleet(...)` in their live `working/` copies - exactly the
   "six queued mods" this item named. Tests: `tests/test_fixers.py` (createFleet rewrite cases,
   including a commented-out call left untouched).
6. **Carrier-bay fixer.** Apply the approved `carrier-bays-proposal` counts, adding the `fighter bays` column where the file predates it, with per-hull approval (`--hull ID=N`).
   **Done 2026-09-15.** `fix <mod> --finding carrier-bays-proposal --hull ID=N [--hull ID=N ...] --apply` (`bridgeforge/fixers.py` `_fix_carrier_bays_proposal`). `--hull` is repeatable and required; an id with no ship_data.csv row is refused, and a count must be 0-6 (vanilla's own maximum, the Astral, read from RC8's own `ship_data.csv`). The column is added, blank for untouched hulls, the same way `wing-data-missing-role-desc-column` adds `role desc`, if the file predates it. `_scan_carrier_bays_proposal` no longer proposes a hull whose `fighter bays` is already set, so a partial approval correctly narrows what's still proposed. Tests: `tests/test_fixers.py` (`CarrierBaysProposalFixerTests`, 12 cases incl. CLI wiring), `tests/test_batch_lessons.py` (already-set hulls are skipped).
7. **Jar class rebuild for missing interface methods.** For classes compiled into a jar (AI-War), patch just those classes from source after a class-by-class diff, following the Arkgneisis precedent.
   **Done 2026-09-14/15 (task A9).** `rebuild-jar <mod> --sources DIR --jar JAR` (`bridgeforge/rebuild_jar.py`, sharing `java_toolchain` with the compile check below): rebuilds from source, packages a jar keeping the original manifest/resources, and diffs it against the original class-by-class and member-by-member, normalizing known compiler-only differences (class-file version bump, `synchronized`-only change, Lombok lock fields, synthetic `access$`/`lambda$` members). PASS/REVIEW/FAIL, with `--install` moving the previous jar to `scratch/moved-<date>/` and installing only on PASS.
8. **Removed-vanilla-content catalogue.** Record ids and classes vanilla dropped between versions (the `thruster_fighter_sm` / `shields_formshield` kind), with evidence and successors, so "defined nowhere" becomes "removed in 0.9x; use X".
    **Done 2026-09-21.** `dependency_successors.json` already had the right shape (`match`/`kind`/
    `successor`/`action`/`evidence`) and was already consulted by `dependency-substitutes`, but a
    plain `scan` never read it - `content-reference-unresolved`'s own finding just said "defined
    nowhere" regardless. Added two real, directly-verified `removed-vanilla-content` entries
    (`thruster_fighter_sm`, `shields_formshield`: confirmed absent from the real RC8 install's own
    `weapon_data.csv`/`hull_mods.csv` directly, confirmed present and resolvable in RevenantLib's
    own files directly - not taken on faith from `PROVENANCE.md`'s own claims, both independently
    re-checked). `_scan_unresolved_content_references` now consults this same catalogue (local
    import to avoid a `scanner`<->`substitutes` cycle) and enriches the matched id's evidence line
    with the successor text plus a note in the finding's own explanation - "defined nowhere"
    genuinely becomes "removed-vanilla-content, not just missing: <successor>", read directly off
    a plain scan, no separate `dependency-substitutes` run needed. Neither real id currently
    triggers this in the live corpus (both `Xenoargh-ExplorerSociety` and other real consumers
    already vendored `thruster_fighter_sm` locally or declare `revenantlib`) - verified with a
    hermetic synthetic case instead, using the real catalogue text. Tests: `tests/test_scanner.py`
    (`test_a_known_removed_vanilla_content_id_gets_its_catalogued_successor_in_the_evidence`).
9. **Licence-aware revival of dependencies.** Before REVIVE_DEPENDENCY, check `release_policy.json` so a revived library is marked local-only when its licence doesn't allow redistribution.
    **Done 2026-09-21.** New `substitutes._licence_note`/`strategy(..., policy_path=...)`: any
    provider `strategy()` recommends reviving (the `revive`/`heavy` lists) gets its
    `release_policy.json` entry checked via `release._licence_gate` (the exact same function
    `release` itself uses - one licence check, not two), and a local-only provider's recommendation
    text gets a `[licence: local-only, not for release distribution - <reason>]` note appended right
    where the recommendation is made, not discovered later at `release` time. Read-only; never
    changes the recommended verdict itself, since licence status is a distribution constraint on
    the outcome, not a reason to prefer a different strategy. `dependency_substitutes(...,
    policy_path=...)` and a new `dependency-substitutes --policy` CLI flag thread a custom policy
    path through (default: the bundled `release_policy.json`, same default `release` itself uses).
    Verified against the real bundled policy: `xxx_ss_FX_mod_core` (Xenoargh's FX Core, genuinely
    local-only per its real entry) produces the real licence note text unprompted. The one live mod
    that used to need FX Core revived (`Xenoargh-FX-Example`) now resolves to `SWAP` instead of
    `REVIVE_DEPENDENCY`, because this session's own earlier fold-in work already folded FX Core into
    RevenantLib - confirmed there is currently no live `REVIVE_DEPENDENCY`+local-only case left in
    the corpus to demonstrate end-to-end, which is itself a sign the fold-in work did its job; the
    licence-check path itself is fully covered by direct tests against the real policy file and a
    full `dependency_substitutes()` integration test with a custom policy and a real workspace
    layout. Tests: `tests/test_substitutes.py` (`LicenceAwareRevivalTests`, 5 cases).
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

    **FX Core folded 2026-09-20 (task A13, `In operation/ESCALATIONS.md` E9, owner course A).** Ran
    `fold` for real against `In operation/Xenoargh-FX-Core/working` (dry-run first). The tool names the
    copied provenance folder after the literal basename of its `source` argument, which under
    BridgeForge's own `<Mod>/working` layout is always `working` — the raw output landed at
    `original/working/` and was renamed to `original/Xenoargh-FX-Core/` right after (logged in
    RevenantLib's `scratch/MOVES.log`), to match the naming convention `original/Vacuum`/
    `original/Xenoargh-Rebal` already set; every future fold of a `working/` copy will hit the same
    naming quirk unless `fold.py` is changed to name the folder from mod_info.json's own id/name
    instead of the source path's basename. Unlike Vacuum/Rebal, FX Core's package (`data.scripts.*`)
    was deliberately kept unrenamed (Xenoargh-FX-Example resolves it by name), making this fold's
    do-not-enable-alongside-the-original warning a hard class clash rather than the softer duplicate-id
    case. The owner's "make the cost lazy" decision was implemented as a lazy, thread-safe
    (double-checked locking) `ensureExecutor()` around `FX_Plugin`'s static `ExecutorService` field,
    scoped to exactly that field per the task; `FX_Plugin`'s modPlugin was not declared (redundant with
    RevenantLib's existing `lw_lazylib` dependency). RevenantLib bumped to `1.2.0+bf.1`.
    Xenoargh-FX-Example's dependency was repointed via the `revenantlib-fold-conflict` fixer path
    (add `revenantlib` by hand first, then `fix --apply`); rescanned clean (0 MANUAL, same REVIEW/SAFE
    counts as before). Details: `In operation/RevenantLib/reports/PROVENANCE.md` ("Origin: Xenoargh FX
    Core"), `reports/README.md`, `working/reports/REVIVAL_REPORT.md`'s 2026-09-20 update.

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
    **Done 2026-09-21.** New `scanner._dependency_jar_class_names`, extending
    `_scan_loose_script_janino_risk` (already the single place that walks every loose script once)
    to also check a script's class name against every *declared dependency's* jar classes, using
    the same `provider_index`/class-file-parsing machinery `compile-check`/`verify-shadow` already
    use - not a second implementation. A shadowed script's `loose-script-janino-risk` is suppressed
    the same way the existing same-mod case already was, and the new
    `loose-script-shadowed-by-dependency-jar` (MANUAL) names the shadowing dependency. Only a
    *declared* dependency counts - an undeclared mod sharing a class name by coincidence is not
    claimed as shadowing.
    **A real regression caught and fixed before committing:** the first version defaulted
    `provider_roots` to `java_toolchain.DEFAULT_PROVIDER_ROOTS` (this repo's own real `In
    operation` folder) whenever the caller didn't supply one - reasonable for an explicit,
    single-purpose command like `compile-check`, but `_scan_loose_script_janino_risk` runs on
    *every* `scan_mod` call unconditionally, so this silently made every scan of a mod with
    declared dependencies walk the real ~325-mod `In operation` folder regardless of what was
    actually being scanned. The full test suite went from ~78 seconds to 518 seconds before this
    was caught by simply re-running it after the change. Fixed by requiring an explicit
    `provider_roots` with no default fallback at all - the check is a safe no-op unless the caller
    opts in (`scan --providers`, `fix --providers`, or any direct caller that supplies its own),
    mirroring `compile-check`'s own explicit opt-in. Extended item 14's `_refuse_shadowed_edits`
    fixer guard to the same cross-mod case (a new `fix --providers` flag), since a fixer editing a
    dependency-jar-shadowed script is exactly as dead-on-arrival as editing a same-mod-shadowed one.
    Verified against the real, original Maelstrom bug state (the two files item 27 had already
    moved out of the working copy this session were copied back in for this test): the check
    correctly fires with real evidence naming "Interstellar Imperium," and correctly produces
    nothing when `provider_roots` isn't supplied. Tests: `tests/test_intake_scanner_fixes.py`
    (`CrossModLooseScriptShadowTests`, 3 cases), `tests/test_fixers.py`
    (`RefuseCrossModShadowedEditTests`, 3 cases).

13. **compile-check: two javac-integration bugs (found by task A14, 2026-09-20).**
    - `compile_check` does not pass `-sourcepath ""`, so when a dependency jar bundles `.java`
      sources beside its classes (Interstellar Imperium`s `II.jar` does), javac implicitly
      recompiles those bundled sources and reports errors for libraries the mod under test never
      declared. Pure noise, attributed to the wrong mod.
    - `java_toolchain.parse_javac_errors` does not recognise javac`s jar-embedded source header
      format `somejar.jar(/entry.java):LINE: error:`, so those lines` `symbol:`/`location:` detail
      lines are appended to whichever real error was parsed last. In A14`s run one genuine error
      accumulated 726 spurious detail entries.
    **Done 2026-09-20.** `DEFAULT_JAVAC_ARGS` now carries `-sourcepath ""` (every caller already
    passes its sources explicitly, so nothing relied on implicit lookup), and
    `parse_javac_errors` recognises the `<jar>(/entry.java):LINE:` header and skips it, resetting
    `current` so its continuation lines cannot attach to the previous real error. Verified on the
    real case (Maelstrom compiled against Interstellar Imperium): the worst error went from 726
    spurious detail entries to 2, with all 22 errors still correctly attributed to the one
    pre-existing file. Tests: `tests/test_java_toolchain.py` (`JarEmbeddedSourceDiagnosticTests`).
    Both inflate error counts and mis-attribute them, which matters most for `scan --compile-check`
    across the Ironclads queue. Needs a fix plus a regression test with a jar that carries sources.

14. **Fixers must refuse to edit a jar-shadowed loose script.** `loose-script-shadowed-by-jar` is
    SAFE/informational, and its own explanation says edits to those files have no effect - yet
    nothing stops a fixer (or an agent) editing one. On 2026-09-20 task A17 converted six
    `setPersonality("suicidal")` calls to `"reckless"` in Thule-Legacy's
    `data/missions/thule_mission_operation_n/MissionDefinition.java`, wrote a full evidence trail,
    and produced **no behaviour change at all**, because `jars/ThuleLegacy.jar` ships that class and
    the jar wins. The scan it ran listed the file under `loose-script-shadowed-by-jar` (`count:18`)
    both before and after.
    Fix: `apply_fix` should check the target against the shadow set and refuse (or demand an explicit
    override), naming the jar that supplies the class and pointing at the real remedy - rebuild the
    jar from patched source, or strip the class so the loose script compiles. Pairs with item 12
    (the same detection across mods) and the `loose-script-jar-precedence` rule. Needs a regression
    test with a mod whose jar shadows a file a fixer would otherwise edit.
    **Done 2026-09-21.** `compute_fix` now calls a new `_refuse_shadowed_edits` before returning a
    plan, for every `.java` change under `data/`. The real jar-parsing logic
    (`_iter_jar_class_files`/`_parse_class_file`) was factored out of the scanner's own
    `loose-script-shadowed-by-jar` check into two reusable functions -
    `scanner.mod_jar_class_names`/`scanner.loose_script_jar_shadowed_class` - so this is the same
    detection, not a second implementation of it (also lays groundwork for item 26's `verify-shadow`
    command). An explicit `allow_shadowed_edit` option (CLI: `fix --allow-shadowed-edit`) overrides
    the refusal for the case this session actually hit - rebuilding the jar from patched source in
    the same pass. Tests: `tests/test_fixers.py` (`RefuseShadowedEditTests`).
15. **New check: a mod's preset entry can silently downgrade vanilla for the whole game, mod-wide.**
    `engine_styles.json`, `hull_styles.json`, `custom_entities.json`, `sounds.json` and
    `planets.json` are merged by **whole-entry replace, not a per-field merge** (Starsector's own
    wiki: "any mod added entries with keys ... the same as core game entries will see the mod
    entries replace the core game entries"). Found 2026-09-20 on Zorg18: `engine_styles.json`
    redefined vanilla's `LOW_TECH`/`MIDLINE`/`HIGH_TECH` as an older, incomplete copy of each
    (missing a `contrailCampaignColor` key vanilla's current file has, from being copy-pasted as a
    template and never trimmed). The prior pass had called this "byte-for-byte identical, harmless"
    without actually diffing field-by-field against vanilla — it wasn't, and the mod was silently
    stripping that colour from every LOW_TECH/MIDLINE/HIGH_TECH-styled ship in the player's entire
    game (vanilla and every other enabled mod) while enabled. Fixed by hand this time; needs a
    scanner check so it isn't missed again: for each of the five preset files, if a mod redefines a
    top-level id that also exists in vanilla's own copy of that file, diff the two dicts field by
    field and flag REVIEW/MANUAL (severity depends on whether fields are missing vs. actively
    different) naming exactly which fields would be lost mod-wide. A mod's own file that only adds
    new ids (like `ZORG_TECH` alongside the trimmed file) triggers nothing.
    **Done 2026-09-21.** New `_scan_preset_whole_entry_replace`, covering the four files with
    confirmed uniform top-level-id-to-dict structure (`engine_styles.json`, `hull_styles.json`,
    `custom_entities.json`, `planets.json`). `sounds.json` is deliberately excluded: its top-level
    keys are categories, not entry ids, its per-category values are often lists, and this check
    does not guess at unverified merge granularity - a documented gap, not an oversight.
    `preset-whole-entry-replace-loses-vanilla-fields` (MANUAL, missing fields) and
    `preset-whole-entry-replace-changes-vanilla-fields` (REVIEW, only differing values) are two
    separate literal finding ids (not a single id chosen by a ternary), since
    `tests/test_bug_class_registry.py` greps scanner.py for a literal `id="..."` per documented
    check. Verified the check produces no false positive on Zorg18's current, already-hand-fixed
    working copy (`scan --vanilla-core` finds 0 preset-whole-entry findings there now). Recorded as
    `docs/BUG_CLASSES.md` BF-PRESET-01. Tests: `tests/test_release_hygiene_checks.py`
    (`PresetWholeEntryReplaceTests`).
16. **New fixer: `undeclared-library-dependency` (declare the missing dependency automatically).**
    The scanner already detects a mod using a known library's package (LazyLib, MagicLib,
    GraphicsLib) without declaring it (`source-library-dependency-undeclared` /
    `undeclared-library-dependency`), but nothing applies the fix - it was hand-edited into
    `mod_info.json` three times this session (EZFaction, Maelstrom, Leon-Heavy-Industries), each a
    one-line `{"id": ..., "name": ...}` addition to `dependencies` using the exact id/name pairs
    `LIBRARY_PACKAGES` already maps package prefixes to. A fixer following `_add_revenantlib_dependency`'s
    existing pattern (dependencies-array insertion, both-shapes "already declared" check, `.bak`
    backup) would make this mechanical instead of manual, which matters most across the Ironclads
    queue's 264 mods, where this exact defect class is common in mods that age from before
    dependencies were declared explicitly.
    **Done 2026-09-21.** New `_fix_undeclared_library_dependency`, following
    `_add_revenantlib_dependency`'s pattern via a new generalized `_add_dependency_entry` helper.
    Found and fixed a real bug while building it: `scanner.LIBRARY_DEPENDENCY_IDS` had the wrong
    case for two libraries (`magiclib`/`shaderlib` instead of the real `MagicLib`/`shaderLib`) -
    found by reading those libraries' own installed `mod_info.json` directly, corroborated by
    `revival_audit.py`'s already-correct copy of the same table. The scanner's own detection was
    unaffected (its comparison is case-insensitive), but a fixer writing the wrong case would have
    produced a dependency declaration that may not actually resolve in-game - fixed before the fixer
    was built on top of it. Tests: `tests/test_fixers.py` (`UndeclaredLibraryDependencyFixerTests`).
17. **Audit every scanner "known ids" set for the same missing-skin-chain blind spot BF-SKIN-01
    exposed.** `mission-local-variant-hull-missing` built its known-hulls set from `*.ship` files
    only and never chased a `.skin`'s `baseHullId` chain, false-flagging real content on
    Leon-Heavy-Industries (fixed 2026-09-20, `docs/BUG_CLASSES.md` BF-SKIN-01). That was found by
    accident, not by a systematic check - `_scan_variant_validity` already resolved skins correctly
    while its sibling didn't. Worth a deliberate pass over every scanner function that builds a
    hull/weapon/wing "known ids" set (`_declared_spec_ids` callers, mission and campaign fleet
    reference checks, carrier-bay/OP-budget checks) to confirm each one that should resolve through
    `.skin` chains actually does, rather than finding the next instance the same way this one was
    found.
    **Done 2026-09-20.** Audited every `hulls = set(_declared_spec_ids(..., "*.ship", "hullId"))`
    site and every `_ship_file_index` call. Found and fixed one real second instance:
    `_scan_campaign_fleet_references` (`campaign-fleet-reference-missing`) had the exact same gap -
    fixed by resolving a hull literal through `_resolve_hull_id`/`_skin_index` before checking
    membership, same as `_scan_mission_variant_assets`. Two other candidates checked and found
    correctly scoped as-is: `_scan_carrier_bays_proposal`/`_scan_description_missing` iterate
    `ship_data.csv`'s own base-hull rows (which are never skin ids, so no gap), and
    `_scan_faction_known_lists` only checks list *presence*, not whether listed ids resolve (a
    different check shape, out of scope for this bug class). Tests:
    `tests/test_zorg_campaign_checks.py`. Recorded as the second instance under BF-SKIN-01.
18. **Downloads-wide research needs an index, not a live `grep -r` with a short timeout.** While
    investigating O2.2 (2026-09-20), a `timeout 60 grep -rl "shieldbypass" "Downloads"` returned zero
    matches - a false negative caused purely by the timeout, not by the string's absence: the file
    was there (`Ship and Weapon Pack/data/hullmods/hull_mods.csv`), found immediately once searched
    directly. The Ironclads archive is large enough that an unindexed live grep across all of
    Downloads is not reliable evidence of absence. Item 8 (Ironclads queue tooling) should build a
    one-time content index (filenames plus a grep-able concatenation or a small sqlite FTS table) of
    the whole Downloads archive once, rather than repeated ad hoc greps with a timeout that can
    silently fail before reaching the relevant file.
    **Done 2026-09-21.** New `bridgeforge/archive_index.py` (`build_index`, `search_index`), wired
    as `bridgeforge archive-index <root> --output <index.db>` and `bridgeforge archive-search
    <index.db> <query> [--filenames]`. A small sqlite3 database (stdlib only; this Python build's
    sqlite3 ships FTS5) indexes every `*.zip` under `root`: every member's path/size always (a fast
    filename index), and the text content of small, source/data-shaped members only
    (`TEXT_EXTENSIONS`: `.java`/`.json`/`.csv`/`.wpn`/`.ship`/`.variant`/`.skin`/`.system`/
    `.faction`/etc., capped at 5MB/file) via an FTS5 table - binary assets are indexed by filename
    only, never read as content. Incremental: an archive whose size and mtime haven't changed since
    the last run is skipped, so re-running as the archive folder grows stays cheap. A corrupt or
    password-protected member never aborts the run - it's recorded and skipped, found by the very
    first real run hitting a `RuntimeError` from a password-protected entry (`zipfile`'s own
    exception type for that case, easy to miss).
    Verified against the real, full Downloads archive (214 real `*.zip` files, including the nested
    `Ironclads mega archive/` subfolder, 212 indexed cleanly and 2 genuine non-zip files correctly
    reported as errors, not crashes): `archive-search ... "shieldbypass"` reproduces the exact real
    case this item was written from, finding `Ship and Weapon Pack/data/hullmods/hull_mods.csv`
    (and 49 other real matches across the archive) that the original `timeout 60 grep -rl` missed
    entirely. Tests: `tests/test_archive_index.py` (8 cases: filename+content indexing, binary
    content never indexed, incremental skip/reindex, corrupt-archive handling, size-cap behavior,
    the real password-protected-member regression, search-before-build, CLI).
19. **New command: value-diff two org.json-dialect files, not a line diff.** Found 2026-09-20
    building E11's data-only rebuild plan for Rebal: diffing a mod's file against a real historical
    vanilla reference showed the two use different key order and formatting (pretty-printed vs.
    commented blocks), so a plain text diff is swamped by noise and hides the one genuine semantic
    change actually present. Every future data-only rebuild (Rebal is very unlikely to be the only
    mod in the Ironclads queue built this way) needs the same field-level comparison, done by hand
    each time otherwise. A `bridgeforge diff-data <file_a> <file_b>` command should load both through
    `_load_lenient_json_file` and report added/removed/changed keys by value, recursing into nested
    dicts and lists, with formatting/key-order differences producing no output at all.
    **Done 2026-09-21.** New `bridgeforge/diff_data.py` (`diff_data`), wired as
    `bridgeforge diff-data <file_a> <file_b> [--json]`. Loads both files through
    `_load_lenient_json_file` and recurses: a dict diffs key by key (added/removed/changed at that
    key's own path, e.g. `weaponSlots.WS001.arc`); a list diffs by index only when both lists are
    the same length (no reliable way to align differently-sized lists without knowing the data's
    own identity field, which varies per file class - a length mismatch is one whole-value
    "changed" entry instead); everything else compares by value. Verified on real data: a
    formatting/key-order-only pair (comments, trailing commas, reordered keys) reports IDENTICAL,
    and Rebal's real `amblaster.wpn` against RC8 vanilla's real counterpart reports exactly 5 true
    field differences (2 sound/animation fields, a barrel mode, a hardpoint offset, one removed
    field) with zero formatting noise. Tests: `tests/test_diff_data.py`.
20. **`vanilla-path-shadowing` should report the true file count, not a folder rollup.** E3's original
    estimate for Rebal ("~79 files") was a per-folder finding count; the real number, counted
    directly, is 642 - an 8x understatement that shaped this item's scoping for a full session before
    being caught. Whatever scanner logic rolls this finding up by folder should also emit (in
    `migration_context`, and ideally in the finding's own evidence line) the true total file count
    across every shadowed folder, so the next mod with this pattern doesn't need an agent to
    rediscover the same gap between "findings" and "files."
    **Done 2026-09-21.** `result.migration_context["vanilla_path_shadowing_total_files"]` now carries
    one grand total across every shadowed folder in the mod, independent of how many findings the
    `>VANILLA_SHADOW_GROUP_THRESHOLD` grouping produced. Verified against Rebal's real, still-partial
    rebuild state. Tests: `tests/test_rc8_bytecode_checks.py`
    (`test_migration_context_carries_the_true_total_across_every_folder`, and a negative case
    confirming the key is absent when nothing shadows).
21. **Generalize E11's rebuild-from-a-reference-rig method into a command.** Built by hand this
    session (enumerate a mod's files that share a path with a reference rig's vanilla copy; for each,
    value-diff the mod's file against the reference AND against current RC8 vanilla; keep fields RC8
    added since the reference version untouched, overlay only the mod's genuine changes onto a fresh
    copy of the current vanilla file). This is generally useful for any old mod that ships modified
    copies of vanilla files under vanilla's own paths (Rebal's actual defect class, and likely not
    unique to it in the Ironclads queue) - worth a `rebuild-from-reference` command once item 19's
    value-diff primitive exists, parameterized by file class (`.wpn`/`.ship`/`.variant`/etc.) so a
    large mod can be rebuilt in reviewable stages rather than one pass across hundreds of files.
    **Done 2026-09-21.** New `bridgeforge/rebuild_from_reference.py` (`rebuild_from_reference`),
    wired as `bridgeforge rebuild-from-reference <mod> --reference-core <rig> --current-core <RC8>
    [--glob <pattern>] [--apply <output-dir>] [--json]`. For every file the mod shares a relative
    path with in both vanilla copies, diffs mod-vs-reference with item 19's `_diff_values` to find
    only the mod's own genuine authored changes, then overlays just those changes onto a copy of
    the current file (added/changed keys set, removed keys deleted - a removal already absent from
    current is a no-op, not a conflict). Where current vanilla itself diverges from the reference on
    a path the mod also touched, the mod's value still wins but the conflict is surfaced by path
    with all three values, never silently resolved. Read-only by default; `--apply` writes rebuilt
    files under a separate output directory, never the mod's own working copy. `--glob` scopes a
    large mod's rebuild into reviewable stages, per this item's own spec. Verified against real
    data: Rebal's actual registered 0.9a reference rig and RC8's own real `starsector-core` -
    82 real `.wpn` files, 76 REBUILT cleanly and 5 genuine CONFLICTs correctly surfaced (e.g.
    `hammer.wpn`'s `fireSoundTwo`, `hil.wpn`'s `width` - real fields RC8 changed independently
    since the reference version). Tests: `tests/test_rebuild_from_reference.py`.
22. **`rig-doctor`'s `enabled_mods_resolve` check FAILs on every freshly registered reference rig.**
    A brand-new historical install has no mods enabled yet, so `mods/enabled_mods.json` doesn't
    exist - correct and harmless, but it prints as FAIL rather than PASS/SKIP, noise on every P10
    reference-rig registration (found 2026-09-20 registering Rebal's 0.9a rig). Should treat a
    missing `enabled_mods.json` as PASS when the mods folder is otherwise empty of workspaces, or as
    SKIP with an explanation, rather than FAIL.
    **Done 2026-09-21.** A missing `enabled_mods.json` now checks whether `mods/` holds any mod
    workspaces at all (`_mods_by_id`); PASS when it doesn't (a fresh install/reference rig with
    nothing enabled yet), FAIL only when workspaces exist with nothing declared enabled. Verified
    against the real 0.9a reference rig registered for E11 (was FAIL, now PASS). Tests:
    `tests/test_rig_doctor.py` (`test_pass_when_missing_file_but_no_mod_workspaces_exist`,
    `test_fail_when_missing_file_and_mod_workspaces_exist`).
23. **Full corpus recheck before live testing (owner-requested, 2026-09-20).** Every mod that has
    any revival work recorded - a claimed status (`READY_FOR_LIVE_TEST`, `READY_WITH_REVIEW_ITEMS`,
    `IN_PROGRESS`) in `In operation/STATUS.md`'s board, or its own `reports/REVIVAL_REPORT.md` - gets
    re-scanned with everything fixed this session, before any of it reaches an owner live-test
    session. **Scope excludes:** the 264-mod Ironclads lowest-priority intake queue (scanned and
    fingerprinted at intake, but "none is revived or in the rig" per `STATUS.md` - nothing to
    recheck yet, that's item 8's job later) and duplicate mods (the 14 older-version duplicates
    already excluded at intake, plus any workspace that is a strict duplicate/superseded copy of
    another mod already on the recheck list - e.g. an older jar variant or a second intake of the
    same underlying mod under a different name; identify these explicitly as the first step rather
    than assuming the obvious ones are the only ones).

    **Why now, not earlier:** several of this session's fixes change what a scan/compile-check
    actually reports, so mods checked before they landed may have stale or wrong numbers:
    - Item 13 (`650f5903`) - compile-check no longer misattributes jar-embedded-source errors to the
      wrong mod, and no longer inflates one error into hundreds of spurious detail lines. Any mod
      whose compile-check was run before this fix, especially one with a dependency that bundles
      `.java` sources beside its classes, should be re-checked.
    - BF-SKIN-01 (`da13ce1a`) - `mission-local-variant-hull-missing` (and its sibling weapon check)
      no longer false-flags content that resolves through a `.skin` chain. Any mod with mission
      variants and skins should be re-checked for the same false positive Leon-Heavy-Industries had.
    - The undeclared-library pattern (EZFaction, Maelstrom, Leon-Heavy-Industries this session) - a
      mod using LazyLib/MagicLib/GraphicsLib without declaring it is not rare; a corpus-wide
      `compile-check` sweep is the cheapest way to find every remaining instance at once, now that
      item 13 makes the error counts trustworthy.
    - Item 12 (cross-mod loose-script shadowing, still open) and item 17 (auditing every "known ids"
      builder for the same blind spot BF-SKIN-01 exposed) should land before or during this sweep,
      not after, so the recheck benefits from them rather than needing a second pass.

    **Procedure:** (1) enumerate the recheck list and the excluded-duplicates list explicitly, write
    both down before scanning anything; (2) run `scan --compile-check` against each mod with the
    RC8 core and every declared dependency resolvable as a provider; (3) diff each mod's new finding
    set against its last recorded one - flag any *new* MANUAL as a regression needing explanation,
    and any finding that *disappeared* only because of a tooling fix as a confirmation, not silently
    accepted; (4) record results in each mod's own `REVIVAL_REPORT.md` plus one corpus-level roll-up
    table (mod, before count, after count, new issues, status change) so the owner sees the whole
    picture in one place; (5) update `STATUS.md`'s board with any status changes. A mod that comes
    out of this with new MANUAL findings does not proceed to live testing until they're resolved or
    explicitly accepted by the owner.
    **Done 2026-09-21.** Recheck list built from every real `REVIVAL_REPORT.md` under a mod's
    canonical `working/` tree (40 mods; `board --json`'s own status parser only resolves 9 of them
    cleanly, so it couldn't be used alone). Ran `scan_mod(..., compile_check=False)` for the finding
    set plus the standalone `compile_loose_scripts` for the compile signal, since `scan
    --compile-check` itself (`scanner._scan_compile_check`) calls `compile_loose_scripts` with no
    `provider_roots` at all and cannot resolve a declared dependency the way the standalone command
    does by default - a real gap between the roadmap text and the actual code, worked around rather
    than followed literally. Result: all 9 mods with a clean declared ready status are still 0
    MANUAL/compile PASS - no regression in anything currently claimed ready. Real finding: item 15's
    new check (this session's own work) found 6 previously-unknown, real mod-wide preset-override
    bugs (verified by hand against two of them); `Antediluvians`/`Batavia`/`Renis-Imperium`/`Vacuum`/
    `Xenoargh-EZFaction` downgraded to `IN_PROGRESS`, `Xenoargh-FX-Example` to
    `READY_WITH_REVIEW_ITEMS` pending an owner call on whether its custom colors are intentional.
    `Firestorm-Federation` (a real `initStar` signature-drift compile bug) and `Scion-Collective`
    (already-flagged `CrewXPLevel`) got their first full pass; neither was previously claimed ready.
    Full roll-up, every report update and the STATUS.md board entry: `In
    operation/CORPUS_RECHECK_2026-09-21.md` (gitignored, per this repo's workspace convention).
24. **A scanner self-check for the id-resolution blind spot item 17 found by hand.** Item 17 was a
    manual audit: read every function that builds a "known ids" set and reason about whether it
    should chase a `.skin`'s `baseHullId` chain. That worked, but it doesn't stop a *third* instance
    from being found the same way - by accident, in whatever mod happens to trip it next. A small
    dev-facing check (run as part of the test suite or `docs-index`, not shipped as a mod finding)
    should enumerate every call site that builds a hull-id set from `_declared_spec_ids(...,
    "*.ship", ...)` or `_ship_file_index(...)`, and either assert each one also consults
    `_skin_index`/`_resolve_hull_id` (or is on a documented exemption list, with the exemption's
    reasoning inline - `_scan_carrier_bays_proposal`/`_scan_description_missing` iterate
    `ship_data.csv`'s own base-hull rows, which are never skin ids, so they're exempt on principle,
    not by oversight). New code that builds a fourth such set without the resolution (or an
    exemption) then fails this check immediately, at review time, instead of waiting for the next
    mod to expose it in production.
    **Done 2026-09-21.** `tests/test_skin_chain_resolution_audit.py`: an AST walk over
    `bridgeforge/scanner.py` finds every function calling `_declared_spec_ids(..., "*.ship", ...)`
    or `_ship_file_index(...)`, and asserts each either references `_skin_index`/`_resolve_hull_id`
    in its own body or is on a written `EXEMPT_SKIN_CHAIN_RESOLUTION` list (currently
    `_scan_carrier_bays_proposal`/`_scan_description_missing`, matching item 17's own findings).
    Verified the check actually catches a regression (a synthetic offending function was flagged,
    then discarded) rather than rubber-stamping. Runs as part of the normal test suite, not a
    shipped scan finding, per this item's own spec.

    **Note on item 19 (the `diff-data` command):** every stage of E11's Rebal rebuild (weapons done,
    hulls in progress, variants and shipsystems/skins still ahead) has needed the same
    value-diff-not-line-diff logic reimplemented by hand in that stage's brief. Building item 19
    before the variants stage (by far the largest remaining batch, ~308 files) would make that stage
    cheaper and more reliable rather than a fourth from-scratch reimplementation - worth doing
    whenever item 19 is picked up, even though it isn't gating any stage strictly.
25. **"Same path as vanilla" is not proof of jar-shadowing - a real verification gap, found by the
    coordinator's own mistake.** Item 14 guards the failure mode of treating a jar-shadowed loose
    script as live and editing it for nothing (Thule). This is the *inverse* failure, found
    2026-09-21: treating a loose script as safely-droppable *because* it shares a path with a
    vanilla file, without ever confirming a jar actually backs that path. E11's stage 1 moved 50 of
    Rebal's `data/**.java` files (47 hullmod scripts, 3 shipsystem-stats scripts) on exactly that
    reasoning - "present at the same relative path under RC8's own `starsector-core/data`... jar
    wins" - but the check that produced that claim only tested path existence
    (`(vanilla_core / rel).is_file()`), never jar membership. A direct, unrestricted search of every
    jar in `starsector-core` (including `starfarer_obf.jar`) for any of the 50 class names found
    **zero matches for all 50** - none were jar-shadowed; all 50 were live, in-game-effective code
    that RC8's own file-replacement rule (mods override core at a shared path - Starsector Wiki,
    "Miscellaneous modding tidbits") would have run in place of vanilla's current loose scripts.
    Recorded as `In operation/ESCALATIONS.md` E12; course B (port the 50 files properly using
    E11-style diffing rather than accept the drop) chosen 2026-09-21.
    Fix: the same helper `loose-script-shadowed-by-jar` already uses internally (real jar-class-file
    parsing, `_iter_jar_class_files`/`_parse_class_file`) should be the *only* sanctioned way to
    claim a loose script is jar-shadowed anywhere in this codebase - in a scan finding, a fixer
    guard (item 14), or a one-off investigation script written for a specific mod. A `rg
    "\.is_file\(\)"` audit of every ad hoc "is this shadowed" check written during a live
    investigation (not just the scanner's own checks, which item 24 already covers) would catch the
    next instance of this same shortcut before it produces a wrong claim that reaches the owner.
26. **New command: `verify-shadow` - the real jar-parsing check, callable directly instead of
    reimplemented ad hoc.** Item 25's actual fix, not just its lesson. `loose-script-shadowed-by-jar`
    already has the correct logic buried inside a scanner pass
    (`_iter_jar_class_files`/`_parse_class_file`, real class-file parsing against a target jar set),
    but there is no way to just ask it "does *this* jar set actually contain a compiled class for
    *this* loose script" outside a full mod scan - which is exactly why E12 happened: a live
    investigation reached for a quick `Path.is_file()` check instead of the real one, because the
    real one wasn't directly callable. `bridgeforge verify-shadow <script-path> --against <jar-or-core-dir>`
    should answer that one question directly, reusing the scanner's own parsing (not a second
    implementation of it), and print which jar (if any) supplies the class. Every future "is this
    safe to drop" claim - in a task brief, an investigation script, a fixer - should call this
    instead of writing a path check.
    **Done 2026-09-21.** `bridgeforge verify-shadow <script> --against <jar-or-dir> [--root <root>]`
    (new `scanner.verify_shadow`/`scanner._iter_class_files_in`, reusing `_parse_class_file` - the
    same real class-file parsing `mod_jar_class_names`/`loose_script_jar_shadowed_class` (item 14)
    and the scanner's own `loose-script-shadowed-by-jar` check use, no second implementation).
    `--against` takes a single jar or a directory searched recursively for jars, so it answers
    against an arbitrary jar set, not just a mod's own declared jars. Verified against both real
    E12 outcomes: `FrontShieldEmitter.java` against RC8's real `starsector-core` reports
    NOT_SHADOWED (matching the real, corrected finding), and Thule-Legacy's
    `thule_mission_operation_n/MissionDefinition.java` against its own working copy reports
    SHADOWED, naming `ThuleLegacy.jar` (matching item 14's real live bug). Tests:
    `tests/test_verify_shadow.py`.
27. **The full corpus recheck (item 23) should include an audit of every "moved because shadowed"
    decision made before item 25 was found, not just a fresh scan.** E12 (2026-09-20/21) found that
    a `Path.is_file()` path-existence check had been trusted as proof of jar-shadowing at least once
    (Rebal's 50 `.java` files) with the actual claim never verified. Item 23's sweep already re-scans
    every revived mod with current tooling, which will re-run the scanner's own (correct)
    `loose-script-shadowed-by-jar` check - but it won't by itself catch a file that was manually
    *moved out of* a working tree on the same flawed reasoning before the sweep runs, since a moved
    file has nothing left in `working/` to rescan. Item 23's procedure should add an explicit step:
    grep every mod's `scratch/MOVES.log` for a "shadow"/"jar" rationale, and for each one, run item
    26's `verify-shadow` against the actual jar set that reasoning named, before trusting the move
    was correct.
    **Done 2026-09-21 (standalone, ahead of item 23).** `grep -riE "shadow|jar"` across all 299
    `scratch/MOVES.log` files currently in `In operation/`. Filtered out mod-name false positives
    (e.g. "Shadowyards") and ordinary jar-supersession/rebuild entries (AI-War, Omega-Trauma,
    RevenantLib, Xenoargh-AI-Overhaul, Xenoargh-FX-Core/Example, Zorg18 - version swaps, not
    shadowing claims). Two real "moved because shadowed" decisions found:
    Maelstrom-Interstellar-Imperium-Unofficial-Expansion's `II_TitanBombardment.java`/
    `II_TitanPlugin.java` (task A14/E8) and Xenoargh-Rebal's 50-file move (E12, already caught and
    course-B'd - not re-litigated here). Re-verified the Imperium expansion's claim independently
    with item 26's `verify-shadow` against the base mod's real `II.jar`
    (`...\Interstellar Imperium-2.6.9\jars\II.jar`): both report SHADOWED, confirming the original
    claim (which was itself backed by real `javap`/`compile-check` evidence, not a path guess - the
    correct pattern this whole item exists to enforce). No further wrong moves found. Item 23's
    procedure should still re-run this grep as new moves accumulate.
28. **`_scan_variant_validity` doesn't resolve a `.skin`'s own slot-type overrides before checking
    weapon/slot fit - a scanner gap distinct from BF-SKIN-01.** Found 2026-09-20 during E11 stage 5
    on Rebal: `brawler_tritachyon` and `buffalo_pirates` both showed `variant-weapon-slot-mismatch`,
    but both are false positives - each skin's own `weaponSlotChanges` overrides the base hull's slot
    type to match the weapon actually mounted (verified directly: `brawler_tritachyon.skin` retypes
    WS 001/002 to ENERGY, matching `ionbeam`/`gravitonbeam`; `buffalo_pirates.skin` retypes WS 001 to
    BALLISTIC, matching `vulcan`). BF-SKIN-01 (item 17) fixed `hullId` resolution through a skin's
    `baseHullId` chain; this is a different field entirely - a skin's slot-type/size overrides, which
    `_scan_variant_validity` never applies before comparing a mounted weapon against the base hull's
    unmodified slot type. Exact location: `bridgeforge/scanner.py:4972-4977` per the investigating
    task's citation (re-verify the line number before fixing, code has moved since). Fix: build the
    slot-by-id table used for the fit check from the skin's overridden values when a `.skin` applies,
    not the base `.ship`'s raw `weaponSlots`, mirroring how `_resolve_hull_id` already chases the
    `baseHullId` chain for the hull id itself.
    **Done 2026-09-21.** New `_skin_weapon_slot_changes` indexes each `.skin`'s own
    `weaponSlotChanges` (verified against real files, e.g. `{"WS 001": {"type": "ENERGY"}}`,
    overlaying only the given fields); `_scan_variant_validity` now applies a variant's full
    skin-chain of overrides (closest-to-`hullId` last, so the most specific skin wins) onto
    `slot_by_id` before the fit check runs. Verified on real data both ways: Rebal's
    `brawler_tritachyon_Standard` false positive is now gone, and the fix also correctly *surfaced*
    a genuine mismatch it had been hiding (`falcon_p_Strike`: the skin retypes two slots to
    `MISSILE`, and the variant mounts a `BALLISTIC` weapon there) - confirmed not a rebuild artifact
    by checking the skin's own `weaponSlotChanges` directly. Tests:
    `tests/test_rc8_variant_and_asset_checks.py` (`test_skin_slot_override_resolves_a_false_positive`,
    `test_skin_slot_override_can_also_reveal_a_real_mismatch`).
29. **`scan --compile-check` cannot resolve a declared dependency at all - it never passed
    `provider_roots` to `compile_loose_scripts`.** Found 2026-09-21 during item 23's full corpus
    recheck: `scanner._scan_compile_check` called `compile_loose_scripts(root,
    vanilla_core=vanilla_core)` with no third argument, unlike the standalone `compile-check`
    command, which defaults `provider_roots` to `<repo>/In operation` and its rig's mods. A mod
    whose declared dependency (a base mod, a library) lives outside even that default - as
    `Maelstrom-Interstellar-Imperium-Unofficial-Expansion`'s base mod does, installed only in the
    real Starsector install's own `mods/` folder - got a false compile FAIL under `scan
    --compile-check` that the standalone command (given the right `--providers`) does not produce.
    Needs a `provider_roots` parameter threaded through `scan_mod` and a `scan --providers` CLI flag
    mirroring `compile-check --providers`.
    **Done 2026-09-21.** `scan_mod(..., provider_roots: list[Path] | None = None)` now passes it to
    `_scan_compile_check`, which passes it to `compile_loose_scripts` (previously called with no
    third argument at all). New `scan --providers` CLI flag (repeatable, same help text as
    `compile-check --providers`). Verified against the real case: `scan
    --compile-check --vanilla-core <RC8> --providers "<real install>/mods/Interstellar
    Imperium-2.6.9" --providers "In operation" --providers "In operation/_rig/mods"` on Maelstrom
    now produces zero `loose-script-compile-*` findings, matching the standalone command's own PASS.
    Tests: `tests/test_compile_check.py` (`ScanCompileCheckProviderRootsTests`).
30. **`scan_mod` should refuse a workspace root (`In operation/<Mod>/`, holding sibling `original/`
    and `working/`) instead of silently walking into the untouched `original/` copy alongside
    `working/` and misattributing its findings to the live mod.** Found 2026-09-21 doing item 23's
    own corpus recheck by hand: `BF-Legacy-Fleets` and `Leon-Heavy-Industries` were each
    accidentally scanned at their workspace root instead of `working/` (no `mod_info.json` there),
    which meant `scan_mod` still walked the whole tree including `original/`'s frozen copy and
    reported 7 real-looking findings (`target-interface-method-missing`,
    `configured-source-class-missing-from-jar`, `undeclared-library-dependency`,
    `missing-mod-info`) that were actually about `original/`, not the revived `working/` copy
    (which was in fact clean). Corrected in `In operation/CORPUS_RECHECK_2026-09-21.md` once found,
    but nothing stopped the mistake from being made or would catch the next one.
    **Done 2026-09-21.** `scan_mod` now raises `ValueError` when the scanned root has no
    `mod_info.json` of its own, but a sibling `original/` directory exists AND
    `working/mod_info.json` exists - the exact, specific shape of this repo's own workspace
    convention (`CLAUDE.md`), naming the correct path to scan instead. Deliberately narrow: a mod
    root that legitimately has no `original/` sibling, or a directory missing `mod_info.json` for
    an unrelated reason, is unaffected. Tests: `tests/test_scanner.py`
    (`WorkspaceRootGuardTests`, 4 cases: refuses correctly, scanning `working/` directly is
    unaffected, an ordinary mod root is unaffected, a bare directory with no `working/` at all is
    unaffected).
31. **`board`'s status parser resolves a clean status for almost no real report, because the
    strict single-final-line pattern `audit_revival` correctly demands for release gating is the
    wrong bar for `board`'s own best-effort "what does this report currently claim" read.** Found
    2026-09-21 doing item 23's corpus recheck by hand: only 9 of 40 real `REVIVAL_REPORT.md` files
    resolved a status this way, because most write it inline with a trailing em-dash explanation on
    the same line (`**READY_WITH_REVIEW_ITEMS** — 0 MANUAL findings...`), which never matches
    `COMPLETION_STATUS_PATTERN`'s "the whole line is just the status" requirement. The strict
    pattern is the right bar for `audit_revival`/`release` (a release-readiness gate should demand
    a clean, unambiguous final line) - it should not change. `board` needs its own, separate,
    genuinely best-effort fallback.
    **Done 2026-09-21.** New `project_board._best_effort_last_status`: finds every `**STATUS**`
    bold marker anywhere in the report (not requiring a standalone line) and takes the last one
    (most recent, matching how a person reads these reports top-to-bottom). Used only as a
    fallback when the strict `_completion_statuses` doesn't resolve a single final status; each
    row now also carries `declared_completion_status_confidence` (`"EXACT"` or `"BEST_EFFORT"`,
    `None` when nothing resolves at all), and `stage` gets a `_BEST_EFFORT` suffix so a consumer
    can tell the two apart rather than trusting a best-effort read as confidently as a clean one.
    Verified against the real corpus: resolution went from 9/40 to 32/40 mods (23 more resolved via
    the new fallback; 8 remain genuinely unresolved, no bold status marker present at all).
    Deliberately never used by `audit_revival`/`release` - the strict release gate is unchanged.
    Tests: `tests/test_project_layout.py` (`BoardTests`, 4 new cases plus a confidence assertion
    added to the existing malformed-evidence test).
32. **Generalize item 23's full corpus recheck into a reusable command, not a throwaway script.**
    Item 23 was done entirely by hand with an ad hoc Python driver written for that one session -
    exactly the kind of mechanical, well-specified, repeatable task that should be a real command
    the next agent (or the same one, next time) can just run, per the owner's own "make it
    easier/quicker for you" instruction (2026-09-21).
    **Done 2026-09-21.** New `bridgeforge/corpus_recheck.py` (`corpus_recheck`, `render_markdown`),
    wired as `bridgeforge corpus-recheck [--repo-root] [--vanilla-core] [--write-markdown] [--json]`.
    Mod discovery reuses `project_board`'s own tested layout logic (a mod qualifies when it has a
    `working/mod_info.json` AND a `REVIVAL_REPORT.md`) rather than re-deriving it by hand - verified
    this produces the exact same 40-mod list item 23 built manually. Uses the corrected item-23
    procedure (`scan_mod(..., compile_check=False)` for the finding set, the standalone
    `compile_loose_scripts` for the compile signal - see item 29) rather than the roadmap text's
    literal `scan --compile-check`. Flags a `REGRESSION` when a mod with a declared ready status
    (`READY`/`READY_FOR_LIVE_TEST`/`READY_WITH_REVIEW_ITEMS`, via item 31's now-much-more-complete
    status resolution) now carries any MANUAL finding - exit code 1, so it's script-usable as a
    live-test gate. `--write-markdown` emits the same roll-up table format item 23 wrote by hand.
    Tests: `tests/test_corpus_recheck.py` (report-presence filtering, finding/status reporting,
    regression detection with and without a declared-ready status, one mod's scan failure not
    crashing the rest, markdown rendering, CLI JSON/markdown/exit-code).
33. **`substitutes.required_from_scan` read only `content-reference-unresolved`'s/`source-import
    -unresolved`'s own evidence lines, which are capped for human readability (25 ids total, 20
    imports) - a mod with more distinct unresolved ids than that would silently feed an incomplete
    `needed` set into `cover()`/`strategy()`, understating what `dependency-substitutes` (and
    item 4's strip/vendor planner, built on the same function) actually recommends.** Found
    2026-09-21 while building item 4: not yet biting any real mod in the corpus (the largest real
    count found, Communist Clouds, is 6), but several real Ironclads-queue mods already have 25+
    instances of a *different* finding kind, so the same shape is plausible there.
    **Done 2026-09-21.** `_scan_unresolved_content_references` already stored the full,
    untruncated per-kind per-id file list in `migration_context["unresolved_content_references"]`
    for exactly this reason (a comment left there when item 4 was first scoped, 2026-09-20/21) -
    `required_from_scan` just never read it. `source-import-unresolved` gained the same:
    `migration_context["unresolved_foreign_class_imports"]` now carries the full list. Both are
    now `required_from_scan`'s preferred source, falling back to the capped evidence lines only for
    a `result` that doesn't carry `migration_context` (e.g. reconstructed from a saved report).
    Tests: `tests/test_substitutes.py` (`RequiredFromScanTruncationTests`, 30 hullmod ids and 25
    imports, both confirmed fully returned).
34. **Fixer coverage gap: 38 MANUAL findings exist in `scanner.py`, but `fixers.SUPPORTED_FINDINGS`
    only mechanically fixed 13 of them.** Found 2026-09-21 while auditing BridgeForge and
    RevenantLib together for further gaps (both already very clean individually - RevenantLib
    `compile-check` PASS/0 errors, `rebuild-jar` 0 drift, `scan_mod` only 4 low-severity findings;
    checking the tool's own coverage instead). Most of the 34 uncovered MANUAL ids genuinely need a
    human decision (a missing/invalid mod_info.json, an unresolved content reference with no known
    successor, `orbit-period-zero`'s literal argument, `fighter-wing-role-invalid`'s tactical
    role) and stay MANUAL by design. Two were real, narrow, deterministic gaps with a single
    correct rewrite already spelled out in their own scanner explanation text:
    **Done 2026-09-21.** Added `rules-firebest-populate-options` (VAC-DIALOG-01: `FireBest
    PopulateOptions` -> `FireAll PopulateOptions` in rules.csv, a literal keyword swap - vanilla's
    own rules.csv uses `FireAll PopulateOptions` 462 times and `FireBest` never) and
    `personality-id-unknown` (SK13-1d: `setPersonality("cowardly"/"suicidal"/"fearless")` -> RC8's
    own `timid`/`reckless`/`reckless`, using the scanner's own `LEGACY_PERSONALITY_IDS` mapping,
    loose scripts only - a match found only in a jar's bundled source is refused, same convention
    as `target-interface-method-missing`/`removed-api-call`). Tests:
    `tests/test_fixers.py` (`RulesFireBestPopulateOptionsFixerTests`,
    `PersonalityIdUnknownFixerTests` - apply-and-rescan-clean, refuse-when-absent, and for
    personality ids, refuse-when-only-jar-bundled, with a minimal hand-built class file carrying
    `setPersonality`/`suicidal` in its constant pool). Full suite: 1070 tests, OK (skipped=1).
    `docs-index` regenerated (`docs/CHECKS.md`, `docs/COMMANDS.md`).
35. **Getting the real corpus's stragglers across the finish line (aside from live testing) kept
    hitting the same friction: a mod that's genuinely clean (0 MANUAL, compile PASS) still needed
    a hand-authored `REVIVAL_REPORT.md`/`REVIVAL_PLAN.md` pair before `board`/`corpus-recheck`
    could resolve a declared completion status at all.** Found 2026-09-21 triaging the corpus by
    hand (Zorg18, Leon-Heavy-Industries: both clean, neither had a resolvable declared status).
    **Done 2026-09-21.** New command `revival-report-draft`: computes (dry-run) or writes
    (`--apply`) a `REVIVAL_REPORT.md`/`REVIVAL_PLAN.md` pair straight from real scan + compile-check
    evidence - refuses outright (never fabricates a PASS) if any MANUAL finding or a compile FAIL
    exists. SAVE COMPATIBILITY CHECK and LIVE STARSECTOR TEST are never mechanically checkable, so
    they're always recorded as not performed and the drafted status is always `READY_FOR_LIVE_TEST`,
    matching the existing convention for a mod in this exact shape across the real corpus.
    `--apply` refuses to overwrite an existing report/plan without `--force`, so it can never
    silently clobber hand-authored history. Tests: `tests/test_revival_report_draft.py`
    (blocked-without-vanilla-core, blocked-on-a-MANUAL-finding, a full OK draft, write-then-refuse-
    then-force, and a check that the drafted pair actually satisfies `revival_audit.audit_revival`'s
    own structural read - not just that it looks like a report).

    Applying it to the real corpus found a second real bug: **Leon-Heavy-Industries' `working/`
    copy itself held a stray `scratch/` folder** (three files: the stderr/stdout/empty-json debris
    of an earlier, correctly-refused `scan --output <path inside working/>` attempt - the shell
    creates a redirect target before the refused command even runs). This only ever surfaced as an
    opaque `unverified-json-syntax` UNKNOWN finding on the resulting 0-byte JSON file, never as
    what it actually was - and a release built straight from that `working/` copy would have
    shipped it. New scanner check `working-copy-tool-debris` (MANUAL) flags any mod root holding a
    top-level `scratch/` folder - safe and generic for any mod (this project's own workspace
    convention keeps `scratch/` as a sibling of `working/`/`original/`, and no real Starsector mod
    ships a folder literally named `scratch`). Tests: `tests/test_scanner.py`
    (`WorkingCopyToolDebrisTests`). Confirmed no other mod in the corpus currently has this shape.
    The debris itself was moved to Leon-Heavy-Industries' own `scratch/` (never deleted, logged in
    its `MOVES.log`), and its real, existing hand-authored `reports/REVIVAL_REPORT.md` (2026-09-20:
    LazyLib dependency, interface-drift and import fixes) gained the formal `READY_FOR_LIVE_TEST`
    status line it was missing - `revival-report-draft --apply`'s own output was superseded by this
    (moved to `scratch/`, logged) once the real report was found, rather than shipping a generic
    duplicate alongside real revival history. Zorg18's own `reports/REVIVAL_REPORT.md` was left
    alone rather than drafted over (see item 36: it needed a hand read, not a mechanical draft, and
    turned up a real bug of its own). Full suite: 1077 tests, OK (skipped=1). `docs-index`
    regenerated.
36. **Reading Zorg18's own `REVIVAL_REPORT.md` by hand (item 35 refused to draft over it) surfaced
    two things worth fixing: a stale bullet, and a real bug its own author had flagged and
    deferred.** The report's "Open items" list still said `engine_styles.json` trimming needed an
    owner decision, even though the same report's own text above it already said that trim was
    "Fixed" - just never updated after. More importantly, its very last bullet ("noted in passing,
    not part of O5 and not changed... flagged for a future pass") named a real, live, unfixed
    defect: `zorg.faction`'s `traits.captain` block weights `cowardly`/`suicidal`/`fearless`
    (0.6-era ids, `LEGACY_PERSONALITY_IDS`) for random officer generation, alongside RC8's real
    ones. **Done 2026-09-21.** Verified `"traits"` is not dead legacy content before treating it as
    a bug (`Never infer dead code`): no vanilla faction file populates the key, but RC8's own
    `Faction`/`SpecStore` classes reference the string `"traits"` in their constant pool (javap),
    so it is read. An officer drawn with one of these ids gets a null personality and crashes the
    game on deploy - the same class as `personality-id-unknown` (SK13-1d), just reached through
    faction-level generation instead of a hard-coded `setPersonality()` call. New scanner check
    `faction-trait-weight-legacy-personality-id` (MANUAL), generic for any mod's `.faction` `traits`
    block, not just Zorg's. Fixed Zorg's own file: `cowardly`→`timid` (weight unchanged); `suicidal`
    and `fearless` both map to `reckless`, so their weights were merged (`1 + 1 = 2`) rather than
    left as a silently-colliding duplicate JSON key - a fixer would have had to get that merge right
    too, so this one instance was fixed by hand rather than building a generic rewrite fixer for a
    single known case. Verified: the file still parses, rescan is unchanged (10 SAFE, 9 REVIEW, 0
    MANUAL). Zorg18's report gained a formal `READY_WITH_REVIEW_ITEMS` status (its one remaining
    open item, "Omega Escort greetings," is a genuine non-blocking owner question, not a defect).
    Tests: `tests/test_zorg_campaign_checks.py` (`FactionTraitWeightLegacyPersonalityIdTests`) -
    legacy ids flagged, valid ids quiet, and a mod-declared legacy id (via
    `data/characters/personalities.csv`) correctly not flagged. Full suite: 1080 tests, OK
    (skipped=1). `docs-index` regenerated.
37. **Item 36's "fix Zorg's one instance by hand, it's not worth a generic fixer" call turned out
    wrong within the hour: a corpus-wide check for the same shape found the identical bug, byte-
    for-byte identical `cowardly`/`suicidal`/`fearless`-weight-1 pattern, in 8 more mods (10
    `.faction` files total across Antediluvians x3, Batavia, Cobalt-Arms, Firestorm-Federation,
    Gekelonians, Independant-Mining-Faction, Qualljom, Renis-Imperium) - clearly a shared template
    lineage, not one mod's one-off mistake.** **Done 2026-09-21.** Built the fixer after all:
    `faction-trait-weight-legacy-personality-id`, a surgical text-level rename/merge (reuses
    `build_tag._structural_depths` to find each `traits.<role>` object's exact text span without a
    full JSON round-trip, so comments/formatting/key order survive) that renames `cowardly`->
    `timid` and merges `suicidal`+`fearless`'s weights into one `reckless` entry (refuses rather
    than guess if the merge target already has its own explicit entry - not seen in the real
    corpus, but safer than assuming which value should win). Verified against a real copy of
    Batavia's own file before trusting it on the corpus (minimal 4-line diff, rescan 0 MANUAL).
    Applied for real to all 8 affected mods (`fix --apply`, one dry-run review each first); each
    got a short note appended to its own `REVIVAL_REPORT.md` recording the fix. Tests:
    `tests/test_fixers.py` (`FactionTraitWeightLegacyPersonalityIdFixerTests`) - apply-rename-merge-
    and-rescan-clean, refuse-on-an-existing-merge-target-entry, refuse-when-nothing-to-fix. Full
    suite: 1083 tests, OK (skipped=1). `docs-index` regenerated.
38. **`external-mod-api-import` fired MANUAL for direct use of an external mod's API even when that
    mod is declared as a hard dependency in `mod_info.json`.** Found triaging Arkgneisis, the
    smallest remaining corpus straggler (1 MANUAL finding, otherwise clean): it directly uses
    MagicLib's `data.scripts.util.Magic*` API throughout, and `mod_info.json` declares MagicLib
    (the mod's own description literally says "Requires MagicLib"). A declared dependency is
    hard-required - Starsector itself refuses to enable the mod without it - so this isn't a
    "might not be there at runtime" compatibility risk at all; the check's own explanation text
    ("Compile and runtime compatibility require that optional mod...") only makes sense for an
    *undeclared* use. **Done 2026-09-21.** When `mod_info.json` already declares the dependency
    (`_mod_info_declares_dependency`, the same helper `revenantlib-fold-conflict` uses), the finding
    is now `external-mod-api-import-declared` (SAFE) instead of `external-mod-api-import` (MANUAL) -
    a new id, not a classification change on the same id, since three real consumers
    (`cross_mod.py`, `integration_scenarios.py`, `library_api.py`) read
    `migration_context["dependency_compatibility"]["direct_api_dependencies"]` and need to keep
    seeing *every* direct external-API use, declared or not, to reason about cross-mod integration -
    `_dependency_compatibility_context` was updated to harvest both ids so none of the three lost
    data. Applying it to the corpus found the fix generalizes correctly: Arkgneisis's MagicLib use
    is now SAFE (0 MANUAL remaining); Vayra-Merged and Void-Tec each also had a MagicLib
    `external-mod-api-import` reclassified to SAFE, while their real, separate MANUAL findings
    (Vayra's `Console Commands` use, genuinely unregistered in `commands.csv`; Void-Tec's
    `Industrial Evolution` use, genuinely undeclared) correctly stayed MANUAL - confirmed neither
    mod declares those two dependencies. Tests: `tests/test_batch_lessons.py`
    (`test_a_declared_dependency_is_safe_not_manual`); the existing `ConsoleCommandOptionalTests`/
    `MagicLibAttributionTests` fixtures declare no dependency, so none of them changed behavior.
    Full suite: 1084 tests, OK (skipped=1). `docs-index` regenerated.
39. **New fixer for `shiproles-wing-id`, applied to Scion-Collective and Firestorm-Federation (the
    same shape found in both the same day).** 0.98a's `shipRoles` only resolves variant ids; the
    pre-0.8a convention of a fighter-wing id there is fatal at load, not ignored. The correct
    replacement is that wing's own `variant` column in `data/hulls/wing_data.csv` - the same
    file/column the scanner's own check already reads to decide a key "looks like a wing id," so
    the fixer and the check agree on what counts as one. Implementation reuses (refactored, not
    duplicated) the same surgical rename/merge machinery item 37 built for
    `faction-trait-weight-legacy-personality-id` - both are "rename/merge keys in a `.faction`'s
    flat `id: <number>` sub-object," now shared as `_rewrite_id_weight_object(block_text, rename)`.
    Applied for real to both mods (`fix --apply`, dry-run reviewed first) plus their other
    fixer-supported MANUAL findings (`wing-data-missing-role-desc-column`,
    `undeclared-library-dependency`), taking Scion-Collective and Firestorm-Federation both to 0
    MANUAL. Tests: `tests/test_fixers.py` (`ShipRolesWingIdFixerTests`) - apply-and-rescan-clean, two
    roles sharing one wing id both rename, refuse-when-the-wing-has-no-variant-column-value,
    refuse-when-nothing-to-fix.

    Fixing Firestorm-Federation's own `target-interface-method-missing` (the existing
    `showInRefitScreenModPickerFor` fixer) surfaced a real compile blocker beyond that one method:
    RC8's `HullModEffect` interface gained `isSModEffectAPenalty()` and `getTooltipWidth()` too
    (javap-confirmed against `starfarer.api.jar`) since whatever version this mod's own
    `data/hullmods/BaseHullMod.java` was written against - each discovered one at a time as the
    compiler hit it, since it `implements HullModEffect` directly rather than extending RC8's real
    `BaseHullMod`. Added `isSModEffectAPenalty` as a new `TARGET_INTERFACE_CONTRACTS` entry and
    fixer default (`false`, matching vanilla's own `BaseHullMod`, javap-verified) for the general
    case. For Firestorm-Federation itself, root-caused instead: every other hullmod in the mod
    already extends its own `data.hullmods.BaseHullMod`, so changed that one file to extend RC8's
    `com.fs.starfarer.api.combat.BaseHullMod` instead of implementing the raw interface - it now
    inherits every current and future default automatically, matching the scanner's own existing
    suggestion text ("prefer extending the target BaseHullMod"). Also fixed on the same mod, found
    working down its finding list: `mod-info-jar-missing` (a stale `"jars"` entry - the mod has only
    ever shipped loose scripts, confirmed against the untouched `original/` archive too) and
    `invalid-csv` (`data/lights/Firestorm_light_data.csv`, 0 bytes, confirmed genuinely dead - its
    only reference is entirely commented out in source - moved to `scratch/`, logged). Tests:
    `tests/test_revival_lessons.py` (extended `HullModEffect` assertion). Full suite: 1088 tests, OK
    (skipped=1). `docs-index` regenerated.

40. **Corpus-wide check on `mod-info-jar-missing` prevalence before deciding on a fixer (the
    prevalence-check discipline item 37 established after getting the call wrong once).** Scanned
    every mod on the board; only two instances exist total - Firestorm-Federation (already fixed by
    hand in item 39) and Covert-Cargoliners (`"jars":["jars/example.jar"]`). Two instances doesn't
    justify a generic fixer, so Covert-Cargoliners was fixed by hand the same way: `jars/example.jar`
    is unedited mod_info.json template boilerplate (never present in `working/` or the untouched
    `original/` archive), and the mod ships zero `.java` files, so there was never a jar to build.
    Removed the `"jars"` key. This was also this mod's first full revival pass (no prior
    `REVIVAL_REPORT.md`): drafted one via `revival-report-draft --apply` off the post-fix scan (0
    MANUAL, 6 REVIEW, `compile-check` PASS on 0 loose scripts) and prefixed it with the fix note.
    `READY_FOR_LIVE_TEST`. Full suite: 1088 tests, OK (skipped=1), no code change so nothing to
    regenerate in `docs-index`.

41. **Thule-Legacy triage: 37 MANUAL -> 0, `compile-check` FAIL (65 errors) -> PASS (ROADMAP P14
    "review all" sweep).** LazyLib is a real hard dependency (`TLPlugin.onApplicationLoad` itself
    throws if it's missing) - declared. Nexerelin is a real, deliberately soft one (its only call is
    guarded by `isModEnabled`, short-circuiting before `SectorManager` ever resolves) - left
    undeclared, matching real corpus precedent (`docs/RECREATION_PLAN_FLUX_VACUUM.md`, "Nexerelin
    optional, never declared as required"); verified `TLPlugin.java` still compiles clean with a
    one-off `javac` that puts Nexerelin's real jar on the classpath without declaring it. The
    existing `target-interface-method-missing` fixer (with `--allow-shadowed-edit`, since all 18 of
    this mod's loose scripts are jar-shadowed) handled RC8's six new `ShipSystemStatsScript`
    `*Override` methods and `OnHitEffectPlugin.onHit`'s new parameter across 6 files. Hand-fixed:
    `FakeEntity implements CombatEntityAPI` directly and was missing 8 RC8 methods (only mod in the
    corpus doing this, not worth a generic fixer); `AddMarketplace.java`'s
    `setBaseSmugglingStabilityValue` (removed outright, was called with a no-op `0`) and
    `EconomyAPI.addMarket` (gained a `boolean` param, `true` per 6+ real corpus precedents).
    **New scanner check `removed-market-condition-id`**, a genuine corpus-wide gap: RC8's colony
    overhaul turned four 0.8-era `Conditions` ids into buildable `Industries`
    (`MILITARY_BASE`->`MILITARYBASE`, `ORBITAL_STATION`->`ORBITALSTATION`, `TRADE_CENTER`->
    `COMMERCE`, `HEADQUARTERS`->`HIGHCOMMAND`) - a different API (`addIndustry`, not `addCondition`).
    Real precedent for the exact mapping already existed (Exigency's `Avesta.java`); also live (not
    commented out) in 3 Tore-Up-Plenty files, noted for that mod's own future pass. No generic fixer
    (each mod's market-helper shape differs too much); hand-fixed Thule-Legacy by extending its own
    `AddMarketplace` helper with a second `industries` list, matching Exigency's real shape.
    **Jar rebuild done surgically, not via a whole-tree `rebuild-jar --install`:** the whole tree
    compiled clean, but its own comparison flagged 5 classes the source has that the shipped jar
    doesn't (2 apparently-orphaned, unwired dev hullmods; 1 currently-loose script that would become
    newly, harmlessly shadowed; 1 genuinely-wired mission that should ship but doesn't yet) - rather
    than resolve four separate judgment calls as a side effect, recompiled and byte-replaced only the
    9 already-shipped classes the RC8 fixes actually touched (`rebuild_jar._package_jar` used
    directly, same precedent as FlowerGod/Arkgneisis): 18 classes before and after, 0 added/removed,
    0 forbidden sandbox references, every method change matches an intended fix. Original jar backed
    up to the mod's own `scratch/jar-patch-2026-09-22-thule-rc8-compat/`, logged in `scratch/
    MOVES.log`.
    **New tooling fix:** `compile_loose_scripts` now separates `jar_shadowed_errors` (a jar-shadowed
    loose script's compile errors, which can never block the game) from the blocking `errors`/
    `status` - found because Thule-Legacy's unedited, correctly-jar-shadowed `TLPlugin.java` was
    reporting a `compile-check` FAIL it could never actually cause in game (Nexerelin intentionally
    undeclared). `compile-check`'s CLI prints the jar-shadowed count as an informational line.
    Verified: rescan 0 MANUAL (was 37), `compile-check` PASS (was FAIL, 65 errors; the 2 remaining
    are the correctly-informational `TLPlugin.java` ones). `READY_WITH_REVIEW_ITEMS`, `EXACT`.
    Tests: `tests/test_removed_market_condition_ids.py`. Full suite: 1091 tests, OK (skipped=1).
    `docs-index` regenerated.
    **Follow-up tooling idea (not built this pass):** `compile-check`/`rebuild-jar` can only put a
    dependency's jar on the classpath if it's *declared* - there's no way to verify a genuinely
    optional/soft-integration code path (guarded by `isModEnabled`) compiles without forcing that
    declaration, which would change real player-facing behavior. A `--optional-providers` flag (put
    on the classpath, never in `dependencies_missing`/status gating) would close this honestly if it
    keeps recurring.

42. **Design pass on the two parked mods (Xenoargh-Rebal, Maelstrom II Unofficial Expansion), plus
    two new checks for the vanilla-script-shadow pattern it found.** Both were carrying
    owner-approved multi-stage escalation threads; picked those up rather than restarting. Full
    briefs: `In operation/ESCALATIONS.md` E13 (new) and E8 addendum 3.
    - **Maelstrom: the "42 compile errors" were never real.** E8 course B's deliverables are all
      present and compile clean; every error resolved against base Interstellar Imperium, which the
      expansion correctly declares but which is installed only in the **real** Starsector install,
      not under any default provider root. `compile-check --providers "<real install>/mods"` gives
      **PASS, 0 errors**. Worth generalizing: a mod depending on a base mod we do not host reports a
      false FAIL under default providers.
    - **Rebal: `"replace"` in mod_info.json is a live RC8 mechanism**, not legacy metadata -
      `ModManager` holds it as a string literal beside `modPlugin`/`jars`/`dependencies` and feeds it
      to `ModSpec.getFullOverrides()`, **skipping any entry ending in `settings.json`** (bytecode-
      verified). Rebal declares 648 entries against 759 actual shadows: 128 undeclared, 17 stale. The
      merge-semantics files were checked rather than assumed and are **fine** - the preset JSONs are
      purely additive (BF-PRESET-01 does not apply), and `settings.json`'s 53 targeted keys over
      vanilla's 616 are *correct* as a merge, with the nested `plugins` object deep-merging key-by-key
      (verified empirically: MagicLib/GraphicsLib/LunaLib/Console Commands/AI Tweaks all ship only
      their own plugins there, and Nexerelin deliberately overrides exactly the two vanilla keys it
      replaces).
    - **A runtime spec-delta library was considered and ruled out:** `ShipHullSpecAPI` has getters
      but **no setters** for hitpoints/armor/flux/OP/bays, and the RC8 sandbox bans reflection, so
      base stats cannot be rewritten at runtime and spec-file replacement is unavoidable.
    - **New scanner check `vanilla-script-shadow-repointable` (REVIEW).** A mod replacing a vanilla
      *script* at vanilla's path usually need not: the class is resolved by a CSV row's `script`
      column (or a `.system` `statsScript` key) and those CSVs merge by row id, so renaming the class
      and repointing the mod's own row gives identical behaviour with no shadow - and survives the
      next vanilla update instead of silently reverting it. Prevalence before building: 9 mods shadow
      a vanilla `.java`, **49 instances across 3 are repointable** (Rebal 47, Mountain-and-Sea 1,
      Shielded-Holds-For-All 1). Fires on all 50 of Rebal's.
    - **New cross-mod check `vanilla_script_shadow_collisions`** (`cross-mod-analyze --vanilla-core`).
      Two mods shadowing the *same* vanilla script is a conflict, not duplication - load order picks a
      winner silently. **Rebal and Better-Deserving-Smods collide on 22 hullmod scripts**; 25 of 72
      shadowed vanilla scripts corpus-wide have more than one owner. Reports `resolution`:
      `REPOINT_TO_SHARED_LIBRARY` when every owner already ships a row (the RevenantLib fold-in case)
      or `NEEDS_ROW_BEFORE_REPOINTING` when one path-shadows only - which is the real Rebal/BDS state,
      since BDS ships no rows.
    - Caught a real bug in my own first cut of the cross-mod check: it keyed owners by
      `directory.name`, and **every working copy in this repo is named `working`**, so both mods
      collapsed into one owner and it reported zero collisions against a pair I had already proven
      collide. Now keyed by mod identity, with a regression test.
    - Tests: `tests/test_vanilla_script_shadow_repointable.py` (5),
      `tests/test_vanilla_script_shadow_collisions.py` (6).
    - **Known limitation, recorded deliberately (see E14 stage 3):** the collision check matches on a
      shared *file path*. Acting on `vanilla-script-shadow-repointable` removes the shared path but
      leaves both mods overriding the same CSV **row id**, which is last-loaded-wins too — so the
      check would then call the pair clean while they still conflict. Item 43 closes this.

43. **`replace`-array hygiene, identical-copy detection, and cross-mod row-id collisions (built).**
    The honest completion of item 42; full rationale in `In operation/ESCALATIONS.md` E14 and E15.
    Also executed **E14 stage 0** on the real corpus.
    - `replace-entry-ignored` (REVIEW) — a `replace` entry ending in `settings.json`. RC8's
      `ModManager` silently drops exactly those before building the full-override set
      (bytecode-verified), so the declaration never takes effect and the author is never told.
    - `replace-entry-stale` (REVIEW) — a `replace` entry naming a file the mod does not ship
      (**Rebal: 5**; an earlier by-hand estimate of 17 counted declared-vs-*shadowing* rather than
      declared-vs-*shipped*, which is the meaningful comparison). Same family as items 39/40's stale
      `jars` entry.
    - `settings-json-override-breadth` (REVIEW) — how many vanilla settings keys a mod's
      `settings.json` overrides (**Rebal: 29 of 616**, a deliberate tuning set). Since settings.json
      can only ever merge, each overridden key silently wins over the current game's value; a few
      hundred would mean a stale wholesale copy reverting the game's own tuning. Blast radius, not a
      verdict.
    - `vanilla-file-identical-copy` (REVIEW) — a file byte-identical to vanilla's at the same path.
      It overrides vanilla with vanilla and changes nothing; a *script* copy is the misleading case,
      since it looks like the mod customises that hullmod and does not. Corpus-wide: **613 across 13
      mods** (Valhalla-Starworks 232, Rebal 205). Collected inside the existing shadow walk, which
      already has both files' bytes, rather than a second pass — deliberately, after item 42's own
      O(n²) lesson. Scoped to `data/`; redundant `graphics/` copies are release bloat and belong to
      the packaging tooling that already walks everything.
    - **Cross-mod `merge_table_row_collisions`** — two mods shipping a row with the same id in
      `hull_mods.csv`/`ship_systems.csv`. Merge-by-row is last-loaded-wins, so this is item 42's
      defect one layer up, and it is exactly what a path collision *becomes* once both mods repoint
      off vanilla's path (E14 stage 1). Reports `same_script`, which is false for a real conflict and
      true once both point at one shared implementation — the resolved end state.
    - **Fixed a real defect in item 42's own `vanilla-script-shadow-repointable`:** it did not skip
      files byte-identical to vanilla, so it advised *repointing* 14 no-op copies when the correct
      advice is to drop them. Found by executing stage 0; pinned with a regression test.
    - **E14 stage 0 executed:** moved Rebal's 14 byte-identical hullmod copies to `scratch/` (logged;
      never deleted), having first verified vanilla provides every one of those classes at the same
      path and that Rebal's own `hull_mods.csv` row for each still resolves. Verified effect:
      `vanilla-script-shadow-repointable` 50 → 36, and the Rebal↔Better-Deserving-Smods path
      collisions **22 → 15**, exactly as E14 predicted. `vanilla-path-shadowing`'s own count is
      unchanged at 64/427 because it already skipped byte-identical files — the cleanup removed
      files that check never counted.

44. **Maelstrom Interstellar Imperium Unofficial Expansion closed out: E8 resolved,
    `READY_WITH_REVIEW_ITEMS`.** Its long-standing "compile FAIL, 42 errors" was a classpath
    artifact, not a defect — base Interstellar Imperium is installed only in the real game install,
    outside both default provider roots, so `--providers "<real install>/mods"` gives PASS with 0
    errors. E8 course B's deliverables were already built; this pass verified and reported them.
    - **Row-id drift check, the one genuinely open risk: clean.** E8 addendum 2 enumerated the
      expansion's rules.csv overrides against base II **2.5.2**, but 2.6.9 is installed. rules.csv
      merges by row id, so a drifted id fails silently and leaves the base row in play. All **8** ids
      exist verbatim in 2.6.9; every base row referencing `II_TitanStrike` is covered. Delegated the
      lookup to an `Explore` subagent and re-verified the result independently before recording it.
    - **New caveat found:** base 2.6.9 still uses `II_TitanStrikeAvailable` in further rows the
      expansion does not override, so both condition classes coexist and must stay consistent.
    - **A real latent launch blocker, fixed.** The three new `IIUE_` scripts honour E8 deliverable 4
      (Janino-only syntax), but pre-existing `imperiumVectorThruster.java` used a typed for-each over
      `List<ShipEngineAPI>` — which Janino 2.7.8 cannot compile, a Fatal before the main menu.
      Confirmed genuinely exposed rather than assumed: `II.jar` does **not** supply that class (unlike
      the two Titan scripts, which it does), and it is live via `everyFrameEffect`. Rewritten as a raw
      `Iterator` with an explicit cast. This is exactly the case `loose-script-janino-risk` exists for,
      and the first time in this corpus it caught a live, unshadowed one.
    - Scope fork recorded as **B1**, inferred from what is absent (no `IIUE_TitanPlugin`, no `iiue_`
      projectile spec — both required by B2). `ii_titan_w2`/`deco2`/`deco3` remain specced but mounted
      by no hull or variant, left as the author's unfinished intent rather than wired silently.

45. **Better-Deserving-Smods first revival pass, and a 0.95.1a reference rig registered.** BDS had no
    report and had never been triaged; it is the other half of E14's collision with Xenoargh-Rebal.
    Findings **12 → 4**; `compile-check` PASS (0 errors, 50 loose scripts — 2023 code compiles clean
    on RC8, no API drift at all).
    - **Fixed 7 Janino launch blockers (10 instances).** BDS ships no jar, and **no core jar supplies
      any `data/hullmods` class** (checked across every jar in `starsector-core`), so all 50 loose
      scripts are Janino-compiled at startup. 10 typed for-eaches over generic collections rewritten
      as raw `Iterator` with explicit casts. Every one was over a real collection, never an array —
      an array for-each is fine under Janino and has no `.iterator()`, so rewriting one would have
      broken it. Second mod in two days where `loose-script-janino-risk` caught a live, unshadowed
      blocker (Maelstrom was the first).
    - Fixed `gameVersion` 0.95.1a-RC6 → 0.98a-RC8; without it the launcher unchecks the mod entirely.
    - **Owner installed 0.95.1a mid-pass; registered it as a reference rig** (`rig-create`), joining
      0.62a/0.7.2a/0.8.1a/0.9a. **This is the highest-value reference in the set by a wide margin:
      255 of the corpus's mods declare a 0.95.x base version** (176 × 0.95.1a, 76 × 0.95a), against
      40 already on 0.98a.
    - **The real defect, now measured exactly rather than inferred: BDS silently reverts 260 lines of
      vanilla's own post-0.95.1a hullmod changes**, across 28 overrides, while deliberately removing
      only 10. It is overwhelmingly *additive* — imports, a guarded S-mod block, and a new
      `addPostDescriptionSection` method per hullmod — which is why its intent is recoverable at all.
      A first pass using the 0.9a rig as a proxy reported 255/1; that was **not** a looser bound as
      claimed but an under-count, because it silently skipped files with no 0.9a counterpart. The
      same-era measurement supersedes it — a concrete argument for era-matched references over
      near-miss proxies.
    - Declared `ESCALATION_REQUIRED` (E14): the rebuild onto RC8-current source and the repointing
      are both real work, and the Rebal collision needs owner decisions.

46. **`corpus-recheck` now honours a mod's own accepted-findings baseline, plus four owner decisions
    recorded.** The baseline mechanism already existed on both ends — `scan --write-baseline` writes
    the file and `scan --baseline` reads it — but **`corpus-recheck` was the one consumer that
    ignored it**, so baselining a mod had no effect on the signal it was meant to quiet: the mod kept
    reporting as a `REGRESSION` on every sweep, forever. `_recheck_one` now picks up
    `working/reports/baseline*.json` and filters through `split_by_baseline`, reporting
    `baselined_findings` and the `baseline` path so the suppression is visible rather than silent. A
    corrupt or unreadable baseline is ignored and the findings still count — a broken file must never
    hide a real regression. Found executing the owner's "baseline Xenoargh-FX-Example" instruction:
    writing the baseline appeared to work (`scan --baseline` reported 0 new findings) while the
    recheck would have gone on flagging it. Verified on the real mod: 19 findings baselined, MANUAL
    3 → 0. Tests: `tests/test_corpus_recheck.py` (+2, including the corrupt-baseline guard).
    - **Owner decisions recorded 2026-09-22** in `In operation/ESCALATIONS.md` and the mods' reports:
      **E14 course A** — Rebal and Better-Deserving-Smods are listed as **incompatible** rather than
      reconciled, so the 8 contested hullmods and ~16 contested numbers are moot; **E12** — Rebal's
      `SafetyOverrides` and `StabilizedShieldEmitter` divergences **preserve the author's behaviour**
      and are not to be "corrected" later; **BDS's two orphaned `*Old.java` files** verified
      unreachable across every reference domain and moved to `scratch/`; **live testing** deferred
      until the corpus is RC8-compatible and relatively done.
    - **New E16** answers the owner's question about Maelstrom's unmounted Titan content with a
      concrete verdict: wiring `ii_titan_w2` would be a **regression, not a completion**. It declares
      the same `ii_titan_missile` spec base II's handler keys on, and base II zeroes the firing tube
      on the first shot — so the 3-ammo weapon fires **once**, where the ship's three separate 1-ammo
      tubes fire **three** times. It would also return 320 OP (3 × 160 collapsing to 1 × 160). Making
      it work needs scope B2's fork of base II's launch pipeline, already declined. Abandoned intent,
      not unfinished wiring.

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
