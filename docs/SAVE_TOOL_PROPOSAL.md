# Proposal: save doctor, editor and trainer (separate program, 2026-09-29)

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
4. **Trainer.** In-game toggles (credits, repairs, CR, reveal map, instant travel) through a small helper mod on the
   public API only, the same pattern as BridgeForge's probe and SPW's Tick Marker. First check how much Console
   Commands already covers, and integrate with it rather than copy it.

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

## Decisions for the owner

1. **A working name, and its own repository:** separate, like SPW and Project Go.
2. **Language:** Python reuses BridgeForge's save reader at once; Java fits Project Go's GUI. Suggested: start as
   a Python CLI (diagnose, then fix on a copy) and add a GUI later.
3. **Trainer:** our own helper mod, integration with Console Commands, or both.
4. **Public or local-only:** a diagnose-only first release carries the least risk.
