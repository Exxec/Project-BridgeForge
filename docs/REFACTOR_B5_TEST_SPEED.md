# B5 unittest partition evidence

2026-10-23. Local branch `perf/b5-test-speed`, parent `docs/b4-command-audit` (`ecbccf3d`). Owner decision: keep the current CLI and skip B4 grouping/deprecations. This is approved item 83 maintenance work, not implementation of proposed S1-S4 capabilities.

## Change

Problem: CI previously waited for the same full test suite in both OS matrix jobs; slow timeout/large-input checks delayed all normal-test feedback. Existing touched-module selection serves local pre-push checks but does not partition CI.

`tests/run_partitioned.py` uses standard-library unittest discovery, preserves case order and partitions exact test IDs using `tests/slow_tests.json`. The marker records every case over two seconds in the measured suite. New cases default to fast; stale markers and duplicate discovered IDs fail. Partitioning does not suppress tests, change assertions, or change normal full-suite discovery. Timing includes each test's setup/teardown; class/module fixture overhead is reflected in suite wall time rather than attributed to individual cases.

The Windows/Ubuntu test matrix now runs separate fast and slow jobs with fail-fast disabled. Both jobs retain `test_guard` hermeticity. Coverage remains a full, unsplit Ubuntu job with the existing coverage floor. The weekly reversed-order suite and touched-module selector are unchanged. No dependency, runtime code, CLI/golden, package payload or coverage threshold changed.

## Measurements

Same local Windows host, Python 3.15 B3 validation environment and process-local matched JDK 25. Hosted CI uses JDK 17; these are local measurements, not observed hosted timings. The profile contains 2,619 cases, 12 skips: B4's 2,614 plus five runner guards. All pass with hermeticity PASS.

Initial full suite without coverage: **269.513s**. Ten individual cases exceeded two seconds, totaling 49.002s. Timings are one observed run, not a benchmark distribution; caches and host scheduling can change them.

Separate partition validation ran under coverage to verify the split preserves coverage. Those wall times include instrumentation and should not be directly compared with the uninstrumented full profile:

| Partition | Tests | Skips | Wall seconds (coverage enabled) |
|---|---:|---:|---:|
| fast | 2609 | 12 | 219.564 |
| slow | 10 | 0 | 52.590 |

The partitions run 2619 cases total with 12 unchanged skips. Their recorded test IDs are disjoint and their union exactly matches the full profile. Combined branch coverage is **83.1122629%**, not below B3's 83.1122629% (comparison uses its unrounded value). Separate partition runs have hermeticity PASS.

The largest cost remains in the fast partition, so this split provides bounded early feedback, not an order-of-magnitude acceleration. The full coverage job can still dominate overall CI completion; no end-to-end CI speedup is claimed.

## Timestamp stability correction

The first combined coverage run was 83.1091960%: exactly one line and one branch below B3, in `copy_drift.py`'s equal-mtime path. An existing test relied on write timing plus a sleep, so coverage varied with filesystem timestamps. `tests/test_copy_drift.py` now uses explicit `os.utime` values and asserts working-newer, deployed-newer and equal-time outcomes. The 14 focused tests passed; the affected fast partition was rerun, and combined coverage restored the exact B3 level. The slow partition had no code/test changes and its successful receipt is retained. Initial logs/reports are preserved under ignored state. No product code changed.

## Slow markers

| Test ID | Profile seconds |
|---|---:|
| `test_fixer_backups.ApplyFixGuardTests.test_large_rules_csv_with_isolated_cp1252_byte_survives_the_fix` | 24.168 |
| `test_new_game_generic.DriveFallbackTests.test_the_generic_flow_runs_after_the_fixed_flow_and_its_stage_is_recorded` | 4.158 |
| `test_revive.EscalationRunTests.test_a_timeout_kills_the_agent_and_its_helpers` | 3.193 |
| `test_launch_watchdog.BootTestWatchdogTests.test_a_running_java_keeps_the_run_waiting_until_its_own_timeout` | 3.150 |
| `test_saved_object_compiled.SavedObjectCompiledTests.test_transient_fleet_only_unsaved_and_game_copies_are_quiet` | 2.643 |
| `test_one_launcher.InteractiveTests.test_interactive_run_waits_for_the_operator_and_records_natural` | 2.531 |
| `test_java_ast.Java_astTests.test_bytecode_inspector_reports_symbolic_references_without_execution` | 2.522 |
| `test_boot_test.BootTestNaturalExitTests.test_game_still_running_when_the_test_stops_it_is_recorded_killed` | 2.260 |
| `test_boot_test.BootTestLaunchTests.test_suspect_fatal_dialog_when_alive_without_marker` | 2.252 |
| `test_fixers_guards.OrbitPeriodGuardTests.test_refuses_side_effects_and_unknown_calls` | 2.125 |

## Reproduce and refresh

Run either partition with the existing guard:

```powershell
python -m bridgeforge.test_guard -- python -m tests.run_partitioned --partition fast --timings bridgeforge-state/fast.json
python -m bridgeforge.test_guard -- python -m tests.run_partitioned --partition slow --timings bridgeforge-state/slow.json
```

If test IDs were renamed or removed, update stale marker IDs before profiling. For a new full profile, omit `--partition` and supply a new ignored timings path. Review every `seconds` entry over `threshold_seconds` (2.0) and update the manifest's exact IDs, observed seconds, date and environment. Keep normal full-suite discovery as the cross-check. New slow cases do not silently disappear: they run in fast until reclassified. No per-test timing threshold is an assertion.

Raw local profile/partition logs, timing JSON and combined coverage remain ignored under `bridgeforge-state/b5-*`. Five new guards verify complete/disjoint selection, new-case placement, stale/duplicate refusal, nested-suite flattening, and preservation of failure/skip/timing results. Ruff, CLI golden, docs index, gates lint and diff checks pass. Wheel/consumer compatibility is inherited from B3 because runtime and package inputs are unchanged; those are not new package/runtime claims.

B5 implementation is locally validated; owner review/merge and hosted CI remain pending. B6 close-out is next and cannot mark item 83 done before its review/merge gates close. LIVE TEST NOT PERFORMED.
