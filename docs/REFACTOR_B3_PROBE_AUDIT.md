# B3 probe package evidence

Checkpoint: 2026-10-23. Parent `refactor/b3-escalation` (`679f3a69`). Local dependent branch, review/merge pending.

7 modules moved with `git mv`, retaining leaf filenames and touched-test selection.
Internal imports and command registration use implementation paths; no CLI names, flags, behavior or dependencies change.
Consumer compatibility shims added: none required.
Shims name Salvor and remain until its pin/import migration. Safe-write counts move unchanged with their implementations.

| Evidence | Result |
|---|---|
| Full guarded suite | 2613 tests, OK; 12 unchanged skips |
| Suite seconds | 334.921 |
| Branch coverage | 83.10889570552148% (parent 83.10889570552148%) |
| Hermeticity | PASS |
| Installed-wheel Salvor suite | 208 tests, OK; 4 unchanged skips |
| Ruff / generated docs / whitespace | PASS |

CLI golden SHA256 unchanged: `b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.
Wheel comparison preserves every non-code payload byte; moved/added paths and import edits are in the local result JSON.
All previous family evidence remains available in its parent worktree. Raw evidence: `bridgeforge-state/probe-*.log`,
`probe-coverage.json`, `probe-result.json` and `probe-wheel/`.

Changed package paths invalidate stored source fingerprints; refresh with `finding-stats --rescan-stale` after merging.
This is structural implementation evidence, not acceptance or release evidence. No game, mod or save files were edited.
LIVE TEST NOT PERFORMED. B4-B6 and owner review/merge remain independent.
