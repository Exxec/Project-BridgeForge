- Security: a mod can no longer make compile-check run its own code (ROADMAP-3 93.46). A mod_info.json "jars" entry with
  line breaks reached javac's argument file, where a line break ends a token even inside quotes. That put `-proc:full`
  after `-proc:none`, so javac ran an annotation processor from the mod's jar. Fixes:
  - argument-file lines refuse line breaks;
  - jar paths holding control characters are left off the classpath;
  - `build` and the probe build now pass `-proc:none` too.
