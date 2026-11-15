# Game-version compatibility across BridgeForge and its sister repos (proposal, 2026-11-15)

Status: **proposed, not approved.** It extends `SISTER_REPO_INTEROPERABILITY_DESIGN.md` (section 5 there would point
here) and ROADMAP-3 item 89. Changing what a sister repo accepts is that repo's decision under its own contract; this
document proposes the shared contract and the order of work.

## Problem

Every project hard-codes one game build, so a new Starsector release breaks each one separately and silently. A
read-only audit on 2026-11-15, after the target moved from 0.98a-RC8 to 0.98.5a-RC3, found:

| Repo | Where | Effect on 0.98.5a |
|---|---|---|
| Salvor | `salvor/rig.py:128` `_preflight` requires `game_version == '0.98a-RC8'` | every rig launch for a 0.98.5a save is refused |
| Salvor | `salvor/rig.py:53` direct start requires mod `gameVersion` in `{'0.98a','0.98a-RC8'}` | every mod retargeted to 0.98.5a is refused |
| Salvor | `salvor/repair.py:143` mappings keyed on exact `game_version` | RC8-qualified repairs do not match (safe: refused, reads as "no recipe") |
| Salvor | evidence RC8-28..36 (menu/Continue layout, capacity, save-on-pause) | unproven on 0.98.5a |
| VoidSmith | `campaign/format.py:19` `SUPPORTED_VERSION = ("0.98a-RC8", "0.6")` | `save inspect` refuses every 0.98.5a save |
| VoidSmith | `campaign/overage.py:22`, locators RC8-CREDITS/STACK/STORY | unproven on 0.98.5a |
| Project Go | `SWE handoff.md` RC8 `JAVA_HOME`; `settings.json` "rules" list not checked | documentation only |
| RevenantLib | `dl_DroneAPI` | fixed in RevenantLib PR #4 (1.3.0+bf.2; links on both builds) |
| BridgeForge | "RC8" in fixer names, `RC8_BEHAVIOUR.md`, profiles; `--vanilla-core` on every command | item 90 |

The fix is not to widen each string. A build string in these checks stands for *"the facts this code relies on were
proven on this build"*, and widening it would claim proof nobody has. The facts have to be qualified per build.

## Design

### 1. One build registry, produced by BridgeForge

`target-bump NEW_CORE` (item 90) writes `bridgeforge-state/targets/<build>/build.json`, and BridgeForge exports the set
as a versioned **game-build registry** (`game-builds.json`, `schema_version: 1`):

- `build`: the version string read from the core (`core_game_version`), e.g. `0.98.5a-RC3`;
- `core_fingerprint`: SHA-256 of `starfarer.api.jar`, `starfarer_obf.jar` and `fs.common_obf.jar` (so a renamed or patched
  install is not taken for the build);
- `save_versions`: the `saveFileVersion` values observed in real saves (empty until one exists);
- `mod_game_versions`: the `mod_info.json` `gameVersion` strings that mean this build (`0.98a`, `0.98a-RC8` for RC8);
- `previous`: the build it was diffed against, and the paths of the API, data and parameter diffs;
- `status`: `QUALIFIED` (target with live evidence), `OBSERVED` (diffed and scanned, no live proof), `RETIRED`.

Consumers read the registry; they never infer a build from a string pattern. Salvor already depends on the
`bridgeforge` package and can read it directly; VoidSmith reads the exported file (no new runtime dependency). An
unknown build or a fingerprint mismatch is `UNKNOWN`, never a default.

### 2. Behaviour facts carry a build, and a delta says which to recheck

`RC8_BEHAVIOUR.md` becomes a per-build register (`GAME_BEHAVIOUR.md`; old ids `RC8-NN` keep working as aliases). Each row
gains a **surface**: the API members, vanilla files or UI screens its evidence touched. For a new build, `target-bump`
classifies every row:

- `CARRIED (inferred)`: the API, data and content diffs touch none of its surface. Usable for read-only analysis, labelled
  inferred, never for anything that writes a save or ships a fix.
- `RECHECK`: the diff touches its surface; it is unproven on the new build until rechecked.
- `PROVEN`: a live run, vanilla file or javap on the new build settles it (evidence and date, as now).

UI-layout facts (Salvor's Continue row, the probe's mission list) have no API surface, so they are always `RECHECK`. The
sister repos keep their own fact ids (VoidSmith's locator ids, Salvor's capacity facts) but record the same three states
per build, so one table answers "what is unproven on 0.98.5a" for every project.

### 3. Per-repo gates read the registry and the fact states

| Repo | Read-only paths | Paths that launch, write or ship |
|---|---|---|
| BridgeForge | scans and target-impact run on any `OBSERVED` build | `retarget`/archive stamp a build only when the target-impact verdict is CLEAN and the scan has no blocking finding; "LIVE_VALIDATED" needs a run on that build |
| Salvor | diagnosis on any build in the registry, citing inferred facts as such | rig launch (`rig.py:128`) only on a build whose layout facts are `PROVEN`; direct start (`rig.py:53`) accepts a mod `gameVersion` the registry maps to that build; repair mappings stay exact per build and are re-qualified one by one (never carried) |
| VoidSmith | `save inspect` accepts a registry build plus an observed `saveFileVersion` (warning on `OBSERVED`) | edit and overage paths require the build's locator facts `PROVEN` |
| Project Go | no game dependency; doc fix only | none |
| RevenantLib | CI runs target-impact in both directions | a release names every build it links on |

### 4. Dual-build mods

The JVM links a call when it first runs, so a call to a member only the new build has is harmless on the old build if
the old build never reaches it (RevenantLib's forwarding methods). `target-impact` gains a `dormant` class: a call that
the old core lacks, made only inside a method the old core's interfaces do not declare. A mod is `BOTH` when the forward
check is CLEAN and the reverse check has only dormant calls. `gameVersion` still holds one string; the release notes and
the registry list the builds a mod links on. Wrappers for removed members (a reflective call, as RevenantLib's
`isBeingIgnored()`) are a `REVIEW` fixer, not `auto`: the fallback value is a judgement.

## Order of work

0. **Owner, about 10 minutes:** start one New Game on 0.98.5a, save, and quit. That gives a real 0.98.5a save for
   `save_versions` and for the Salvor and VoidSmith readers. Nothing below needs a decision until then except step 1.
1. **BridgeForge item 90:** `target.json`, `target-bump` (registry entry, catalogue, fact classification), bulk
   `retarget` for CLEAN mods, dormant-call verdict, registry export with schema tests and a synthetic fixture.
2. **Salvor and VoidSmith, read-only first:** replace the hard-coded strings with registry lookups; their tests use a
   synthetic two-build registry. Behaviour on RC8 stays byte-identical (pinned by their existing golden tests).
3. **Live qualification on 0.98.5a:** a 0.98.5a rig, the probe, the `RECHECK` facts (Salvor layout facts first, they
   gate automatic launch), and grouped smoke runs of the CLEAN archive.
4. **Write paths per build** as their facts become `PROVEN`; repair mappings re-qualified individually.

## Decisions for the owner

1. Should read-only tools accept an `OBSERVED` build, with a warning? (Recommended: yes; refusing to *read* a new save
   protects nothing.)
2. Registry location: BridgeForge exports and each repo pins a copy by hash (recommended, no cross-repo runtime coupling),
   or Salvor and VoidSmith import it from the `bridgeforge` package.
3. Keep RC8 `QUALIFIED` alongside 0.98.5a (recommended: yes; archives validated before 2026-11-15 rest on it).

## Exit

A new Starsector build costs one `target-bump` run plus the live `RECHECK` list. No sister repo needs a code change to
accept it, and none accepts it for writing before its facts are proven.
