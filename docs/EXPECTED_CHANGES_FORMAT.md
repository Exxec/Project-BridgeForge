# Expected-changes file (roadmap P9 v2 D4/D5)

A revival changes a mod on purpose: added known lists, a migrated wing schema, a fixed crash. Differential validation (`behavior-diff`) compares the reference with the revived build and finds **every** difference, deliberate or not. This file is how a deliberate change is declared, so it can be told apart from drift.

Status: **implemented in the D-series command set**. See
`docs/DISCOVERY_FIRST_WORKFLOW.md` for the executable workflow.

## Where it lives

`In operation/<Mod>/reports/expected-changes.json` (after release: `Done/<Mod>/reports/…`).
- **One file per mod.** Every entry names the build that introduced it, so the file reads as the mod's change history.
- **Kept next to the mod's reports, not in `bridgeforge-state/`,** because these are human decisions, not generated data, and they must survive a state wipe.
- **Never inside `working/`,** so it is never packaged into the mod.
- **Lenient JSON:** `#` comments and trailing commas are allowed, using the parser the scanner already has. No new dependency, and it works on Python 3.10.

## Shape

```jsonc
{
  "schema_version": 1,
  "mod_id": "exigency",
  # what "before" means for this mod: an old-game run of the original, or the first bootable build
  "reference": { "kind": "old-game-rig", "id": "0.7.2a-original" },   # or { "kind": "build", "id": "r1" }
  "changes": [
    {
      "id": "EXP-EXI-001",
      "build": "r1",                        # the [BF rN] build that introduced it
      "layer": "runtime",                   # runtime | save | static
      "summary": "Avesta's market sells ships and weapons",
      "why": "Pre-0.8a factions had no knownShips/knownWeapons; RC8 leaves their stock empty. Lists derived from the faction's own shipRoles.",
      "links": {
        "bug_class": ["faction-known-lists-missing"],
        "risk": ["RISK-EXI-014"],
        "test": ["EX-2"],
        "hyp": []
      },
      "match": {
        "observation": "market.stock",
        "subject": "market_exipirated*/open_market",
        "field": "ships",
        "change": "from_to",
        "from": 0,
        "to": ">0"
      },
      "status": "APPROVED",                 # PROPOSED | APPROVED | RETIRED
      "proposed_by": "agent", "approved_by": "owner", "approved_on": "2026-09-10"
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `id` | Stable `EXP-<MOD>-nnn`. Never reused, even after RETIRED. |
| `build` | Build tag that introduced the change. The release note groups entries by it. |
| `layer` | Which comparison it answers. `runtime` = probe baseline or census diff; `save` = `save-inspect` / `save-content` diff; `static` = archaeology map diff (P9-4). |
| `summary` / `why` | One line each, readable in a release note. `why` is required: an unexplained expectation is just a disguised unknown. |
| `links` | Breadcrumbs (P9-3) to bug classes, risks, tests and hypotheses. At least one RISK/HYP/TEST id is required; `expect check --artifact ...` rejects ids that don't exist in the supplied artifacts. |
| `match` | What the diff must see. See below. |
| `status` | PROPOSED (written with the change) → APPROVED (owner accepted it) → RETIRED (no longer applies, kept for history). |

## Matchers (`match.change`)

Each observation in a baseline has a kind, a subject and fields. Those names come from the `probe-baseline` / census JSON schema, so matchers can't drift from what is actually recorded.

| `change` | Use for | Extra fields |
|---|---|---|
| `from_to` | A value moved from one state to another | `from`, `to`; each may be a literal, `>0`, `<n`, `n..m` or `*` |
| `count` | How many of something | `from`, `to` (ranges allowed), optional `tolerance` for RNG-driven counts such as fleets |
| `added` / `removed` | Something appears or disappears (an entity, a listener, a market condition) | none |
| `renamed` | A class or id changed name | `old`, `new`. Also fed to `save-compat --compare-*`, so old saves are checked against the rename. |
| `any` | "Anything under this subject may change" | Discouraged: `expect check` lists every broad matcher, and the release note flags them. |

`subject` accepts `*` globs. A matcher has to be specific enough that it can't silently absorb a real bug. That's why `any` is flagged rather than forbidden.

## How `behavior-diff` uses it

Every delta between the reference baseline and the revived build's baseline lands in exactly one bucket:

| Bucket | Meaning | Release gate |
|---|---|---|
| `UNCHANGED` | Same as the reference | ok |
| `EXPECTED_CHANGE` | Matches an APPROVED entry | ok |
| `PENDING_APPROVAL` | Matches only a PROPOSED entry | blocks until approved |
| `UNEXPLAINED_CHANGE` | Matches nothing | blocks: explain it (add an entry), fix it, or cover it with a test |
| `EXPECTED_BUT_ABSENT` | An APPROVED entry the diff did not see | blocks: either the fix didn't take effect or the entry is wrong |
| `MISSING_OBSERVATION` / `NEW_BEHAVIOR` | The reference lacks the observation, or the revived build has something the reference never had | reported, then decided case by case |

`EXPECTED_BUT_ABSENT` is the bucket plain diffing can't give you. It catches a fix that silently stopped working: for example, known lists added but markets still empty.

## Lifecycle and commands

- **`expect add <mod> …`:** written by the agent or person **in the same step as the change**, as PROPOSED. This is the P9-3 breadcrumb.
- **`expect approve <file> EXP-… --by <owner> --on <YYYY-MM-DD>`:** the owner accepts it and it becomes APPROVED. Nothing counts toward release until this happens, and approval provenance is mandatory.
- **`expect retire <file> EXP-… --by <owner> --why "…"`:** for when a later change supersedes an entry; retirement provenance is mandatory.
- **`expect check <mod>`** reports:
  - links to ids that don't exist
  - duplicate ids
  - entries whose `build` has no manifest
  - broad `any` matchers
  - PROPOSED entries older than the last release
- **`release`:** the note gains a "Changes from the original" section built from APPROVED entries grouped by build, and the D5 gate reads the buckets above.

## Examples from this project

```jsonc
{ "id": "EXP-EXI-002", "build": "r1", "layer": "static",
  "summary": "Exipirated/Exigency fighters moved from shipRoles to knownFighters",
  "why": "RC8 treats shipRoles keys as variant ids; wing ids there aborted faction loading (EX-NPE-001).",
  "links": { "bug_class": ["wing-ids-in-shiproles"], "test": ["EX-1"] },
  "match": { "observation": "faction.data", "subject": "exipirated", "field": "knownFighters", "change": "count", "from": 0, "to": "16" },
  "status": "APPROVED" }

{ "id": "EXP-EXI-003", "build": "r1", "layer": "runtime",
  "summary": "Tasserus renders as a modern black hole",
  "why": "Owner request 2026-09-10; the 0.7.2a look relied on a removed nebula-mask path.",
  "links": { "test": ["EX-3"] },
  "match": { "observation": "planet.spec", "subject": "Tasserus/tasserus*", "field": "type", "change": "from_to", "from": "*", "to": "black_hole" },
  "status": "APPROVED" }

{ "id": "EXP-SKR-001", "build": "r0", "layer": "static",
  "summary": "All SEEKER hulls tagged rare_bp; Betelgeuse added to sim opponents",
  "why": "Owner decision: Betelgeuse was unreachable in the original.",
  "links": { "test": ["SK-8"] },
  "match": { "observation": "hull.tags", "subject": "SKR_*", "field": "tags", "change": "added" },
  "status": "APPROVED" }
```

The first real run will seed the file for Exigency from `STATUS.md` history (known lists, wing migration, procgen rows, Tasserus, carrier bays). Every later change then adds its entry as it's made.
