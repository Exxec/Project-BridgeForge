# Salvor (working name): save doctor, editor and trainer, a separate program (2026-09-29)

Status: idea, owner-requested. Start small and grow, as BridgeForge did. It will be messy at first, and that is
expected.

## Why a separate program

BridgeForge's save tooling is read-only on purpose. P3b decided "no general save editor, and no direct XML
editing: the game creates state, BridgeForge reads it" (`docs/P3B_SAVE_TOOLING_RECOMMENDATIONS.md`). Writing to
saves is a different risk class, and it has a different audience: players, not mod revivers. A sibling program
keeps BridgeForge's evidence rules intact, as SPW and Project Go do. It borrows code and ideas; it adds no runtime
dependency.

## What it would do, in growth order

1. **Diagnose (read-only; the first release).** Why a save will not load or has gone bad. Package what BridgeForge
   already has as a player-facing tool:
   - class and data-id compatibility (`save-compat`, `save-content`);
   - what a mod leaves in a campaign (`save-removal`);
   - duplicated scripts and listeners (`save-scripts`);
   - growth and bloat across a chain of saves (`save-growth`);
   - which build made the save (`save-provenance`);
   - a risk summary (`save-risk`);
   - a shareable redacted bug-report summary (`save-summary`).

   Read the crash, too: `log-triage` and the Fatal dialog text `bf-test` records, and SPW's `hs_err` crash-log
   analysis.
2. **Fix on a copy (guarded writes).** Each fix is a plan, then a write to a copy, then a verify step. Starting
   fixes, each from a failure we have actually seen:
   - drop or replace references to content a removed or renamed mod no longer defines;
   - remove duplicate scripts that `onGameLoad` re-adds;
   - strip a mod cleanly mid-campaign, driven by what `save-removal` lists;
   - reset a stuck event or intel.

   Verify by re-reading the result, then loading it in a test rig (`bf-test launch`, with the probe) before the
   player uses it. The original save is never overwritten.
3. **Editor.** Credits, cargo, blueprints, fleet members, officers and skills, faction relations, market
   conditions and industries. Adding Exigency blueprints to the owner's save by hand (2026-09-28) is the first use
   case. Every value is checked against the RC8 registries BridgeForge already reads:
   - registered skill ids, since an unregistered skill is a Fatal (RC8-18);
   - market conditions versus industries (RC8-16);
   - a hull's real weapon slots (RC8-17);
   - hull, variant, weapon and special-item ids.
4. **Trainer, offline.** Presets applied to a copy of the save between play sessions: max credits, repair and
   full CR for the fleet, reveal the map, add blueprints, set relations. There is no in-game mod and nothing
   runs inside the game (owner decision 2026-09-29). Every preset goes through the editor's validation and the
   same copy, re-read and rig-load gate.

## What to reuse

| From | What |
|---|---|
| BridgeForge | the save reader and all 13 `save-*` commands; lenient JSON/CSV parsers (`_parse_json`, `_read_csv_rows_lenient`); RC8 registries and checks (skills, market conditions, hull slots, content ids); the rig, launch and log capture (`bf-test.ps1`, `log-triage`, the Fatal dialog capture); the probe mod pattern; `progress.Checkpoint` for long runs; the evidence and classification rules (`SAFE`/`REVIEW`/`MANUAL`/`UNKNOWN`) |
| `docs/RC8_BEHAVIOUR.md` | proven game behaviour to validate edits against (RC8-01 to RC8-19) |
| Project Go | a Java GUI and packaged distribution, release-chain evidence, stable-id and hash-guarded apply |
| SPW | the in-game agent-mod pattern, the HTML report viewer, `hs_err` crash analysis, benchmark scenarios |
| VoidSmith / Starsector project forge | release evidence fields |

## Lessons that apply from day one

- **The game's hard limits:**
  - The script sandbox forbids `java.lang.reflect`.
  - A common file over 1 MB is a Fatal (probe 0.2.11).
  - A Fatal dialog never reaches the redirected log, so capture window text the way `bf-test.ps1` does.
- **Saves:**
  - A save names content by string id, so a removed id breaks a save just as a missing class does.
  - Obfuscated class names change between game versions.
  - Only edit paths the tool recognises, and refuse the rest.
- **Rig and process:**
  - The real install and the player's saves are read-only; work on copies in a rig with a junctioned core.
  - Compiling or parsing is not proof: a fix counts only after the save loads in the rig.
  - Long runs print progress and checkpoint.

## Later, and higher risk: an in-game battle assistant (owner idea, 2026-09-29)

A separate helper mod that assists in live battles, kept apart from Salvor's offline tools. It is well down the
road. It runs inside the game, so it inherits every runtime hazard BridgeForge has recorded:
- the script sandbox forbids reflection;
- a common file over 1 MB is a Fatal;
- listeners that `onGameLoad` re-adds pile up;
- anything it spawns or changes lives in the save.

Treat it as its own project with its own live-test gates; it is not a Salvor feature.

## Decisions (owner, 2026-09-29)

1. **Name:** Salvor, a working name that can change later. In Starsector a salvor recovers what is wrecked. It
   gets its own repository, separate like SPW and Project Go.
2. **Language:** Python. It reuses BridgeForge's save reader, parsers and registries directly. A GUI can come later
   (for example the stdlib `tkinter`, or a local HTML viewer as SPW has) without changing the core.
3. **Trainer:** completely independent of the game: offline presets on a save copy, no helper mod, no Console
   Commands dependency.
4. **Distribution:** local-only.

Still open: when to start. BridgeForge's live queue comes first.

## Revision (owner, 2026-10-06): Salvor stays a save rescue; the editor goes to VoidSmith

Salvor is now **lightweight save rescue**: diagnose a save and repair a copy (stages 1 and 2 above; v0.1 `repair`
exists in `Documents/Project Salvor`). It will not grow an editor or trainer. Editing moves to **VoidSmith**
(`Documents/Starsector project forge`), which already has the GUI, the ship, hull and weapon registries, and the
legality rules an editor needs to validate against.

The editor's scope now starts with **minor edits to the player's current state**:

| Tier | Edits | Check before writing |
|---|---|---|
| 1 (first) | credits; cargo commodities in the player fleet (supplies, fuel, crew, marines, heavy machinery); story points | quantity is a non-negative whole number; commodity id exists (RC8 `commodities.csv`); capacity behaviour above the cargo/fuel/crew limit is **unproven**, so it needs live evidence (probe, then `RC8_BEHAVIOUR.md`) before the tool allows or refuses it |
| 2 | fleet member repair state: CR, hull, armour, crew on a member; officer level and skills | skills must be registered (RC8-18); CR in range for the hull |
| 3 | blueprints known, fleet members added or removed, relations, market conditions and industries | hull, variant and weapon ids and slots (RC8-17), conditions versus industries (RC8-16) |
| later | offline trainer presets (max credits, full repair, reveal map) | all of the above through the same gate |

Rules that carry over unchanged: never write the original save; plan, then write a copy, then re-read it, then load
it in the rig before a player trusts it; refuse paths the tool does not recognise.

**VoidSmith side (done 2026-10-06, design only).** VoidSmith is published and read-only, and its roadmap item 56
kept campaign-save parsing decision-gated. Owner approved the change; VoidSmith now has
`docs/SAVE_WORKSHOP_DESIGN.md` and roadmap phase 57 (decision-gated, not implemented), with `AGENTS.md` 0.6
allowing exactly one write: a new copy of a user-selected save below its configured output directory, never the
original and never the game's saves folder. Nothing is built there until its parser-gate inputs exist.
BridgeForge provides the read side (`save-*` commands, RC8 behaviour rows) and evidence.

**Capacity overages (owner report, 2026-10-06; unproven).** Carrying more than the fleet's capacity slows the fleet
if the limit is weight based, and raises supplies per day. The calculation is unknown. Rules: the editor never
predicts the effect; it refuses over-capacity quantities by default, and allows them only on explicit opt-in with a
warning. Evidence needed before any rule is written into `RC8_BEHAVIOUR.md`: a controlled rig run that sets cargo,
fuel and crew at, below and above capacity on a throwaway save, then records fleet speed and daily supplies use
for each case. A probe setup (`probe-config --setup`) can apply the quantities in game; this is a candidate
roadmap item for the next live session.

## Groundwork done (2026-10-02)

`bridgeforge save-doctor SAVE --mods DIR [--vanilla-core DIR]` is the diagnose stage's front door: one read-only
pass of a save against a whole mods folder, one verdict per problem class with how recoverable that class usually
is (`bridgeforge/save_doctor.py`, tests in `tests/test_save_doctor.py`):

| Class | What it means | Usual recovery |
|---|---|---|
| MOD_MISSING | a mod enabled in the save is not installed | high: reinstall, or remove its content from a copy |
| CLASS_UNRESOLVED | a class the save serializes is in no installed jar or the game's | high: same remedy |
| NON_FINITE | a NaN or Infinity number in the save | high for the file; fix the mod bug that wrote it |
| TRUNCATED | campaign.xml cut off before its closing tag | low: use an older save |
| VERSION_CHANGED | an installed mod's version differs from the save's | informational |

First run over the rig's 57 saves: 54 clean, 3 real problems (two saves with a since-removed mod enabled, one with
Doc's Needless Economic Expansion Pack industries but the mod no longer enabled). Two false-positive classes were
found and handled on the way: dotted XStream aliases the game registers (`WSR.V`, no such class exists) and the
obfuscator's keyword-named classes and fields (`if.new`, `super.Object`). Salvor's first fix (stage 2) is the
remedy for MOD_MISSING and CLASS_UNRESOLVED on a copy, then a rig load of that copy.

`bridgeforge save-removal-plan SAVE --mods DIR` is the evidence for stage 2's first fix: for every object of a
CLASS_UNRESOLVED class it collects the XStream ids inside it (`z="N"`) and every `ref="N"` to them, and marks it
DROPPABLE (only other doomed objects refer to it) or BLOCKED (listing the outside references). On the rig's
Ward Franks save, all 134 objects of Doc's Needless Economic Expansion Pack (133 industry entries and one lamp
remover script an industry refers to) are droppable; the two saves with only a missing mod in their descriptor hold
no objects of it at all, the simplest case. Matching is by exact class name, never package (`data.scripts` is
shared by many mods).

## Handed to VoidSmith (2026-10-06)

VoidSmith's `docs/SAVE_WORKSHOP_IMPLEMENTATION_PLAN.md` has the module layout, GUI design, build slices and an appendix
of what BridgeForge's rig and save work taught (observed save structure, rig isolation, window-text capture, snapshot
discipline, evidence rows, progress and checkpoint rule). BridgeForge's part is the evidence: roadmap item 57 (the
capacity-overage run) and any `RC8_BEHAVIOUR.md` rows it produces, which VoidSmith's plan cites by id.
