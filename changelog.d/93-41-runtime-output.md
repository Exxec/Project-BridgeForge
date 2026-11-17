- A live run under StarsectorPrepatcher no longer reads as drifted (ROADMAP-3 93.41). The agent writes
  `logs/prepatcher.log` into its own mod folder while the game runs; that folder now stays out of the mod's staged hash
  (`run_manifest.RUNTIME_OUTPUT_DIRS`). Every other mod hashes exactly as before.
