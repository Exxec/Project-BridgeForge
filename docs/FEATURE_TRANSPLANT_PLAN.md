# Feature tracing and transplanting (ROADMAP-3 item 84)

Owner-approved 2026-10-22 as a long-term item. Nothing here is built. It starts after item 83's refactor (B3 at least),
because the feature graph needs the package layout. LIVE TEST NOT PERFORMED.

## Goal

Pick a mod apart and trace every feature end to end (data ids, assets, code, hooks, runtime behaviour), then move a named
feature from one mod into another with its dependencies, id remapping, conflict and save checks, live validation and
recorded provenance.

## Rules

- Bytecode stays authoritative; decompiled code (Vineflower, items 82.7-82.9) is a reading aid.
- No research finding becomes a migration or transplant rule automatically: finding -> validated pattern -> candidate ->
  approved rule, with an owner decision at the last step (item 82).
- A gate is never upgraded without recorded evidence. STATIC, OBSERVED and VALIDATED keep item 82.4's meaning.
- Hook adaptation in a code transplant is human or agent work that BridgeForge checks; it is never automatic.
- Without the source author's permission a transplant stays LOCAL_ONLY (release_policy.json).

## Phases

| Phase | Builds | Reuses | Done when |
|---|---|---|---|
| T0 Feature graph | One queryable graph per mod: ids joined to the code that creates, reads or registers them, and to callers | Atlas, D-series, scanner, 82.2 reconciliation, 82.8 method map | `research report` answers from the graph, not by re-scanning |
| T1 Feature boundaries | Reviewable boundary record for a named feature | T0, `research report`, REMOVALS | Templar Crusade and SEEKER station modules each have a record a person agrees with |
| T2 Runtime trace | Probe stages proving entry points and hooks fire; evidence linked into the graph | probe mod, `probe-group live`, live records, gates.json | One feature's hooks are OBSERVED in a recorded run |
| T3 Data-only transplant | Dependency closure, id/namespace remap, collision check, install via `revise` | scanner id indexes, content parity, `revise`, archive gate | One EPTA ship line moves into a test mod, builds, boots and passes a live gate |
| T4 Code transplant planning | Decompile, package remap, hook-point list, rebuild against the target | `decompile-jar`, 82.7-82.9, `rebuild-jar`, `bytecode-inspect` | One code-backed feature moves into a test mod and passes a live gate |
| T5 Save safety | What an existing save needs when a feature is added or removed | save tools, migration packs, REMOVALS, `revise migration` | Adding and removing the T4 feature both load an existing save in a live run |
| T6 Provenance and permission | Per-file provenance record; archive gate check | release_policy.json, archive gate | The archive gate refuses a transplant with missing provenance |

## Data model sketch

Feature graph (T0), one per mod and mod version, stored under git-ignored `bridgeforge-state/`, keyed by the mod's file hashes
so a changed mod rebuilds it:

```
node  {id, kind, mod, version, source}        kind: hull | weapon | hullmod | shipsystem | faction | market | rule
                                                     | sprite | sound | string | setting | class | method | memkey
                                                     | script | listener | hook
edge  {from, to, kind, evidence, label}       kind: defines | reads | registers | creates | calls | references
                                                    | extends | listens | fires
                                              evidence: file:line, class#method descriptor, or live record id
                                              label: STATIC | OBSERVED | VALIDATED
```

Where Atlas and the D-series disagree about a concept, the edge keeps both readings and the 82.2 agreement category until a
decision says which stack is authoritative for that concept.

Feature boundary record (T1), JSON, reviewed by a person before any transplant uses it:

```
{schema_version, feature, mod, version, question,
 members: {files[], classes[], ids[], memory_keys[], scripts[], listeners[], hook_points[]},
 entry_points: [{kind: modplugin | listener | rules | economy | campaign_plugin, where}],
 dependencies: {libraries[], other_features[], vanilla_ids[]},
 excluded: [{item, reason}],              # things that look related but are not part
 evidence: [{claim, label, where}],
 review: {by, date, verdict: AGREED | CHANGES_NEEDED, note}}
```

Transplant plan (T3/T4) adds: target workspace, id/namespace remap table (into the target's namespace), an install manifest
for uninstalling as a unit, collision list, hook adaptations (each with a
reviewer), save notes (T5) and the provenance record (T6: source mod, version, file hash, author, licence).

## Pilots

1. T1: Templar Crusade (from the item 82 pilot, `bridgeforge-state/research/templar-crusade/`) and SEEKER station modules.
2. T2: the Crusade's hooks, scheduled with gate bf-0b-13 (Templar Crusade live run) so one rig session serves both.
3. T3: one EPTA ship line into a test mod (EPTA is LOCAL_ONLY, so the result stays local).
4. T4/T5: one small code-backed feature, chosen after T1 as the first proof of a path meant for any feature (candidates: a
   single hullmod with its ship system, or one campaign listener).

## Owner decisions (2026-10-22)

1. Targets: eventually both. Pilots go into a new empty test mod first; real target mods follow once a pilot passes its live
   gate.
2. Scope: not one feature. The tooling must handle any feature a mod has; the T4 pilot is only the first proof, chosen after
   T1 for being small, and later features use the same path.
3. Id remapping: transplanted ids, packages and memory keys take the target's namespace (prefix), recorded in the remap
   table so provenance and uninstall can map them back.
4. Removable: preferably yes. A transplant is installed as a unit with a recorded manifest, so it can be uninstalled as a unit;
   T5 checks both directions (add and remove) against an existing save.
5. Permission: no extra permission note. Provenance (T6) is still recorded per file, and release_policy.json keeps the result
   LOCAL_ONLY by default as for any revival.
