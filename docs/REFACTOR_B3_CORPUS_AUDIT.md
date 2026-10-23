# B3 corpus package evidence

Checkpoint 2026-10-23, parent Atlas `f57803e4`. Local dependent branch; not merged or published.

Six modules (`corpus.py`, `corpus_audit.py`, `corpus_index.py`, `corpus_recheck.py`,
`corpus_releases.py`, `cmd_corpus.py`) moved with `git mv` into `bridgeforge/corpus/`.
Leaf filenames remain unchanged. All six ASTs are identical after removing imports.
CLI registry and internal/test imports use the new paths; no consumer shims are required by the
Python/Java imports audited in Salvor, VoidSmith, SPW and Project Go. No new dependencies.
Safe-write allowances move with their modules, with unchanged counts. Source moves invalidate
stored scan identities; refresh with `finding-stats --rescan-stale` after merging the stack.

| Evidence | Atlas parent | Corpus |
|---|---:|---:|
| Full suite | 2612 | 2612 |
| Skips | 12 | 12 |
| Branch coverage | 83.1088957% | 83.1088957% |
| Hermeticity | PASS | PASS |

Fresh full guarded suite: 2612 tests in 289.298 seconds, OK (skipped=12).
Ruff, diff whitespace and generated-doc checks pass. The focused run passes 65 tests (3 existing
optional-archive skips under the base interpreter); the full suite uses the parent's validation
environment and retains exactly 12 skips. Before/after test selection is identical (9 modules).
CLI golden SHA256 remains `b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.

Wheel comparison removes 6 flat paths and adds 7 package paths (including `__init__.py`).
The only other changed members are `cli_commands.py`, `cmd_analysis.py` and generated RECORD metadata.
Every non-code payload byte is preserved. Salvor imports the installed wheel from the new consumer
environment's site-packages and passes 208 tests with its 4 existing skips.

Raw local evidence: `bridgeforge-state/corpus-tests.log`, `corpus-coverage.json`,
`corpus-build.log` and `corpus-wheel/`. Atlas's parent evidence is in its separate review worktree.
Next B3 family is escalation; probe, rig, live, bytecode, scan and save follow in plan order.
The full B3/B-series remains incomplete. No live, save-upgrade, rights or release gate closes here.
LIVE TEST NOT PERFORMED.
