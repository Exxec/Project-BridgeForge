- `revive --apply` registers the scan it decided on, dependency providers included, instead of scanning the finished tree a
  second time without them; compile-check compiles the core's loose scripts and the Janino harness once per process, not on
  every scan (about 1.8 s a scan on RC7) (ROADMAP-3 96.5 P3).
