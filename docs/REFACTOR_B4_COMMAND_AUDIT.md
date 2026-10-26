# B4 command-reference audit

2026-10-23. Report only, based on B3 tip `6a843117`. No commands, aliases or deprecations changed.

The live parser exposes **267 command paths**, including **185 top-level names**. The count agrees with the plan and this inventory exactly matches the current CLI golden.

Scanned 2087 text files across BridgeForge and five sibling repositories, plus local BridgeForge `tools/*.ps1` scripts. Full file/line references and scope revisions are in [the companion inventory](REFACTOR_B4_COMMAND_REFERENCES.json). Dirty tracked working-copy contents are included; revision IDs identify checkout bases, not clean snapshots. No queue, game, save, generated state, archived assets, ignored work directories or remote repositories were scanned.

## Method and limits

Each row matches a full command path at word boundaries, including quoted argv lists and compact two-token alternatives such as `run-manifest prepare|release|check`. Counts are matching source lines, not executions. A group reference does not prove use of each child; a child reference also counts for its parent. Plain words such as `apply` and `inspect` can be prose or unrelated symbols: REFERENCED means a lexical hit, not confirmed operational use. Wrapped or dynamically assembled invocations can be missed. No runtime telemetry was collected.

Generated command/check indexes and the CLI golden are separated and cannot alone prevent candidacy. Own tests are conservatively identified by exact/prefixed test filename against the top-level name, final subcommand or parser module leaf. Shared tests remain in the other-tests column; filename ownership is a heuristic, not proof of independence. The owning parser module and central registry are excluded because definitions do not establish consumers. Other BridgeForge implementation modules are shown separately as internal lexical references; these can also be symbols or documentation rather than calls. Sibling source, docs, tests and workflow references are included. Historical docs remain references, not proof of current operation.

A REVIEW_CANDIDATE has no observed reference outside its own tests/generated inventory in these scopes. Absence is bounded evidence only; the owner must verify consumers and select candidates. No deletion or deprecation is authorized by this audit.

## Findings

**2 review candidates:** `atlas diff`, `mod-changelog seed`

Counts dominated by generated material or common-word hits warrant manual inspection in the companion inventory before any owner decision.

## Complete inventory

D = docs/other; W = workflows; G = gates; T = other tests; O = own tests; X = sibling repos; R = rig/scripts; I = internal modules; A = generated inventory.

| Command | Parser module | D | W | G | T | O | X | R | I | A | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `accept` | `rig.cmd_rig` | 43 | 0 | 1 | 38 | 0 | 62 | 0 | 64 | 14 | REFERENCED |
| `agent-diff-check` | `agent_diff_check` | 9 | 0 | 0 | 0 | 3 | 4 | 0 | 0 | 3 | REFERENCED |
| `api` | `api_how` | 326 | 0 | 0 | 268 | 38 | 1034 | 0 | 171 | 19 | REFERENCED |
| `api how` | `api_how` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 5 | REFERENCED |
| `api-diff` | `cmd_analysis` | 13 | 0 | 0 | 0 | 4 | 0 | 0 | 14 | 6 | REFERENCED |
| `apply` | `cmd_workspace` | 90 | 0 | 0 | 74 | 2 | 181 | 0 | 179 | 35 | REFERENCED |
| `archaeology` | `cmd_behavior` | 41 | 0 | 0 | 14 | 0 | 0 | 0 | 34 | 10 | REFERENCED |
| `archive` | `cmd_archive` | 257 | 1 | 3 | 321 | 25 | 574 | 40 | 541 | 40 | REFERENCED |
| `archive-preflight` | `cmd_archive` | 8 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `archive-stage` | `cmd_archive` | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas` | `atlas.atlas_report` | 53 | 0 | 0 | 43 | 140 | 1 | 0 | 66 | 68 | REFERENCED |
| `atlas api-usage` | `atlas.atlas_report` | 3 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas build` | `atlas.atlas_report` | 6 | 0 | 0 | 1 | 2 | 0 | 0 | 5 | 9 | REFERENCED |
| `atlas diff` | `atlas.atlas_report` | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 4 | REVIEW_CANDIDATE |
| `atlas exemplars` | `atlas.atlas_report` | 3 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas forecast` | `atlas.atlas_report` | 8 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 3 | REFERENCED |
| `atlas id` | `atlas.atlas_report` | 3 | 0 | 0 | 0 | 2 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas libraries` | `atlas.atlas_report` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas migrations` | `atlas.atlas_report` | 7 | 0 | 0 | 1 | 2 | 0 | 0 | 6 | 5 | REFERENCED |
| `atlas outcome` | `atlas.atlas_report` | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `atlas precision` | `atlas.atlas_report` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas runtime` | `atlas.atlas_report` | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas save-risk` | `atlas.atlas_report` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `atlas show` | `atlas.atlas_report` | 3 | 0 | 0 | 0 | 4 | 0 | 0 | 1 | 3 | REFERENCED |
| `atlas sweep` | `atlas.atlas_report` | 4 | 0 | 0 | 0 | 2 | 0 | 0 | 2 | 3 | REFERENCED |
| `audit-explain` | `cmd_archive` | 15 | 0 | 2 | 1 | 0 | 0 | 0 | 5 | 5 | REFERENCED |
| `audit-shipped` | `cmd_archive` | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `auto-open` | `auto_open` | 9 | 0 | 2 | 0 | 2 | 0 | 0 | 0 | 3 | REFERENCED |
| `baseline-accept` | `baseline_audit` | 7 | 0 | 4 | 0 | 2 | 0 | 0 | 2 | 3 | REFERENCED |
| `baseline-accept-finding` | `baseline_accept_finding` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `baseline-audit` | `baseline_audit` | 4 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `baseline-stats` | `scan.cmd_scan` | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `behavior-decide` | `cmd_behavior` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `behavior-diff` | `cmd_behavior` | 18 | 0 | 0 | 4 | 0 | 0 | 0 | 6 | 4 | REFERENCED |
| `behavior-map` | `cmd_behavior` | 9 | 0 | 0 | 1 | 0 | 0 | 0 | 5 | 3 | REFERENCED |
| `board` | `cmd_archive` | 54 | 0 | 0 | 19 | 0 | 3 | 0 | 24 | 7 | REFERENCED |
| `boot-test` | `rig.cmd_rig` | 34 | 0 | 0 | 3 | 3 | 0 | 6 | 4 | 3 | REFERENCED |
| `bootstrap` | `rig.cmd_rig` | 2 | 0 | 0 | 1 | 1 | 12 | 0 | 1 | 3 | REFERENCED |
| `build-input-manifest` | `scan.cmd_scan` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `build-plan` | `cmd_workspace` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `build-probe-mod` | `rig.cmd_rig` | 11 | 0 | 0 | 0 | 0 | 5 | 0 | 1 | 3 | REFERENCED |
| `build-tag` | `cmd_archive` | 21 | 0 | 0 | 0 | 2 | 0 | 0 | 5 | 3 | REFERENCED |
| `bump-version` | `cmd_archive` | 4 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `bytecode-apply` | `cmd_bytecode` | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `bytecode-diff` | `cmd_bytecode` | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `bytecode-inspect` | `cmd_bytecode` | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 3 | REFERENCED |
| `bytecode-plan` | `cmd_bytecode` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `campaign-identity-check` | `cmd_analysis` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `campaign-identity-inventory` | `cmd_analysis` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `check-impact` | `scan.cmd_scan` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 3 | REFERENCED |
| `close` | `cmd_archive` | 24 | 0 | 0 | 20 | 0 | 178 | 2 | 71 | 7 | REFERENCED |
| `compat-set` | `save.cmd_save` | 13 | 0 | 0 | 3 | 0 | 0 | 2 | 7 | 7 | REFERENCED |
| `compat-set install` | `save.cmd_save` | 9 | 0 | 0 | 2 | 0 | 0 | 2 | 1 | 3 | REFERENCED |
| `compile` | `cmd_workspace` | 100 | 0 | 0 | 11 | 1 | 112 | 3 | 541 | 27 | REFERENCED |
| `compile-check` | `scan.cmd_scan` | 62 | 0 | 0 | 6 | 1 | 0 | 0 | 24 | 6 | REFERENCED |
| `compile-feedback` | `cmd_workspace` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `conflicts` | `cmd_workspace` | 20 | 0 | 0 | 9 | 6 | 35 | 0 | 59 | 9 | REFERENCED |
| `content-diff` | `corpus.cmd_corpus` | 5 | 0 | 0 | 0 | 3 | 0 | 0 | 8 | 8 | REFERENCED |
| `copy-drift` | `cmd_bytecode` | 23 | 0 | 0 | 0 | 4 | 1 | 0 | 5 | 5 | REFERENCED |
| `corpus` | `corpus.corpus_releases` | 112 | 0 | 1 | 22 | 8 | 89 | 0 | 36 | 12 | REFERENCED |
| `corpus releases` | `corpus.corpus_releases` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 3 | 6 | REFERENCED |
| `corpus-audit` | `cmd_analysis` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `corpus-compare` | `cmd_analysis` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `corpus-index` | `corpus.cmd_corpus` | 27 | 0 | 0 | 3 | 6 | 0 | 0 | 9 | 12 | REFERENCED |
| `corpus-index build` | `corpus.cmd_corpus` | 8 | 0 | 0 | 0 | 3 | 0 | 0 | 5 | 3 | REFERENCED |
| `corpus-index search` | `corpus.cmd_corpus` | 4 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 3 | REFERENCED |
| `corpus-recheck` | `corpus.cmd_corpus` | 13 | 0 | 0 | 1 | 3 | 0 | 0 | 6 | 3 | REFERENCED |
| `coverage` | `cmd_behavior` | 103 | 10 | 0 | 7 | 0 | 312 | 1 | 21 | 4 | REFERENCED |
| `cross-mod-analyze` | `cmd_analysis` | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `decision` | `decision` | 125 | 0 | 1 | 31 | 5 | 183 | 0 | 323 | 31 | REFERENCED |
| `decision apply` | `decision` | 6 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 3 | REFERENCED |
| `decision template` | `decision` | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `declare-providers` | `cmd_archive` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `decompile-jar` | `cmd_bytecode` | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `decompiler-review` | `cmd_bytecode` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `dependency-api-check` | `cmd_analysis` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `dependency-graph` | `corpus.cmd_corpus` | 20 | 0 | 0 | 3 | 0 | 1 | 0 | 4 | 3 | REFERENCED |
| `dependency-substitutes` | `corpus.cmd_corpus` | 29 | 0 | 0 | 3 | 0 | 0 | 0 | 17 | 7 | REFERENCED |
| `descriptions` | `cmd_translate` | 36 | 0 | 0 | 30 | 12 | 53 | 0 | 70 | 17 | REFERENCED |
| `descriptions apply` | `cmd_translate` | 6 | 0 | 0 | 2 | 1 | 0 | 0 | 10 | 5 | REFERENCED |
| `descriptions draft` | `cmd_translate` | 5 | 0 | 0 | 0 | 1 | 0 | 0 | 4 | 3 | REFERENCED |
| `descriptions sheet` | `cmd_translate` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `diff-data` | `corpus.cmd_corpus` | 14 | 0 | 0 | 3 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `docs-index` | `scan.cmd_scan` | 25 | 0 | 0 | 3 | 0 | 0 | 0 | 4 | 5 | REFERENCED |
| `doctor` | `cmd_workspace` | 8 | 0 | 0 | 23 | 0 | 22 | 8 | 14 | 3 | REFERENCED |
| `done-audit` | `cmd_archive` | 12 | 0 | 0 | 3 | 1 | 0 | 0 | 4 | 3 | REFERENCED |
| `dossier` | `rig.cmd_rig` | 51 | 0 | 0 | 5 | 4 | 5 | 0 | 23 | 5 | REFERENCED |
| `dropped-features` | `dropped_sweep` | 8 | 0 | 0 | 0 | 5 | 0 | 0 | 13 | 3 | REFERENCED |
| `env-check` | `rig.cmd_rig` | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `escalation` | `cmd_revive` | 97 | 0 | 0 | 12 | 42 | 9 | 0 | 65 | 53 | REFERENCED |
| `escalation accept` | `cmd_revive` | 6 | 0 | 0 | 0 | 1 | 0 | 0 | 4 | 3 | REFERENCED |
| `escalation apply` | `cmd_revive` | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `escalation list` | `cmd_revive` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 7 | REFERENCED |
| `escalation queue` | `cmd_revive` | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 4 | 3 | REFERENCED |
| `escalation review` | `cmd_revive` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 4 | REFERENCED |
| `escalation revoke` | `cmd_revive` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `escalation rule` | `cmd_revive` | 4 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 5 | REFERENCED |
| `escalation run` | `cmd_revive` | 15 | 0 | 0 | 0 | 2 | 0 | 0 | 6 | 3 | REFERENCED |
| `escalation sheet` | `cmd_revive` | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 3 | REFERENCED |
| `escalation show` | `cmd_revive` | 2 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `escalation triage` | `cmd_revive` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `escalation verify` | `cmd_revive` | 4 | 0 | 0 | 0 | 3 | 0 | 0 | 2 | 3 | REFERENCED |
| `expect` | `cmd_behavior` | 34 | 0 | 0 | 28 | 0 | 7 | 1 | 29 | 15 | REFERENCED |
| `expect add` | `cmd_behavior` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `expect approve` | `cmd_behavior` | 6 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `expect check` | `cmd_behavior` | 8 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `expect retire` | `cmd_behavior` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `export-patch` | `cmd_workspace` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `finding-stats` | `corpus.cmd_corpus` | 61 | 0 | 6 | 3 | 7 | 1 | 0 | 11 | 3 | REFERENCED |
| `fix` | `cmd_translate` | 138 | 0 | 0 | 37 | 0 | 142 | 8 | 109 | 10 | REFERENCED |
| `fold` | `cmd_archive` | 24 | 0 | 0 | 1 | 22 | 10 | 0 | 21 | 4 | REFERENCED |
| `gates` | `cmd_gates` | 105 | 0 | 1 | 11 | 17 | 162 | 0 | 110 | 20 | REFERENCED |
| `gates check` | `cmd_gates` | 3 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 3 | REFERENCED |
| `gates lint` | `cmd_gates` | 4 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `gates record` | `cmd_gates` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `hygiene` | `hygiene` | 28 | 0 | 0 | 1 | 30 | 14 | 0 | 1 | 3 | REFERENCED |
| `hypotheses` | `cmd_behavior` | 20 | 0 | 0 | 4 | 3 | 0 | 0 | 29 | 7 | REFERENCED |
| `inspect` | `cmd_workspace` | 20 | 0 | 0 | 2 | 0 | 118 | 0 | 42 | 9 | REFERENCED |
| `intake` | `cmd_archive` | 52 | 0 | 0 | 13 | 1 | 4 | 0 | 22 | 4 | REFERENCED |
| `integration-scenarios` | `scan.cmd_scan` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `jar-audit` | `cmd_bytecode` | 24 | 0 | 0 | 1 | 2 | 0 | 0 | 5 | 5 | REFERENCED |
| `jar-packets` | `cmd_bytecode` | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 6 | 4 | REFERENCED |
| `java-matrix` | `rig.cmd_rig` | 25 | 0 | 0 | 1 | 3 | 0 | 0 | 10 | 21 | REFERENCED |
| `java-matrix describe-log` | `rig.cmd_rig` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `java-matrix discover` | `rig.cmd_rig` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `java-matrix instances` | `rig.cmd_rig` | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `java-matrix mass` | `rig.cmd_rig` | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `java-matrix run` | `rig.cmd_rig` | 5 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 3 | REFERENCED |
| `java-matrix setup` | `rig.cmd_rig` | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 3 | REFERENCED |
| `library-api-inventory` | `cmd_analysis` | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `library-api-match` | `cmd_analysis` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `live-ledger` | `live.live_ledger` | 4 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 3 | REFERENCED |
| `log-triage` | `rig.cmd_rig` | 46 | 0 | 0 | 3 | 3 | 0 | 8 | 6 | 4 | REFERENCED |
| `lookup` | `cmd_behavior` | 35 | 0 | 0 | 12 | 6 | 77 | 0 | 44 | 7 | REFERENCED |
| `merge-train` | `merge_train` | 13 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 3 | REFERENCED |
| `migrate-inventory` | `move_machine` | 4 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 4 | REFERENCED |
| `migrate-verify` | `move_machine` | 4 | 0 | 0 | 4 | 0 | 0 | 0 | 2 | 9 | REFERENCED |
| `migrate-verify check` | `move_machine` | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `migrate-verify write` | `move_machine` | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `migration-pack-candidate` | `cmd_workspace` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `mod-changelog` | `cmd_revive` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 9 | REFERENCED |
| `mod-changelog add` | `cmd_revive` | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `mod-changelog seed` | `cmd_revive` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REVIEW_CANDIDATE |
| `mods-compat` | `scan.cmd_scan` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 3 | REFERENCED |
| `novelty` | `cmd_behavior` | 5 | 0 | 0 | 5 | 0 | 1 | 0 | 3 | 3 | REFERENCED |
| `opportunities` | `cmd_workspace` | 2 | 0 | 0 | 2 | 0 | 3 | 0 | 0 | 4 | REFERENCED |
| `package-jar` | `cmd_workspace` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `packs` | `cmd_workspace` | 22 | 0 | 0 | 1 | 5 | 39 | 0 | 11 | 6 | REFERENCED |
| `patch-jar-class` | `cmd_bytecode` | 16 | 0 | 0 | 2 | 0 | 0 | 0 | 22 | 7 | REFERENCED |
| `patch-jar-sources` | `cmd_bytecode` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 3 | REFERENCED |
| `perf-gate` | `rig.cmd_rig` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `pipeline` | `cmd_workspace` | 26 | 0 | 0 | 1 | 1 | 58 | 0 | 3 | 4 | REFERENCED |
| `plan` | `cmd_workspace` | 185 | 0 | 1 | 262 | 0 | 549 | 1 | 226 | 31 | REFERENCED |
| `port-hullmod-state` | `cmd_bytecode` | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `port-interfaces` | `cmd_bytecode` | 5 | 0 | 0 | 2 | 0 | 0 | 0 | 7 | 3 | REFERENCED |
| `prepare-test` | `rig.cmd_rig` | 18 | 0 | 0 | 0 | 1 | 0 | 0 | 4 | 3 | REFERENCED |
| `preset-check` | `scan.cmd_scan` | 2 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `probe-baseline` | `cmd_behavior` | 11 | 0 | 0 | 2 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `probe-config` | `rig.cmd_rig` | 45 | 0 | 0 | 1 | 2 | 0 | 4 | 14 | 6 | REFERENCED |
| `probe-group` | `probe.cmd_probe_group` | 115 | 0 | 19 | 8 | 2 | 5 | 7 | 44 | 33 | REFERENCED |
| `probe-group bisect` | `probe.cmd_probe_group` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `probe-group duel` | `probe.cmd_probe_group` | 5 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `probe-group install` | `probe.cmd_probe_group` | 18 | 0 | 0 | 1 | 0 | 0 | 0 | 10 | 3 | REFERENCED |
| `probe-group live` | `probe.cmd_probe_group` | 27 | 0 | 12 | 3 | 1 | 3 | 6 | 11 | 3 | REFERENCED |
| `probe-group plan` | `probe.cmd_probe_group` | 16 | 0 | 0 | 0 | 1 | 0 | 1 | 4 | 3 | REFERENCED |
| `probe-group record` | `probe.cmd_probe_group` | 31 | 0 | 5 | 1 | 0 | 1 | 0 | 13 | 3 | REFERENCED |
| `probe-group regress` | `probe.cmd_probe_group` | 8 | 0 | 2 | 0 | 1 | 0 | 0 | 4 | 3 | REFERENCED |
| `probe-group report` | `probe.cmd_probe_group` | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 4 | REFERENCED |
| `probe-group smoke` | `probe.cmd_probe_group` | 5 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 3 | REFERENCED |
| `promote` | `cmd_archive` | 14 | 0 | 0 | 1 | 2 | 6 | 1 | 4 | 3 | REFERENCED |
| `provenance` | `cmd_workspace` | 65 | 0 | 3 | 36 | 0 | 345 | 4 | 48 | 5 | REFERENCED |
| `provider-index` | `corpus.cmd_corpus` | 11 | 0 | 0 | 6 | 0 | 0 | 0 | 4 | 9 | REFERENCED |
| `provider-index build` | `corpus.cmd_corpus` | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 5 | REFERENCED |
| `ready-list` | `cmd_revive` | 6 | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 3 | REFERENCED |
| `rebuild-from-reference` | `corpus.cmd_corpus` | 15 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `rebuild-jar` | `cmd_bytecode` | 15 | 0 | 0 | 1 | 2 | 0 | 0 | 10 | 5 | REFERENCED |
| `release` | `cmd_archive` | 258 | 0 | 0 | 48 | 6 | 350 | 10 | 137 | 36 | REFERENCED |
| `release-behavior-evaluate` | `cmd_behavior` | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `release-evaluate` | `cmd_analysis` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `release-lineage` | `cmd_analysis` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `release-notes` | `release_notes` | 4 | 0 | 0 | 0 | 4 | 0 | 0 | 0 | 3 | REFERENCED |
| `release-policy` | `cmd_archive` | 6 | 0 | 0 | 4 | 0 | 1 | 0 | 2 | 9 | REFERENCED |
| `release-policy set` | `cmd_archive` | 3 | 0 | 0 | 2 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `release-policy show` | `cmd_archive` | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `relink` | `cmd_archive` | 9 | 0 | 0 | 0 | 0 | 0 | 2 | 7 | 3 | REFERENCED |
| `relocate` | `move_machine` | 5 | 0 | 0 | 6 | 0 | 1 | 0 | 0 | 3 | REFERENCED |
| `remove` | `hand_remove` | 28 | 0 | 0 | 15 | 0 | 105 | 0 | 58 | 5 | REFERENCED |
| `renamed-ids` | `cmd_translate` | 3 | 0 | 0 | 0 | 1 | 0 | 0 | 1 | 3 | REFERENCED |
| `research` | `research.cmd_research` | 63 | 0 | 0 | 18 | 54 | 11 | 0 | 19 | 10 | REFERENCED |
| `research diff` | `research.cmd_research` | 3 | 0 | 0 | 0 | 5 | 0 | 0 | 3 | 3 | REFERENCED |
| `research report` | `research.cmd_research` | 15 | 0 | 0 | 0 | 6 | 0 | 0 | 13 | 3 | REFERENCED |
| `restore-from-done` | `cmd_archive` | 3 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `revenantlib-check` | `scan.cmd_scan` | 12 | 0 | 0 | 4 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `review-bundle` | `cmd_workspace` | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `revise` | `revise` | 34 | 0 | 6 | 2 | 10 | 0 | 0 | 6 | 15 | REFERENCED |
| `revise finalize` | `revise` | 18 | 0 | 4 | 1 | 0 | 0 | 0 | 4 | 3 | REFERENCED |
| `revise migration` | `revise` | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `revise prepare` | `revise` | 11 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `revise status` | `revise` | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `revival-audit` | `cmd_analysis` | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 4 | 5 | REFERENCED |
| `revival-report-draft` | `corpus.cmd_corpus` | 8 | 0 | 0 | 1 | 0 | 0 | 0 | 5 | 4 | REFERENCED |
| `revive` | `cmd_revive` | 87 | 0 | 2 | 51 | 41 | 0 | 0 | 116 | 13 | REFERENCED |
| `revive-queue` | `cmd_revive` | 5 | 0 | 0 | 0 | 1 | 0 | 0 | 2 | 3 | REFERENCED |
| `revive-review` | `cmd_revive` | 4 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `rig-create` | `rig.cmd_rig` | 7 | 0 | 0 | 1 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `rig-doctor` | `rig.cmd_rig` | 46 | 0 | 0 | 1 | 1 | 1 | 6 | 3 | 5 | REFERENCED |
| `rig-reset` | `rig.rig_reset` | 5 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `rig-up` | `rig.rig_up` | 15 | 0 | 9 | 0 | 1 | 0 | 0 | 6 | 4 | REFERENCED |
| `risk-register` | `cmd_behavior` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `roadmap-lint` | `roadmap_lint` | 10 | 0 | 0 | 0 | 3 | 0 | 0 | 0 | 3 | REFERENCED |
| `rollback` | `cmd_workspace` | 12 | 0 | 0 | 2 | 0 | 16 | 0 | 4 | 3 | REFERENCED |
| `run-manifest` | `run_manifest` | 11 | 0 | 0 | 1 | 0 | 0 | 0 | 7 | 14 | REFERENCED |
| `run-manifest check` | `run_manifest` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `run-manifest prepare` | `run_manifest` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 4 | REFERENCED |
| `run-manifest release` | `run_manifest` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `runtime-profile` | `cmd_workspace` | 2 | 0 | 0 | 0 | 0 | 1 | 0 | 2 | 3 | REFERENCED |
| `runtime-smoke` | `cmd_workspace` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `save-baseline` | `cmd_behavior` | 9 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 3 | REFERENCED |
| `save-compat` | `save.cmd_save` | 26 | 0 | 0 | 1 | 0 | 2 | 2 | 7 | 3 | REFERENCED |
| `save-content` | `save.cmd_save` | 12 | 0 | 0 | 0 | 1 | 0 | 2 | 0 | 3 | REFERENCED |
| `save-diff` | `save.cmd_save` | 5 | 0 | 0 | 0 | 0 | 0 | 2 | 1 | 3 | REFERENCED |
| `save-doctor` | `save.cmd_save` | 11 | 0 | 0 | 0 | 2 | 5 | 0 | 7 | 3 | REFERENCED |
| `save-fingerprint` | `save.cmd_save` | 1 | 0 | 0 | 0 | 2 | 2 | 0 | 0 | 3 | REFERENCED |
| `save-format-survey` | `save.cmd_save` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `save-growth` | `save.cmd_save` | 5 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 3 | REFERENCED |
| `save-inspect` | `save.cmd_save` | 15 | 0 | 0 | 0 | 0 | 2 | 0 | 8 | 3 | REFERENCED |
| `save-provenance` | `save.cmd_save` | 5 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 3 | REFERENCED |
| `save-removal` | `save.cmd_save` | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `save-removal-plan` | `save.cmd_save` | 3 | 0 | 0 | 0 | 0 | 2 | 0 | 1 | 3 | REFERENCED |
| `save-risk` | `cmd_workspace` | 14 | 0 | 0 | 1 | 0 | 0 | 0 | 6 | 7 | REFERENCED |
| `save-scripts` | `save.cmd_save` | 7 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 3 | REFERENCED |
| `save-snapshot` | `save.cmd_save` | 11 | 0 | 0 | 0 | 0 | 2 | 6 | 3 | 12 | REFERENCED |
| `save-snapshot list` | `save.cmd_save` | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 3 | REFERENCED |
| `save-snapshot restore` | `save.cmd_save` | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 3 | REFERENCED |
| `save-snapshot tag` | `save.cmd_save` | 1 | 0 | 0 | 0 | 0 | 0 | 2 | 0 | 3 | REFERENCED |
| `save-summary` | `save.cmd_save` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `save-upgrade` | `save.save_upgrade` | 15 | 0 | 4 | 0 | 7 | 0 | 0 | 0 | 10 | REFERENCED |
| `save-upgrade evaluate` | `save.save_upgrade` | 7 | 0 | 1 | 0 | 5 | 0 | 0 | 0 | 3 | REFERENCED |
| `save-upgrade plan` | `save.save_upgrade` | 5 | 0 | 1 | 0 | 1 | 0 | 0 | 0 | 3 | REFERENCED |
| `scan` | `scan.cmd_scan` | 179 | 0 | 1 | 183 | 12 | 855 | 0 | 382 | 220 | REFERENCED |
| `scenario` | `save.cmd_save` | 96 | 0 | 28 | 40 | 1 | 357 | 10 | 146 | 21 | REFERENCED |
| `scenario check` | `save.cmd_save` | 4 | 0 | 0 | 0 | 0 | 0 | 4 | 0 | 3 | REFERENCED |
| `scenario list` | `save.cmd_save` | 2 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 3 | REFERENCED |
| `scenario plan` | `save.cmd_save` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `shadow-triage` | `cmd_shadow` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `sibling-assets` | `corpus.cmd_corpus` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | 3 | REFERENCED |
| `snapshot-restore-check` | `snapshot_restore` | 8 | 0 | 2 | 0 | 2 | 0 | 0 | 1 | 3 | REFERENCED |
| `soak-report` | `rig.cmd_rig` | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `source-authority` | `scan.cmd_scan` | 3 | 0 | 0 | 0 | 0 | 3 | 0 | 0 | 3 | REFERENCED |
| `state-snapshot` | `state_snapshot` | 5 | 0 | 0 | 0 | 2 | 0 | 0 | 6 | 6 | REFERENCED |
| `strip-plan` | `cmd_translate` | 18 | 0 | 0 | 1 | 5 | 0 | 0 | 7 | 4 | REFERENCED |
| `substitution-proposals` | `substitution_proposals` | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 5 | 5 | REFERENCED |
| `supersession` | `corpus.cmd_corpus` | 10 | 0 | 0 | 1 | 3 | 0 | 0 | 3 | 3 | REFERENCED |
| `test-plan` | `rig.cmd_rig` | 13 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 5 | REFERENCED |
| `translate-apply` | `cmd_translate` | 7 | 0 | 0 | 0 | 0 | 3 | 0 | 1 | 3 | REFERENCED |
| `translate-batch` | `cmd_translate` | 6 | 0 | 0 | 0 | 2 | 1 | 0 | 6 | 3 | REFERENCED |
| `translate-check` | `cmd_translate` | 7 | 0 | 0 | 1 | 0 | 1 | 0 | 3 | 3 | REFERENCED |
| `translate-export` | `cmd_translate` | 7 | 0 | 0 | 0 | 0 | 2 | 0 | 2 | 3 | REFERENCED |
| `translate-tm` | `cmd_translate` | 2 | 0 | 0 | 0 | 0 | 1 | 0 | 1 | 3 | REFERENCED |
| `validate` | `cmd_workspace` | 25 | 0 | 0 | 3 | 0 | 146 | 0 | 15 | 9 | REFERENCED |
| `value-proposals` | `value_proposals` | 7 | 0 | 0 | 0 | 2 | 0 | 0 | 3 | 3 | REFERENCED |
| `vendor-copy` | `corpus.cmd_corpus` | 23 | 0 | 0 | 10 | 3 | 0 | 0 | 14 | 3 | REFERENCED |
| `vendor-plan` | `corpus.cmd_corpus` | 16 | 0 | 0 | 1 | 3 | 0 | 0 | 9 | 6 | REFERENCED |
| `verify-shadow` | `corpus.cmd_corpus` | 20 | 0 | 0 | 0 | 2 | 0 | 0 | 4 | 3 | REFERENCED |
| `who-locks` | `rig.cmd_rig` | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 3 | REFERENCED |
| `working-tree-layout` | `scan.cmd_scan` | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 | REFERENCED |
| `workspace` | `cmd_workspace` | 138 | 2 | 2 | 668 | 20 | 663 | 8 | 1332 | 125 | REFERENCED |

## Manual candidate review

- `atlas diff`: three direct CLI calls in `tests/test_atlas_calls.py:248-260`; generated docs explain original-versus-working comparison. No independent consumer observed. Retain pending a real workflow review.
- `mod-changelog seed`: `tests/test_mod_changelog.py:21-26` tests the underlying `seed_from_archives` API; no direct CLI consumer observed. This is a one-time archive-history bootstrap, so infrequent use is expected. Retain unless the owner explicitly decides otherwise.
- `run-manifest release` and `run-manifest check` are documented together using compact alternatives in README and the revival guide; they are not candidates after accounting for that syntax.

## Owner decision required

B4 PR 2 starts only after the owner reviews this inventory and selects grouping/deprecation policy. Recommended first pass: retain all existing names, choose noun groups for discoverability, and investigate candidates individually. The plan requires every old name to keep working as an alias; removal requires a separate decision. This report proposes no specific command removal.

This advances approved item 83 architecture/maintenance work; it does not implement proposed strategic S1-S4 capabilities. B4 grouping, B5 and B6 remain open. LIVE TEST NOT PERFORMED.

## Validation

Full regression suite: 2,614 tests, 12 unchanged skips; hermeticity PASS (see ignored `bridgeforge-state/b4-suite.log`). Runtime source, tests, package configuration, payloads and CLI golden are byte-identical to B3 tip `6a843117`; B3 wheel/coverage/consumer evidence is inherited, not newly rerun. Parser inventory matches all 267 golden command paths. Ruff, documentation index, gates lint and diff whitespace checks pass. No performance or live claim is made.

Validation used the B3 research worktree Python environment and a process-local matched JDK. The initial default-Python run passed with 18 skips because optional py7zr/psutil were absent; its log is retained as ridgeforge-state/b4-suite-default-python.log. The matched-environment rerun exercises all six and restores the baseline 12 skips.
