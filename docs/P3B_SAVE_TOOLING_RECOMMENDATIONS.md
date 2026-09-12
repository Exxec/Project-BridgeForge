# P3b save tooling: further recommendations (2026-09-11)

This expands roadmap P3b ("test-oriented save tooling") for the owner to review and extend. Already decided: **B `save-compat`** (done), **A `save-inspect`**, **D `save-snapshot`** and **C probe setups**. No general save editor, and no direct XML editing. The principle: *the game creates state, BridgeForge reads it.*

Saves hold **runtime truth**: which of a mod's objects, scripts and ids actually exist once the game has run. The static scan can only guess at that. So save tooling helps two ways: it **checks test results** and it **dissects mods dynamically**.

## Recommended additions, in priority order

| # | Name | What it does | Why it matters (evidence from this project) | Effort |
|---|---|---|---|---|
| E | **save-content-compat** | Extends `save-compat` from classes to **data ids**: hull, variant, weapon, wing, hullmod, faction, commodity, industry, market-condition and special-item ids that the save stores as plain strings (e.g. `<st>ART_organicHull</st>`). It checks each against the build's data plus vanilla. | `save-compat` returned `UNKNOWN` on the SEEKER save precisely because SEEKER's footprint there is string ids, not classes. A renamed or removed hull or weapon id breaks old saves just as a missing class does. | S–M |
| F | **Script and listener duplication audit** | From a save, counts each mod-owned `EveryFrameScript`, listener and transient script per entity and sector-wide. It flags duplicates, i.e. the same script registered N times. | A classic revival bug is `onGameLoad` re-adding scripts on every load, which grows cost and doubles effects. Void-Tec's VT-7 ("no duplicate scripts accumulating") exists for exactly this and is currently manual. | S |
| G | **Save growth / bloat trend** | Object and element counts per mod namespace across a chain of saves (day 1 → day 30 → day 90), plus save size, with a growth-rate warning. | Catches leaks (ever-growing lists, intel that's never cleaned up) that only show up in long campaigns, like Arkgneisis's colonial system storing event maps in sector memory. | S |
| H | **Save provenance** | Reads `descriptor.xml` for the save's mod list and versions, including our `[BF rN]` build tags. It warns when a save being checked or tested was made with an older build than the current one. | Stops tests running on stale state. It's the save-side twin of `copy-drift` (we hit a stale rig copy of SEEKER once). | S |
| I | **Mod-removal safety check** | The inverse of E plus B: lists everything in a save that depends on a mod (classes, ids, factions, markets, memory keys), and answers "can this mod be removed mid-campaign?" | Players ask this constantly, and it's the other half of save compatibility. It also shows what a mod really leaves in a campaign. | S (reuses B and E) |
| J | **Runtime footprint section in the dossier** | The dossier gains an optional `--save` input and a "runtime footprint" section: the mod's live objects, scripts, factions, markets and memory keys from a real rig save. | Merges static and dynamic evidence in one packet. That would have shown directly that Exigency's `exipirated` faction never registered (EX-NPE-001), where a static read took a session. | S (after A/E) |
| K | **Scenario fixtures (C + D together)** | Named, versioned scenarios (`avesta-near`, `betelgeuse-damaged`, `nex-corvus-day1`), each with probe setup steps, a `save-snapshot` tag and the expected probe or `save-inspect` assertions. A regression suite replayable per build. | Turns one-off live tests into repeatable ones. The SK-6c damaged-module setup took real effort to build by hand. | M |
| L | **Redacted save summary for bug reports** | Writes a small JSON summary: mod list and versions, the failing references, runtime footprint, no player data. It's shareable without the 10 MB save. | The other player's ring crash could only be diagnosed from screenshots; a summary would have pinned it. | S |
| M | **Save corpus regression** | Keeps saves we or players supply (with permission), and runs B/E/H/I against every new build before release (a P8 release gate). | Protects existing players' campaigns across our updates. | S (after E/H) |

## Suggested sequencing

B (done) → **E** → A → **F** → H → D → C → K → G → I → J → L → M.

E and F are the highest-value additions. E closes the `UNKNOWN` gap `save-compat` already hit on SEEKER, and F turns the manual VT-7 test into an automatic one.

## Guardrails (unchanged)

- **Read-only on saves.** Snapshots are file copies inside the rig, never edits.
- **All state changes happen in-game** through the rig-gated probe (C, K).
- **Streaming parsers only.** Saves are ~10 MB and grow with long campaigns.
- **Nothing leaves the machine** unless the owner shares it. The redacted summary (L) is explicit, and opt-in.

## Open questions for the owner

1. Should player-submitted saves (M) be part of the release gate, and how should they be stored or anonymised?
2. Which scenario fixtures (K) matter most first? Suggestion: `avesta-near` (Exigency), `betelgeuse-damaged` (SEEKER), and `nex-corvus-day1` (the Nexerelin B5 matrix).
3. Is a "can I remove this mod?" answer (I) something to expose to players, or internal only?
