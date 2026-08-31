# Scanner evidence model

Bridgeforge reports evidence, not a verdict that a mod is broken.

- A strict JSON rejection is `unverified-json-syntax` unless Bridgeforge has
  target-parser evidence for the exact syntax. Trailing commas have such
  evidence and are reported separately as `REVIEW`.
- A JSON file that cannot be read is `unreadable-json` (or
  `unreadable-mod-info`), not parser-tolerance evidence.
- Character decoding is distinct from CSV structure. A non-UTF-8 CSV is an
  encoding-review finding, not an invalid-CSV finding.
- Missing or untrusted metadata emits `version-inference-blocked`; it prevents
  confident environment claims rather than inventing a target version.
- Duplicate source layouts and large bundled archives are structural ambiguity
  findings. They require ownership/authority review before compilation,
  migration, or redistribution. Source-layout identity uses raw file bytes,
  not replacement-decoded text.
- A modern game target does not make historically loose data syntax safe by
  itself; parser tolerance remains target-evidence-specific.
