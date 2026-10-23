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
| B3 research | refactor/b3-research-package | main | Implemented; review/merge pending |
| B3 Atlas | refactor/b3-atlas-reviewed | refactor/b3-research-package | Implemented and locally validated; review/merge pending |
| B3 corpus | refactor/b3-corpus-reviewed | refactor/b3-atlas-reviewed | Implemented and locally validated; review/merge pending |
| B3 escalation | refactor/b3-escalation | refactor/b3-corpus-reviewed | Implemented and locally validated; review/merge pending |
| Remaining B3 families | pending | preceding family branch | probe next; not implemented |
| B4 report | pending | preceding B3 branch | Report only; owner decides candidates/grouping |
| B4 grouping | pending owner decision | pending | Decision gate open |
| B5/B6 | pending | pending | Not complete |

After a parent merges, retarget its following PR to main and rerun its checks; integrate changed main with ordinary merges,
not rebases/force-pushes. The existing merge-train selector is used to preserve touched-test coverage. Do not execute the
mutating merge-train command unattended here: it merges PRs and rebases/force-pushes, contrary to this owner's merge plan.

B4's report does not authorize command grouping/deprecation decisions. B6 must not mark item 83 done until its required
implementation, review/merge and validation gates have actually closed. Live, rights and release gates remain independent.
