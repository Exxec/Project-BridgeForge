# AoTD / Theory of Toolbox compatibility: plan (ROADMAP item 63)

Written 2026-10-10 at the owner's request ("plan compatibility changes and improvements for the AoTD toolbox
etc."). **Plan only, nothing built.** Every fact below was read from the local install on 2026-10-10; claims that
are not yet proven are marked *unproven*.

## What is installed (read from `Starsector/mods/`)

| Mod | id | Version | Needs |
|---|---|---|---|
| AoTD - Dreams of Past | `Cryo_but_better` | 3.0.5 (`gameVersion` 0.98) | LazyLib |
| AoTD - Question of Loyalty | `aotd_qol` | 2.0.9 (0.98) | Ashlib 2.0 |
| AoTD - Seats of Power | `aotd_sop` | 3.2.1 (0.98a) | Ashlib 2.2.3, BMO 2.1.0, **Toolbox 1.0.11**, LazyLib |
| AoTD - Vaults of Knowledge | `aotd_vok` | 5.0.7 (0.98a-RC8) | Ashlib 2.2.3, BMO 2.1.0, **Toolbox 1.0.11**, LazyLib |
| zz AoTD - Theory of Toolbox - Scheduler Fork | `aotd_theory_of_toolbox` | 1.0.14-spp13 (0.98a-RC8) | **StarsectorPrepatcher 0.18.3**, LazyLib, Ashlib 2.2.3, BMO 2.1.0 |
| StarsectorPrepatcher (kirpoly) | `starsector_prepatcher` | 0.18.4 | a `-javaagent`, last in the chain |

The fork is a maintained, third-party replacement for Kaysaar's Toolbox. Its README says that with Prepatcher
it "requires an active, compatible Prepatcher javaagent" (capability mask `0xbff`); merely having the mod folder
installed is not enough. Seats of Power and Vaults of Knowledge ask for Toolbox 1.0.11, the fork is 1.0.14-spp13.

## Why this matters now

1. **Prepatcher supports Java 17 and one validated Java 27 (`27+22`).** Its `docs/COMPATIBILITY.md`: newer JVMs
   get the same capability check but "support is not claimed without separate validation". Java 28 is therefore
   unvalidated by its author. On Java 27+ it also repairs obfuscator member names such as `while.new`, which
   Java 27's class-file parser rejects.
2. **Prepatcher must be the last `-javaagent`, and it picks a profile from the effective JVM flags**
   (`JAVA17_STANDARD`, `JAVA27_STANDARD`, `FR_AGENT_CHAIN`, `FR_PREDEFINE_BRIDGE`). Configuring both Fast Rendering
   architectures at once is an explicit conflict that stops the launch.
3. **This install's `vmparams` and `fr.vmparams` carry no Prepatcher agent** (only `fr.agent.jar` in
   `fr.vmparams`). So the fork's startup requirement is unmet here as configured. *Unproven whether Mikohime's
   launcher adds it; I found no `-javaagent` for it in `Miko_Rouge.bat` or `mikohime/`.*
4. The tester's traces (`SpecStore.lambda$SpecStore_init$0` on a thread pool) show a patched class loader.
   Prepatcher and Fast Rendering both patch game classes, so the cause of those errors may be either, or the
   combination. The environment matrix (item 61/62) must therefore include Prepatcher as an axis.

## What already exists (do not redo)

- Item 38 (done): `industry-plugin-override` (AoTD sets six RC8 industry plugins), `new-game-plugin-override`,
  `temporary-market-fleet-source` (Toolbox turns a per-fleet market add/remove into a structural economy refresh),
  and `done-audit` compatibility sections. Evidence there was gathered against the **original** Toolbox, which
  replaces the economy object (`AoTDEconomy`). The fork changes how that economy is refreshed.
- Item 39 (open): population-delta fixer, to be proven first on DNEEP with AoTD on the rig.

## Plan

Order is the order I recommend. "Cloud" means it needs no game; "Local" needs the rig.

1. **Prepatcher axis in the environment matrix (Local build, cloud-testable).** `java-matrix` variants gain
   `prepatcher: off|on`. `on` appends `-javaagent:../mods/StarsectorPrepatcher/agent/StarsectorPrepatcherAgent.jar`
   as the *last* agent (to the generated bat for `direct`, to the filtered `fr.vmparams` copy for `fr`). The install
   files are only read, as today. Variants: `j25/j27/j28` x `direct/fr` x `prepatcher off/on`, with the owner's
   three-at-a-time limit and screening unchanged. Done = a pass-rate table that separates Fast Rendering from
   Prepatcher.
2. **`env-check`, a preflight before any boot (Cloud).** Reads the launcher and `vmparams`/`fr.vmparams` and reports:
   javaagent order (Prepatcher last), both FR architectures configured, Java version against Prepatcher's validated
   set (17, 27), and every enabled mod that declares `starsector_prepatcher` as a dependency while no agent is
   present. Output is a finding with `SAFE`/`REVIEW`/`MANUAL` and confidence, per house rules. Extends
   `java-matrix describe-log` to read the agent and Prepatcher lines from a tester's log, so a report says
   "Java 28, FR agent, no Prepatcher" without asking.
3. **An `aotd` compat set (Cloud config, Local run).** Add to `config/` compat sets: libraries (LazyLib, Ashlib, BMO,
   Prepatcher, the Toolbox fork) plus each AoTD module alone, then pairs, then all four. The modules claim to be
   independent of each other (their descriptions), so pairwise boot is the cheap proof. Boot-test must also load a
   new game and a save, because the fork's work (deferred economy refresh, restore-safe rebuild) happens after the
   menu: a menu-only pass proves little (*unproven*).
4. **Toolbox version check (Cloud).** New finding when a mod's declared Toolbox minimum (1.0.11) is lower than the
   installed fork (1.0.14-spp13), or the installed Toolbox is the original while another enabled mod requires the
   fork's capability mask. Also flag `gameVersion` spread across the set (0.98, 0.98a, 0.98a-RC8): harmless to the
   game but it hides which build a mod was tested on.
5. **Re-prove item 38 against the fork (Local).** For each of the six overridden industries and the temporary-market
   pattern, repeat the javap and live check on the fork instead of the original Toolbox, because the fork rewrites
   the refresh path ("condition-only, detached-Cargo, loot suppression"). Record rows in `docs/RC8_BEHAVIOUR.md`.
   Only if the fork behaves differently does `temporary-market-fleet-source` change its wording or severity.
6. **Per-frame market work scan (Cloud check, evidence first).** The fork's changelog records a rollback from
   ~50 to ~90 FPS after a redesign, so economy refresh cost is the known sensitivity. Add a REVIEW check for revived
   mods that call `reapplyIndustries`, `reapplyConditions`, `addCondition`/`removeCondition` or `addMarket` /
   `removeMarket` from `advance` / `EveryFrameScript` paths. Prove it by running one flagged mod with and without the
   fork before it ships as a finding.
7. **Release policy note (Cloud).** The fork is third-party and AoTD is Kaysaar's: record both in
   `release_policy.json` as not redistributable by BridgeForge, and make `dependency-substitutes` name the fork,
   not the original, when a revived mod needs Toolbox.

## Evidence still to collect before building 4-6

- Whether the owner's real launch path loads Prepatcher at all (item 3 above); a `java-matrix` run with
  `prepatcher on` and the fork enabled gives the answer without guessing.
- Whether a tester's setup includes Prepatcher: their log (not available) or one question.
- A Java 28 boot with and without Prepatcher: Prepatcher's author does not claim it.
