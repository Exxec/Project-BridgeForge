- Item 93.33: every zip and jar entry the package reads now goes through `zipsafe.read_limited` or the streamed
  `zipsafe.entry_sha256`; there were 35 unbounded reads in 25 modules. `test_safeio_ratchet` fails on any new unbounded
  `ZipFile.read`, and the scanner's jar walk names the class entries it skipped.
