- Records name the real game build (ROADMAP-3 96.5 A1). Every record used to say "RC8", also for mods revived against
  0.98.5a-RC7 on an RC7 rig: archive notes, MOD_CHANGELOG lines, credits files, the master log, live-run headings and report
  drafts. They now name the build each mod was revived for, from its `gameVersion` or its last revive's target, and the build
  each rig's core reports.
- Group records no longer credit the owner with runs the harness played.
- Help texts that called RC8 the core (`revive --vanilla-core`, `close --reason`, `relink`, `scan --compile-check`,
  `compile-check`, `content-diff`, `rebuild-from-reference`) now name the target or the given core.
