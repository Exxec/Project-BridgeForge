# P12C Vacuum layout completion — 2026-09-12

This is a layout-only checkpoint, not a completed revival or live-test approval.

| Previous path under In operation | Current path |
|---|---|
| Vacuum-0.98a | Vacuum/working |
| Vacuum (earlier modified attempt) | Vacuum/scratch/Vacuum-earlier-copy |
| Vacuum-rc8-runtime | _rig-vacuum |
| Vacuum-0.98a.PRE-CARRIER-FIX-BUILD.zip | Vacuum/builds/Vacuum-0.98a.PRE-CARRIER-FIX-BUILD.zip |

No untouched `original` was inferred from an earlier modified attempt. No mod
was moved to Done, and no old attempts or archives were discarded.

## Scope and evidence

The existing HIGH-complexity revival plan, source, data, JARs and reports were
preserved byte-identically. Their historical path references remain historical;
use the mapping above for current locations. This does not authorize uncertain
campaign, combat, save-state, or cross-mod changes.

Before/after inventories attest regular file SHA256, directories (including empty
ones), and link targets without traversing junctions:

| Root | Files | Directories | Links |
|---|---:|---:|---:|
| Earlier attempt | 1,592 | 134 | 0 |
| Active working copy | 1,755 | 148 | 0 |
| Isolated rig | 16,422 | 396 | 2 |

The archive hash also matched after moving. All root moves preserved inventoried
bytes and link targets. Two subsequent path corrections were independently checked:

- `_rig-vacuum/run-java25.bat` now uses the existing shared
  `../_rig/jdk-25.0.4.1+1` instead of the stale Flu-X-rc8-runtime path; only that
  path and its comment changed (line-ending normalization is ignored for the
  textual comparison). The pre-edit BAT is retained.
- `_rig-vacuum/mods/Vacuum-0.98a` remains the same mod-facing folder but its
  junction now targets `Vacuum/working`. Only the validated dangling junction
  was removed/recreated; no target directory was deleted.

Final rig inventory matched every other file, directory and link. The core
junction still targets the same dedicated installed core. Libraries, logs,
save files and screenshots were neither edited nor followed into external roots.

Local evidence: `In operation/_attic/P12C-vacuum/` holds before/after/final JSON
inventories, `moves.jsonl`, `checkpoint.json`, `final-verification.json`, and the
pre-edit launcher. One-shot scripts and the scoped plan are beside that folder.
Their outputs are operational evidence, not bundled proprietary game/mod assets.

Evidence SHA256 receipts:

- Retained pre-carrier archive:
  `81741EDBF4C3ED4C24342D6605C3AD2492444F3AA5F7B1B3324D6B9FC4C745D6`
- `final-verification.json`:
  `689C59F6A3E3A1A83FF9266730CB9D7112F187CD40BE0B86D8161BB8139EF1AC`
- `moves.jsonl`:
  `670FB2BB58069177A5835A4F495C7EF73287593AA2352EF2E776F728526843B9`

The first final verifier comparison wrapped PowerShell 5.1's JSON array in an
extra array. An entry-by-entry check showed exactly the two approved differences;
the verifier was corrected and the final inventory recomputed successfully.

## Separate validation results

- SOURCE REVIEW: PASS for layout scope; no mod source changes.
- COMPILE: NOT RUN; no mod source/build change or new compile claim.
- STATIC VALIDATION: PASS for hashes, links, paths and convention discovery.
- PACKAGE VALIDATION: retained archive SHA256 matched; no new mod package made.
- DEPENDENCY CHECK: rig-doctor reports all four enabled ids/dependencies resolve.
- API SIGNATURE CHECK: NOT RUN; no new API compatibility claim.
- SAVE COMPATIBILITY CHECK: NOT RUN; rig save bytes preserved, behavior untested.
- LIVE STARSECTOR TEST: LIVE TEST NOT PERFORMED; LIVE VALIDATION REQUIRED.

Read-only board discovers Vacuum/working with build tag r1. It does not grant a
completion status: the existing report lacks a single final completion status,
and named test/risk evidence remains unknown. These findings were not rewritten
to make promotion pass.

Read-only rig-doctor: isolation, no-running-game, enabled ids/dependencies,
working-copy identity and project layout PASS. Overall WARN: the probe is absent;
real-install save-baseline verification was SKIPPED (not supplied). Process lock
diagnostics found no candidates but hundreds of queries were denied, so this is
not proof of universal lock visibility. No process was killed or game launched.

## Recovery and next work

Tool regression suite: 630 tests passed, one environment-dependent symlink skip;
checkout/probe-release hermeticity PASS. Log: `_attic/P12C-test-suite.log`.

Do not rerun the old 2026-09-11 reorganisation/undo script: this separate move is
not part of that log. Do not rerun the one-shot P12C script on migrated folders.
For recovery, inspect each planned/completed move against actual paths and hashes;
restore launcher/junction from the recorded evidence before reversing root moves
in reverse order. Never recursively delete partial destinations or guess ownership.

P12 layout movement is complete. Remaining: exact-commit v0.2.0 tool tag/GitHub
release publication, and the separately gated probe/live/behavior evidence.
