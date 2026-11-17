- The shipped-copy audit reads a fixer run's `files` in the escalation ledger (ROADMAP-3 93.44). Bultach's
  `star_gen_data.csv`, added by the `procgen-star-row-missing` fixer, had stayed unexplained. Ledger lines that are not
  objects are skipped instead of raising.
