# BridgeForge repository architecture

Source-audited 2026-10-23 on the B6 stack based on `577afd3a` (B5). This is the implementation map for approved ROADMAP-3 item 83. It describes source layout and contracts, not live-game qualification or completion of proposed S1-S4 capabilities. `CLAUDE.md` is the committed agent companion; local `AGENTS.md` governs operation.

## Package map

The recursive Python inventory contains **334 files**: 186 at package root and 148 inside domain packages, including package initializers. B3 moved 114 modules; 11 root compatibility facades remain. Tests retain their leaf filenames in the flat `tests/` directory.

| Package | Python files | Responsibility |
|---|---:|---|
| `bridgeforge/research/` | 16 | Evidence retrieval, research inputs and research command handlers. |
| `bridgeforge/atlas/` | 18 | Atlas database, extraction, census, matching and reports. |
| `bridgeforge/corpus/` | 7 | Corpus indexing, release inventory and corpus command handlers. |
| `bridgeforge/escalation/` | 8 | Packets, agents, sheets, rules and escalation decisions. |
| `bridgeforge/probe/` | 8 | Probe build/configuration, group planning, installation and reporting. |
| `bridgeforge/rig/` | 6 | Rig setup, preferences, diagnosis, reset and rig command handlers. |
| `bridgeforge/live/` | 6 | Live-run orchestration, log/result handling and the live ledger. |
| `bridgeforge/bytecode/` | 10 | Java/bytecode/JAR analysis, toolchain and helper compilation. |
| `bridgeforge/scan/` | 28 | Scanner orchestration, parsing, registry and check families. |
| `bridgeforge/save/` | 17 | Save inspection, fingerprints, compatibility, upgrade planning and save commands. |
| `bridgeforge/fixers/` | 24 | B2 domain rewrites, common helpers and the public fixer API. |

Root modules hold entry points (`__main__.py`, `cli.py`, `cli_commands.py`), shared models/safety/storage helpers (`models.py`, `safeio.py`, `zipsafe.py`, `source_paths.py`), workspace/archive/translation workflows not moved by B3, and the explicitly retained consumer facades. B3 did not relocate every workflow or invent a new dependency/plugin layer.

## Commands and dispatch

The parser exposes **185 top-level names** and **267 command paths including subcommands**. The owner chose to keep this CLI on 2026-10-23: B4 grouping and deprecations are declined. See [the reference audit](docs/REFACTOR_B4_COMMAND_AUDIT.md) and generated [command/options catalogue](docs/COMMANDS.md).

`cli.py` builds the parser and handles argv/stream setup; `cli_commands.COMMAND_MODULES` imports each owner module and calls its `add_parser`. `dispatch` finds the owner and calls `run_cli`. There is no `CommandRegistry` class. Package moves change registry module paths, not command names, flags, defaults, exit codes or output contracts.

| Parser/handler module | Top-level commands | Count |
|---|---|---:|
| `bridgeforge/atlas/atlas_report.py` | `atlas` | 1 |
| `bridgeforge/api_how.py` | `api` | 1 |
| `bridgeforge/substitution_proposals.py` | `substitution-proposals` | 1 |
| `bridgeforge/baseline_audit.py` | `baseline-audit`, `baseline-accept` | 2 |
| `bridgeforge/baseline_accept_finding.py` | `baseline-accept-finding` | 1 |
| `bridgeforge/decision.py` | `decision` | 1 |
| `bridgeforge/rig/rig_reset.py` | `rig-reset` | 1 |
| `bridgeforge/rig/rig_up.py` | `rig-up` | 1 |
| `bridgeforge/run_manifest.py` | `run-manifest` | 1 |
| `bridgeforge/revise.py` | `revise` | 1 |
| `bridgeforge/live/live_ledger.py` | `live-ledger` | 1 |
| `bridgeforge/roadmap_lint.py` | `roadmap-lint` | 1 |
| `bridgeforge/agent_diff_check.py` | `agent-diff-check` | 1 |
| `bridgeforge/hygiene.py` | `hygiene` | 1 |
| `bridgeforge/auto_open.py` | `auto-open` | 1 |
| `bridgeforge/dropped_sweep.py` | `dropped-features` | 1 |
| `bridgeforge/hand_remove.py` | `remove` | 1 |
| `bridgeforge/move_machine.py` | `migrate-inventory`, `relocate`, `migrate-verify` | 3 |
| `bridgeforge/state_snapshot.py` | `state-snapshot` | 1 |
| `bridgeforge/snapshot_restore.py` | `snapshot-restore-check` | 1 |
| `bridgeforge/save/save_upgrade.py` | `save-upgrade` | 1 |
| `bridgeforge/value_proposals.py` | `value-proposals` | 1 |
| `bridgeforge/cmd_workspace.py` | `workspace`, `plan`, `apply`, `rollback`, `build-plan`, `compile`, `package-jar`, `compile-feedback`, `review-bundle`, `validate`, `save-risk`, `pipeline`, `packs`, `migration-pack-candidate`, `runtime-profile`, `runtime-smoke`, `inspect`, `export-patch`, `opportunities`, `doctor`, `conflicts`, `provenance` | 22 |
| `bridgeforge/scan/cmd_scan.py` | `mods-compat`, `baseline-stats`, `docs-index`, `preset-check`, `scan`, `working-tree-layout`, `source-authority`, `build-input-manifest`, `integration-scenarios`, `compile-check`, `revenantlib-check`, `check-impact` | 12 |
| `bridgeforge/cmd_analysis.py` | `corpus-audit`, `cross-mod-analyze`, `campaign-identity-inventory`, `campaign-identity-check`, `release-lineage`, `library-api-inventory`, `library-api-match`, `dependency-api-check`, `corpus-compare`, `release-evaluate`, `revival-audit`, `api-diff` | 12 |
| `bridgeforge/cmd_bytecode.py` | `decompile-jar`, `port-interfaces`, `patch-jar-sources`, `decompiler-review`, `bytecode-inspect`, `bytecode-plan`, `bytecode-diff`, `bytecode-apply`, `copy-drift`, `jar-audit`, `jar-packets`, `port-hullmod-state`, `patch-jar-class`, `rebuild-jar` | 14 |
| `bridgeforge/cmd_translate.py` | `translate-export`, `translate-apply`, `translate-tm`, `translate-check`, `fix`, `strip-plan`, `descriptions`, `translate-batch`, `renamed-ids` | 9 |
| `bridgeforge/save/cmd_save.py` | `compat-set`, `save-compat`, `save-removal-plan`, `save-doctor`, `save-fingerprint`, `save-format-survey`, `save-content`, `save-diff`, `save-growth`, `save-inspect`, `save-provenance`, `save-removal`, `save-scripts`, `save-summary`, `save-snapshot`, `scenario` | 16 |
| `bridgeforge/rig/cmd_rig.py` | `accept`, `soak-report`, `log-triage`, `prepare-test`, `env-check`, `java-matrix`, `boot-test`, `dossier`, `build-probe-mod`, `probe-config`, `bootstrap`, `rig-create`, `rig-doctor`, `who-locks`, `test-plan`, `perf-gate` | 16 |
| `bridgeforge/probe/cmd_probe_group.py` | `probe-group` | 1 |
| `bridgeforge/cmd_behavior.py` | `lookup`, `novelty`, `behavior-decide`, `archaeology`, `behavior-diff`, `behavior-map`, `coverage`, `expect`, `hypotheses`, `probe-baseline`, `release-behavior-evaluate`, `risk-register`, `save-baseline` | 13 |
| `bridgeforge/corpus/cmd_corpus.py` | `dependency-substitutes`, `provider-index`, `supersession`, `finding-stats`, `dependency-graph`, `corpus-recheck`, `sibling-assets`, `vendor-copy`, `revival-report-draft`, `diff-data`, `rebuild-from-reference`, `corpus-index`, `content-diff`, `verify-shadow`, `vendor-plan` | 15 |
| `bridgeforge/corpus/corpus_releases.py` | `corpus` | 1 |
| `bridgeforge/cmd_archive.py` | `audit-shipped`, `audit-explain`, `archive`, `relink`, `bump-version`, `declare-providers`, `close`, `restore-from-done`, `promote`, `board`, `intake`, `archive-preflight`, `archive-stage`, `build-tag`, `release`, `release-policy`, `done-audit`, `fold` | 18 |
| `bridgeforge/release_notes.py` | `release-notes` | 1 |
| `bridgeforge/merge_train.py` | `merge-train` | 1 |
| `bridgeforge/cmd_shadow.py` | `shadow-triage` | 1 |
| `bridgeforge/cmd_gates.py` | `gates` | 1 |
| `bridgeforge/research/cmd_research.py` | `research` | 1 |
| `bridgeforge/cmd_revive.py` | `revive-review`, `mod-changelog`, `ready-list`, `revive-queue`, `revive`, `escalation` | 6 |

## Where a new module goes

1. Put domain implementation in the matching package above; keep parsing/dispatch in the owner command module and reusable logic in its leaf implementation. Shared mechanisms with real cross-domain consumers can remain at root; do not create a new package solely for one CLI name.
2. Use implementation imports, for example `from bridgeforge.scan.scanner import scan_mod` or `from bridgeforge.save.save_reader import ...`. Avoid root consumer shims inside BridgeForge. For fixers, preserve the existing public `bridgeforge.fixers` API exported by `fixers/__init__.py`.
3. Register a new command through `cli_commands.COMMAND_MODULES`; its module provides `add_parser(subcommands)` and `run_cli(args)`. A CLI change needs an intentional golden review and regenerated `docs/COMMANDS.md`, not a baseline update to conceal a refactor regression.
4. Retain descriptive leaf names and matching `tests/test_<leaf>*.py` files so touched-module selection continues to find them. Nested source paths are supported; `tests/test_source_paths.py` guards the selector and recursive audit inventory.
5. Enumerate source through `source_paths.python_sources` or `family_sources`, not a root-only glob. Checks, source fingerprints and safety ratchets must include nested files. Use `safeio`/`zipsafe` for their existing write/read boundaries; module moves must not broaden exemptions.
6. Resolve resource and repository roots explicitly. A new directory level changes `__file__` relationships; preserve the intended data location and add a focused resource-location regression where needed.

## Consumer shim rule

The move manifest `tests/refactor_module_moves.json` is the reviewed inventory of 114 B3 moves and 11 allowed facades. `tests/test_refactor_imports.py` rejects internal old-path imports; `tests/test_refactor_compat_shims.py` (if present) or the compatibility checks in `tests/test_refactor_imports.py` preserve object identity. The actual guard names should be read from the test files when extending them.

Root shims exist for Project Salvor consumers and import the implementation objects rather than copying logic. They are not the preferred internal API. Current exceptions:

| Old consumer module | Implementation |
|---|---|
| `bridgeforge.rig_prefs` | `bridgeforge.rig.rig_prefs` |
| `bridgeforge.live_run` | `bridgeforge.live.live_run` |
| `bridgeforge.scanner` | `bridgeforge.scan.scanner` |
| `bridgeforge.save_compat` | `bridgeforge.save.save_compat` |
| `bridgeforge.save_content_compat` | `bridgeforge.save.save_content_compat` |
| `bridgeforge.save_cycles` | `bridgeforge.save.save_cycles` |
| `bridgeforge.save_doctor` | `bridgeforge.save.save_doctor` |
| `bridgeforge.save_fingerprint_offline` | `bridgeforge.save.save_fingerprint_offline` |
| `bridgeforge.save_inspect` | `bridgeforge.save.save_inspect` |
| `bridgeforge.save_reader` | `bridgeforge.save.save_reader` |
| `bridgeforge.save_removal_plan` | `bridgeforge.save.save_removal_plan` |

The scanner facade also preserves `_load_lenient_json_file`; the save-doctor facade preserves `_installed`, because consumers use those private aliases. Preserve these identities until the consumer migrates. After the save-family merge and Salvor pin/import update, run Salvor against the installed BridgeForge wheel, then remove only the no-longer-needed shims in a separate reviewed change. Update the manifest and guards together; do not retire shims just because BridgeForge itself no longer imports them.

Keep move and facade commits distinct when merging if retaining the recorded `git log --follow` history matters. A facade intentionally shrinks its old file; review the moved implementation and the phase evidence rather than treating the facade as deleted logic.

## Resources and source identity

Bundled data stays at its existing package locations: `compat_sets/`, `rules/`, `scenarios/`, `packs/`, `probe_profiles/`, `java/`, `java-tools/bytecode/lib/`, and root JSON catalogues/policies. Python domain packages do not own a duplicate data copy. `pyproject.toml` remains the package-data contract. Java helper class names such as `bridgeforge.bytecode.BridgeforgeBytecode` and `BridgeforgeBytecodeRewrite` are Java namespaces, not retired Python import paths.

B3 resource guards preserve repository/profile/catalogue/Java-source locations. Source-file paths participate in stored analysis identities; after the intended stack merges, refresh stored scans with `finding-stats --rescan-stale` on the authorized queue. This documentation change does not run that mutation or renew any evidence.

## Test and CI layout

Normal discovery remains `python -m bridgeforge.test_guard`, which runs unittest and checks that checkout/probe files stay unchanged. `tests/run_partitioned.py` provides B5 fast/slow selection by the measured IDs in `tests/slow_tests.json`, rejects stale/duplicate IDs and assigns new cases to fast. CI runs both partitions on Windows and Ubuntu with Python 3.15/JDK 17. The coverage job remains full and unsplit, with the existing floor; weekly reversed-order testing remains separate. See [B5 timings and validation](docs/REFACTOR_B5_TEST_SPEED.md) for environment limits and refresh instructions.

B0/B3 guards cover recursive source inventories, safe-write allowances, internal import paths, resources, consumer identities and the CLI golden. Synthetic/static, package/consumer, hosted CI and observed game behavior remain separate evidence classes.

## Workspace and evidence boundaries

`workspace.py`/`pipeline.py` use `workspace-manifest.json`, `original-reference/` and `working-copy/`. `intake.py`/`revive.py` use the convention workspace's `original/`, `working/`, `reports/` and `scratch/`. Do not pass one layout blindly to commands expecting the other. Logical adapters and a common revival case are proposed under S1; B-series source moves implement no physical workspace migration.

Inputs, game installs, mod sources, saves and archives are outside this refactor. Module layout does not establish runtime correctness or authorization to mutate them. Current qualification limitations belong in [architecture gaps](docs/ARCHITECTURE_GAPS.md), [roadmap status](docs/ROADMAP_STATUS.md), [local handoff](docs/LOCAL_HANDOFF.md) and their dated evidence.

## Review and close-out

[The stack ledger](docs/REFACTOR_STACK.md) identifies branch parents and PRs; [B6 evidence](docs/REFACTOR_B6_CLOSEOUT.md) distinguishes documentation implementation from review/merge completion. Item 83 stays open until its required gates, including applicable cross-repository work, actually close. No new live test was performed for B6.
