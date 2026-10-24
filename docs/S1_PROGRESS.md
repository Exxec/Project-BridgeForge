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
2. Continue S1.3: design versioned case/candidate/receipt persistence, exact selected file set and environment/policy identities; reuse existing scan/run/revise contracts where meanings match. Do not treat WorkspaceView paths as frozen byte identity or mutation authority.
3. Review exact supported operator entry points/profile before S1.4 enforcement; preserve legacy caller distinctions and missing/unknown evidence.
4. Add interruption/stale-input/refusal tests before mutation/finalization integration. Candidate freezing must revalidate payload paths and concurrent changes; this read-only view checks selected boundaries only.
5. Select real P1-P6 pilots, permissions and rig/reviewer capacity with the owner before operational acceptance. Save-changing cases retain higher-capability/person routing. New-game proof cannot become save-upgrade proof.

S1 is IN_PROGRESS. S1.3-S1.6 are NOT_IMPLEMENTED; S2-S4 are PLANNED. The B-series review/merge gates remain independent. This slice is local-only; no push, PR creation, main merge, archive or release is authorized by this checkpoint. LIVE TEST NOT PERFORMED.

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
