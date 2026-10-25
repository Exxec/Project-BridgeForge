# S1 real pilot evidence: 2026-10-24

Scope: unchanged, already revived, data-only Faction Relationships Uniquified baseline (`0.1.1+bf.1`), not historical legacy-to-revival repair acceptance. The selected release policy is local-only. Source inputs were copied; primary saves and existing rig instances were preserved. All payloads, screenshots, manifests, logs, inventories and receipts remain ignored under `bridgeforge-state/s1-pilot-20261024-a1/`.

| Attempt | Observed result | Interpretation |
|---|---|---|
| A1 | Startup fatal; probe mission icon missing; LIVE_STUCK | Private staging copied tracked files instead of using the existing release packager. Failure retained. |
| B2 | Actual menu playback; no save-descriptor log; driver remained at main-menu and was stopped | Fresh-rig driver bug: readiness assumed existing saves. Failure retained. |
| C1 | LIVE_DONE: main-menu, campaign, one combat round; 223.736 seconds | Real runtime sequence observed after fixing readiness. Not whole-case acceptance. |
| C1 qualification | REFUSED, solely missing expected `campaign_load` | Current new-game profile v1 incorrectly requires saved-campaign loading. No override, archive or acceptance was performed. |
| C1 exit | KILLED, exit code unknown | Natural exit is not proven. |

C1 manifest ID: `8a091e7a83bdfdf6c557fd5334dad8c57616e1db64af3fda5abb5a0954aa78cf`. Specific candidate/member binding is good; manifest echo matches; completion reports no staged drift. Triage: FATAL 0, MOD-ERROR 0, caught exceptions 0, probe FAIL 0 (30 OK/18 INFO; 3 known-noise log events). Observed milestones: menu, private save, content IDs, combat. Not observed: saved-campaign load or reload-after-save. Probe campaign START/END and combat END were observed. These facts must not be relabeled into save-load/upgrade or feature-effect coverage.

The runtime used a byte-identical private core copy and absolute save/mod/log/screenshot paths under its owned rig. Probe 0.3.2 was built from this worktree in private staging. `install_release(..., core_dir=...)` supplied its ignored vanilla mission icon locally; no vanilla asset is committed. Failed and partial setup directories were retained. The readiness fix uses log triage's actual menu-playback marker while retaining the historical descriptor marker, with healthy/preload-only/unrelated-music controls. Generic fallback tests retain their assertions and use the real zero-timeout readiness predicate.

## Preservation and measurements

Post-C1 byte inventories match the recorded before state: primary core 5532 files, primary saves 93 files, source mod 3 files. Digests and full private inventories are in protected-inputs.json, setup.json and preservation-after-c1.json. The game generated its campaign save only within the private rig. Existing rig instances, prior archives and primary inputs were not moved or overwritten.

Selected measured command times (seconds): setup 54.412; initial open 26.419; initial non-live qualification 27.633; initial prepare 25.540; initial run binding 52.300; C1 prepare 25.223; C1 run binding 51.574; C1 live driver 223.736. Exact argv/exit codes and other command times are in operator-commands*.json and live-driver-c1-timing.json. This is a diagnostic session, not a representative throughput benchmark. Human review time and independent operator resume are NOT_MEASURED/NOT_PERFORMED.

P1 is PARTIAL, with real driver observations and an explicit profile refusal. P2 reviewed loose-source repair, P3 authority refusal, P4 provider refusal, P5 save/persistence routing, P6 changed-after-qualified refusal and the second layout still need their concrete pilot evidence. Earlier synthetic tests remain implementation evidence only.

## Packaging finding and correction

The local build exposed broad setuptools namespace discovery (`bridgeforge*`) absorbing ignored environments. The inspected old local wheel contained 10,495 extra Python files under bridgeforge-state (44,264,678 bytes total); no private core files or pilot-input JSON entries were found. Previous local S-series comparisons checked only the intended bridgeforge subtree and missed this contamination. Those runtime byte comparisons remain useful, but their whole-wheel purity implication is superseded. Do not distribute the prior local S-series wheels. No S-series artifacts were published by this work.

Discovery is now explicit `bridgeforge`/`bridgeforge.*`, namespaces disabled. Existing generated build/egg-info caches were preserved in workspace-local quarantine before rebuilding; stale build caches must not be trusted after changing discovery. A real-backend regression includes a synthetic ignored environment and lookalike package and checks their exclusion plus runtime subpackage/resource inclusion. CI/development install the existing setuptools build backend for that test; runtime dependencies do not change.

Corrected wheel: `bridgeforge-state/s1-menu-fixed-wheel/bridgeforge-0.4.0-py3-none-any.whl`, 1,474,770 bytes, 373 entries, zero foreign namespaces. Complete top-level allowlisting passes; intended runtime/payload bytes match the prior intended subtree except the live driver fix. Installed-wheel Salvor: 208 tests, 4 unchanged skips, PASS. Older published releases were not audited by this local check.

## Combined validation and next action

44 focused driver/triage/fallback tests PASS; real-backend packaging regression PASS. Final guarded suite: 2694 tests, OK (12 unchanged skips), 340.419 seconds; hermeticity PASS. Coverage 83.0928266%, above unchanged 80% threshold; no baseline/skip weakening. Ruff, CLI golden, generated docs, gates lint and whitespace pass. Raw logs/results are ignored under bridgeforge-state/s1-menu-* and s1-pilot-final-*.

S1 acceptance remains open. Next define an explicitly versioned new-game campaign obligation, using completed campaign checks with healthy and refusal controls, while preserving saved-campaign load/reload/upgrade meanings and historical v1 results. Review the existing new-game harness's default expected milestones and update callers/tests together. Do not edit old manifests or convert C1's v1 refusal to PASS. Prepare a fresh evaluator-bound operation and new run ID, then establish an actual qualified positive, local finalization/retry, drift negative, both layouts and the remaining pilot matrix before advancing operational acceptance. Independent owner/support/save gates remain separate throughout S1-S4.
