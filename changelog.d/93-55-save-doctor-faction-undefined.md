- Fix: `save-doctor` reports FACTION_UNDEFINED when a save holds a faction that neither the core nor an enabled mod
  defines. The game stops loading such a save in `Faction.readResolve`; a Templars save with Templars removed had read
  NO_KNOWN_PROBLEM (ROADMAP-3 93.55).
