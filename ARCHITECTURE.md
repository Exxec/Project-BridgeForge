# BridgeForge — Repo Architecture

This document describes the repository itself. A separate `AGENTS.md` documents how to
operate this repo (CLI conventions, repo conventions, workflows, tooling).

Status: **source-audited 2026-10-18** at `3342654d`, then command, module and archive notes updated against `c62c82a6`
(items 73 and 75, offline). This is a repository map, not proof that all workflows are
integrated or live-qualified. Strategic limitations and evidence are in `docs/ARCHITECTURE_GAPS.md`; S1 convergence
is proposed in `docs/NEXT_MILESTONE.md`. The committed agent companion is `CLAUDE.md`; `AGENTS.md` is local-only.

---

## 1. Repository layout

```
bridgeforge/          Python package
  __main__.py         python -m bridgeforge entry
  cli.py              parser construction and dispatch entry
  cli_commands.py     COMMAND_MODULES dictionary and registration/dispatch functions
  cmd_*.py            grouped command parsers and handlers
  atlas_report.py     example standalone command module (other names vary)
  compat_sets/        compatibility-test mod sets
  rules/              bundled migration rules
```

`cli.py` calls `register_all` and `dispatch` from `cli_commands.py`. `register_all` dynamically imports the modules
named in the `COMMAND_MODULES` dictionary and calls their `add_parser`; handlers expose `run_cli`. There is no
`CommandRegistry` class or registry instance. Each module defines its parser defaults/options; the dictionary maps
top-level command names to modules. `tests/test_cli_golden.py` checks command/subcommand help compatibility.

## 2. Command catalogue

**173 top-level commands**, counted from `COMMAND_MODULES` at `c62c82a6` (2026-10-18): 154 in 13 `cmd_*.py` modules and 19 in
16 other modules (the earlier count of 164 predates items 73 and 75). Nested subcommands are a different count. See generated `docs/COMMANDS.md` for current options.

### 2a. Command groups by topic (`cmd_*.py`)

| Module | Commands | Count |
|---|---|---|
| `cmd_workspace.py` | workspace, plan, apply, rollback, build-plan, compile, package-jar, compile-feedback, review-bundle, validate, save-risk, pipeline, packs, migration-pack-candidate, runtime-profile, runtime-smoke, inspect, export-patch, opportunities, doctor, conflicts, provenance | 22 |
| `cmd_scan.py` | mods-compat, baseline-stats, docs-index, preset-check, scan, working-tree-layout, source-authority, build-input-manifest, integration-scenarios, compile-check, revenantlib-check, check-impact | 12 |
| `cmd_analysis.py` | corpus-audit, cross-mod-analyze, campaign-identity-inventory, campaign-identity-check, release-lineage, library-api-inventory, library-api-match, dependency-api-check, corpus-compare, release-evaluate, revival-audit, api-diff | 12 |
| `cmd_bytecode.py` | decompile-jar, port-interfaces, patch-jar-sources, decompiler-review, bytecode-inspect, bytecode-plan, bytecode-diff, bytecode-apply, copy-drift, jar-audit, jar-packets, port-hullmod-state, patch-jar-class, rebuild-jar | 14 |
| `cmd_translate.py` | translate-export, translate-apply, translate-tm, translate-check, fix, strip-plan, descriptions, translate-batch, renamed-ids | 9 |
| `cmd_save.py` | compat-set, save-compat, save-removal-plan, save-doctor, save-format-survey, save-content, save-diff, save-growth, save-inspect, save-provenance, save-removal, save-scripts, save-summary, save-snapshot, scenario | 15 |
| `cmd_rig.py` | accept, soak-report, log-triage, prepare-test, env-check, java-matrix, boot-test, dossier, build-probe-mod, probe-config, bootstrap, rig-create, rig-doctor, who-locks, test-plan, perf-gate | 16 |
| `cmd_probe_group.py` | probe-group | 1 |
| `cmd_behavior.py` | lookup, novelty, behavior-decide, archaeology, behavior-diff, behavior-map, coverage, expect, hypotheses, probe-baseline, release-behavior-evaluate, risk-register, save-baseline | 13 |
| `cmd_corpus.py` | dependency-substitutes, provider-index, supersession, finding-stats, dependency-graph, corpus-recheck, sibling-assets, vendor-copy, revival-report-draft, diff-data, rebuild-from-reference, corpus-index, content-diff, verify-shadow, vendor-plan | 15 |
| `cmd_archive.py` | audit-shipped, audit-explain, archive, relink, bump-version, declare-providers, close, restore-from-done, promote, board, intake, archive-preflight, archive-stage, build-tag, release, release-policy, done-audit, fold | 18 |
| `cmd_revive.py` | revive-review, mod-changelog, ready-list, revive-queue, revive, escalation | 6 |
| `cmd_shadow.py` | shadow-triage | 1 |

Top-level command counts were checked against `COMMAND_MODULES` in `bridgeforge/cli_commands.py`.

### 2b. Other command modules (each defines its own `add_parser`/`run_cli`)

| Module | Commands | Count |
|---|---|---|
| `atlas_report.py` | `atlas` | 1 |
| `substitution_proposals.py` | `substitution-proposals` | 1 |
| `baseline_audit.py` | `baseline-audit`, `baseline-accept` | 2 |
| `rig_reset.py` | `rig-reset` | 1 |
| `rig_up.py` | `rig-up` | 1 |
| `run_manifest.py` | `run-manifest` (`prepare`, `release`, `check`) | 1 |
| `revise.py` | `revise` (`prepare`, `finalize`, `status`, `migration`) | 1 |
| `live_ledger.py` | `live-ledger` | 1 |
| `roadmap_lint.py` | `roadmap-lint` | 1 |
| `agent_diff_check.py` | `agent-diff-check` | 1 |
| `auto_open.py` | `auto-open` | 1 |
| `move_machine.py` | `migrate-inventory`, `relocate`, `migrate-verify` | 3 |
| `state_snapshot.py` | `state-snapshot` | 1 |
| `snapshot_restore.py` | `snapshot-restore-check` | 1 |
| `save_upgrade.py` | `save-upgrade` (`plan`, `evaluate`) | 1 |
| `value_proposals.py` | `value-proposals` | 1 |

`atlas` is a single subcommand that routes to the functions in `bridgeforge/atlas.py`
(`atlas.py` itself contains no CLI subparser).

### 2c. Trust and evidence modules added by items 73 and 75 (library modules, offline-tested; live gates pending)

- `run_manifest.py` binds a run to the staged rig files; `live_accept.py` and `probe_group.py` consume it through one evaluator.
- `scan_registry.py` registers scans with input fingerprints (`scan-registry.json`); `finding_stats.py` and `auto_open.py` read it.
- `escalation_policy.py` holds the report-only auto-accept gates (`ENABLED = False`); `escalation_review.py` writes the review sheet.
- `new_game_generic.py`, `raid_run.py` (with `probe-mod/raid-mod/bf_raid`) and the `LAUNCH_NO_PROCESS` watchdog in `boot_test.py`
  support unattended live runs.
- `descriptions_draft.py`, `translation_memory.py`, `scan_shadowing.py`, `scan_hyperspace_market.py`, `scan_mission_map.py`,
  `scan_mission_variants.py`, `scan_port.py`, `fixers_guards.py`, `fixers_presets.py`, `fixers_substitute.py` and
  `signature_rewrites.py` hold the new drafts, checks and fixers.

## 3. The package (`bridgeforge/`)

- `__init__.py` — package init.
- `__main__.py` — `python -m bridgeforge` entrypoint.
- `cli.py` — parser/stream setup and entry dispatch through the registry functions.
- `cli_commands.py` — `COMMAND_MODULES` mapping plus dynamic parser registration and handler dispatch.
- `cmd_*.py` — one module per command group. Each exposes a `add_parser`-style
  constructor used by the registry to add its subcommands to the main parser.
- `models.py` — data models.
- `scan_common.py` — shared scan helpers.
- `scanner.py` — `scan_mod` orchestration and compatibility re-exports; check families live in `scan_*.py` modules.

## 4. Data files

- `bridgeforge/compat_sets/standard.json` — a compatibility-test mod-set profile.
- `bridgeforge/rules/v0_2.json` — bundled migration rules.

## 5. Data subpackages (under `bridgeforge/`)

Verified via `find bridgeforge -maxdepth 2 -type d`:

- `compat_sets/` — compatibility-test mod-set profiles, including `standard.json`.
- `rules/` — `v0_2.json` (the legacy v0_2 rule set).
- `java/`, `java-tools/` (→ `bytecode/`), `probe_profiles/` — runtime/probe data.
- `scenarios/` — scenario data.
- `packs/` — holds `ashlib/`, `graphicslib/`, `java/`, `lazylib/`, `lunalib/`,
  `magiclib/`, `nexerelin/`, `starsector/` (8 pack subpackages).

## 6. Workspace and evidence boundaries

`workspace.py`/`pipeline.py` use `workspace-manifest.json`, `original-reference/` and `working-copy/`.
`intake.py`/`revive.py` use the convention workspace's `original/`, `working/`, `reports/` and `scratch/`.
Neither layout should be passed blindly to commands expecting the other. Logical adapters and a common revival
case are proposed under S1; no physical workspace migration has been implemented by this document.

Qualification/release paths also have different contracts; source/compile/static/package/save/live evidence are
separate. DOC-001 in `BUGS.md` (archive refresh deleted the old archive) was fixed 2026-10-18: refresh now moves it to
`Done/_replaced-<date>/`; it has not been exercised on a real `Done/` archive. Module reshuffling is not a substitute
for addressing these S1 workflow blockers. This architecture map does not authorize application changes.
