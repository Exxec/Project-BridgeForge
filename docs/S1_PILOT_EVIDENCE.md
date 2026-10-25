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


## V2 positive and drift controls: D1/E1

New cases default to rc8-local-new-game/v2: menu, completed ordered campaign probe START/END, content IDs and combat. Historical v1 remains evaluable under its original saved-load requirement; an actual C1 recheck still returned REFUSED before the owned drift control was introduced. Old manifests and qualification labels were not edited. The new-game driver requests campaign_checks because it creates a new campaign; explicit campaign_load/save/reload requirements retain their meanings. The only CLI help change adds the campaign_checks choice to run-manifest prepare.

D1 (`S1-P1-20261024-D1`, convention layout) completed its own run, qualified under v2, archived locally through the public case flow and retried with identical output. After adding S1_DRIFT_CONTROL.txt only to its owned working copy, both qualification and finalization returned REFUSED. The previously qualified archive's full inventory stayed unchanged. Case b's current input state is intentionally stale; the archived qualification is historical evidence, not current acceptance of the changed working copy. Primary core, all 93 primary-save files and the real source mod were byte-identical afterward.

E1 (`S1-P1-20261024-E1`) used a separately copied manifest workspace with custom reference/edit paths, a fresh isolated rig, its own case/candidate/run/manifest and no borrowed D1 observations. It independently completed menu/campaign/combat, qualified, archived locally and retried exactly. Current R1 evidence is ACCEPTABLE: campaign_checks/content_ids/menu/combat/private-save observed, campaign_load/reload_after_save not observed. Process exit remains KILLED; natural exit is not proven. Primary core/saves/source inventories remain unchanged after E1.

These are two layouts of **one unchanged already-revived mod**, not two independent mods or new historical repair approval. P1's supported data-only lane and P6's real owned-copy drift control have been exercised; P2 reviewed loose-Java repair, P3/P4 actual authority/provider refusal coverage, P5 save/persistence routing and independent operator/owner acceptance remain open. No saved-campaign upgrade, feature equivalence, publication permission or support commitment is inferred.

Raw evidence: pilot-result-d1/e1.json, pilot-ids-d1/e1.json, qualification-d1/e1.json, finalize/retry outputs, drift-qualification/finalize-d1.json, archive-inventory-d1/e1.json, pilot-evaluation-e1.json and preservation-after-d1/e1.json beneath the ignored pilot root. Each local archive contains its own CASE_QUALIFICATION.json outside the tested mod. Legacy revival-report annotations are retained as historical metadata; the bound case qualification remains separately identified.

Measured D1 qualification/finalization/retry: 30.352/70.542/45.829 seconds; drift qualification/finalization refusal: 14.107/13.966 seconds. E1 open/prepare/run-bind: 32.224/31.116/64.016 seconds; qualification/finalization/retry: 29.716/69.260/41.929 seconds; live driver 223.902 seconds. This diagnostic timing is not a cohort throughput claim. Human active-review time and independent operator resume remain NOT_MEASURED/NOT_PERFORMED.

V2 validation: 58 focused case/operation/CLI/manifest checks PASS; full guarded suite 2698 tests, OK with 12 unchanged skips, 328.714 seconds, hermeticity PASS. Coverage 83.0964043% with unchanged 80% floor. Corrected wheel complete namespace allowlist PASS; only case_qualification.py, run_manifest.py and live/live_run.py change from the prior clean runtime artifact, and no package paths are added/removed. Installed-wheel Salvor 208 tests/4 skips PASS. No runtime dependencies, safety baselines or skips weakened. Hosted CI was not run for these local commits.


## Additional real-input boundaries: P2-P5, 2026-10-25

These observations extend the matrix; they do not turn an incomplete case into acceptance. Real inputs and private originals were inventoried before/after and remained unchanged. All mutations below were confined to the owned P2 working copy. No additional game was launched and no additional archive was produced.

| Role | Concrete observation | Remaining limit |
|---|---|---|
| P2 | Leon Heavy Industries 0.35: four missing OnHitEffectPlugin parameters repaired under the existing dated standing approval for target-interface-method-missing; exact four-file delta and backups verified; fresh scan no longer reports that finding; repeat computation produces no change | Full 14-script javac compilation still FAILS: 39 errors before, 31 afterward, including unavailable library symbols. Janino PASS covers only six accepted sources after repair. Whole case REFUSED; the standing fixer ruling does not supply the new evaluator's candidate-bound whole-case owner decision. No successful repair qualification claimed. |
| P3 | Unchanged Adjusted Sector mixed JAR/loose-source input: source_authority INCOMPLETE, whole result REFUSED | Requires explicit packaged-byte authority; source-only evidence is insufficient. No fix applied. |
| P4 | Unchanged Antediluvians: dependencies INCOMPLETE because revenantlib was not selected | No provider inferred from an installation, historical cache or first match; no successful qualification. |
| P5 | Existing-save-upgrade scope requested against the real P3 world-generation baseline: target INCOMPLETE, unsupported scope | Routing refusal only. No save was loaded, migrated, saved or reloaded; no persistent-change repair or upgrade acceptance. |

P2 source inventory: 256 files, SHA256 05940321e7cf6a0d6db69313ff0a1229db67ff4d0bb7cfaa94b5c1979233917a. The unchanged standing policy hash is b4be58ef794c4afa966932f65488806cf3531255654e7bbdd683ddd1f29a1cbd, recorded 2026-09-30. The existing revival governor explicitly permits its named non-SAFE fixer with standing approval; this pilot did not invent a new owner decision or broaden that ruling to other findings. Method bodies and all other original paths were untouched. Four .pre-bf-fix backups contain the exact old bytes. Before/after candidate IDs and per-file hashes are retained in the private receipt.

Raw records beneath the existing ignored pilot root: refusal-pilot-results.json; p3/p4/p5-qualification.json; p2-investigation-leon/proposal.json, proposed-interface-repair.diff, before-compile-observation.json, after-compile-observation.json, case-qualification-after.json and repair-continuity-result.json. Private case IDs are d/e/f repeated 32 times for P3/P4/P5 and 2 repeated 32 times for P2. P3/P4/P5 elapsed qualification times: 44.491/52.141/13.622 seconds; P2 after-repair scan/compile worker: 51.574 seconds. These remain diagnostic wall times, not human-review or cohort-performance measurements.

P3/P4 refusal behavior and P5 unsupported-scope routing are now observed on real inputs. P2 has exact repair/compile/review continuity evidence but lacks a passing full compile and candidate-bound case review. Independent maintainer resume and owner acceptance remain outstanding. S1 stays IN_PROGRESS; no S2-S4 completion is inferred. The S2 named cohort and measurement-first ordering proposal is recorded separately in S2_COHORT_PROPOSAL.md and awaits the requested owner choices.
