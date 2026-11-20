- Gene closures now treat a literal that only names another id as a suspect, not a need (94.G2 slice 13; owner ruling
  2026-11-20). In a jar class, each string is followed on the operand stack to the call that takes it:
  - **Mentions:** `hasHullMod` checks, `contains` checks, stat-modifier and status keys, and constants nothing loads. These
    are recorded as suspects.
  - **Needs:** uses, and anything that cannot be followed.

  Vendor-plan no longer reads a string equal to a same-package class name as a use of that class.
