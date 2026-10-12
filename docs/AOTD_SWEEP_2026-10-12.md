# AoTD compatibility sweep (Mod Atlas, 2026-10-12)

`bridgeforge atlas sweep aotd`: every indexed mod forecast against the whole AoTD family (Vaults of Knowledge 5.0.7, Theory of
Toolbox and its fork). ROADMAP item 67. Static evidence only: nothing here is proven to break a game; each REVIEW names a call site
a person or a live run should look at (DNEEP's `farming` lookup was exactly this kind of finding, and a live run confirmed it).

## Scope and method

- Atlas of 350 mod versions (Done/, the rig, the working copies, vanilla): 338 mods checked, the AoTD family excluded.
- A **call site** (`getIndustry`, `hasIndustry`, `removeIndustry`, `getCondition`, ...) of an id the family replaces, removes or
  upgrades is **REVIEW**. Creating one (`addIndustry("farming")` at generation, which AoTD expects) is not flagged. A string equal to
  the id somewhere in a jar's constant pool is only a **mention (UNKNOWN)**: javac inlines `Industries.FARMING` as `"farming"` into
  every jar that names it. Both rules were added after the first sweep flagged 80 mods, nearly all through `addIndustry` or mentions.
- "Replaced" comes from AoTD's `industries.csv` upgrade/downgrade chains and from remove-and-add pairs in the same class of its jar.

## Result

| Verdict | Mods |
|---|---|
| no static conflict found | 167 |
| REVIEW (a real call site) | 128 |
| UNKNOWN (string mentions only) | 42 |
| NEEDS PATCH (a MANUAL finding) | 1 |

Of the REVIEW mods, 83 have ATLAS-READS-REPLACED, 63 ATLAS-MUTATE-SHARED, 58 ATLAS-SAVE-HOLDS-HEAVY, 39 ATLAS-READS-MISSING, 37
ATLAS-SHADOW-CLASS. The last four are not about AoTD alone (they also fire between other mods in the set).

## Which ids AoTD changes that other mods look up (ATLAS-READS-REPLACED, REVIEW)

| Mods | Id | Examples |
|---|---|---|
| 28 | industry `orbitalworks` | AcceleratedConstruction, ArkLeg_dev, IndEvo, Neutrino, Omega_Psychasthenia |
| 22 | submarket `open_market` | ArkLeg_dev, IndEvo, InvisibleHand, SalvageEverything, armaa, ezfaction |
| 15 | industry `heavyindustry` | AcceleratedConstruction, ArkLeg_dev, IndEvo, Terraforming & Station Construction, nexerelin |
| 12 | industry `mining` | Erexeus_Tech_Complex_FactionMod, Gensoukyou_Daze, Sylphon_RnD, nexerelin |
| 12 | conditions `ruins_extensive`, `ruins_widespread` | Adjusted Sector, Nightcross, SalvageEverything, nexerelin |
| 10 | industry `lightindustry` | Sylphon_RnD, alcoholism, kadur_remnant, nexerelin |
| 8 | industry `farming` | Erexeus_Tech_Complex_FactionMod, SalvageEverything, kadur_remnant, seven_nexus (DNEEP, fixed in +bf.3, is the ninth) |
| 7 | industry `refining` | Neutrino, Sylphon_RnD, kadur_remnant, nexerelin |
| 7 | condition `hot` | Adjusted Sector, DNEEP, MagicLib, vayrasector |

Caveats on reading the table:

- **Conditions** `hot`, `cold`, `very_cold`, `ruins_*`: AoTD's data inserter removes them from specific planets at new game and adds
  its own (javap of `AoTDDataInserter`, 2026-10-12). The finding is true and narrow (a few planets), not a general replacement.
- **`open_market`** (22 mods) is the least certain row: it comes from a remove-and-add pair in an AoTD class and has not been read
  closely. Treat it as a question, not a finding.
- Whether a lookup breaks depends on what the mod does with the result. A mod that only asks "does this market have heavy
  industry" gets a different answer when AoTD converted the industry; a mod that removes an industry it never added may do nothing.

## A worked example: Legacy of Arkgneisis (our revival, `ArkLeg_dev`)

`loa_spawnRandomMarketsPlugin.EconomyFixer` scores each Anarakis market's "development level" from
`factionMarket.hasIndustry(Industries.HEAVYINDUSTRY)` and `ORBITALWORKS` (source in
`In operation/Arkgneisis/scratch/original-extracted`, lines 609-661). The sweep predicted that with AoTD converting those industries
the faction would lose its development bonus. **The live check did not support that at new game** (probe 0.2.27 `faction-economy`,
each run is a fresh new game, so the headquarters row is the comparable one):

| Run | Java / launcher | AoTD | HQ `orbitalworks` | `fleetQualityMod` | `combatFleetSizeMult` |
|---|---|---|---|---|---|
| GRP-ARK-BASE-J25 | 25 direct | no | true | 0.375 | 1.875 |
| GRP-ARK-BASE-J28FR | 28 Fast Rendering | no | true | 0.375 | 1.875 |
| GRP-ARK-AOTD-J25FR | 25 Fast Rendering + Prepatcher | yes | true | 0.375 | 2.125 |
| GRP-ARK-AOTD-J27FRP2 | 27 Fast Rendering + Prepatcher | yes | true | 0.375 | 2.125 |
| GRP-ARK-AOTD-J28FRP | 28 Fast Rendering + Prepatcher | yes | true | 0.375 | 2.125 |

AoTD leaves the NPC faction's orbital works alone and only adds a hidden helper industry (`aotd_misc_hidden_industry`) to each
market; the fleet-size modifier is a little higher, not lower. Java version and Fast Rendering changed nothing for this mod. The
REVIEW row stays a valid warning for markets AoTD converts later (for example a player-owned market), but for Arkgneisis' own
NPC markets the prediction was wrong. Lesson: a call-site finding says where to look; only a run says whether it matters.

## What to do with this

1. Live-check the highest-impact rows the way DNEEP and Arkgneisis were checked: a probe run with AoTD on and, where needed,
   `swap-industry` setups, reading the specific result with a probe check (`market-supply` for commodities, `faction-economy` for a
   faction's markets, fleet modifiers and industries). Next candidates: the `open_market` submarket readers and Nexerelin.
2. Fix only what a run shows: a fallback like DNEEP's lookup array is a small, local change.
3. Re-run `atlas sweep aotd` after any Atlas rule change; `reports/sweep-aotd.json` (local) holds the per-mod rows.
