# B3 rig package evidence

Checkpoint: 2026-10-23. Parent `refactor/b3-probe` (`09b8be99`). Local dependent branch, review/merge pending.

5 modules moved with `git mv`, retaining leaf filenames and touched-test selection.
Internal imports and command registration use implementation paths; no CLI names, flags, behavior or dependencies change.
Consumer compatibility shims added: `bridgeforge.rig_prefs`.
Shims name Salvor and remain until its pin/import migration. Safe-write counts move unchanged with their implementations.

| Evidence | Result |
|---|---|
| Full guarded suite | 2614 tests, OK; 12 unchanged skips |
| Suite seconds | 328.163 |
| Branch coverage | 83.10915476756492% (parent 83.10889570552148%) |
| Hermeticity | PASS |
| Installed-wheel Salvor suite | 208 tests, OK; 4 unchanged skips |
| Ruff / generated docs / whitespace | PASS |

CLI golden SHA256 unchanged: `b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.
Wheel comparison preserves every non-code payload byte; moved/added paths and import edits are in the local result JSON.
All previous family evidence remains available in its parent worktree. Raw evidence: `bridgeforge-state/rig-*.log`,
`rig-coverage.json`, `rig-result.json` and `rig-wheel/`.

Changed package paths invalidate stored source fingerprints; refresh with `finding-stats --rescan-stale` after merging.
This is structural implementation evidence, not acceptance or release evidence. No game, mod or save files were edited.
LIVE TEST NOT PERFORMED. B4-B6 and owner review/merge remain independent.

AST comparison excluding imports checked 5 moved modules. Other differences: bridgeforge.cmd_rig, bridgeforge.rig_doctor.
Non-import differences are limited to module-relative resource locations and implementation-path references; resource guards cover their retained meaning.
History uses a move commit followed by a compatibility-facade commit, so `git log --follow` reaches original sources. Validation covers the final combined snapshot.
