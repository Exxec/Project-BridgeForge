# Test-suite maintenance threshold

The suite is separated by concern so a failure is visible in its domain:

- `test_scanner.py`: intake, scanner evidence, archives, corpus, and API inventory;
- `test_workspace.py`, `test_migrations.py`, and `test_java_ast.py`;
- `test_build.py`, `test_packs.py`, `test_conflicts.py`, and `test_save_risk.py`;
- `test_provenance.py` and `test_pipeline.py`.

Keep individual modules focused, and split one further when either condition is
observed:

- the file exceeds 50 KiB or 700 lines;
- a change regularly requires editing unrelated test domains; or
- failures are difficult to locate because of a mixed layout.

The split is hygiene only and does not block reliability or product work.

## Hermetic suite runner

Run `python -m bridgeforge.test_guard` from the checkout root. CI uses this runner
on all six Windows/Linux and Python-version combinations. It compares git status,
hashes tracked and non-ignored untracked files (including pre-existing dirty files),
and inventories/hashes the ignored `probe-mod/releases/bridgeforge-probe` tree
before and after unittest. Changed inputs fail the run even when tests pass.
This is an end-state guard, not a filesystem access sandbox: temporary writes that
are restored, other ignored build outputs, and writes outside the checkout are
not detected. No files are restored automatically.

Use `tests.support.resolved_temp_dir()` for new path-sensitive fixtures; it yields
a resolved `Path` so Windows runner 8.3 aliases do not change comparisons.

Managed-sandbox diagnostics (2026-09-12): four boot cleanup tests and two real
probe compiler tests failed with process/log-lock or compiler-resource permission
errors. Running `tests.test_boot_test` and `tests.test_probe_mod_build` outside the
sandbox passed all 12 tests. These failures are environment limitations, not
evidence that a behavior-changing process fix is needed.
