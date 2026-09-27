# BridgeForge: notes for Claude sessions

BridgeForge is an offline, evidence-first toolkit for reviving legacy Starsector mods on
0.98a-RC8 (Java 17). Charter: `docs/PROJECT_CHARTER.md`. Command guide:
`docs/BRIDGEFORGE_REVIVAL_GUIDE.md`. Plan and history: `ROADMAP.md` (P14 is the live track),
`CHANGELOG.md`.

## Non-negotiables

- Understand first, modify second, validate always. Never edit an input mod in place; work on
  copies under `In operation/` or emit patches.
- Findings are `SAFE`, `REVIEW`, `MANUAL` or `UNKNOWN` with explicit confidence. `MANUAL` and
  `UNKNOWN` are never auto-applied. Compiling is not proof of behaviour.
- A claim about the game or its API needs evidence (javap output, a vanilla file, a log line).
  Record the evidence and date in the code comment or roadmap entry, as the existing code does.
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

## Work that needs a local machine

Anything that needs the game install, a test rig, Windows or `In operation/` cannot be finished
in a cloud session. Build and test what you can, then add an entry to `docs/LOCAL_HANDOFF.md`
(what to run, what "done" looks like, which roadmap item) and say so in the roadmap entry.

## Layout

- `bridgeforge/` the package; `cli.py` wires every subcommand; `scanner.py` holds the checks
  (`scan_mod`); `fixers.py` the `fix` command's rewrites.
- `tests/` unittest suite; `tests/support.py` has `resolved_temp_dir()` and `link_dir()`.
- `probe-mod/` the in-game probe (Java, public API only); built by `build-probe-mod`.
- Gitignored and local-only: `In operation/`, `Done/`, `AGENTS.md`, `tools/*.ps1` (except
  `bf-test.ps1`), `.githooks/`. RevenantLib is a separate private repo, `Exxec/RevenantLib`
  (`working/`, `original/`, `reports/`); `revenantlib-check` verifies it provides what the fixers call.

## Checks before committing

```bash
ruff check .                              # pyflakes + syntax only; one-line statements are house style
python -m bridgeforge.test_guard          # full suite; also fails if the checkout changed
python -m bridgeforge docs-index          # after adding a check or CLI option; commit docs/*.md
uv lock --check                           # after touching pyproject dependencies
```

Optional extra: `pip install ".[archives]"` (py7zr) lets `corpus-index` read `.7z`; tests needing it skip
without it. The web-session hook installs it.

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

## Commits and roadmap

- Commit subjects follow the roadmap: "Fix item N: ...", "Add item N: ...". The body explains
  what was found, the evidence, and ends with the full-suite result, e.g.
  "Full suite: 966 tests, OK (skipped=10)."
- When an item is finished, mark it `**Done <date>.**` in `ROADMAP.md` with what was built and
  which tests cover it.
