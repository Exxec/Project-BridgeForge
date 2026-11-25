---
name: bridgeforge-catalogue
description: Catalogue what every archived mod in Done/ needs on a new Starsector build, read-only: run `target-impact` from the old core to the new one over Done/, then summarise the verdicts, the shared game members, the next step per mod and the time savers for the owner. Use it whenever a new game build or release candidate appears, when the owner asks to "scan the revived mods", "check what the new version breaks" or "catalogue what needs doing", or before any retarget or target-bump.
---

# Cataloguing Done/ against a new build

This is read-only: nothing is fixed until the owner says so. On 2026-11-17, RC8 -> 0.98.5a-RC7 over 175 archives took
about 5 minutes on Test1, which holds the main archive; on 2026-11-25, RC7 -> RC9 over 350 took about the same.

## 1. Run it where the archive is

```
bridgeforge target-impact "<previous core>" "<new core>" "<repo>\Done" --write "<repo>\bridgeforge-state\target-impact-<OLD>-to-<NEW>-<date>"
```

- **Run it in the background** (it is a long-running command) and read its progress lines. On Test1, use a one-off
  scheduled task or a plain SSH command (the `test1-run` skill), then copy `TARGET_IMPACT.json` and `TARGET_IMPACT.md` back.
- **Name the build each core reports, not the folder name.** Test1's `Starsector-0.98.5a-RC3` folder is RC3; check it
  with `bridgeforge target show`.
- **Skipped archives:** folders starting with `_` (for example `_replaced-<date>`) are skipped. So are archives the owner
  closed with `bridgeforge close "Done/<Mod>" --status SUPERSEDED|NOT_REVIVABLE --reason ...` (95.15); they are listed under
  `skipped`.

## 2. Summarise for the owner

- **Counts:** CLEAN / BREAKS / RELINK / REVIEW. CLEAN means no API, linkage or data change; it is not a live result.
- **Shared members:** the "By game member" table. One changed member often explains several mods, for example
  `StarSystemGenerator.addStableLocations` returning a List hit three archives and Sunrider.
- **Per mod, the cheapest next step:**
  - gated fixer only;
  - `restore-from-done`, then `relink`;
  - a default-argument rule (95.14);
  - a hand port (calls into obfuscated game internals);
  - a review (id collisions with new vanilla content).
- **Informational lines** that change nothing at load, for example a replaced CSV missing new columns, which read as blank.
- **Time savers:**
  - mods archived more than once (the owner keeps only the latest; older ones move to `Done/_replaced-<date>/`);
  - checks the catalogue could do itself;
  - report noise.

Before you recommend work, ask the owner which mods are active upstream (skip those) and which are abandoned (port them).
On 2026-11-17: AoTD was active and is skipped; the rest were abandoned and are ported.

## 3. After the owner decides

Follow CLAUDE.md "When a new game version appears":
- `target-bump`;
- the gated fixers the catalogue lists;
- `retarget` for the CLEAN workspaces, which carries current baselines (95.10);
- per-mod revivals with the `bridgeforge-revive` skill.

Record the decisions in the memory note for this catalogue.
