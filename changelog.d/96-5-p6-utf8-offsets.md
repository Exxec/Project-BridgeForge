- Finding the non-UTF-8 bytes of a data file takes one pass instead of re-decoding the rest after every bad byte (ROADMAP-3
  96.5 P6). The offsets are unchanged. The suite's slowest test, a large CP-1252 rules.csv, went from 37.6 s to under
  0.75 s.
