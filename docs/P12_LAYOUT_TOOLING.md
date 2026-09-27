# P12A: intake and declared-evidence board

Run commands from the checkout root, or pass `--repo-root <directory>` explicitly.
These tools do not promote builds, run Starsector, approve migration plans, repair
findings, or move layout strays.

## Intake

```powershell
python -m bridgeforge intake C:\downloads\OldMod.zip --name OldMod --archaeology
```

Creates only a fresh `In operation/OldMod` folder. Without `--name`, a portable
folder name is derived from the parsed metadata id; metadata identifiers are never
edited. Multi-root ZIPs require an exact preflight candidate via `--selected-root`.

The layout is `original/archive/<download.zip>`, `original/extracted/<full tree>`,
`working/<selected-root contents>`, plus `reports`, `builds`, and `scratch`.
Archive SHA-256 and extracted/selected tree hashes are recorded in `reports/intake.json`.
Tree hashes inventory file bytes and paths, not empty-directory metadata or vendor
authenticity. Empty directories are retained during extraction. Archive and extracted
bytes are checked before/after analysis. Reports are relocated to published paths;
temporary staging paths must not remain in provenance.

Preflight rejects traversal, symlinks, reserved/invalid portable path components,
case-insensitive duplicates, file/ancestor collisions, and configured size/count
limits. This is conservative portable-path validation, not an exhaustive filesystem
or malicious-archive sandbox. The original ZIP remains untouched on failure.

Analysis runs in a fresh `_intake-*` staging directory before publication. Folder
reservation is exclusive, including existing empty/case-colliding folders. Controlled
publication failure rolls back this attempt's moves; no existing folder is removed.
The completion marker is published last. An abrupt process/power loss can leave a
new incomplete attempt or staging tree: it is never overwritten by a later intake,
and the board does not treat an incomplete intake as approved work.

The read-only dossier builder is serialized only inside this owned fresh report
tree; the generic dossier command's In operation/Done write prohibition is unchanged.

`ASSESSMENT_REQUIRED` is not a revival completion status. Complete
`reports/REVIVAL_PLAN.md`, classifications, authoritative complexity score and routing
before making any mod-source changes. Scan/archaeology success is not compile,
runtime, save compatibility or release assurance.

## Board evidence

```powershell
python -m bridgeforge board --json
python -m bridgeforge board --write
```

Default output is read-only and deterministic (no generated timestamp).
`--write` updates only `In operation/STATUS.generated.json` and `.md`, never manual
`STATUS.md`, originals, working copies or completed builds. Linked/non-file output
targets are refused. The two generated files are not a transactional pair.

Each row includes area, metadata id, current build tag, stage, last declared test,
open-risk count, warnings and the exact paths used as evidence. Recognized named
evidence is preferred under `<Mod>/reports`, with per-file fallback to legacy
`<working-or-release>/reports`. Original/build/scratch/workspace copies are never
used as active working copies. Linked evidence paths are not followed.

- `REVIVAL_REPORT.md`: one recognized standalone completion status at the end;
  stage is explicitly `REPORT_DECLARED_*`, not independently verified readiness.
- `REVIVAL_PLAN.md`: presence only, not verified approval or complexity routing.
- `discovery/risks.json` or `risks.json`: an object containing a `risks` list with
  string `status` fields. Every record other than `CLOSED` is conservatively counted
  as open. Missing/malformed evidence means unknown, not zero risks.
- `last-test.json`: a declared object with nonempty string `test_id`, `status`, and
  `build` (e.g. `{"test_id":"BOOT-1","status":"PASS","build":"r2"}`). Other
  fields may retain timestamp/log/kind information. A build mismatch warns; PASS
  does not imply gameplay was tested. Existing free-form logs are not guessed into
  this schema. No producer automatically rewrites the declared evidence yet.
- `intake.json` plus matching root `intake-complete.json`: completed assessment
  staging, not permission to edit. A later plan/report can advance the declared stage.

Multiple release folders under `Done/<Mod>` get separate rows. Folder-level reports
are explicitly warned as not independently bound to each release. The board does
not infer completion from directory placement, file times, scanner counts, or an
old test passing on another build.

## Layout check

`rig-doctor` adds a read-only `project_layout` check. It warns about files/unlinked
legacy folders at the operation root, missing convention working roots, linked
working roots and explicitly supplied working paths outside
`In operation/<Mod>/working` or `Done/<Mod>/<release>`.
Known root entrypoint/generated files, SWEEP Markdown and reserved `_` directories
are ignored. No auto-move/delete or exhaustive filesystem/reference audit is implied.

Promotion, Vacuum's safe move and v0.2.0 release hygiene remain the next P12 tranche.

## Dependency evidence on the board (2026-09-25)

`board` also reads recorded dependency evidence, never scanning for it: each workspace's
`reports/dependencies.json` (from `dependency-substitutes --write`, or `dependency-graph --write`)
fills a Dependencies column, and `In operation/DEPENDENCY_GRAPH.json` (from `dependency-graph --write`)
adds a "Revival order" section. Both show the date they were recorded; a mod rescanned since its
dependencies were recorded gets an evidence warning.
