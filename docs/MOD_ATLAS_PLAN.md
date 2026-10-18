# Mod Atlas: index everything a mod adds, changes and hooks, then forecast conflicts

Original design (owner request 2026-10-11), ROADMAP item 67. Phases 1-3 and subsequent evidence/refinement tools have
implementations in `bridgeforge/atlas*.py` and tests. The dated roadmap records local indexing/forecast uses; the complete
design below is not all implemented or live-qualified. Use `atlas --help`, root ROADMAP 67 and `ROADMAP_STATUS.md` for
current scope. A forecast remains PREDICTED until its particular runtime behavior is observed. Clarified 2026-10-18.

## Why

Every incompatibility found so far was visible in the files before anyone launched the game, but no single tool
connected the pieces:

- **DNEEP + AoTD (2026-10-11):** DNEEP looks up `getIndustry("farming")`, and AoTD replaces Farming with
  `aotd_subsidised_farming` and three others. Two facts in two mods; nothing joined them.
- **Station Augments save NPE:** a `market` field in a script saved into the campaign, forming a memory cycle.
- **SEEKER Bone-Breaker:** a hull mod's death effect re-fired on wrecks (RC8-27).
- **GRP-3 / GRP-7:** content the copy allowlist dropped.
- **Tritachyon / TASC:** a library renaming an industry id.

The scanner judges one mod against RC8. The Atlas judges mods **against each other**: what each one defines, overrides,
reads, removes and hooks, in one index that every mod shares.

## What gets indexed (per mod, per version)

Each record is one *fact*: `{mod, version, kind, id, action, source file:line, evidence, confidence}`.

| Layer | Kinds | Actions | Source |
|---|---|---|---|
| Content ids | hull, variant, weapon, wing, hullmod, ship system, commodity, industry, condition, special item, faction, submarket, planet type, terrain, ability, skill, tech (AoTD), mission | defines / overrides (same id as vanilla or another mod) / removes | CSV, JSON, `.ship` `.wpn` `.variant` |
| Data merges | `settings.json` keys, `rules.csv` rows (trigger + conditions), `.faction` lists, `default_ship_roles.json`, `tips`, `descriptions.csv`, sounds, graphics paths | adds / replaces / appends | JSON/CSV (merge semantics per file: lists add, keys replace; RC8 merge rules already in scanner) |
| Code references | ids used in Java strings: `getIndustry("x")`, `hasCondition`, `getCommodityData`, `getFaction`, `getHullSpec`, memory keys `$x`, tags | **reads** id | loose `.java` + jar constant pools (`javap -c`, already used by `revenantlib-check`) |
| Code mutations | `addIndustry`/`removeIndustry`, `addCondition`/`removeCondition`, `getConditions().clear()`, `setFaction`, `market.getIndustries()` reorder, spec edits (`getHullSpec(..).set*`), `Global.getSettings().getCommoditySpec(..).set*` | **mutates** id or collection | same, via call-site pattern + javap |
| Hooks | `BaseModPlugin` lifecycle, `EveryFrameScript`s (transient or saved), listeners (`ColonyInteractionListener`, `EconomyTickListener`, `ShowLootListener`…), `GenericPluginManager` plugins, `CampaignPlugin` pick methods (they compete by priority), `BaseCampaignEventListener` | registers | call-site scan |
| Class replacement | the same FQCN in two jars, or a loose script shadowed by a jar (memory: jar beats loose) | shadows | jar listings (`_loaded_mod_jars`) |
| Saved state | classes added to the save (scripts, intel, `customData` values) and what they hold (a `MarketAPI` field = the Station Augments cycle) | persists | field types via javap |
| Runtime facts | probe output: commodity supply/demand by industry (0.2.25), factions, fleets, markets | observed | probe logs, recorded per test id |

Confidence: data files are `SAFE` facts. A string literal in code is `REVIEW` (it might be dead code). An id built at
runtime (`"aotd_" + x`) is `UNKNOWN` and listed, never guessed.

## The master index

- **Store:** one SQLite file, `reports/atlas.sqlite` (gitignored; rebuilt from sources). It has a `facts` table plus
  `mods`, `versions` and `runs` tables. SQLite because the Ironclads backlog alone is about 350 mods, and the reports
  need joins (who reads an id that someone else removes).
- **Inputs:** it reuses `corpus-index` for archives (`.zip`/`.7z`) so mods are indexed without extracting them, and
  the workspaces under `In operation/`, `Done/`, the rig, and the reference installs (vanilla RC8 is mod `vanilla`).
- **Long-running rule:** `atlas build` reports one progress line per mod, writes a checkpoint, accepts `--quiet`, and is
  listed in `LONG_RUNNING_COMMANDS`. It is incremental: a mod is re-read only when its file hash changes.
- **Export:** `atlas show MOD` gives a per-mod page (everything it adds, changes, reads and hooks), and
  `atlas id ID` gives a per-id page (every mod that touches the id, and how). There is a JSON form, and an optional
  HTML artifact for browsing.

## Conflict rules (each one a finding with an id and a test, like scanner checks)

| Rule | Meaning | Default level |
|---|---|---|
| `ATLAS-DUP-DEFINE` | two mods define the same id (last loaded wins) | REVIEW; MANUAL for hulls/weapons with different stats |
| `ATLAS-READS-REPLACED` | mod A reads id X; mod B removes or replaces X (DNEEP `farming` vs AoTD) | REVIEW, with the replacing ids listed |
| `ATLAS-READS-MISSING` | A reads an id that no enabled mod and not vanilla defines | REVIEW (often an optional soft dependency) |
| `ATLAS-MUTATE-SHARED` | two mods mutate the same collection (market conditions order, industry list, spec values) | REVIEW; AoTD's condition reorder plus any condition-order mod |
| `ATLAS-PICK-PRIORITY` | two `CampaignPlugin`s claim the same pick at the same priority | REVIEW |
| `ATLAS-SHADOW-CLASS` | same FQCN in two mods | MANUAL |
| `ATLAS-RULES-CLASH` | two `rules.csv` rows with the same trigger and overlapping conditions, different options | REVIEW |
| `ATLAS-SETTINGS-OVERRIDE` | two mods set the same `settings.json` scalar to different values | REVIEW |
| `ATLAS-SAVE-HOLDS-HEAVY` | a saved class holds a `MarketAPI`/`SectorEntityToken`/`CampaignFleetAPI` field | REVIEW (save-cycle risk) |
| `ATLAS-RUNTIME-SUPPLY` | probe saw demand with no supply for a mod commodity | FAIL evidence attached to the static finding |

Every finding names both sides, the files and lines, and the evidence. Nothing is auto-fixed from the Atlas. A
proposed patch follows the usual route (fixer or workspace edit, then a live run).

## Forecasting

- `atlas forecast MOD [MOD ...]`: given a load set (or a modpack's `enabled_mods.json`), run every rule over just
  those mods plus vanilla and rank the results: crash-class (shadowed class, missing id read at startup) first, then
  silent-behaviour (READS-REPLACED, MUTATE-SHARED), then cosmetic.
- `atlas forecast --against aotd`: the broad AoTD case. Build an **AoTD profile** once: every id AoTD replaces or
  upgrades (its `industries.csv` upgrade chains, tech-tree unlocks, the Toolbox corrector conditions, the `settings.json`
  keys it changes). Then list every indexed mod that reads one of them. Output: per mod, compatible / needs a patch
  like DNEEP's / unknown, plus the exact lines. Run against `Done/` and the Ironclads backlog together.
- **Prove the forecast:** each high-ranked pair gets a probe-group run with `swap-industry` and `--expect-supply`
  (built 2026-10-11) or a smoke boot, and the result is written back as a `runtime` fact. Forecast precision is
  tracked (forecasts confirmed vs wrong), the same way the scanner's misrankings were measured (memory: bytecode
  linkage method).

## Phases

1. **Content and data layers (no code reading):** schema, `atlas build/show/id`, DUP-DEFINE, SETTINGS-OVERRIDE,
   RULES-CLASH. Test on `Done/` (about 60 mods). Done when every scanner-known duplicate id appears.
2. **Code references and mutations:** literal-id extraction from loose Java (comment-blanked, as the scanner does) and
   jars (javap constant pools), then READS-REPLACED, READS-MISSING, MUTATE-SHARED. Done when it reproduces DNEEP×AoTD
   and Tritachyon×TASC from files alone.
3. **Hooks, class shadowing, saved state:** PICK-PRIORITY, SHADOW-CLASS, SAVE-HOLDS-HEAVY. Done when it flags the
   Station Augments `market` field.
4. **Per-mod replacement profiles and forecasts:** every mod's profile, pairwise `atlas forecast`, then
   `--against aotd` (all AoTD modules as one set) over `Done/` plus the backlog; live-verify the top 5.
5. **Runtime feedback:** `probe-group record` writes runtime facts; the probe's market-supply output joins the index.
6. **Modpack mode:** forecast a whole pack (friend's 6.3 list) before anyone loads a save.

Phases 1-3 can be built and tested in a cloud session. Phases 4-6 need local archives and the rig (they go in
`LOCAL_HANDOFF.md` when reached).

## Risks and limits

- **Ids built at runtime** (string concatenation, reading from CSV at load) are invisible to static reading; they are
  listed as `UNKNOWN`, and the runtime layer is the backstop.
- **Obfuscated or Kotlin jars:** constant pools still show string literals, but call-site attribution is weaker
  (`REVIEW`).
- **Size:** about 400 mods × tens of thousands of facts fits SQLite easily. javap over every jar is the slow step, so it
  is cached by jar hash.
- **Ordering:** a conflict often depends on load order (alphabetical by folder in RC8). The index records order where
  it matters (DUP-DEFINE: who wins).

## Owner decisions (2026-10-11)

1. **Scope:** go with the recommendation. Phases 1-3 index `Done/`, the rig and the reference installs. The Ironclads
   backlog joins in Phase 4, when corpus-index reading is needed anyway and the rules have been tuned on known mods.
2. **Browsing:** a local file (`reports/atlas/*.html` plus JSON), not an artifact page.
3. **Profiles are per mod, not AoTD-only.** Every scanned mod gets its own *replacement profile*: the ids it removes,
   replaces, upgrades or renames, and the shared collections it mutates. `atlas forecast` checks every pair of mods
   against each other's profiles. On top of that, `atlas forecast --against aotd` checks a mod against the whole
   AoTD family together: every installed module (Vaults of Knowledge, Theory of Toolbox and its fork, and any other
   `aotd_*` mod found in the rig, `Done/` or the backlog), profiled as one set.
