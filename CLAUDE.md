# BridgeForge: notes for Claude sessions

BridgeForge is an offline, evidence-first toolkit for reviving legacy Starsector mods on
0.98a-RC8 (Java 17). Charter: `docs/PROJECT_CHARTER.md`. Command guide:
`docs/BRIDGEFORGE_REVIVAL_GUIDE.md`. Plan and history: `ROADMAP.md` (numbered items; the newest, 70 onward,
are at the end of the file), `CHANGELOG.md`. Direction for fixers, checks and automation: item 73,
`docs/AUTOMATION_PLAN.md`, including the owner's 2026-10-14 decisions on what may run without a person. Local sessions also
have `AGENTS.md` (gitignored), the agent contract: who may decide what, escalation rules, sister projects.

## Non-negotiables

- Understand first, modify second, validate always. Never edit an input mod in place; work on
  copies under `In operation/` or emit patches.
- Findings are `SAFE`, `REVIEW`, `MANUAL` or `UNKNOWN` with explicit confidence. `MANUAL` and
  `UNKNOWN` are never auto-applied. Compiling is not proof of behaviour.
- A claim about the game or its API needs evidence (javap output, a vanilla file, a log line).
  Record the evidence and date in the code comment or roadmap entry, as the existing code does.
  Proven runtime behaviour goes in `docs/RC8_BEHAVIOUR.md` (one row per fact, cite its id in code).
- The real Starsector install is read-only. Rig commands refuse to run unless the rig's
  `starsector-core` is a junction/symlink.
- Never commit Fractal Softworks game files (jars, art, data). The probe's mission icon is
  copied in locally for that reason (see `.gitignore`).

## Long-running commands (rule since 2026-09-27)

Every command that walks a whole queue, corpus or archive must (1) print one progress line per item
as it finishes (`[12/305] Mod: detail (38.2s)`, via `bridgeforge/progress.py`'s `report`), with
`--quiet` to turn it off, and (2) append each finished item to a checkpoint (`progress.Checkpoint`,
a `*.partial.jsonl` whose header names the inputs) so an interrupted run resumes instead of starting
over, deleting it once the full result is written. List the command in
`progress.LONG_RUNNING_COMMANDS`; `tests/test_progress.py` enforces it. Found when `finding-stats
--scan` ran 44 minutes silent over 305 workspaces, with `dependency-graph` and `corpus-index build`
the same. When running such a command from a session, run it in the background and read its
progress rather than waiting blind.

## Things learned the hard way

- Measure "before" states on a mod's `original/`, not `working/`: working copies are already
  fixed, so `compile-check` or `rebuild-from-reference` there shows nothing. `original/` usually nests
  the mod one folder down (`original/<Mod Name>/`).
- `rebuild-from-reference` merges only `.ship`/`.wpn`/`.variant`/`.skin`/`.system` JSON, not `.java`
  or CSV. It reports a CONFLICT only where the mod and RC8 both changed a value; a value only RC8
  changed takes RC8's.
- Reference installs sit beside RC8 in `C:\Program Files (x86)\Fractal Softworks\`: `Starsector62`,
  `Starsector7.2`, `Starsector8.1`, `Starsector9a` (0.9a, 2018-11), `Starsector9.0` (0.91a,
  2019-05), `Starsector9.5.1a`. `SectorAPI.addMessage`/`createFleet(String, String)` were removed
  between 0.8.1a and 0.9, so API-drift checks for them need the 0.8.1a reference.

- Judge loose scripts with RC8's own Janino (`compile-check` runs it; 2026-09-27), not by pattern: Janino 2.7.8
  accepts a typed for-each over `List<String>`, but rejects lambdas and a method call on a generic-typed value
  (erased to Object). The game runs with `-noverify`, so the harness does too. 47 of 48 mods the old pattern
  flagged compile clean.
- RC8 content behaviour, live-proven 2026-09-27: a variant naming a missing weapon is a Fatal dialog at New
  Game; a missing hull mod in a variant is dropped silently. A Fatal dialog never reaches the redirected log:
  `bf-test.ps1` records dialog text in `<TESTID>.windows.txt`, and `log-triage` reads it.
- `bf-test launch` logs only the session it starts; a player relaunch logs only to the rig's `starsector.log`.
- Rebuild or patch a jar only with the JDK `jar` tool (or `patch-jar-class`): a jar rewritten with .NET `ZipArchive` Update mode loaded no class at all in RC8 (every class fell back to loose-script compile; Station Augments 2026-10-11).
- Edit code with Write/Edit, not Python-in-bash heredocs: `
`, `

` and `\"` inside a heredoc'd Python string are
  unescaped once by Python and land as real newlines or quotes, which broke six edits in one session. For a long
  generated file, write it to the scratchpad with Write and run it. Git Bash's `/tmp` is not Python's `/tmp` on Windows.
- The shipped copy is every root file and every top-level folder except tool/build folders (`copy_drift`); allowlists
  dropped `sun_fr/` (GRP-3) and a root `*.json.default` (GRP-7), both Fatal at startup. Probe groups must enable
  dependencies of dependencies (SPARKLE -> SOTF -> four libraries).
- A mission whose `MissionDefinition.java` names a variant RC8 lacks is Fatal when that mission is started, not at New Game
  (found 2026-10-12 in Aivon Republic, Sylphon RnD and Silent Armada; `content-ids|mission-variant:` FAIL in the probe). A
  mission row listed by both a list-replacing mod and the probe mod is one row (the game loads an id once).
- `settings.json` lists add to vanilla's, not replace (`ruleCommandPackages`, 2026-09-27; ROADMAP item 19).
- 0.6-era stations sold from the station's own cargo; RC8 trades only through markets. Give the entity a market;
  for a hostile faction, a submarket with `isBlackMarket()` is reachable with the transponder off (`rules.csv`
  `marketPostOpenNoTrade`). A one-off commodity nothing produces needs the `nonecon` tag or it will not show.
  "Any weapon" random stock must skip `restricted`/`threat`/`omega`/`dweller`/`no_sell` weapons.
- Addon retargets: check the base mod's renamed ids and sprite prefixes, and compare PNG sizes before reusing
  art (SOTF `fronsec_` -> `sotf_`, Vow redrawn). SOTF hulls are `codex_unlockable`: absent from the codex until met.

## Work that needs a local machine

Anything that needs the game install, a test rig, Windows or `In operation/` cannot be finished
in a cloud session. Build and test what you can, then add an entry to `docs/LOCAL_HANDOFF.md`
(what to run, what "done" looks like, which roadmap item) and say so in the roadmap entry.

## Layout

- `bridgeforge/` the package. Commands: `cli.py` is 60 lines; every command's parser and handler lives in a
  `cmd_*.py` or its own module and is listed in `cli_commands.COMMAND_MODULES` (a module defines
  `add_parser(subcommands)` and `run_cli(args)`; a new command is a module plus one line there). Checks:
  `scanner.py` keeps `scan_mod`, `_scan_jars` and re-exports every moved name; the checks live in 20
  `scan_*.py` modules (no module imports `scanner`). `fixers.py` holds the `fix` command's rewrites.
- `tests/` unittest suite; `tests/support.py` has `resolved_temp_dir()` and `link_dir()`.
- `probe-mod/` the in-game probe (Java, public API only); built by `build-probe-mod`.
- Gitignored and local-only: `In operation/`, `Done/`, `AGENTS.md`, `tools/*.ps1` (except
  `bf-test.ps1`), `.githooks/`. RevenantLib is a separate private repo, `Exxec/RevenantLib`
  (`working/`, `original/`, `reports/`); `revenantlib-check` verifies it provides what the fixers call.

## Hardening rules (ROADMAP item 70, 2026-10-12)

- Write files with `safeio.atomic_write_text`/`atomic_write_json` and delete trees with `safeio.safe_rmtree(path, allowed_roots)`
  (refuses junctions and paths outside the roots). `tests/test_safeio_ratchet.py` counts bare `write_text`/`rmtree` per file
  against `tests/safeio_baseline.json`, which may only shrink.
- Read jar and zip entries of untrusted mods with `zipsafe.read_limited`, never `ZipFile.read`.
- Accepted-finding baselines are stamped with the mod version and expire on any version change (`baseline-audit`,
  `baseline-accept`); `archive` refuses a stale baseline unless `reports/SHIPPED_CHANGES.json` carries a written `baseline` reason.
- `tests/known_failures.json` lists known environmental failures with an expiry; `test_guard` reports them without failing.
- `tests/test_cli_golden.py` pins the `--help` hash of every command: a change to the command line fails it; if deliberate,
  `python -m tests.test_cli_golden --write` and review the diff.
- Before merging an agent's branch run `bridgeforge agent-diff-check BRANCH` (deleted files, files cut by over a fifth).
- Line endings are LF (`.gitattributes`; batch files CRLF). `state-snapshot --to DIR` keeps an append-only copy of `Done/`,
  `bridgeforge-state/`, the working copies and the memory folder. It runs by itself after every archive when
  `bridgeforge-state/snapshot.json` names a destination (owner rule 2026-10-12: after major new revisions, not on a weekly
  clock). `rig-reset` returns a rig to a known state.
- Live harness: the game launcher waits for a click (`auto_click=True` for any new boot path); the probe row in the mission
  list is found by unique mission id and the list is scrolled two ticks per row. A LIVE_STUCK with no `combat-round` line in
  the log means another mission started, not that the probe's combat hung.
- Run `ruff` from a Python that has it: the project `.venv` does not (use the Python 3.14 install first on `PATH`, see
  `docs/LOCAL_HANDOFF.md`). It runs pyflakes plus flake8-bugbear (`B`, four noisy rules ignored in `pyproject.toml`).
- Workspace arguments take a path (`"In operation/<name>"`); `audit-explain` refuses one without `working/`.

## Checks before committing

```bash
ruff check .                              # pyflakes + bugbear + syntax; one-line statements are house style
python -m bridgeforge.test_guard          # full suite; also fails if the checkout changed
python -m bridgeforge docs-index          # after adding a check or CLI option; commit docs/*.md
uv lock --check                           # after touching pyproject dependencies
```

Optional extra: `pip install ".[archives]"` (py7zr) lets `corpus-index` read `.7z`; tests needing it skip
without it. The web-session hook installs it.

After a push, watch the run (`gh run watch <id> --exit-status`): CI was red for a day unnoticed (2026-10-13) because a local suite on
one Python passed while argparse output, home and checkout paths, and junction handling differ on the CI matrix.

CI (`.github/workflows/ci.yml`) runs all of these, plus the tests on Windows and Ubuntu with
Python 3.10–3.13 and a coverage floor (`[tool.coverage.report] fail_under` in pyproject; raise
it when coverage rises, never lower it).

## Test conventions

- Use `resolved_temp_dir()` for path-sensitive fixtures: Windows runners use 8.3 temp aliases
  (`RUNNER~1`) and product code resolves paths.
- Use `link_dir()` for a rig's `starsector-core`: a junction on Windows, a symlink elsewhere.
- Tests must not write into the checkout (`test_guard` fails the run if they do).
- Every new finding id needs a test that names it; `tests/untested_checks_baseline.json` may
  only shrink (`test_untested_findings_can_only_shrink`).
- `tests/support.py` is shipped in the sdist (`MANIFEST.in`).

## Mod changelog (owner rule 2026-09-30)

`MOD_CHANGELOG.md` lists bigger updates to revived mods by date, with mod name and version (`archive` adds one per
archived mod). Add a line with `bridgeforge mod-changelog add MOD "what changed" --version V` for any other bigger
update: a new revision, a crash fixed, a translation. When a shipped mod changes after archiving, iterate its version
(`+bf.N`) and record it there.

## Commits and roadmap

- Commit subjects follow the roadmap: "Fix item N: ...", "Add item N: ...". The body explains
  what was found, the evidence, and ends with the full-suite result, e.g.
  "Full suite: 966 tests, OK (skipped=10)."
- When an item is finished, mark it `**Done <date>.**` in `ROADMAP.md` with what was built and
  which tests cover it.
