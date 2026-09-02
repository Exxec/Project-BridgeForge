# Safe campaign discovery and optional external raids

This is a migration pattern for Starsector campaign content that should work in a new game and in an existing save. It is deliberately a pattern, not a copy of another mod's character, dialogue, rewards, or assets.

## Goals

- Give a revived faction a discoverable story hook without assuming a particular named system exists.
- Add at most one copy of every persistent entity or recurring script.
- Make an Askonia visit/raid optional, bounded, and harmless when Askonia is absent.
- Keep the content understandable when a player enables the mod mid-save.

## Discovery signal at an uninhabited world

Run an idempotent `trySpawnZorgSignal(SectorAPI sector)` from the mod plugin's campaign lifecycle hook. Its selection should be deterministic: gather planets from all star systems, retain only non-star planets that have no market or an uninhabited market, sort by a stable key such as `planet.getId()`, then choose one with a seeded `Random` based on the sector seed plus a fixed Zorg salt.

Before creating anything, use both guards:

1. A unique custom-entity ID, such as `zorg_signal_<planet-id>`, or a tag such as `zorg_discovery_signal`, to find an already-existing entity.
2. A sector-memory state machine: `$zorg_discovery_state = unstarted | spawned | completed | abandoned`.

Spawn a custom entity in the chosen planet's orbit, attach a Zorg-owned interaction plugin, and add a small ping/intel entry only after the player has detected it. The interaction can offer original choices such as salvage a dormant relay, trace a transmission, or leave it alone. Completion should set the memory state and remove/retire the signal so the lifecycle hook cannot recreate it.

Do not choose a new random planet every load. Do not use a display name as a persistent identity. Save the selected planet ID in sector memory once the signal is created.

## Optional Askonia branch

Askonia can give the faction a familiar presence, but it must never be required for the core discovery path:

```java
StarSystemAPI askonia = sector.getStarSystem("askonia");
if (askonia == null || sector.getMemoryWithoutUpdate().getBoolean("$zorg_askonia_event_done")) {
    return;
}
```

Use the lower-case system ID, not `"Askonia"` as a display-name assumption. Only schedule the branch after the discovery is completed, then choose a low probability (for example 20 percent) once per campaign month. Mark `$zorg_askonia_event_done` before spawning the fleet; this prevents duplicates on reload or on a second lifecycle callback.

Prefer a small reconnaissance/interdiction fleet that enters and leaves Askonia, with a hard cap of one active Zorg raid. Give it a clear return/despawn action and do not make it destroy markets or force a relationship change. It can send an intel update or leave a trace that points back to the discovery signal. This feels connected without turning a missing or altered Askonia into a crash or a mandatory quest gate.

## Sierra-like feel without copying Sierra

The useful structural ingredients are a persistent state machine, a discoverable world object, short context-sensitive dialogue, and a follow-up triggered by player behavior. Secrets of the Frontier uses these ideas while keeping its characters and encounters specific to that mod. For Zorg, create an original voice and premise—e.g. an intermittent collective signal, a captured submind, or an abandoned assimilation relay—rather than reusing Sierra, her dialogue, or her assets.

Keep the first version small:

1. Find a signal at one uninhabited planet.
2. Resolve one original interaction with a non-essential reward.
3. Optionally trigger one Askonia recon/raid aftermath.
4. Retire the event cleanly and expose its state in a small Intel entry.

Add a companion, persistent officer, or multi-stage quest only after those four pieces survive new games, existing saves, reloads, and a sector where Askonia is absent.

## BridgeForge review coverage

BridgeForge reports these as review findings:

- `hard-coded-campaign-system-reference` for `getStarSystem("...")` calls. Verify the stable ID, null guard, and optional-path behavior.
- `hard-coded-campaign-entity-reference` for `getEntityById("...")` calls. Verify creation order, save migration, and null handling.
- `mission-local-fleet-reference-missing` when a mission names a ship variant or fighter wing with this mod's prefix that is not packaged locally.
- `campaign-spawn-registration-disabled` when campaign fleet-spawn calls survive only in source comments.

These findings intentionally require review: a literal ID is often valid, but it is a dependency that static scanning cannot prove is present in every campaign configuration.

## Manual test matrix

| Scenario | Expected result |
| --- | --- |
| New game | Exactly one signal is placed; no Askonia raid until the prerequisite is met. |
| Existing save, first enable | Exactly one signal is added without duplicating campaign scripts. |
| Save/reload before completion | The same signal and selected planet remain. |
| Askonia absent or renamed | Discovery still works; optional branch quietly does nothing. |
| Askonia present | At most one bounded raid/recon event is active and it despawns afterward. |
| Signal completed | It cannot respawn; its memory state and Intel result remain coherent. |
