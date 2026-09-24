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
