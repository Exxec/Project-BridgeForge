# Bridgeforge bug ledger

## Found by the 2026-10-20 dropped-feature sweep

### FIX-001 — A data-file-not-utf8 fix left a backup and no file: All the Domain Drones shipped without rules.csv

- Impact: shipped content loss. `In operation/All-the-Domain-Drones-New-Drones/working/data/campaign/` holds
  `rules.csv.pre-bf-fix-data-file-not-utf8.bak` (1,452,325 bytes, 2026-09-27, byte-identical to the downloaded original,
  sha256 prefix `99016f258998987e`) and no `rules.csv`. Both archived zips in `Done/All-the-Domain-Drones-New-Drones/`
  (0.6 and 0.6-with-readme) have no `rules.csv` either, so every rule the mod defines (14,297 lines: drone interactions and
  dialogue) is missing from the archived revival. The archive says LIVE_VALIDATED (2026-10-05): a boot and campaign load
  does not notice a missing rules.csv, so the live gate passed.
- Source evidence: the original fails UTF-8 at byte 286,759 on an isolated CP-1252 apostrophe (`It\x92s`), which
  `_fix_data_file_not_utf8` accepts and re-encodes; `apply_fix` backed the file up but the re-encoded file is absent.
  Cause not yet determined (the write, a later step, or a hand step removing it). An audit of all 867
  `.pre-bf-fix-*.bak` files under `In operation/` and `Done/` found this the only backup whose working file is missing
  (six others sit in `scratch/` folders by design).
- Required: find the cause and add a regression test; add a check (scan or `archive-preflight`) that fails when a
  `.pre-bf-fix-*.bak` has no file beside it in `working/`, or when a data file present in `original/` is absent from
  `working/` without a recorded removal; restore ATDD's rules.csv by re-running the fixer on the backup, rescan, live
  run that exercises a drone rule, and `archive --refresh` (moves the old archive aside). Correct the archive status.
- Status: OPEN (ROADMAP-3 item 77.16).

## Implementation issues identified during the 2026-10-18 documentation audit

### DOC-001 — Archive refresh contradicts the preservation contract

- Strategic impact: S1 blocker for safe revision finalization; item 75 R5 also requires prior-archive preservation.
- Source evidence: `bridgeforge/archive.py:archive_mod` calls `_remove_previous_archive` when `refresh=True`;
  that helper calls `safe_rmtree(target, [done_dir])`. The CLI help also describes deletion. This is source evidence,
  not a newly performed destructive/live test. The local agent contract requires moving old archives aside, never deletion.
- Affected paths: `archive --refresh` and `probe-group record --archive --refresh`. Do not use them on known-good archives.
  The separate `move_aside=True` path with `refresh=False` does preserve an old archive; it does not make refresh safe.
- Required implementation: preserve the prior archive before replacement, refuse unsafe/conflicting destinations,
  and recover or clearly report failures without losing the old artifact. Test old bytes surviving success and injected
  failure; qualify against the S1 candidate/acceptance contract. Documentation edits do not close this issue.
- Status: FIXED in the commit "Fix item 75 DOC-001: archive refresh moves the previous archive aside" (`git log --grep DOC-001`).
  `archive_mod(refresh=True)` now validates the target (directly inside Done/, holds an ARCHIVE_NOTE.md), moves it to
  `Done/_replaced-<date>/<Mod>[-N]` with the existing move-aside helper (a holder that is a link or a file is refused),
  and `_remove_previous_archive` is gone. If the new write fails part-way, the partial archive is moved to
  `Done/_failed-<date>/`, the earlier archive is moved back, and the ArchiveError states where each one is. CLI help for
  `archive --refresh` and `probe-group record --refresh` no longer says delete. Tests: `tests/test_archive_preserves.py`
  (old bytes survive success and an injected failure, `-N` suffix on a conflicting destination, unsafe targets refused) and
  `tests/test_probe_group.py::test_record_refresh_replaces_an_earlier_archive_only_when_asked` (group path). Not
  live-tested against a real Done/ archive; the S1 candidate/acceptance qualification still applies.

## Resolved in the historical "1.0 hardening" tranche

The tranche name below is historical, not a claim that package version 1.0 has been released. The current package
identifies as 0.3.0; latest published tool release is the 0.2.0 pre-release (checked 2026-10-18).

| ID | Resolution |
| --- | --- |
| BUG-001 | All workspace and migration targets are resolved beneath their permitted root. |
| BUG-002 | Manifest paths and checkpoint restores are containment-checked. |
| BUG-003 | Immutable checkpoints receive deterministic numeric suffixes on repeat runs. |
| BUG-004 | Apply preflights every approved edit and restores originals if a write fails. |
| BUG-005 | Java UTF-16 offsets are converted before Python source slicing. |
| BUG-006 | Subsequent same-file rules are surfaced in plan conflicts instead of omitted silently. |
| BUG-007 | JAR inspection reads bounded headers and rejects archives over entry/uncompressed-size limits. |
| BUG-008 | Save-risk compares identifier values across the union of original and working files. |
| BUG-009 | Compiler paths are normalized relative to the workspace working copy. |
| BUG-010 | AST analysis and javac compilation use argument/source-list files. |
| BUG-011 | MANUAL and UNKNOWN rules cannot be automatically applied. |
| BUG-012 | Explicit empty pack selections no longer fall back to core rules. |

## Original review evidence

### BUG-001 — Migration paths can escape the working copy

- Severity: Critical
- Area: migration planning and apply
- Evidence: `bridgeforge/migrate.py` joins unvalidated `rule.file` and planned `migration["file"]` to the working-copy path.
- Impact: an absolute path or `../` path from an external rule pack or altered plan can modify files outside the workspace, violating the source-safety contract.
- Required fix: resolve each target and require it to remain beneath the working-copy root before reading, planning, or writing.

### BUG-002 — Workspace manifest paths are not contained

- Severity: Critical
- Area: workspace loading, checkpoints, rollback
- Evidence: `bridgeforge/workspace.py` reads `original_reference` and `working_copy` from the manifest and joins them to the workspace without containment validation.
- Impact: a modified manifest can direct checkpoint or rollback operations outside the workspace.
- Required fix: resolve manifest paths and reject any path outside the workspace before every operation.

### BUG-003 — Planning and pipeline runs are not repeatable

- Severity: High
- Area: migration planning and pipeline orchestration
- Evidence: `build_plan()` always creates checkpoint `01-scanned`; a second run fails because the checkpoint already exists. Applied plans similarly reuse `02-approved-fixes`.
- Impact: retrying a failed or revised pipeline requires manual workspace surgery.
- Required fix: make checkpoints immutable but uniquely numbered, or explicitly reuse an equivalent checkpoint only after hash verification.

### BUG-004 — Migration application can leave a partial state

- Severity: High
- Area: migration apply
- Evidence: `apply_plan()` writes each approved file before validating the rest of the plan; an error later in the loop exits before a manifest/checkpoint is written.
- Impact: the working copy can contain undocumented partial changes.
- Required fix: validate all approved targets first, then apply atomically with a recovery manifest/checkpoint.

### BUG-005 — AST method offsets disagree with Python Unicode indexing

- Severity: Medium
- Area: Java AST transformations
- Evidence: javac source positions are UTF-16 offsets, while Python slices Unicode code points using the reported position.
- Impact: source containing non-BMP characters before a matched invocation may skip or misaddress a migration.
- Required fix: exchange byte offsets or UTF-16-aware offsets, with Unicode regression fixtures.

### BUG-006 — Later migration rules for the same file are silently omitted

- Severity: Medium
- Area: migration planning
- Evidence: `planned_files` suppresses every later rule targeting an already planned file.
- Impact: valid independent migrations disappear from the plan without a finding or explanation.
- Required fix: compose non-overlapping edits deterministically; report conflicts explicitly.

### BUG-007 — JAR scanning can decompress unbounded class entries

- Severity: High
- Area: intake scanner
- Evidence: `bridgeforge/scanner.py` uses `archive.read(name)[:8]`; `ZipFile.read()` decompresses the entire entry before slicing it.
- Impact: a malformed or hostile mod JAR can cause excessive memory/time consumption during a supposedly safe scan.
- Required fix: read only the first eight bytes through a bounded archive stream and enforce archive/file limits.

### BUG-008 — Save-risk analysis misses changed identifier values and deleted files

- Severity: High
- Area: save-risk analysis
- Evidence: `bridgeforge/save_risk.py` compares the set of matched field *names*, not their values, and only iterates files still present in the working copy.
- Impact: changing `factionId` from one value to another, or deleting a file containing persistent IDs, can produce no warning.
- Required fix: compare identifier key/value evidence across the union of original and working files, including removals.

### BUG-009 — Compile feedback cannot normally match javac source paths

- Severity: Medium
- Area: compile feedback
- Evidence: javac diagnostics normally begin with an absolute source path; `compile_feedback()` checks whether the relative planned path ends with that absolute path.
- Impact: known planned migrations are omitted from compiler feedback for real builds.
- Required fix: normalize diagnostic paths relative to the working copy before candidate matching.

### BUG-010 — Large source sets can exceed process command-line limits

- Severity: Medium
- Area: AST analysis and compilation
- Evidence: `java_ast.py` and `build.py` pass every Java source path directly on one subprocess command line.
- Impact: large installed mods can exceed Windows command-line limits, causing analysis/compile failures before Java starts.
- Required fix: use javac argument files or bounded batches, with large synthetic-source regression coverage.

### BUG-011 — MANUAL and UNKNOWN migration rules can be applied

- Severity: High
- Area: migration apply policy
- Evidence: `apply_plan()` accepts any migration whose ID is supplied through `--approve`; it does not reject `MANUAL` or `UNKNOWN` classifications.
- Impact: classifications that are supposed to require human resolution can still alter a working copy through the normal automated apply command.
- Required fix: permit automated apply only for `SAFE` and explicitly approved `REVIEW` rules; reject `MANUAL` and `UNKNOWN` rules regardless of CLI approval.

### BUG-012 — Empty selected packs fall back to the default core rule pack

- Severity: Medium
- Area: pack selection
- Evidence: CLI uses `selected or None`; selecting a scaffolded pack with no rules produces an empty list, which `load_rules(None)` converts into the default V0.2 core rules.
- Impact: `--pack java` or another empty pack can plan an unrelated metadata migration.
- Required fix: distinguish “no pack/rule option supplied” from “an explicitly selected pack set resolved to zero rule files.”
