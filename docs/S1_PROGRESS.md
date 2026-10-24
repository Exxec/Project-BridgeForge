# S1 progress and resume instructions

2026-10-24. Branch `feat/s1-workspace-contracts`, parent `docs/b6-closeout` (`8736e13a`), worktree `C:/Users/exxec/Documents/bf-wt/s1-workspace-contracts`. Main and the published B stack are preserved. Helpers/logs belong in BridgeForge, not SpriteForge.

## Implemented

S1.1 compatibility/policy map: existing entry points and their different acceptance/side-effect semantics are source-reviewed in S1_CONTRACT_MAP.md. The initial qualification profile is a design, not active policy.

S1.2 initial library boundary: frozen `bridgeforge.case_workspace.WorkspaceView` returned by `open_workspace_view(Path(...), original_relative=...)`. It opens manifest-v1 and convention/intake-v1 layouts, references rather than relocates originals, identifies optional capabilities, and refuses malformed/ambiguous/unsafe paths. Selected intake roots come from supported records; nested legacy originals require explicit selection. Readability does not certify hashes, source/jar authority or acceptance; provenance is UNVERIFIED.

16 synthetic acceptance/refusal tests cover the existing workspace and intake APIs, unchanged trees, optional capabilities, explicit source selection, unsupported schemas/JSON, mixed dialects, overlap, traversal/drives/UNC and real junction/symlink boundaries. No private mod/game/save fixture is committed. No existing CLI, caller behavior, policy, dependency or public import changes.

## Validation

Focused adapter/resource/compatibility checks: 20 tests PASS; Ruff PASS.

- Full guarded suite: **2635 tests, OK (12 unchanged skips), 265.442s**; hermeticity PASS.
- Branch coverage: **83.1451218%**, up from B6/B5's 83.1122629%; adapter 98.56% (102/103 statements, 35/36 branches).
- Existing CLI golden unchanged; generated docs, gates lint (zero contradictions), whitespace and Ruff PASS.
- Wheel adds only `bridgeforge/case_workspace.py`; every existing runtime and non-code payload byte matches the validated B3 save wheel. Installed-module smoke resolves from the isolated environment.
- Installed-wheel Project Salvor suite: **208 tests, 4 unchanged skips, PASS**.
- Source inventory now has 335 Python files; nested source audits still pass. Existing APIs/commands and safety baselines are unchanged.

Raw suite/coverage/build/consumer logs and `s1-result.json` remain ignored in this worktree's `bridgeforge-state/`. No live test or real pilot was performed.

## Resume next

1. Read S_SERIES_IMPLEMENTATION_PLAN.md and S1_CONTRACT_MAP.md. Inspect current Git state and this evidence before editing.
2. Continue S1.4: implement explicit qualification obligations and independently verified evidence adapters over the S1.3 store. Read S1_CASE_RECORDS.md first; generic recorded PASS receipts must not manufacture qualification.
3. Review exact supported operator entry points/profile before S1.4 enforcement; preserve legacy caller distinctions and missing/unknown evidence.
4. Add interruption/stale-input/refusal tests before mutation/finalization integration. Candidate freezing must revalidate payload paths and concurrent changes; this read-only view checks selected boundaries only.
5. Select real P1-P6 pilots, permissions and rig/reviewer capacity with the owner before operational acceptance. Save-changing cases retain higher-capability/person routing. New-game proof cannot become save-upgrade proof.

S1 is IN_PROGRESS. S1.3 records are IMPLEMENTED OFFLINE and validated (evidence below); S1.4-S1.6 are NOT_IMPLEMENTED; S2-S4 are PLANNED. The B-series review/merge gates remain independent. This slice is local-only; no push, PR creation, main merge, archive or release is authorized by this checkpoint. LIVE TEST NOT PERFORMED.

## Try the library boundary

```python
from pathlib import Path
from bridgeforge.case_workspace import open_workspace_view

view = open_workspace_view(Path("path/to/workspace"))
# For a legacy nested original without an intake selection record:
# view = open_workspace_view(Path("path/to/workspace"), original_relative="ModName")
print(view.layout, view.original, view.working, view.unavailable, view.provenance)
```

This is a library slice; no `case` CLI command has been added or implied.


## Active S1-S4 goal (owner instruction, 2026-10-24)

"set goal for all S series, if need be run automated live test."

The active goal now covers implementation and validation of all S1-S4 in dependency order, not only S1. Automated live testing is authorized where required, using the dedicated isolated rig with its ownership, staged-input/run-manifest and existing policy checks. Inspect current rig/process ownership before staging; serialize GUI/live resources. Preserve originals, primary saves and prior archives. Ordinary implementation/verification may continue without per-slice confirmation; gameplay/save-content decisions, licence/publication, PR creation, main merges, second-operator evidence and owner support/acceptance commitments remain distinct gates. A synthetic/automated test does not impersonate an independent human operator.

Next: S1.3's content-bound candidate/receipt spine, followed by durable case records and qualification adapters. Reuse `copy_drift._collect`/`run_manifest.FILESET_ALGORITHM` for the shipped set only after validating physical payload boundaries. Retain scan-registry's broader analysis-input identity separately; generated reports must not invalidate shipped payload identity. Bind receipts to candidate AND explicit dependency/core/tool/rule/policy context; missing context/provenance cannot become acceptance. Keep decisions and evidence outside frozen payloads and test stale inputs, same-version drift, tampering, unsupported schemas, interruptions and retries before wiring mutations.

## S1.3 implementation checkpoint, 2026-10-24

Content-bound candidates and generic observation receipts plus atomic append-only `CaseStore` are implemented. [Contract and limits](S1_CASE_RECORDS.md) describe schema, exact payload/context binding, provenance and recovery. The shipped digest matches the existing run-manifest algorithm; broader analysis and generated-report exclusions retain their distinct semantics. Persisted input locations support revalidation without chat. No existing CLI, acceptance gate or mutation flow changed.

25 new identity/store tests pass; 47 focused identity/workspace/safety/compatibility/resource tests pass. Full guarded suite: **2660 tests, OK (12 unchanged skips), 268.643s**, hermeticity PASS. Branch coverage **83.1940548%** (previous slice 83.1451218%); case identity 85.75%, store 94.74%. Wheel adds only `case_identity.py` and `case_store.py`; all prior package bytes are identical. Installed-wheel import smoke and Salvor **208 tests/4 skips PASS**. Ruff, docs-index, gates lint and whitespace checks PASS. Raw evidence is ignored under `bridgeforge-state/s13-*`. No generic recorded receipt is qualified evidence yet. S1 remains IN_PROGRESS; next is S1.4's explicit profile and evidence adapters, not broad auto-acceptance.

### Next action: S1.4

Implement a shared, explicit obligation evaluator plus caller-specific evidence adapters. Start with a read-only local-new-game qualification view; do not mutate archive/release/accept callers until their compatibility obligations are proven. Required observations must include source authority/review, candidate/package, static, applicable compile, dependency/API, and bound applicable live scenarios. Missing/unsupported/legacy observations stay INCOMPLETE/UNKNOWN; recorded PASS labels alone never satisfy obligations. Re-evaluate candidate/context/artifact identity on every qualification, and retain separate per-dimension results. In particular, reuse `run_manifest.evaluate_run` plus the existing log/probe refusal checks; require the specific candidate/member and scenario scope, not an unrelated passing member or a clean startup log.
