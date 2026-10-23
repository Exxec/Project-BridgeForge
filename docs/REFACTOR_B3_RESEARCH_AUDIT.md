# B3 research-package evidence

Checkpoint: 2026-10-22; parent main `05bb602c` (B2 merge). Pending owner review and merge.

Moved 14 `research_*` modules and `cmd_research.py` into `bridgeforge/research/` with `git mv`.
Leaf filenames remain unchanged so the existing test-selection mapping keeps working. The command registration now uses
`research.cmd_research`; all CLI names/help/output remain unchanged. There are no research consumers in the sister projects
and no compatibility shims in this step. Python consumer/import audits cover Salvor, VoidSmith and SPW; Project Go's tracked
Python/Java sources also have no research imports. Its graphify executable was unavailable during this read-only import audit.

All moved module ASTs compare equal after excluding imports. No module-relative resource paths occur in this family.
The new `tests/test_refactor_imports.py` guard rejects internal imports via retired module paths and future consumer shims;
`tests/refactor_module_moves.json` records the current mappings and initially empty shim set. Subsequent B3 steps extend it.

## Before/after evidence

| Check | Before | After |
|---|---:|---:|
| Full suite via `bridgeforge.test_guard` | 2,610 | 2,611 |
| Skips | 12 | 12 |
| Branch coverage | 83.1088957% | 83.1088957% |
| Test wall time | 302.569 s | 287.250 s |
| Recursive source inventory | 313 | 314 |
| CLI commands | 267 | 267 |
| Hermeticity | PASS | PASS |

The only new test is the import guard. All 56 focused research tests and 22 source/CLI/check-index/safe-write contract checks
pass. Ruff passes; generated COMMANDS/CHECKS files are unchanged after `docs-index`. CLI golden SHA-256 remains
`b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.
`merge_train.test_modules_for` selects the same eight modules for old/new paths. Local hooks are retained and not skipped.

The wheel removes the 15 flat module paths and adds their 15 package paths plus `research/__init__.py`.
The only other changed wheel member is `cli_commands.py`'s required module key (apart from generated metadata).
All data payload bytes and other package members match. Salvor's full suite against the installed final wheel passes:
208 tests, 4 existing skips. Its validation environment lives outside setuptools' discovery tree.

The final full run collects per-test durations using unittest's existing `--durations 0` option for B5's later measured
fast/slow split. These wall-time receipts are not a performance-improvement claim.

## Review and stack

See [REFACTOR_STACK.md](REFACTOR_STACK.md) for the owner's 2026-10-22 authorization to continue B-series work as stacked PRs
before tomorrow's merges. This first family targets main; following families target their preceding branch. No force-push,
agent merge, CLI behavior change, dependency change, baseline relaxation or evidence-gate promotion is included.
Source moves make stored scans stale; refresh with `finding-stats --rescan-stale` after the desired stack is merged.
LIVE TEST NOT PERFORMED. Item 83 and later phases remain open.
