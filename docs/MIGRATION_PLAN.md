# Moving BridgeForge to another computer: plan (ROADMAP item 64)

Written 2026-10-10 at the owner's request ("a plan to migrate everything to a different computer; I know Syncthing
but not what can and can't be migrated"). **Plan only, nothing built or moved.** Facts below were read from this
machine on 2026-10-10. File sizes are **not measured**: a `du` over `In operation/` and `Done/` ran past six minutes
without finishing, which is itself the finding (hundreds of workspaces, very many small files; plan for hours, not
minutes, and run any inventory in the background).

## 1. What there is, and what to do with each

| Class | What | How to move it |
|---|---|---|
| **In git** (`Exxec/Project-BridgeForge`) | `bridgeforge/`, `tests/`, `probe-mod/` source, most of `docs/`, `ROADMAP.md`, `CHANGELOG.md`, `CLAUDE.md`, `tools/bf-test.ps1` and two tracked tools | `git clone`, check out `local/handoff-pass-2026-09-27`. Everything up to `cc619afb` is pushed. |
| **Gitignored and irreplaceable** | `In operation/` (originals, working copies, reports, scratch for every mod), `Done/` (archives, zips, readmes), `bridgeforge-state/` (baselines, provider index, build manifests, reference-rig records, `project-go-*`), `artifacts/`, `bridgeforge-artifacts/`, `AGENTS.md`, `EXAMPLES.md`, untracked `tools/*.ps1`, the gitignored `docs/` files (`fable-briefs/`, `REVIVAL_*`, `ESCALATION_TEMPLATE.md`), `.githooks/`, `config/bridgeforge.local.psd1`, `Project BridgeForge.code-workspace` | Copy (section 4). This is the real migration. |
| **Regenerable, do not move** | `.venv/`, `__pycache__/`, `*.egg-info/`, `.pytest_cache/`, coverage files, `hs_err_pid*.log`, every rig's `logs/`, `instances/` (throwaway, full of junctions), `mass-test.partial.jsonl` and other `*.partial.jsonl` checkpoints, `.claude/worktrees/` | Skip. Recreate with `uv sync` / `pip install -e .` and by re-running commands. |
| **Expensive to regenerate** | `bridgeforge-state/corpus-index.sqlite` (a full `corpus-index build` took 44 minutes over the archive), decompile caches under `In operation/*/scratch/` | Copy once if the machine is idle, otherwise rebuild. Never copy a sqlite file while a command is writing it. |
| **Outside the repo, same person** | `Documents/Project Salvor`, `Starsector project forge`, `Starsector project go` (the translator CLI), `Starsector project workbench`, `To be translated`, `Zorg18-BridgeForge-Evaluation`; the RevenantLib repo (`Exxec/RevenantLib`, private); the ~350-mod "Ironclads mega archive" in `Downloads` | Each its own decision. Git repos by `git clone`; the archive once, as a plain copy (it is not a working tree). |
| **Game files (never in git)** | `Program Files (x86)\Fractal Softworks\Starsector` (RC8, `mods/`, `saves/`, FR, Prepatcher, Mikohime, the `jdk-27+22` and `jdk-28+13` folders), and the six reference installs `Starsector62`, `7.2`, `8.1`, `9a`, `9.0`, `9.5.1a` | Reinstall RC8 on the new machine, then copy `saves/` and the owner's `mods/` folder and Mikohime files. The reference installs are needed for API-drift checks: copy them over a drive or LAN, not through git. |
| **Claude Code state** | The memory folder `~/.claude/projects/c--Users-exxec-Documents-Project-BridgeForge/memory/` (20+ owner rules and findings), project `.claude/settings.json` and `hooks/` | Copy the memory folder; see section 2 for the key. |

## 2. What breaks on a new machine (absolute paths found 2026-10-10)

1. `git config core.hooksPath` is the absolute `C:\Users\exxec\Documents\Project BridgeForge\.githooks`. Without
   resetting it the pre-commit and pre-push checks do not run (or fail).
2. `config/bridgeforge.local.psd1` holds four absolute paths (`ProjectRoot`, `InOperation`, `Done`, `StarsectorRoot`).
3. Every rig's `starsector-core` is a **junction** to the real install, by absolute path, and rig `.bat` files hold an
   absolute JDK path. Junctions are not portable; recreate them (`java-matrix setup` rewrites the bats; the junction is
   made by the rig setup, not copied).
4. JSON in `bridgeforge-state/` records absolute paths: `provider-index.json`, `real-saves-baseline*.json`,
   `reference-rigs/*.json` (JRE paths), and the corpus index. Stale paths there give wrong answers quietly, not errors.
5. Checkpoints name their inputs by path; a moved run restarts instead of resuming. Harmless, but expect it.
6. The Claude memory folder name is derived from the project path (`c--Users-exxec-Documents-Project-BridgeForge`). A
   different drive or user name gives a different folder; copy the files into the new name or the rules are not loaded.
7. The Python on `PATH`: this session lost it once (the Windows Store stub answered instead), which broke the pre-commit
   hook. Install Python 3.10-3.13 or 3.14 and `uv`, and check `python --version` in the shell the hooks use.
8. Windows long paths: deep `In operation/*/scratch/...` trees need `LongPathsEnabled` on both machines.

**Easiest safe option:** give the new machine the *same absolute paths* (same user name or a drive layout that
produces identical `C:\...` paths). Then items 1-6 need no rewriting. If the paths must differ, build the
`relocate` command in step 3 below rather than hand-editing JSON.

## 3. Syncthing: what it can and cannot do here

- **Good for:** moving the gitignored data trees (`In operation/`, `Done/`, `bridgeforge-state/` without the sqlite),
  the `Downloads` archive, and the small memory folder. Use **send-only on the old machine / receive-only on the new
  one** while moving, then stop. A one-time `robocopy <src> <dst> /E /COPY:DAT /XJ /R:1 /W:1` (the `/XJ` skips
  junctions) is equal or better for a one-off and has no daemon to fight.
- **Never sync `.git/`** together with a live checkout on two machines; use `git push` / `git pull`. Syncing a repo's
  object store from two places corrupts it.
- **Junctions and symlinks:** Syncthing does not carry NTFS junctions reliably. Rigs (`_rig`, `_rig-vacuum`) and
  `instances/` are full of them. Put them in `.stignore` (`/In operation/_rig*/starsector-core`, `**/instances`,
  `**/mods/*` junction children) and recreate them on the new side.
- **Do not two-way sync a working tree you run commands in.** `mass`, `corpus-index build` and probe runs write
  thousands of files and a sqlite database; two writers produce `.sync-conflict-*` files and a half-written index.
- **Ignore patterns to set:** `.venv`, `__pycache__`, `*.pyc`, `*.partial.jsonl`, `hs_err_pid*`, `**/logs`,
  `**/instances`, `.pytest_cache`, `.coverage*`.
- **Cost:** the first scan of hundreds of workspaces with very many small files is slow and memory hungry. Syncthing
  is not a backup either: a deletion on one side deletes on the other. Keep the old machine untouched until the new
  one is verified.

## 4. Plan

1. **`migrate-inventory` (cloud-testable, background, progress per top-level folder).** Walks the repo and the known
   outside locations, classifies every top-level item with the table above, lists junctions/symlinks, counts files and
   bytes, and greps JSON/psd1/sqlite-adjacent files for absolute paths. Output: one manifest the owner reads before
   copying. This replaces guessing sizes. Follows the long-running-command rule.
2. **`relocate --from OLD --to NEW` (cloud-testable).** Rewrites path fields in `config/*.psd1` and the known
   `bridgeforge-state/*.json` files, reports the sqlite index as "rebuild", and never edits a path it does not
   recognise. Dry-run by default; writes `.bak` copies.
3. **`migrate-verify` (cloud-testable).** A hash manifest of a tree written on the old machine and checked on the new
   one (reuses the `copy-drift` comparison), so "everything arrived" is a result, not a feeling.
4. **Cutover checklist (this document, section 5)** and a rollback rule: the old machine stays read-only until the
   new one passes the checks.
5. **Local:** do the move once the owner picks the target layout; run the checklist on the new machine.

## 5. Cutover checklist (new machine)

1. Install Git, Python, `uv`, JDK(s), RC8; enable long paths.
2. `git clone` the repo; `git config core.hooksPath .githooks` (a relative path works across machines).
3. Copy the gitignored trees (section 1), `config/bridgeforge.local.psd1` rewritten for the new paths.
4. Recreate the venv; `python -m bridgeforge --help` and `python -m bridgeforge.test_guard` (expect the suite to pass;
   one known environmental failure, `test_locks`, is recorded in `docs/LOCAL_HANDOFF.md`).
5. Recreate rigs: junction `starsector-core`, `java-matrix discover` then `setup`.
6. Copy the memory folder to the key derived from the new project path; start a session and confirm it is loaded.
7. Run one mod through `java-matrix mass --only <mod>` and compare with the old machine's result.
8. Only then retire the old machine's copy.

## 6. Questions for the owner

- New machine: same user name and drive layout, or different? (decides whether `relocate` is needed)
- Is `Documents` on this machine synced by OneDrive (a "Shortcut to Documents (OneDrive - Personal)" sits in it)? If
  so, a second sync tool on the same folder is a conflict risk.
- Which outside projects move, and are the six reference installs copied or re-downloaded?
