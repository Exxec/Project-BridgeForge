# Refactor PR stack

Owner authorization, 2026-10-22: "you can continue working B series and i'll merge them all tomorrow."
This authorizes continuing the B-series as a dependency-ordered PR stack before its individual PRs merge, superseding the
plan's per-step merge wait for this stack. The agent does not merge or force-push. Each step is reviewed against its parent,
with full tests/coverage, CLI, path-safety, wheel and consumer evidence. The owner merges in dependency order.

| Step | Branch | PR base | State |
|---|---|---|---|
| B0 | refactor/b0-path-safety | main | Merged #64 |
| B1 | docs/b1-roadmap-archive | main | Merged #65 |
| B2 | refactor/b2-fixers-package | main | Merged #72 |
| B3 research | refactor/b3-research-package | main | Merged #73 (verified 2026-10-23) |
| B3 Atlas | refactor/b3-atlas-reviewed | refactor/b3-research-package | Implemented and locally validated; review/merge pending |
| B3 corpus | refactor/b3-corpus-reviewed | refactor/b3-atlas-reviewed | Implemented and locally validated; review/merge pending |
| B3 escalation | refactor/b3-escalation | refactor/b3-corpus-reviewed | Implemented and locally validated; review/merge pending |
| B3 probe | refactor/b3-probe | refactor/b3-escalation | Implemented and locally validated; review/merge pending |
| B3 rig | refactor/b3-rig | refactor/b3-probe | Implemented and locally validated; review/merge pending |
| B3 live | refactor/b3-live | refactor/b3-rig | Implemented and locally validated; review/merge pending |
| B3 bytecode | refactor/b3-bytecode | refactor/b3-live | Implemented and locally validated; review/merge pending |
| B3 scan | refactor/b3-scan | refactor/b3-bytecode | Implemented and locally validated; review/merge pending |
| B3 save | refactor/b3-save | refactor/b3-scan | Implemented and locally validated; review/merge pending |
| B4 report | docs/b4-command-audit | refactor/b3-save | Report implemented and locally validated; owner review pending |
| B4 grouping | owner declined 2026-10-23 | n/a | Keep current CLI; no grouping or deprecations |
| B5 | perf/b5-test-speed | docs/b4-command-audit | Implemented and locally validated; review/merge pending |
| B6 | docs/b6-closeout | perf/b5-test-speed | Documentation locally validated; push/CI pending |

After a parent merges, retarget its following PR to main and rerun its checks; integrate changed main with ordinary merges,
not rebases/force-pushes. The existing merge-train selector is used to preserve touched-test coverage. Do not execute the
mutating merge-train command unattended here: it merges PRs and rebases/force-pushes, contrary to this owner's merge plan.

B4's report does not authorize command grouping/deprecation decisions. B6 must not mark item 83 done until its required
implementation, review/merge and validation gates have actually closed. Live, rights and release gates remain independent.

B3 implementation complete locally, 2026-10-23: [completion evidence](REFACTOR_B3_COMPLETION.md). All family reviews/merges remain pending.

## Publication checkpoint, 2026-10-23

The following branch tips are pushed, with green push-triggered CI. Draft PR creation is pending explicit owner approval; no new PR numbers are claimed. These branches were not merged or rewritten. Research is already merged as [PR #73](https://github.com/Exxec/Project-BridgeForge/pull/73).

| Branch | Pushed tip | Push CI |
|---|---|---|
| `refactor/b3-atlas-reviewed` | `f57803e4` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026430485) |
| `refactor/b3-corpus-reviewed` | `2e329e3a` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026431782) |
| `refactor/b3-escalation` | `679f3a69` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026431134) |
| `refactor/b3-probe` | `09b8be99` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026431743) |
| `refactor/b3-rig` | `defd9f28` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026430846) |
| `refactor/b3-live` | `4c7184a0` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026431601) |
| `refactor/b3-bytecode` | `f5990c64` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026430242) |
| `refactor/b3-scan` | `57e93d3e` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026431351) |
| `refactor/b3-save` | `6a843117` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026430441) |
| `docs/b4-command-audit` | `ecbccf3d` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026430395) |
| `perf/b5-test-speed` | `577afd3a` | [PASS](https://github.com/Exxec/Project-BridgeForge/actions/runs/40026431192) |
