- Faster scans: the settings-key and procgen-argument checks start javap once per jar, not once per class (ROADMAP-3 96.5
  P1). On United Aurora Federation's three jars that is 5 launches instead of 252, and about 2 s instead of 49.5 s, with the
  same findings.
