---
name: bridgeforge-pr
description: Ship a BridgeForge change the house way, from branch to merged pull request. Covers ruff via uvx, the full suite under test_guard with the project .venv and JDK 25, roadmap-lint, the regenerated docs index and CLI golden file, the changelog fragment, the Done note in ROADMAP-3.md, an independent review, the owner's PR layout (TEST STEPS / BEFORE FIX / AFTER FIX / EXPECTED BEHAVIOR), CI and merging by head commit. Use it whenever you commit, open, update or merge a pull request in this repository, or finish a roadmap item. Also use it when the user just says "push it", "open a PR", "ship it", "merge it" or "sync to github".
---

# Shipping a BridgeForge change

One roadmap item per branch and per pull request. Each step below exists because skipping it once broke CI or the record
(the notes say when). CLAUDE.md has the full house rules; this is the order to apply them in.

## 1. Branch, in a worktree when several items run at once

```bash
git fetch -q origin
git worktree add -b fix/<item>-<slug> ../BridgeForge-<item> origin/main   # or docs/..., feat/...
```

A worktree per item lets you run several full suites in parallel (about 11 minutes each; 24 CPUs handled seven at
once). **Never edit a checkout while its suite runs**: `test_guard` fails the run if the checkout changed, and the result
would describe code you no longer have. Edit another worktree meanwhile.

## 2. Tests first, and tests that do not depend on this machine

Write the failing test, watch it fail for the right reason, then fix. For a test that guards a property, run
`scripts/mutate_check.py` (break the code on purpose; the test must fail). A test that still passes against the broken
code proves nothing. That happened twice on 2026-11-17. How the script decides:
- **Baseline:** it first runs the selector unmutated, and stops unless that run passes with a test that is not skipped.
  Without it, a mistyped selector reads as a kill: a Project Go driver printed void kills that way (2026-11-22).
- **No stale bytecode:** each run compiles from source under an empty bytecode cache. A same-length mutant restored
  within the second otherwise kept running.
- **Verdicts and exit codes:**
  - FAILS (0): the test catches the mutation, the only result to claim;
  - PASSES (1);
  - nothing run (2);
  - INVALID (3): the test module no longer loads;
  - timed out (4).
- **A mutant that breaks a module imported only inside a test** shows as an ERROR, so it reads FAILS. Check that the
  failure is the assertion you meant.
- **Several mutants:** write them as a spec and run `scripts/mutate_batch.py SPEC.json RESULTS.json`. It runs each through
  `mutate_check.py`, records the verdicts, checks the checkout is clean after each, and resumes a stopped batch. Keep the
  spec with the claim, so the claim can be re-run (`mutations/2026-11-22-rerun/` holds the re-run of 2026-11-17 to
  2026-11-22's claims).
- **Snippet files** (`@FILE`) are read byte for byte, so a multi-line snippet keeps CRLF and matches a CRLF module.

CI runs on clean Windows and Ubuntu runners: no Starsector install, no licence key in the registry, Java 8 on PATH. Patch
machine state (registry, installed games, home folder) in tests. One rig-doctor test read the developer's registry and
would have failed only on the Windows runner.

## 3. Before committing

Run `scripts/checks.sh` from the checkout root. It runs ruff, roadmap-lint, the docs index and the golden and index tests.
- **Changed a CLI `--help` text?** Run `python -m tests.test_cli_golden --write` and review the diff.
- **Any change at all:** run `python -m bridgeforge docs-index`. A new test that only *names* a finding id changes
  `docs/CHECKS.md`; that failure turns up only in the full suite.
- **Code changes:** add `changelog.d/<slug>.md`, one bullet ("- Item N: what changed for the user"). Never edit
  CHANGELOG.md. Roadmap-only PRs need no fragment.
- **Finished item:** add `**Done <date>.**` to its ROADMAP-3.md entry, saying what was built and naming the tests
  (`tests/test_x.py` `test_name`). roadmap-lint refuses a Done entry without evidence.

## 4. The full suite

```bash
export JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-25.0.4.101-hotspot"
export PATH="/c/Program Files/Eclipse Adoptium/jdk-25.0.4.101-hotspot/bin:$PATH"
.venv/Scripts/python.exe -m bridgeforge.test_guard > <scratch>/suite-<item>.log 2>&1   # run in the background
```

Plain `python` lacks psutil and PATH `java` is Java 8, so use the `.venv` interpreter and JDK 25. From another worktree,
call the main checkout's `.venv/Scripts/python.exe` by its full path. Read the result from the log's `Ran N tests`,
`OK (skipped=K)` and `Test hermeticity PASS` lines. (The `hermeticity FAIL` lines that appear inside test_guard's own
self-tests are expected.)

### A change to a scanner check: the archive, old code against new

A check that passes its tests can still drop real findings, or add new ones, across the archives in Test1's `Done/` (98.8:
53 `settings-key-missing` findings became 20, and each dropped one had to be explained; that sweep ran the one check over
351 mod folders with a script, before `findings-diff` existed). Measure it before review:
1. On Test1, put main and the branch side by side: `git fetch origin <branch>` and `git worktree add <dir> origin/<branch>`
   (push the branch first, no PR needed yet).
2. Run `done-audit --all-findings` once with each checkout's code, one after the other, never at the same time:
   `<repo>\.venv\Scripts\python.exe -m bridgeforge done-audit --all-findings --done "<repo>\Done" --queue "<repo>\In operation" --vanilla-core @target`.
   - Without `--all-findings` a record keeps only the crash-class, MANUAL and UNKNOWN findings the baseline does not accept,
     about a third of the check ids: a change to any other check compares nothing.
   - For the worktree's run, start in the worktree with `PYTHONPATH` set to it (otherwise the main checkout's code runs) and
     `BRIDGEFORGE_DATA_ROOT` set to `<repo>`. A worktree otherwise takes itself for the data root: `@target` fails ("no
     target set"), and `find_jdk` finds no rig JDK, so every jar check is skipped (seen 2026-11-27).
   - Before each run, move `Done\DONE_AUDIT.json` away, and check that the run exits 0. A run that crashes writes no new
     file, so the other run's would be compared with itself (`findings-diff` refuses two files from the same checkout and
     HEAD, which the JSON records). Copy the new file aside after each run.
   - Run the branch first and main last, so `Done\DONE_AUDIT.md` ends as main's audit. The checkpoint records the code, so an
     interrupted run resumed under the other checkout starts over.
3. `bridgeforge findings-diff main.json branch.json --id <the check's id>` lists, per archive, the findings dropped and the
   new ones, counting identical findings one by one. An archive either run could not audit is listed as not compared. It
   exits 1 when the inputs come from the same code, an `--id` appears in neither input (a typo, or a filtered run), or no
   archive is in both.
4. In the PR body, give the totals line and a reason for every dropped finding. Read every new one before merging.

## 5. Review before pushing

Get a reading that is not anchored on yours: the `code-review` skill, or one review agent per batch of diffs, given the
diffs and not your conclusions. Check every finding against the code before fixing it, then rerun the suite. Use
`security-review` for untrusted input handling, file-system writes and anything over SSH.

## 6. Commit message

```
Fix item 93.33: bound every zip and jar entry read

What was found, with evidence (file:line, counts, the log line), and what changed.

Full suite: 2907 tests, OK (skipped=12); hermeticity PASS.

<the Co-Authored-By line from the session's attribution reminder>
```

The subject is `Fix item N: ...` or `Add item N: ...`. Review fixes go in a new commit, not an amend.

## 7. Pull request body (owner rule, 2026-11-01)

```
<one-line summary>

**TEST STEPS**
1. the commands, or the user actions with versions

**BEFORE FIX**
- what happened, with evidence

**AFTER FIX**
- what happens now, specifically; only what was observed (say so if not run live)

**EXPECTED BEHAVIOR**
- the requirement

<the generated-with line from the session's attribution reminder>
```

Write the body to a file and pass it with `gh pr create --body-file <file>`, which avoids quoting trouble in the shell.
(The Exotica repository uses its maintainer's layout instead; see the memory note.)

## 8. CI and merge

Run `bash .claude/skills/bridgeforge-pr/scripts/merge_when_clean.sh <N>` in the background right after the push. It waits for the checks to settle, then
merges by the head commit CI saw, and only when `mergeStateStatus` is CLEAN. UNSTABLE means a red check and is never merged
(#185 was, by mistake, 2026-11-19); `--match-head-commit` does not stop that. It re-reads the head on every poll, so a push
during the wait restarts the wait for the new head. `--no-merge` only waits and reports. Exit codes: 0 merged, 1 settled but
not CLEAN (the failing checks are printed), 124 timeout.

By hand, the same steps:

```bash
gh pr checks <N>                                   # can show a stale "pending"; confirm with:
gh run list --branch <branch> --limit 3
gh pr view <N> --json mergeStateStatus,headRefOid  # merge only when CLEAN
H=$(gh pr view <N> --json headRefOid -q .headRefOid)
gh pr merge <N> --merge --match-head-commit "$H"   # merges exactly what CI saw
```

A pull request that changes only Markdown outside `bridgeforge/`, `tests/`, `probe-mod/`, `tools/` and `.github/` runs
Lint and Documentation tests (the modules in `tests/doc_tests.json`); its other checks show as skipped, and the merge to
main runs everything (`tools/ci-scope.py`, 96.5 C3). A test that starts reading a document belongs in that list.

Before merging, a branch behind main takes main in: `gh pr update-branch <N>` (or `git merge origin/main` in its worktree),
then CI again, then merge by the new head. A pushed branch is never rebased.

After any merge of main into a branch, run `python tools/regen-generated.py` (or `python -m tests.test_cli_golden --write`
and `python -m bridgeforge docs-index`) and commit the result: when both sides added commands, git's merge of
`docs/COMMANDS.md` and `tests/cli_help_golden.json` can come out clean but stale (2026-11-19, caught by the pre-push hook).

Merge only green PRs. After merging:
- `git fetch`.
- Bring main into the other open item branches the same way (merge, not rebase, once pushed), stashing any uncommitted
  work first.
- Pull on Test1 (the `test1-run` skill, or `git -C "<Test1 repo>" pull --ff-only origin main`).
- Remove the worktree with `git worktree remove ../BridgeForge-<item>`.

## Releases

When the owner asks for a release, or after a batch of merged items:
1. Run `python -m bridgeforge release-notes assemble --version <V>` to move the fragments under the version heading.
2. Bump the version in pyproject.
3. Ship it through the same PR route.
4. Tag only on the owner's word.

`release-notes --check` lists the pending fragments.
