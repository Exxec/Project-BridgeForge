# Test-suite maintenance threshold

`tests/test_scanner.py` currently contains 35 tests across scanner, workspace,
migration, AST, build, pack, conflict, save-risk, provenance, and pipeline
concerns. It is deliberately retained as one file for now: the tests share
small local fixture helpers and the current review/edit cost remains low.

Split it into the roadmap's named modules when one of these conditions is
observed:

- the file exceeds 50 KiB or 700 lines;
- a change regularly requires editing unrelated test domains; or
- failures are difficult to locate because of the mixed layout.

The split is hygiene only and does not block reliability or product work.
