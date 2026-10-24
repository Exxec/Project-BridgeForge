# B6 architecture and handoff evidence

2026-10-23. Documentation implementation on `docs/b6-closeout`, parent `perf/b5-test-speed` (`577afd3a`).

## Delivered

- Re-audited `ARCHITECTURE.md`: 334 Python files, 11 domain packages, 185 top-level commands and 267 command paths.
- Documented where new domain/shared/CLI modules belong, recursive source inventory and resource-root rules.
- Listed all 11 Salvor facades with implementation targets, required private aliases, pin/import migration and removal conditions.
- Updated `CLAUDE.md` to current scanner, package and test-partition paths.
- Recorded the owner decision to keep the current CLI: no B4 grouping or deprecations.
- Linked the per-family and B5 evidence instead of treating local/static tests as hosted or live qualification.

`ARCHITECTURE.md` is intentionally rewritten from its outdated flat-package map. The diff audit may flag prose removal; no source logic is deleted. The new map is checked against the live recursive inventory and CLI registry, rather than preserving stale tables.

## Completion boundary

B6 documentation implementation does not mark item 83 Done. B0 (#64), B1 (#65), B2 (#72) and research (#73) are merged as verified on GitHub 2026-10-23. Remaining B3 family review/merge, B4 report review, B5 review/merge, B6 publication/hosted CI/review/merge remain open; see the stack ledger for published branches, existing PRs and approval-pending PR creation. Applicable Project Go, VoidSmith and Salvor work remains independently tracked by the approved plan, not closed by these BridgeForge documents.

Remote main was inspected at `6c5473d3` (research and the item-86 roadmap note merged). The local main checkout remains preserved. No upstream integration across the existing eleven-branch stack was performed; ordinary owner-managed integration and parent-order reviews remain pending. No history was rebased, force-pushed or merged into main by this work.

After the intended source-move stack merges, refresh authorized stored scans with `finding-stats --rescan-stale`; source paths participate in scan identities. Do not use this documentation checkpoint to claim a fresh queue, game test, archive or release.

## Validation

B6 changes only architecture/companion/roadmap/evidence/changelog documentation. Runtime source, tests, packaging inputs, CLI golden and bundled payloads remain byte-identical to B5. Full guarded suite: **2,619 tests, OK (12 unchanged skips), 255.397s**; hermeticity PASS. Ruff, generated docs index, gates lint (zero contradictions) and whitespace checks PASS. Runtime/test/package/CLI identity is verified against parent `577afd3a`. All eleven newly pushed B3-B5 tips have green push CI; exact run links are in the stack ledger. B6 hosted CI is recorded separately after publication. B5 coverage (83.1122629%) and B3 installed-wheel consumer evidence are inherited, not rerun package/live qualification.

LIVE TEST NOT PERFORMED.

## Remaining publication step

The twelve concrete branch changes (nine remaining B3 families, B4 report, B5 and B6) are intended for parent-ordered draft PRs. Opening those PRs awaits explicit owner approval; their descriptions are prepared, but no PR number or review is invented. The owner retains all merge decisions.
