- Fix: `save-doctor` (and `installed_mods`, the provider Salvor imports) no longer reports VERSION_CHANGED when a mod writes
  its version as `{"major", "minor", "patch"}` and the save recorded the same version dotted (ROADMAP-3 93.52). On Test1's
  rig saves 32 of 43 such findings were false; the 11 left are real.
