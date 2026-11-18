- Faster batch scans: the vanilla core's API classes, loose scripts and faction ids are read once per process, not twice per
  scan (ROADMAP-3 96.5 P7). About 1.2 s saved per scan after the first, about 4 minutes over a 184-archive `done-audit`.
