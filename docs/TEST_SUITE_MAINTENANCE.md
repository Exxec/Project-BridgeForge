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
