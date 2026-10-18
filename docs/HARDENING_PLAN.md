# BridgeForge hardening plan (ROADMAP item 70)

Original proposal (owner request 2026-10-12: "plan any possible hardening for bridgeforge overall"). Some sub-items were
subsequently implemented; see ROADMAP item 70 and [ROADMAP_STATUS.md](ROADMAP_STATUS.md). The measurements below are
historical observations on 2026-10-12, not current counts or proof that all items are implemented.

Owner-approved specification revision 2026-10-17: [ROADMAP_IMPLEMENTATION_HANDOFF.md](ROADMAP_IMPLEMENTATION_HANDOFF.md),
item 75, refines H1.5/H1.6 (content identities and all acceptance paths), H3.2/H3.3 (run evidence and current statuses),
and H4 (isolated restore proof). Its R1-R8 acceptance conditions take precedence over weaker original wording here.
In particular, an acceptance-time working hash is not launch provenance, a link is not live proof, and snapshot creation
is not restore qualification. These extensions are planned, not newly implemented by this document update.

## What the evidence says

Measured on `main` (`10162977`):

| Fact | Number |
|---|---|
| Package modules / test files | 161 / 182 |
| `scanner.py`, `cli.py`, `fixers.py` | 8,045 / 4,110 / 3,438 lines (house soft ceiling: 800) |
| `cli.main()` and `cli.build_parser()` | one function of 2,852 lines and one of 1,151 lines |
| Scanner functions over 100 lines | 13 of 257 (longest 243) |
| `write_text(` call sites / modules with an atomic-write pattern | 182 / 1 (`migrate.py`) |
| `shutil.rmtree` / `.unlink(` call sites | 15 / 32 |
| `except Exception` / `shell=True` | 23 / 1 |
| Workspace accepted-finding baselines (`reports/baseline.json`) | 186 (3 with `probe_accepted.json`) |
| Lint rules | ruff `E9`, `F` only (pyflakes and syntax); no type checker |
| CI | Ubuntu and Windows, Python 3.10-3.13, coverage floor 80 |
| Known failing test on a clean checkout here | `test_locks::test_child_with_cwd_inside_target_is_found` |

Failures found in these two days, grouped by what kind of defect they are:

| Class | Example | Cost |
|---|---|---|
| Generated artefact shared between variants | every Fast Rendering launcher used one `fr.filtered.vmparams`; the last variant written won, and `--prepatcher` put the agent in all of them | wrong results from two runs; found by chance |
| Generated command line never executed to check it | `-javaagent` appended after the main class in an argument file is an application argument | Toolbox fork reported "agent not installed" |
| Hand-merged data structures drop keys silently | `merge_configs` dropped `class_sweep` and `mission_fleets`, so group runs never ran those checks | checks silently absent for weeks |
| Wrong tool for a binary format | .NET `ZipArchive` rewrite of a jar: the game loaded no class from it | a failed run and a rebuild |
| Accepted baselines hide real bugs | Zorg's port bugs were flagged by the scanner and sat in the accepted baseline; bf.7 shipped without bf.5/bf.6's fixes | a wrong archive, caught by chance |
| Archive not tied to what was tested | the archive note says "the shipped files are the ones tested"; nothing enforces it | trust, not proof |
| Cache key missing an input | atlas content hash ignored the extractor's own source: after a code change the index kept old facts | stale results |
| Predictions treated as findings | Arkgneisis blamed for a shared-memory save crash (base rate not checked); a predicted AoTD effect that live runs refuted | wrong statements to the owner |
| Hand edits to rig state between runs | `enabled_mods.json` edited by hand for every AoTD run | error-prone, unrecorded |
| Wide edit surface in one file | all three merge conflicts of the day were in `cli.py` / `probe_group.py` | merge work, risk of a bad merge |
| Agent overwrote an existing file | `migrate.py` replaced, noticed and restored | near miss |

## Principles

1. **A generated thing is checked by using it**, not by reading its text (launchers, configs, jars, archives).
2. **State is written atomically and deleted only inside a stated root.**
3. **Contracts between two representations are tested**: Python config writer vs the probe's Java reader, `build_probe_config` vs
   `merge_configs`, CLI parser vs docs.
4. **Evidence has a label**: PREDICTED (static) or OBSERVED (a run), with the run id, and a ledger measures how often predictions held.
5. **Exceptions expire.** Accepted findings and known-failing tests carry a reason, a date and a re-check trigger.
6. **Refactors are bracketed by golden tests** that prove behaviour did not move.

## Phase H1: small, high value (each about a day or less)

| # | Item | Based on | Done when |
|---|---|---|---|
| H1.1 | `bridgeforge/safeio.py`: `atomic_write_text/json` (temp file in the same folder, fsync, `os.replace`) and use it for state and report files: `release_policy.json`, `PROBE_GROUPS.json`, `bridgeforge-state/*`, checkpoints, `MOD_CHANGELOG.md`, archive notes, probe config | 182 `write_text` sites, 1 atomic module | a test kills a write mid-way (fake failing `replace`) and the old file is intact; a lint test fails on a new bare `write_text` to a state path |
| H1.2 | Guarded delete: `safe_rmtree/safe_unlink(path, allowed_roots)` refusing outside `In operation/`, `Done/_replaced*`, the rig and temp; audit the 15 + 32 sites | 47 delete sites, one safety-classifier block on an over-broad `Remove-Item` | every delete goes through it; tests for refusal outside roots, symlink/junction targets and the repo root |
| H1.3 | Launcher self-test in `java-matrix setup`: every `-javaagent` is a JVM option before the main class, argument files exist and are unique per variant, agent jars exist, Prepatcher is last, and a `-version` run of each variant's flags succeeds; fail setup loudly | the two launcher bugs of 2026-10-12 | setup refuses a launcher whose agent comes after the main class (test reproduces the bug) |
| H1.4 | Schema contract tests: every key `build_probe_config` writes is read by `ProbeConfig.java` and handled by `merge_configs`; every `ProbeSetup` kind has a `_SETUP_PATTERNS` entry and vice versa | `class_sweep`/`mission_fleets` drop | adding a config key without the other two sides fails a test |
| H1.5 | Baseline hygiene: each accepted entry gets `reason`, `date`, and the mod version it was accepted at; `baseline-audit` lists entries older than N days, accepted at an older version, or for a check whose definition changed (check ids carry a revision); rebuilding a mod from another line re-opens its baseline | Zorg; 186 baselines | audit lists today's baselines grouped by age; Zorg's case is caught by a test; owner chooses N |
| H1.6 | Archive guard: `probe-group install` records a tree hash per member; `record --archive` refuses when the working copy differs from the tested copy; it also warns when the new archive reverts a file an earlier archive of the mod changed against `original/` and the changelog does not say so | Zorg bf.7; the archive-note claim | a test: edit after the live run -> refused; revert of an earlier fix -> warned |
| H1.7 | Rig control: `probe-group install --also-enable ID ...` and named sets (`aotd`), recording the final `enabled_mods.json` in the run's ledger line; `rig-reset` restores a clean state (enabled mods, common files, old saves) | hand edits before most runs; 121 accumulated saves | no run needs a hand edit; a test covers the AoTD set |
| H1.8 | Known-failure baseline for tests (ROADMAP 60e(3)): a file listing tests that may fail here with reason and an expiry date; `test_guard` reports them and fails on any other failure or an expired entry | `test_locks` on every full run | the suite exits 0 here with the known failure listed; a new failure or an expired entry exits 1 |

## Phase H2: medium

| # | Item | Based on | Done when |
|---|---|---|---|
| H2.1 | Split `cli.py`: one `add_parser` + `run` per command module and a registry, as the Atlas already does; `main()` below 200 lines | 2,852-line `main`, 1,151-line `build_parser`, all three merge conflicts of the day | a golden snapshot of every command's `--help` is identical before and after; no module over the soft ceiling without a reason |
| H2.2 | Split `scanner.py` by check family (data, code, jars, campaign, probe) behind the same `scan_mod` API | 8,045 lines, 199 check ids, 13 functions over 100 lines | `finding-stats` over the whole corpus is identical before and after (finding ids and counts per mod) |
| H2.3 | Lint and types: ruff adds `B` (bugbear), `BLE`, `S` for subprocess and tempfile, `SIM` selectively, with per-file ignores for the current exceptions; pyright (non-strict) on new modules | `E9`,`F` only; 1,716 of 1,810 defs already annotated | CI runs both; the exception list only shrinks |
| H2.4 | Untrusted-input limits: size and time caps in the class-file parser, jar and zip readers, CSV/JSON loaders and the Atlas; fuzz-style tests with truncated and oversized archives | mods and the 42 GB backlog are untrusted inputs; the Atlas parses jars in pure Python | no input makes a command hang or exhaust memory in tests; a skipped file is reported, not silent |
| H2.5 | Test reliability: fix `test_locks` or make it skip with a stated cause; run the suite once a week with `--randomize`/reverse order to find order dependence; track suite time | 12 skip decorators, one environmental failure, 7-minute suite | a weekly CI job; the time and failure history recorded |

## Phase H3: evidence discipline

| # | Item | Based on | Done when |
|---|---|---|---|
| H3.1 | Prediction ledger: when a static finding is live-tested, record `confirmed` or `refuted` with the run id; Atlas output labels PREDICTED vs OBSERVED and `atlas precision` reports hit rates per rule (needs ROADMAP 67c originals) | DNEEP confirmed, Arkgneisis refuted, Arkgneisis-as-cause withdrawn | `atlas precision` prints a table; the AoTD sweep's top rows each get a verdict over time |
| H3.2 | Live ledger `reports/live-ledger.jsonl`: test id, members with versions and tree hashes, launcher file hash, Java, probe version, verdict, log paths; appended by `live`, `smoke`, `duel`, `regress`, `record` | results scattered across logs and roadmap prose | `bridgeforge ledger` lists runs; a regression pass can compare against each mod's last good run |
| H3.3 | `roadmap-lint`: a `Done` item must name a test file or a live test id; RC8 facts cited in code must exist in `docs/RC8_BEHAVIOUR.md` (the rule exists on paper) | claims made from memory this session | the lint passes on the roadmap after a one-time cleanup; CI runs it |
| H3.4 | Base-rate check in diagnosis tools: `save-doctor` and the Atlas report how many other objects share a suspect pattern before naming a culprit | the Arkgneisis misattribution | a diagnosis message includes "n of m similar objects" |

## Phase H4: environment and portability

- **Line endings**: a `.gitattributes` policy (LF in the repo, per-file exceptions) to stop the `LF will be replaced by CRLF` warning on every commit and the churn it hides.
- **Long paths and encodings**: a check in `rig-doctor` for `LongPathsEnabled` and for non-ASCII path hazards (the translator needs ASCII paths).
- **Dependency hygiene**: `pip-audit` in CI (one runtime dependency, `psutil`); keep the `uv.lock` check.
- **Backup of irreplaceable state**: wire ROADMAP 64's `migrate-inventory` and `migrate-verify` into a local snapshot, taken after each major new revision (every archive; owner 2026-10-12: not on a weekly clock), of `Done/`, `In operation/*/working`, `bridgeforge-state/` and the memory folder.

## Phase H5: working with agents

- **Pre-merge diff check** (`tools/agent-diff-check.py`): before merging an agent branch, list files that were deleted or shrank by more than 20 percent and files whose first commit is a rewrite of an existing path (the `migrate.py` near miss).
- **Edit-method rule enforcement**: the heredoc-Python rule cannot be detected; instead the delegation template carries it, and a smoke test rewrites a file with an embedded `\n` through the documented route.
- **Conflict hot spots**: H2.1 removes the main cause; until then, ask agents to add parsers through a registry function in their own module.
- **Instruction-file currency pass (H5.4, last step of the queue, owner request 2026-10-12):** once the other steps are done, review and update every agent-instruction file so it matches the repo as it then is: `CLAUDE.md`, the local-only `AGENTS.md`, `docs/LOCAL_HANDOFF.md`, the memory index and entries (`MEMORY.md` and linked files: drop stale facts, verify named files, commands and flags still exist), and any `.claude/` rules or hook notes in the repo. Fold in the lessons from this hardening work (safeio, zipsafe, baseline expiry, known-failure baseline, rig-reset, agent-diff-check, LF policy, new commands) and re-run the checks they cite. Done when each file's claims were spot-checked against the code and the date is recorded in the roadmap entry.

## Order and effort

1. **First week:** H1.3, H1.4 (they are cheap and protect the live-testing pipeline), H1.8, then H1.1 and H1.2 together.
2. **Second week:** H1.5, H1.6, H1.7, H3.2.
3. **Then:** H2.1 (with its golden snapshot) before H2.2; H2.3-H2.5 in parallel; H3.1, H3.3, H3.4 as the data accumulates.
4. **Whenever convenient:** Phase H4 and H5.

## Decisions for the owner

1. **Refactors (H2.1, H2.2):** worth the risk now, with golden tests first, or after the regression pass has produced a baseline of current results (recommended: after)?
2. **Baseline expiry (H1.5):** how old an accepted finding may get before it must be re-justified (suggested: 90 days or any change of the mod's version).
3. **Line endings (H4):** approve normalising to LF with a one-time renormalise commit?
4. **Archive guard (H1.6):** should a refused archive be overridable with a flag and a written reason, or never?

## What this plan deliberately leaves out

- Rewriting the scanner's checks: they work and are heavily tested; splitting is mechanical and bracketed by golden tests.
- Strict typing everywhere at once: the exception list approach avoids a flag day.
- Sandboxing the game rig beyond today's isolation: out of scope unless untrusted mods become a security concern, not just a compatibility one.
