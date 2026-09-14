# Missing, discontinued and abandoned dependencies

`bridgeforge dependency-substitutes <mod>` answers "can this dependency be replaced?" and recommends one
of four courses. This page is the reasoning behind them; the owner makes the call for everything except
SWAP.

## What the tool measures

- **Needed:** the ids and classes the mod uses that neither it nor vanilla defines. These come from
  the scanner's `content-reference-unresolved` and `source-import-unresolved` findings, plus declared
  dependencies that no visible mod provides.
- **Candidates:** each visible mod is ranked by how much of that set it defines.
  - EXACT: all of it, targeting 0.98a.
  - PARTIAL: some of it. Starsector has no id aliasing, so the rest means editing the mod's data.
- **Footprint:** how many ids and classes lean on the dependency, and in how many files.
- **Dependency workspace:** if the dependency is itself in `In operation`, its revival status and MANUAL
  count.
- **Known successors:** `bridgeforge/dependency_successors.json` covers renames, splits and dead ends,
  each entry with evidence.

## The four courses

The tool picks the smallest set of visible mods that together provide the needed ids (a greedy cover;
ties go to mods targeting 0.98a, then to declared dependencies). Each provider in the set is:

- **current:** it targets 0.98a;
- **revivable:** an outdated workspace here, with 15 MANUAL findings or fewer;
- **heavy:** outdated, and either not a workspace, not scanned, or over 15 MANUAL. Ids that only a heavy
  provider has count as unprovided.

| Course | When | What it means |
|---|---|---|
| **SWAP** | Current providers cover everything | Declare them. Nothing else changes. |
| **REVIVE_DEPENDENCY** | Everything is covered, and at least one provider is revivable | Revive those first as their own mods, then the dependent mod as-is. Keeps both authors' work intact. |
| **STRIP_FROM_MOD** | Whatever is unprovided is 3 ids or fewer, in 5 places or fewer | Declare or revive the providers for the rest; remove or substitute the leftovers in the dependent mod. It is a behaviour change, so it is recorded as an expected change and needs owner approval. |
| **ESCALATE** | Anything else | Owner decision: revive the dependency, rebuild the mod without it, or shelve it. |

## Recommendation for abandoned "library" families (the Xenoargh FX series, Vayra's Sector)

Prefer **reviving the dependency** when:

- it is small, self-contained and a workspace here (FX Core: 12 files; its blockers are forbidden
  sandbox APIs and a bundled lombok.jar);
- its licence allows redistribution of a revived build (check `release_policy.json`; local-only
  otherwise);
- several queued mods depend on it. FX Core serves FX Example and Rebal; EZ Damage serves Explorer
  Society and Rebal. One revival unblocks several mods.

Prefer **rebuilding the mod without it** (STRIP_FROM_MOD) when:

- the mod uses a sliver of the dependency (one hull mod, one decorative weapon), or the use is
  cosmetic;
- the dependency is huge or unavailable (Vayra's Sector is a large campaign mod; Communist Clouds
  uses its `vayra_red_army` hull mod on 9 hulls and skins plus a handful of wings and weapons).

**Escalate** when the dependent mod *is* the integration: FX Example exists to showcase FX Core, and
Communist Clouds is a Vayra's Sector faction add-on. Stripping them leaves little of the author's
intent, so revive the dependency or shelve the pair.

Whatever the course, record it in the mod's REVIVAL_PLAN, and keep the untouched original.

## The 2026-09-14 queue

| Mod | Course | Why |
|---|---|---|
| FX Example | REVIVE_DEPENDENCY | FX Core (0.91a, 10 MANUAL) provides all three classes. |
| Rebal | REVIVE_DEPENDENCY | Declare EZ Damage and Vacuum (both 0.98a here). Revive AI Overhaul (12 MANUAL) and FX Core. |
| Explorer Society | ESCALATE | EZ Damage and Vacuum cover two needs. `shields_formshield` (14 places) exists only in Rebal (84 MANUAL). Options: wait for Rebal, vendor that hull mod if the licence allows, or strip it. |
| Communist Clouds | ESCALATE | 6 `vayra_*` ids in 16 places, and no provider anywhere. Vayra's Sector was last released for 0.9.1a. |
