# Cross-repo structural refactor plan (ROADMAP-3 item 83)

Owner-approved 2026-10-22. Written for the agent doing the work; the coordinating session reviews each PR against
section 6 before it merges. **Behaviour must not change.** This is reorganisation only: no new features, no fixes riding
along (file a BUGS.md entry instead), no renamed CLI flags, no changed output formats.

## 1. Scope and starting point (measured 2026-10-22)

| Repo | Size | Work in this plan |
|---|---|---|
| BridgeForge | 291 modules / 69k lines in one flat `bridgeforge/` folder; 270 test modules / 44k lines; 267 commands; 57 docs + 3 roadmaps (3,660 lines); full suite ~9 min | Phases B0-B6 |
| Project Go | 31k lines in 11 Gradle modules (structure sound) | Phase G1 |
| VoidSmith | 25k lines | Phase V1 |
| Salvor | 3k lines | Phase S1 (import updates only) |
| SPW | 5k lines | None |

Out of scope: rewrites, new architecture or plugin systems, changing what any command does, the probe mod (Java),
anything under `In operation/`, `Done/`, `bridgeforge-state/`.

## 2. Rules for every PR

1. One phase step per PR, small enough to review; merge each before starting the next step that touches the same files
   (moves conflict with everything). Use `bridgeforge merge-train` for BridgeForge chains.
2. Work in a git worktree under `C:\Users\exxec\Documents\bf-wt\`, never in a main checkout. Force-push is blocked in this
   environment: integrate main with `git merge`, not rebase + force-push.
3. Moves use `git mv` so history follows (`git log --follow` must work on a moved file). A move PR contains moves and
   the import/path edits they require, nothing else.
4. Follow each repo's CLAUDE.md / AGENTS.md (hooks, changelog.d fragments, safeio ratchet, generated files regenerated,
   never hand-edited). Never skip hooks.
5. Commit messages: `refactor: ...` (or `docs:` for B1), ending with
   `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. PR body: what moved, the section 6 evidence, ending with
   `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
6. Do not merge. The owner merges after the coordinating session's review.
7. Stop and report instead of improvising when: a test fails for a reason other than an import path; the CLI golden
   changes in a way not listed in the step; a step needs a behaviour change; Salvor or another repo would break.

## 3. BridgeForge

### B0 Baseline and path-safety (do first, one PR)

Several tools enumerate `bridgeforge/*.py` **non-recursively**. Moving modules into subpackages would silently drop
them from these checks while the tests still pass. Fix this before anything moves:
- `tests/test_safeio_ratchet.py` (`PACKAGE.glob("*.py")`), `tests/test_hull_id_resolution_audit.py`,
  `bridgeforge/checks_index.py` (`(repo_root / "bridgeforge").glob("*.py")`), `bridgeforge/scan_registry.py` (fingerprint
  inputs `bridgeforge/*.py`), `bridgeforge/merge_train.py` `test_modules_for` (maps `bridgeforge/<name>.py` to
  `tests/test_<name>*.py`) and `tools/prepush-check.ps1` (same mapping), `cli_commands.COMMAND_MODULES` (module names as
  strings), `LONG_RUNNING_COMMANDS`, the probe contract test's source scan. Grep for any other `glob("*.py")`,
  `"bridgeforge/"` string or module-name string and list them in the PR.
- Make each recursive (`rglob`, skipping `__pycache__`) or package-path aware; make `test_modules_for` map
  `bridgeforge/<pkg>/<name>.py` to `tests/test_<name>*.py` (and `tests/<pkg>/test_<name>*.py` if B4 moves tests).
- Add a guard test asserting the number of modules each of these sees equals the number of `.py` files under
  `bridgeforge/` (minus explicit exemptions), so a future move cannot shrink coverage unnoticed.
- `scan_registry`'s fingerprint will change once files move; note in the PR that corpus fingerprints become stale and
  how they are refreshed (existing command), rather than special-casing it.
- Record the baseline in the PR body: full `python -m bridgeforge.test_guard` count/skips, coverage %, number of
  commands in `docs/COMMANDS.md`, SHA-256 of `tests/cli_help_golden.json`, wall time of the suite.

### B1 Docs and roadmaps (one PR)

- Move the finished `ROADMAP.md` and `ROADMAP-2.md` to `docs/archive/` (keep history with `git mv`); ROADMAP-3 stays the
  only active roadmap. Fix every link to them (grep the repo, other repos' docs too: VoidSmith/Salvor/Project Go cite
  BridgeForge docs).
- Move dated, finished audit/log docs (e.g. `docs/DOCS_AUDIT_2026-10-18.md`, `docs/ARCHITECTURE_GAPS.md` if fully
  superseded) to `docs/archive/`; keep anything still referenced as current. `docs/INDEX.md` lists what is current.
- `roadmap-lint` and the status generation from `gates.json` (80.6) must still pass.

### B2 Split `fixers.py` (3,973 lines) into a `fixers/` package (one PR)

- `bridgeforge/fixers.py` becomes `bridgeforge/fixers/__init__.py` re-exporting the public names (at least
  `apply_fix`, `compute_fix`, `FixerError`, `SUPPORTED_FINDINGS`, `unified_diff_*`, `record_named_encodings` and every
  name other modules or tests import; grep). Split along the existing `# ----` section banners, one module per fixer
  family. Fold `fixers_data.py`, `fixers_guards.py`, `fixers_presets.py` (and other `fixers_*`) into the package; they
  import `from . import fixers as _f` lazily to avoid a cycle, keep that working or remove the cycle.
- No module in the package over ~800 lines. `SUPPORTED_FINDINGS` and fixer ordering must be identical (add a test
  comparing the before/after list if none exists).

### B3 Prefix families into subpackages (one PR per family, in this order)

Order: `research_*` + `cmd_research` -> `research/`; `atlas_*` -> `atlas/`; `corpus*` -> `corpus/`; `escalation_*`;
`probe_*` (+ `probe_group`, `cmd_probe_group`); `rig_*` + `cmd_rig`; `live_*`; `bytecode_*`/`jar_*`/`java_*`
-> `bytecode/`; `scan_*` + `scanner` + `cmd_scan` -> `scan/`; `save_*` + `cmd_save` -> `save/` **last**.
- `cmd_<family>.py` moves into its package as `cli.py` (or keeps its name) and `COMMAND_MODULES` is updated.
- Modules imported by other repos keep a thin re-export module at the old path so pinned consumers keep working:
  Salvor imports `bridgeforge.launcher_click`, `live_run`, `progress`, `rig_prefs`, `save_compat`, `save_content_compat`,
  `save_doctor`, `save_fingerprint_offline`, `save_inspect`, `save_reader`, `save_removal_plan`, `scanner`. Re-grep
  VoidSmith, SPW and Project Go for `bridgeforge.` imports before each family. Each shim is a few lines
  (`from .save.reader import *` plus explicit names used by consumers) with a comment naming the consumer and "remove
  after the consumer's pin moves past this change" (S1).
- Internal imports use the new paths; no shim is used from inside BridgeForge (add a test that fails if one is).
- `pyproject.toml` `package-data` and `packages.find` must still ship every data file (`java/`, `rules/`, `packs/` ...):
  build a wheel and diff its file list against the baseline wheel.
- Tests may stay flat in `tests/`; only move them if B0's mapping supports it.

### B4 Command audit and grouping (two PRs)

- PR 1, report only: for each of the 267 commands, where it is referenced (docs, workflows, `gates.json`, tests other than
  its own, other repos, rig scripts). Commands referenced nowhere outside their own test are deprecation candidates.
  Output a table in the PR; the owner decides. No code change in PR 1.
- PR 2, after the owner's decision: group top-level commands under about 20 nouns (`scan`, `save`, `probe`, `rig`,
  `research`, `atlas`, `archive`, `corpus`, `bytecode`, `translate`, `workspace`, `gates`, ...). Every old command name
  keeps working as an alias that prints one deprecation line to stderr; the alias list is a table in one module and
  pinned by the CLI golden. Deprecated commands print their deprecation line and still work; removal is a later,
  separate decision.

### B5 Test speed (one PR)

- Mark slow tests (measure: anything over ~2 s) and split CI into a fast job and a slow job; local pre-push already runs
  only touched modules. Do not add a test-runner dependency unless the owner agrees; `unittest` stays the runner.
- Report the new fast/slow wall times.

### B6 Close-out (one PR)

- `docs/ARCHITECTURE.md` (or the existing architecture doc): the package map, where a new module goes, the shim rule.
- CLAUDE.md: update paths it names. ROADMAP-3 item 83 marked done with PR numbers.

## 4. Project Go (G1)

- Split `ssmt-gui/.../SsmtApplication.java` (1,993 lines) into one class per tab or pane plus a slim application shell;
  `ReviewInboxPane` (H2) is the model for a self-contained pane. Same for `ProjectWorkspaceController.java` (952) and
  `TranslationWorkflowPane.java` (916) only if a natural seam exists.
- `ssmt-project`: `LocalizationProjectService.java` (1,027) and `TranslationWorkflow.java` (946) split only along existing
  responsibilities; public API unchanged.
- Checks: `.\gradlew.bat build` green; `golden-help.tsv` unchanged; GUI checklist harness (`GuiChecklistTest`) produces
  the same rows and the review inbox still lists the same rows; JUnit test count not lower than baseline.
- AGENTS.md rules apply (identifiers protected, gates never upgraded).

## 5. VoidSmith (V1) and Salvor (S1)

- V1 (only if time allows, lowest priority): split `analysis/gap_recommendation.py` (2,416) and `gui/main_window.py`
  (1,794) along existing responsibilities; `api.py` (1,196) only if trivial. Checks: unittest, ruff, mypy as in
  `.github/workflows/tests.yml`; `--help` output unchanged; the portable build (`tools/build_portable_release.ps1`)
  still produces a working exe (`--version`, `--help`).
- S1 (after B3's `save` family merges and the pin moves): update Salvor's imports to the new BridgeForge paths in the
  pin-bump PR, then remove the matching shims from BridgeForge in a follow-up PR.

## 6. What the review checks (evidence each PR must include)

For every PR, in the body:
1. Test counts: full suite before/after (BridgeForge `python -m bridgeforge.test_guard`; Go `gradlew build` test totals;
   VoidSmith unittest count). After must equal before, plus any new guard tests. No new skips.
2. Coverage not lower than baseline (BridgeForge `fail_under = 80`).
3. CLI surface: `tests/cli_help_golden.json` / `golden-help.tsv` unchanged, except B4 PR 2 where the diff is only the
   new groups and aliases.
4. Path-safety: B0's guard counts equal the module count.
5. For move PRs: `git diff -M --stat` shows renames (similarity >= 90%) rather than delete+add; no logic diff beyond
   import lines (show `git diff -M` stats).
6. Wheel file list unchanged (BridgeForge) or exe smoke (VoidSmith).
7. Other repos: Salvor's test suite run against the PR branch of BridgeForge (install it into a temp venv) passes.
8. ruff / mypy / hooks clean; hermeticity PASS.

## 7. Order and estimate

B0 -> B1 -> B2 -> B3 (families in order) -> B4 PR 1 -> owner decision -> B4 PR 2 -> B5 -> B6. G1 can run in parallel with
B1-B3 (different repo). V1 last and optional. S1 after the `save` family. Roughly 15-20 PRs.
