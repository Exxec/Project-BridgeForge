- Faster scans with provider roots: each scan step that looks a dependency's provider up now reads only that provider's
  mod_info.json, not its CSVs, specs, jars and sources (ROADMAP-3 96.5 P2). One scan used to build the full provider index
  five times.
