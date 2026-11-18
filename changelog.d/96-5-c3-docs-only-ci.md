- CI: a pull request that changes only documents runs Lint and the six test modules that read a document
  (`tests/doc_tests.json`, measured over the whole suite), not the whole suite on every runner; a push to main still runs
  everything (ROADMAP-3 96.5 C3). Every check name still reports, and a failed scope decision runs everything.
