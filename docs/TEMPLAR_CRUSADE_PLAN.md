# Templar Holy Crusade on RC8: design plan (ROADMAP item 71)

Owner question 2026-10-13: can the Crusade system of Templars 0.9.8f be re-created for 0.98a-RC8? **Yes.** RC8 ships the building
blocks the old event lacked, and vanilla already uses them for the same kind of event (Persean League and Sindrian Diktat punitive
expeditions, the Knights of Ludd takeover expedition). This document says what the old system did, what replaces each part in RC8,
how it is packaged, and how it is tested. Nothing is built yet.

## 1. What the 0.9.8f Crusade did

Read from the 0.9.8f sources kept in `In operation/Templars-0.9.8f/scratch/port-0.9.9e-code/before/` (2026-10-13):

| Part | 0.9.8f class | Behaviour |
|---|---|---|
| Scheduler | `TEM_TemplarsManager` | Every `crusadeAverageFrequency` days (default 320, `TEMPLAR_OPTIONS.ini`), times 1.0 to 1.5, picks a target system: a weighted pick of markets hostile to the Templars, weight = market size, within 100,000 units of Ascalon, never Antioch, never the previous target. |
| Event | `TEM_CrusadeEvent` (`BaseEventPlugin`, `events.json`, `reports.csv`) | Stages: planning (told only to a player at least Cooperative with the Templars), "coming" (15 to 30 days, intel to the player), start (30 to 60 days, longer with distance from Ascalon), end, aftermath. Stops early if Ascalon is no longer Templar. |
| Templar side | `TEM_TemplarsAttackFleetManager`, `TEM_TemplarAttackAI` | The normal Templar attack fleets switch to the crusade system while `tem_currentCrusade` is set in persistent data. |
| Defenders | `TEM_CrusadeEvent` + `TEM_ResponseFleetAI` | Nearby markets of the target's faction and its Cooperative friends (with a spaceport, station, base or capital) send "response fleets" (`FleetFactoryV2`, PATROL_LARGE, size by distance and `crusadeScale`) that travel to the system, raid-patrol it, defend markets, then go home and despawn. Pirates and a few outlaw factions never respond. |
| Target markets | `TEM_CrusadeTarget` condition `tem_crusade_target` | During the start stage every market in the system hostile to the Templars gets -3 stability ("Crusade site") and much worse trade: price x2.5 (gaussian, sd 0.5) and smuggling x7.5 on every market connection. |
| Outcome | `TEM_CrusadeEvent` | morale = (Templar losses x 1.5 - allied losses) / (200 x crusadeScale). Six endings, from "crushed" (morale below -3) to "victory" (1.5 and up), each a news report with both sides' losses. After the end, each target market gets 1 to 3 points of recent unrest by ending and market size. |
| Player | `TEM_CrusadeEvent.reportBattleOccurred` | Fleet points the player destroyed on either side are tracked. Defending well (over 15% or 40% of Templar losses): reputation up with every defending faction (up to Cooperative), and Templars driven to Hostile/Vengeful. Helping the Templars: denounced or condemned by the defenders. |
| Debug | `data/console/commands/TEM_TriggerCrusade.java` | Console Commands command to start one now. |

## 2. Why it stopped working, and the RC8 replacement for each part

| 0.9.8f mechanism | Status in RC8 (javap of `starfarer.api.jar`, 2026-10-13) | RC8 replacement |
|---|---|---|
| `BaseEventPlugin`, `events.json`, `reports.csv`, `reportEventStage`, comm messages | Removed (the 0.8 event system) | An intel: `GenericRaidFGI` (`impl.campaign.intel.group`), a `FleetGroupIntel` with built-in prepare, travel, payload and return stages, intel updates and a map route. Vanilla's `PerseanLeaguePunitiveExpedition`, `SindrianDiktatPunitiveExpedition` and `KnightsOfLuddTakeoverExpedition` are subclasses of it, so the pattern is the game's own. |
| `RecentUnrestEvent.increaseStabilityPenalty` | Removed | `RecentUnrest.get(market).add(points, reason)` (`impl.campaign.econ.RecentUnrest`, exists). |
| `MarketConnectionAPI` price and smuggling mods (`EconomyAPI.getConnection`) | Removed with trade connections | Accessibility: `market.getAccessibilityMod().modifyFlat(id, -x, "Holy Crusade")`, which is how RC8 models a blockade's effect on trade (exports and imports scale with accessibility). |
| `FleetFactoryV2.createFleet` | Removed | `FleetCreatorMission` inside `GenericRaidFGI.createFleet/configureFleet` (fleet sizes come from `GenericRaidParams.fleetSizes`), or `FleetFactoryV3.createFleet(FleetParamsV3)` for the defender fleets. |
| `RepActionEnvelope(action, param, CommMessageAPI, boolean)` | Changed | `RepActionEnvelope(action, param, null, textPanel, true)`; message text goes in the intel update instead of a comm message. |
| `CampaignEventListener.reportBattleOccurred` | Still exists, through `ListenerManager` / `FleetEventListener` | Same: count fleet points lost per side and the player's share. |
| `MarketAPI.addCondition(id, boolean)` | Changed | `addCondition(id)`; a `BaseMarketConditionPlugin` subclass for `tem_crusade_target`. |

## 3. Design

### 3.1 Packaging: a separate companion mod

**Templars Holy Crusade (BridgeForge)**, mod id `tem_crusade_bf`, depends on `Templars` (and LazyLib). Its own mod plugin and a small
jar. It does not change any Templars archive (0.9.8f port, 0.9.9e, or the official 2.5.1 if it shares the ids), so an archive stays as
validated, and the Crusade can be enabled, tested and removed on its own. Credit line per the owner's rule: the Templars authors first,
then "Crusade re-created for RC8: BridgeForge by Exxec".

Cost of that choice: the companion cannot change Templars' own attack fleets, so the Templar side of the Crusade is spawned by the
companion itself (3.3), not by redirecting `TEM_TemplarsAttackFleetManager` as 0.9.8f did. That is also safer: 0.9.9e's fleet manager
has no Crusade hooks to rely on.

### 3.2 Scheduler: `TemCrusadeManager` (EveryFrameScript, saved)

- Added in `onGameLoad` if absent; one instance (memory key `$tem_crusade_bf_manager`).
- Timer: average `crusadeAverageFrequency` days (default 320) times 1.0 to 1.5; read from the companion's own settings
  (`data/config/tem_crusade_bf_settings.json`: `crusadeAverageFrequency`, `crusadeScale`, `enabled`), since 0.9.9e's
  `TEMPLAR_OPTIONS.ini` no longer has them.
- Origin: the Templar market `Ascalon` if it is still Templar (Corvus mode: built by `TEM_Antioch`; Nexerelin random sector: built by
  Nexerelin's own `ExerelinProcGen` when `enableAntioch` is on), else the largest Templar market; no Templar market, no Crusade.
- Target: the 0.9.8f pick, kept exactly (hostile to Templars, weight = size, within 100,000 units, not Antioch, not the last target).
- One Crusade at a time (the intel is the lock, as `tem_currentCrusade` was).

### 3.3 The Crusade itself: `TemCrusadeFGI extends GenericRaidFGI`

- `GenericRaidParams`: `factionId = "templars"`, `source` = the origin market, `prepDays` 15 to 30 (the old "coming" stage),
  `payloadDays` 30 to 60 x sqrt(max(distance / 15000, 1)) (the old start-stage formula), `makeFleetsHostile = true`,
  `noun = "Holy Crusade"`, `forcesNoun = "crusaders"`, `memoryKey = "$tem_crusade_bf"`.
- Fleet sizes: from the target system's markets, as 0.9.8f sized the defence: 2 + sum(max(1, size - 2)), times `crusadeScale` / 2.5,
  turned into a list of fleet sizes for `fleetSizes`; Templar doctrine and ships come from the faction (0.9.9e's faction file and
  `default_ship_roles.json`, which the 0.9.8f port also uses).
- Payload: a custom `GenericPayloadAction` (override `createPayloadAction`) that orders the fleets to `RAID_SYSTEM` and
  `ATTACK_LOCATION` around the target markets for the payload days, rather than vanilla's ground raid (the 0.9.8f Crusade fought
  fleets and broke stability; it never raided industries). Optional later: a "victory" ending that disrupts one industry, as vanilla
  raids do, if the owner wants teeth.
- Intel text: the six 0.9.8f endings and the planning, coming and start texts move from `reports.csv` into the intel's description
  and update bullet points (`addBasicDescription`, `addStatusSection`, `addUpdateBulletPoints`). The planning stage is shown only to a
  player at least Cooperative with the Templars, as before; the rest goes to everyone.

### 3.4 Defenders: `TemCrusadeResponseManager`

- While the payload runs, markets of the target's faction and its Cooperative friends within reach, with a spaceport, station,
  military base or capital, send response fleets (0.9.8f rule; pirates, `exipirated`, `junk_pirates`, `merc_hostile` never answer).
- Fleets from `FleetFactoryV3.createFleet(FleetParamsV3)`, PATROL_LARGE, points by distance weight (20000 / max(distance, 5000)) and
  `crusadeScale`; assignments: travel, `RAID_SYSTEM` at the system, `DEFEND_LOCATION` at a target market, return, despawn (the
  0.9.8f `TEM_ResponseFleetAI` sequence).
- An alternative worth one experiment: vanilla `MilitaryResponseScript` (exists in RC8) makes a faction's patrols converge on a point
  without spawning extra fleets. If it gives a credible defence, it replaces the spawner and costs nothing in fleet count.

### 3.5 Market effects: condition `tem_crusade_target`

- Added to every market in the target system hostile to the Templars when the payload starts, removed when it ends.
- -3 stability ("Crusade site"), as 0.9.8f.
- Trade: accessibility -20% while the Crusade is in the system, as the RC8 stand-in for 0.9.8f's x2.5 prices (the number to be
  tuned by the owner; a blockade is the nearest vanilla effect).

### 3.6 Outcome and aftermath

- Losses: a `FleetEventListener`/battle listener adds fleet points lost by the crusaders and by defenders and the share the player's
  fleet destroyed on each side.
- morale = (Templar losses x 1.5 - allied losses) / (200 x crusadeScale): same six endings and thresholds as 0.9.8f.
- Unrest: `RecentUnrest.get(market).add(n, "Holy Crusade")` with 0.9.8f's table (1 to 3 by ending and size).
- Player: 0.9.8f's thresholds and reputation changes (defending helps with the defenders and angers the Templars up to Vengeful;
  helping the Templars draws denouncement), applied with RC8's `RepActionEnvelope` and reported in the intel.

### 3.7 Nexerelin

- Random sector: works if Nexerelin built Antioch (Ascalon present); otherwise the largest Templar market is the origin.
- Corvus mode: as above.
- Nexerelin's own invasions and diplomacy are left alone; the Crusade does not capture markets.
- Zorg comparison (owner's request): this is the same "existential threat" shape as Zorg's hostility, but active rather than passive.
  If the owner wants Zorg to make war the same way, the same `GenericRaidFGI` skeleton serves (a "Zorg Assimilation wave" from
  Unimatrix), see ROADMAP item 71 follow-up.

### 3.8 Save safety

- The manager and the intel are saved objects. Removing the companion mod from a running save leaves their classes missing, so the
  save will not load: say so in the readme, as for any campaign mod.
- No market, planet or fleet is stored inside a Memory (the Station Augments cycle pattern, RC8-31): the intel keeps references to
  markets and fleets as vanilla raid intels do.

## 4. Testing

1. `compile-check` and `scan` on the companion (Janino rules do not apply: it is a jar).
2. A debug setting `debugStartInDays` (default -1) and a short-stage mode (prep 1 day, payload 5 days) in the companion's settings,
   so the BridgeForge live harness can see a whole Crusade in one unattended run; plus the old console command re-created against the
   new intel (`TEM_TriggerCrusade`, Console Commands optional).
3. Live run (probe-group with Templars + companion, Corvus and Nexerelin random sector): log lines `BF-TEMCRUSADE|stage|...` for
   start, fleet count and points, condition added/removed, ending, unrest applied. Done when: an intel appears, crusader and defender
   fleets reach the system, the condition is on and off at the right times, an ending is reported with losses, unrest lands, and the
   save after it reloads.
4. A duel-style frame check while 10+ fleets fight in one system (`combat-perf` is combat only; use the campaign frame time from the
   log), since the old Crusade could pile up fleets.

## 5. Phases and effort

| Phase | Content | Effort |
|---|---|---|
| C1 | Companion skeleton, settings, manager, target pick, intel with prep/travel/payload/return and Templar fleets | half a day |
| C2 | Market condition (stability, accessibility), endings, unrest | 2 to 3 hours |
| C3 | Defender response fleets (or the `MilitaryResponseScript` experiment) | 2 to 3 hours |
| C4 | Battle tracking, player reputation, intel texts from `reports.csv` | 2 to 3 hours |
| C5 | Debug mode, console command, live runs in Corvus and random sector, balance pass | half a day |

## 6. Decisions for the owner

1. Companion mod (recommended) or built into the archived Templars versions?
2. Which Templars it targets: the 0.9.8f port, 0.9.9e, or both (the ids are the same, so one companion can serve both).
3. Trade effect: accessibility -20% as the stand-in for 0.9.8f's price spike, or a different number?
4. Should a Templar victory also disrupt an industry (vanilla raid effect), or stay stability-only as in 0.9.8f?
5. Defenders: spawn response fleets as 0.9.8f did, or try vanilla `MilitaryResponseScript` first?
