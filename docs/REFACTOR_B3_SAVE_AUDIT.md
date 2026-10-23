# B3 save package evidence

Checkpoint: 2026-10-23. Parent `refactor/b3-scan` (`57e93d3e`). Local dependent branch, review/merge pending.

16 modules moved with `git mv`, retaining leaf filenames and touched-test selection.
Internal imports and command registration use implementation paths; no CLI names, flags, behavior or dependencies change.
Consumer compatibility shims added: `bridgeforge.save_compat`, `bridgeforge.save_content_compat`, `bridgeforge.save_cycles`, `bridgeforge.save_doctor`, `bridgeforge.save_fingerprint_offline`, `bridgeforge.save_inspect`, `bridgeforge.save_reader`, `bridgeforge.save_removal_plan`.
Shims name Salvor and remain until its pin/import migration. Safe-write counts move unchanged with their implementations.

| Evidence | Result |
|---|---|
| Full guarded suite | 2614 tests, OK; 12 unchanged skips |
| Suite seconds | 287.584 |
| Branch coverage | 83.11226289236808% (parent 83.10993190601803%) |
| Hermeticity | PASS |
| Installed-wheel Salvor suite | 208 tests, OK; 4 unchanged skips |
| Ruff / generated docs / whitespace | PASS |

CLI golden SHA256 unchanged: `b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.
Wheel comparison preserves every non-code payload byte; moved/added paths and import edits are in the local result JSON.
All previous family evidence remains available in its parent worktree. Raw evidence: `bridgeforge-state/save-*.log`,
`save-coverage.json`, `save-result.json` and `save-wheel/`.

Changed package paths invalidate stored source fingerprints; refresh with `finding-stats --rescan-stale` after merging.
This is structural implementation evidence, not acceptance or release evidence. No game, mod or save files were edited.
LIVE TEST NOT PERFORMED. B4-B6 and owner review/merge remain independent.

AST comparison excluding imports checked 16 moved modules. Other differences: none.
History uses a move commit followed by a compatibility-facade commit, so `git log --follow` reaches original sources. Validation covers the final combined snapshot.

Resumed validation uses matching Temurin java/javac 25.0.4.1, selected for the validation process only. The interrupted log and Java-8/JDK-25 mismatch log are retained under bridgeforge-state; save-java-context.log records the matched tools. No system configuration or product behavior was changed to pass tests.
