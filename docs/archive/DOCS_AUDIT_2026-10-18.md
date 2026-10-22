# Repository and GitHub documentation audit — 2026-10-18

Strategic alignment: S1's coherent operator workflow and item 75 R7 status reconciliation. This is a documentation
correction pass, not S1 implementation or approval of a new strategic direction. Source baseline: `3342654d`.

## Scope and method

The initial inventory read 99 repository-owned documents/fixtures (18,424 lines): tracked Markdown/RST/text, local
Markdown under `docs/`, the new root architecture draft and local agent contract. The new index and this report extend
that set to 101 documents. Local validation JSON records each file's hash, line count, link candidates and status/CLI
wording candidates at the time scanned: `bridgeforge-state/validation/docs-audit-20261018.json` (local-only).

All inventoried texts received mechanical link/top-level-command/status screening. Current entry points, architecture,
agent guidance, workflow/status documents and flagged claims received focused source/CLI review. This is not an
exhaustive semantic proof of every historical statement or execution of every documented example. Dated receipts,
proposals, synthetic fixtures, mission text and old command names in changelogs are retained as history, not rewritten
to imply current validation. Generated command/check references were checked against the current generators.

Excluded from edits: `Done/` and original/working mod payloads, saves, real game files, third-party trees such as
`everything-claude-code`, unrelated research/probe scripts and other repositories. Existing unrelated edits are preserved.
Local-only sibling-project descriptions are labeled historical where their current implementation was not reverified.

## Source-backed corrections

| Area | Problem | Correction / remaining boundary |
|---|---|---|
| GitHub README | Advertised a tooling pack of ignored/private scripts as included; no clear current-source versus release distinction | Describes the actual package, install steps, current 0.3.0 source and latest published v0.2.0 pre-release; routes readers to current docs |
| Workspace guidance | Convention and manifest workflows appeared interchangeable | Names both layouts and explains which commands expect each; S1 convergence remains proposed |
| Runtime/source claims | README suggested a runtime profile changed `validate` behavior and that interface methods were never fixed automatically | Documents current NOT_CONFIGURED runtime report and the narrow approved interface fixer; no behavior proof inferred |
| Architecture draft | Invented `CommandRegistry` object, incorrect 161-command count and group counts, misleading file layout | Corrected to `COMMAND_MODULES`, dynamic registration/dispatch, 164 top-level commands in 20 modules (153 across 12 grouped modules, 11 across eight others); nested count kept separate |
| Agent policy | The owner's milestone-driven policy was only in conversation | Recorded in committed companion `CLAUDE.md`, with required strategic reads and no direction/implementation approval inferred |
| Current handoff | Stale item 39/45 gates, mandatory-person claim, archive collision advice, Prepatcher absence, causal inference from one variant mismatch | Corrected using root roadmap, CLI and source; dated 2026-10-12 snapshot is explicitly historical |
| Plan status | Atlas/AoTD/migration designs claimed nothing existed | Marked partial supporting implementation and pointed to source/tests; no machine move, universal compatibility or complete design acceptance claimed |
| Migration retention | Unique run and JVM crash logs were classified disposable/regenerable | Preserve unique observation evidence; disposable caches/instances are a separate category. Local-only migration plan updated without forcing it into Git |
| Authority/history | Secondary roadmap and completion log could be read as current backlog/standing push authorization | Point to authoritative root roadmap/current strategy and label historical goal records |
| Release/P10 notes | Old tool-publication and suite-failure notes looked current | Point to 0.2.0 receipt/current CI while keeping original-runtime retry and per-mod live gates distinct |
| Hardening reference | Proposed `bridgeforge ledger` command and ledger location differed from implementation | Corrected to `live-ledger` and current `_live`/`live_runs.jsonl` records; stronger provenance stays R1 work |
| Cross-project proposal | Old Salvor/VoidSmith implementation statements looked current | Added dated-history boundary; no unsupported claim about a sister project's present code or approval |

## Significant open implementation conflict

**DOC-001 is OPEN:** `archive_mod(..., refresh=True)` calls `_remove_previous_archive`, which calls
`safe_rmtree(target, [done_dir])`. The owner contract requires preserving the prior archive, not deleting it.
The CLI help also describes deletion. The separate `move_aside=True`, `refresh=False` path is not proof that refresh
is safe. This conclusion comes from source inspection; no destructive test or actual archive refresh was performed.

Affected commands: standalone `archive --refresh` and group `probe-group record --archive --refresh`. Documentation
now advises against using those modes on known-good archives. `BUGS.md`, S1's next milestone, architecture assessment,
status and item 75 handoff record the blocker and required preservation/failure/retry tests. Application code was not
changed, so the issue is not fixed. Resolving it supports S1 rather than creating a new maintenance-only milestone.

## GitHub checks

Live read-only checks on 2026-10-18 established:

- Repository is public, not archived, default branch `main`, commit `3342654d20e44b34bc7fc3abfe37cecf69872abc`.
  GitHub's README blob `3495f19cec43b470a4c62f8791c362e836434cf0` matched local HEAD's original README blob.
- Latest published release is v0.2.0, marked pre-release; source/tag target is
  `e98522109a00c27dbe73e2bb1cffcd5978427ea8`. No 0.3.0 release was listed. Release notes explicitly limit mod/live/save claims.
- The three GitHub-reported asset SHA-256 digests agree with `RELEASE_0_2_0.md`. This was metadata comparison, not a new
  artifact download/install test. The existing receipt retains its historical installation/byte-verification evidence.
- Release notes aggregate earlier changelog limitations; statements such as an older "cross-mod graphing remains
  unimplemented" line should be read in their release-history context, not as current-main capability statements.
  Tagged source/CLI and the publication receipt identify the actual released scope. No old release note/tag was rewritten.
- Open issues and open PR queries returned none (limits 100 and 50). DOC-001 is recorded locally; no issue/comment was posted.
- [Latest main CI](https://github.com/Exxec/Project-BridgeForge/actions/runs/39093112172) is completed/successful for the
  exact current commit. This does not validate today's uncommitted documentation or a mod's live behavior.
- GitHub Pages is disabled. Wiki is enabled in metadata, but the wiki Git repository returned `Repository not found`;
  no wiki content was retrievable/audited. Repository description is broad but consistent with its purpose; unchanged.

The checks above describe the pre-publication audit snapshot. The owner subsequently authorized committing and
pushing these documentation corrections and proposed strategy on 2026-10-18. Their publication does not approve
strategy implementation or qualify a new runtime release. Source version remains 0.3.0; v0.2.0 pre-release assets
and historical tags remain unchanged. Publication validation is recorded in the commit and its CI run.

## Validation and residual limits

- Initial inventory: zero missing local Markdown link targets; command candidates were triaged as historical/proposed
  names or false positives, except the corrected `ledger` reference. Local link existence alone does not prove a target
  is shipped in Git; the index distinguishes intentionally local-only instructions/templates from publication candidates.
- `python -m bridgeforge docs-index --check`: PASS; generated CHECKS/COMMANDS already match source and were not hand-edited.
- `python -m bridgeforge roadmap-lint`: zero new violations, one pre-existing tolerated item; baseline not enlarged.
- `git diff --check`: PASS. Application Python/Java code, tests, game/mod/save payloads unchanged by this audit.
- Targeted documentation/CLI tests: `python -m unittest tests.test_checks_index tests.test_cli_golden
  tests.test_roadmap_lint` — 10 tests, OK. Five supporting documentation JSON files also parsed successfully.
- The audit itself did not rerun the full Python suite; publication validation is recorded separately in the commit.
  Game behavior, archive replacement, installed package and sibling projects were not rerun/requalified.

Future wording should state whether a claim is implemented, tested offline, observed in a particular run, planned,
or unknown. Preserve dates and evidence rather than replacing historical counts with unsupported current totals.
The next implementation remains S1; DOC-001 and shared case/qualification contracts are blockers within it.
