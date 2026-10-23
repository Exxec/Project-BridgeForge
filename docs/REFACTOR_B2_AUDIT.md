# B2 fixer-package refactor evidence

Checkpoint: 2026-10-22, based on B1 merge `fcf9bf97`. Pending owner review and merge.

The 3,973-line `bridgeforge/fixers.py` is split into family modules under `bridgeforge/fixers/`.
The facade keeps every previously defined name, including private helpers imported by tests and other modules.
All 61 supported findings and 62 dispatch entries (including the retired wing-role handler) retain their order.
The three new `tests/test_fixers_package.py` guards pin these contracts to the pre-split baseline.

## Source and paths

- 24 package modules; largest is `csv_data.py`, 368 lines. Shared models/text helpers are in `common.py`.
- `fixers_data.py`, `fixers_guards.py`, `fixers_presets.py` and `fixers_substitute.py` moved into the package with `git mv`.
  Their call-time facade imports remain lazy. Internal consumers use the new paths.
- Every original function/class body has an identical AST after excluding imports. Constants and registry entries retain
  their original expressions. Only import/path wiring changed; no rewrite, approval, evidence or file-writing behavior changed.
- The safe-write allowance moves from `fixers.py` to `fixers/encoding.py`: the same one call, no increase.
- Generated CHECKS/COMMANDS documentation is unchanged after `docs-index`; current fixer instructions and source links follow
  their moved paths. Historical size measurements and completed-roadmap receipts remain historical.

## Validation

| Evidence | Before | After |
|---|---:|---:|
| Full suite under `bridgeforge.test_guard` | 2,603 | 2,606 |
| Skips | 12 | 12 |
| Branch coverage | 83.05805% | 83.08854% |
| Suite wall time | 278.151 s | 286.402 s |
| CLI commands | 267 | 267 |
| Hermeticity | PASS | PASS |

All 200 focused fixer tests pass. The CLI golden, recursive source guards, safe-write ratchet and ruff pass.
Salvor passes all 208 tests (4 existing skips) against the installed B2 wheel in a separate virtual environment.
The consumer run imports BridgeForge from that environment's site-packages, not the source checkout.

The wheel removes the five old fixer module paths and adds the 24 intended package modules. All other package members
and non-code payload bytes are preserved (apart from generated wheel metadata). Cleaned stale copies in the ignored build
cache before comparison; no scratch source is shipped. CLI golden SHA-256 remains
`b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.

## Review boundaries

The plan's >=90% rename threshold cannot describe the main 3,973-line file split into modules capped at 800 lines.
The four existing family files retain high-similarity renames; the main split is reviewed with the body-level AST comparison
and baseline history rather than claiming an impossible whole-file similarity. All moves were initiated with `git mv`.
Use `git show fcf9bf97:bridgeforge/fixers.py` for the intact pre-split source.

As in every source move, stored scan fingerprints become stale; refresh with `finding-stats --rescan-stale`.
This advances item 83's structural prerequisite without changing strategic policy or closing product/live gates.
LIVE TEST NOT PERFORMED. B3 remains pending B2 review/merge.
