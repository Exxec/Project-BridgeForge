# Bug-class registry (roadmap P7)

One row per bug class actually found during live testing of the mods under `In operation/`
(2026-09-08 .. 2026-09-11, per `In operation/STATUS.md` and `CHANGELOG.md`). Per
`docs/REVIVAL_ASSURANCE_PLAN.md` principle 2 and the `AGENTS.md` rule it backs: **no live finding
closes without a scanner check, a probe assertion, a test, or a written reason.** A check id in
the table below is a literal scanner `Finding.id`, a `fixers.SUPPORTED_FINDINGS` id, or a
`probe-mod` `ProbeLog` check name (all in backticks); `tests/test_bug_class_registry.py` parses
this table and asserts every such id actually exists somewhere in the codebase. A row with no
check yet must instead read `NONE (written reason: ...)` and give the reason inline.

| Bug class | Symptom | Root cause | Check / probe assertion | Test file | First mod hit |
| --- | --- | --- | --- | --- | --- |
| VAC-CARRIER-01 | A revived carrier hull launches no fighters after the 0.98a carrier rework | `ship_data.csv` predates the `bays` column; the hull keeps a `CARRIER` hint with no bays or wings | `carrier-without-bays-or-wings`, `ship-data-missing-fighter-bays-column` | `tests/test_scanner.py` | Vacuum |
| BS-PROCGEN-01 / EX-NEWGAME-02 / EX-NEWGAME-03 | `Fatal: PlanetGenDataSpec`/`StarGenDataSpec ... not found` at new game | A custom planet/star type has no matching row in `planet_gen_data.csv`/`star_gen_data.csv` | `procgen-planet-row-missing`, `procgen-star-row-missing` | `tests/test_scanner.py`, `tests/test_fixers.py` | Broken Star |
| EX-NPE-001 / FLX-KNOWN-01 / FG-KNOWN-01 | A faction never spawns ships/fleets, or an NPE walks its known lists | A `.faction` file has an empty/missing `knownShips`/`knownWeapons`/`knownFighters` | `faction-known-lists-missing` | `tests/test_scanner.py`, `tests/test_fixers.py` | Exigency |
| EX-MARKET-01 | A market's submarket stocks fighters but not ships, or vice versa | A shipRoles/known-list migration didn't carry every role variant across | `faction-known-lists-missing`; probe assertion `submarket-stock` | `tests/test_scanner.py`, `probe-mod/src/com/bridgeforge/probe/CampaignProbeScript.java` | Exigency |
| SK-13 | `NullPointerException: Person.getPersonality() is null` in `CombatFleetManager.deployAll` once AI Tweaks is enabled | A module-hull's captain has no personality; vanilla tolerates this, AI Tweaks' extended ship AI does not | `module-captain-personality-risk`, `spawned-ship-captain-personality-risk`; probe assertion `combat-captain-personality` | `tests/test_scanner.py`, `probe-mod/src/com/bridgeforge/probe/BfProbeCombatPlugin.java` | SEEKER |
| SK-10 | A fighter wing that should still spawn standalone silently stops appearing after a carrier-rework migration | A wing's role/id regressed while adding the `bays` column elsewhere in the same hull family | `wing-role-assault-removed`, `carrier-without-bays-or-wings` | `tests/test_scanner.py`, `tests/test_boot_test.py` | SEEKER |
| LOA-RING-01 | `RingBand.writeReplace: JSON does not allow non-finite numbers` at new game | A ring/orbit radius or period is computed without a guard against a non-finite result | `orbit-period-zero`, `orbit-period-computed-unguarded`; probe assertion `rings-orbits` | `tests/test_scanner.py`, `probe-mod/src/com/bridgeforge/probe/CampaignProbeScript.java` | Legacy of Arkgneisis |
| LOA-VAR-01 | A weapon silently vanishes from a variant at load, with no error | The variant mounts a weapon whose slot type doesn't match the hull's declared slot type at that mount | `variant-weapon-slot-mismatch` | `tests/test_scanner.py` | Legacy of Arkgneisis |
| FG-DESC-01 | A ship/weapon description renders truncated or with a stray quote | A `descriptions.csv` row's quoting doesn't round-trip through the CSV parser | `description-missing`, `csv-row-extra-columns` | `tests/test_scanner.py`, `tests/test_fixers.py` | FlowerGod |
| EC-LVL-01 | A revived `LevelupPlugin` silently overrides XP progression for every mod in the load order | The target-engine `LevelupPlugin` interface gained a mandatory method the old implementation never provided | `target-interface-method-missing` | `tests/test_scanner.py` | Edmund's Church 2.5 |
| EX-REFLECT-01 | `SecurityException` at class-load time inside the RC8 script sandbox | Reflection/`File`/NIO API use, which RC8's sandbox forbids at class-load | `script-sandbox-forbidden-api`; jar-audit reflection findings | `tests/test_scanner.py`, `tests/test_jar_audit.py` | Exigency |
| EX-ROUTE-01 | A moving custom entity (e.g. Avesta) drifts far from its intended waypoints | Hard-coded hyperspace coordinates that don't scale with a changed hyperspace size | `hardcoded-hyperspace-coordinates`, `hardcoded-terrain-grid-size` | `tests/test_scanner.py` | Exigency |
| EX-BUNDLE-01 / OMG-BUNDLE-01 | A rebuilt jar silently carries dozens of extra library or vanilla classes | `javac` compiled a library's (or vanilla's) sources off the classpath into the mod's own jar | `bundled-library-classes`, `vanilla-class-duplicated-in-jar` | `tests/test_scanner.py`, `tests/test_jar_audit.py` | Exigency |
| EX-MASK-02 | A procedurally-placed nebula/mask lands in the wrong spot relative to a named system after a resolution change | A hyperspace mask was rescaled for size but never verified for placement -- this is an evidence-tier-T3 visual judgment, not something a static or probe check can prove | NONE (written reason: needs a human's eye on where the cleared region actually renders relative to Tasserus; tracked as `ROADMAP.md`'s post-1.0 "campaign-state coupling" research track, and as risk 1 in `docs/REVIVAL_ASSURANCE_PLAN.md` §5) | -- | Exigency |
| VT-7 (script/listener duplication) | A UI-lifecycle script re-adds itself on every open/close cycle, or on every `onGameLoad`, growing per-frame cost | `onGameLoad`/dialog-open code re-registers an `EveryFrameScript`/listener without checking it is already present | NONE (written reason: needs a save-inspect-style duplication audit of live per-entity script counts from a real save -- roadmap P3b-A and P3B_SAVE_TOOLING_RECOMMENDATIONS.md item F; not yet implemented) | -- | Void-Tec r13 |

## Durable conventions (moved out of `In operation/STATUS.md`)

- **Scope authority:** revival targets player-visible behaviour on the current API, not
  byte-for-byte preservation of removed internals (`ROADMAP.md`, `In operation/STATUS.md` §"Scope
  authority").
- **Never rebuild a shipped jar from bundled `src/`** without a class-by-class diff first --
  bundled source routinely lags the shipped jar (see `docs/THIRD_PARTY_MOD_PATCHING` conventions
  and the Arkgneisis crash-fix precedent); `jar-audit`'s removed/added-class lists are the
  authoritative check.
- **Every edit that changes shippable content gets a build-tag bump** before it goes to a rig, so
  the in-game launcher name proves which build is running.
