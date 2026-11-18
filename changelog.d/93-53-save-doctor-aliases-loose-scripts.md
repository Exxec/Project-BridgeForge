- Fix: `save-doctor` resolves the XStream aliases a mod's plugin registers (Star Lords' `faction.LawProposal`, `ai.LordAI`)
  and the classes of loose `.java` scripts, which read as unresolved classes and made loadable saves WILL_LIKELY_FAIL
  (ROADMAP-3 93.53). Three of the owner's seven RC8 saves now read NO_KNOWN_PROBLEM.
