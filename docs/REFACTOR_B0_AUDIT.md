# Refactor B0 source-path audit

Checkpoint: 2026-10-22, baseline `171ae504`; scope is [item 83 B0](REFACTOR_PLAN_2026-10.md).
No package moves or CLI changes occur in this step.

## Discovery changes

| Consumer | Coverage after B0 |
|---|---|
| Safe-I/O ratchet | Every Python source, except the root `safeio.py`; relative keys prevent duplicate-leaf collisions |
| Hull-id audit | Every Python source; relative module/function keys preserve explicit exemptions |
| Checks index | Every Python source and nested test module; relative finding locations and dotted test names |
| Scanner helper index, skin-chain audit, bug-class registry | Legacy scan/scanner files and all Python sources within the future scan package |
| Scan registry identity | Every Python source and JSON rule recursively, keyed by package-relative path |
| Atlas extractor identity | Legacy Atlas prefix files and all Python sources within the future atlas package |
| Merge train / PowerShell pre-push | Nested source paths map to flat or nested matching test modules; caches excluded |
| Probe config contract | Recursive Java source scan, including nested reader classes |

`source_paths.python_sources` excludes `__pycache__` and directories ending in `.py`.
`tests/test_source_paths.py` compares the inventories actually requested by audit consumers with an independent
recursive module inventory before their documented exemptions/family filters. It also tests nested source/rule mutations,
duplicate leaves, Windows separators, dotted command imports, and the real PowerShell selector on Windows.
The guard is in both cross-cutting test lists.

## Search inventory and later move obligations

Searched Python/PowerShell files under `bridgeforge/`, `tests/` and `tools/` for Python globs, directory enumeration,
literal `bridgeforge/` paths and module-name registries. All flat Python-source globs found are replaced.
Additional discoveries beyond the named B0 list: Atlas extractor fingerprint, scanner helper catalogue,
skin-chain audit, bug-class registry, and nested test-name collisions in the checks catalogue.

The remaining literal-path consumers are recorded here so B2/B3 do not assume discovery changes rewrite imports or resources:

- `cli_commands.COMMAND_MODULES` already accepts dotted relative modules, pinned by a new regression test.
  B3 must update its entries without changing registration order.
- `progress.LONG_RUNNING_COMMANDS` contains CLI token tuples, not Python module paths. Its existing `--quiet`
  checks remain applicable unchanged. `merge_train.CROSS_CUTTING_TESTS` and the PowerShell list contain dotted test names.
- `regress_changed.PROBE_HARNESS_PREFIXES` names exact live/probe/rig source paths. B3 must update it when those
  files move, preserving historical-path detection for comparisons against older commits.
- `probe_config.PROFILE_DIR`, `rig_doctor._repo_root`, module-relative data paths and setuptools package-data patterns
  need adjustment in their family move PRs; wheel/resource tests must verify the new locations.
- Safe-I/O baseline keys and hull-audit exemption keys must follow moved relative paths; do not raise allowances.
  Tests with explicit source-file constants/imports must move with their owning family.
- `test_guard.RECORD_ONLY_PREFIXES` intentionally names Git paths for receipt invalidation, not source discovery.
  `agent_diff_check` examines Git diffs recursively already.
- Other literal `bridgeforge/` matches are documentation, diagnostic strings, fixture paths, or tests of changed-path
  behavior in `test_finding_stats`, `test_fold`, `test_merge_train`, `test_probe_log_triage`,
  `test_probe_profile`, `test_regress_changed`, `test_scenarios` and `test_test_guard`; review them with each family.
  `tools/bf-test.ps1`, `fixers.py`, `live_trust.py` and `scan_jarchecks.py` also contain explanatory path references.

## Identity and compatibility

B0 changes scanner identity; later moves change it again because relative paths are hashed.
Stored scans become STALE, never silently current. Refresh using the existing
`finding-stats --rescan-stale --write <report-dir> --vanilla-core <core>` command.
Atlas extractor changes likewise trigger its existing rebuild behavior.

The wheel removes no files. Its sole added member is `bridgeforge/source_paths.py`, the shared B0 inventory helper;
all previous package data remains present. This is an intentional B0 addition, rather than a move or a missing resource.
The CLI golden and generated command/check documentation remain byte-identical to baseline.

## Plan review boundaries

B4 command grouping/deprecation output is an explicit behavior change and needs the decision already required by B4.
B1 must determine that a document is superseded before archiving it.
Use accurate tool attribution for this Codex implementation, rather than the plan's Claude-specific footer.
B1 and later steps remain pending owner review/merge of preceding overlapping PRs.
No game, mod, save, acceptance policy or live-evidence gate was changed. LIVE TEST NOT PERFORMED.

## Validation receipt

Same Python 3.15 environment before/after: 2,590 -> 2,602 tests, 12 skips unchanged, hermeticity PASS.
Suite time: 300.099 -> 303.179 seconds. Coverage with branches enabled: 82.46% -> 83.06%.
Python inventories: 291 -> 292; all audit guards see all 292 before explicit exemptions/family filters.
CLI headings: 267 unchanged. Golden SHA-256:
`b384ee0dc6e73a63dcea9f827c3e0859428a8907141f76f180d426f13664175f`.
Salvor consumer suite against the installed PR wheel: 208 tests, OK (skipped=4).
Ruff and generated-doc freshness checks pass. B0 does not move files; rename similarity is not applicable.
