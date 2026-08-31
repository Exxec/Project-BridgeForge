# Changelog

## 0.1.0a1 — 2026-08-31

First public alpha of the read-only Bridgeforge compatibility workflow.

- Scan Starsector mod folders without modifying them and emit Markdown plus
  JSON compatibility artifacts.
- Use evidence-aware JSON, encoding, metadata, archive, bytecode, source, and
  dependency findings; `UNKNOWN` is not a breakage verdict.
- Provide explicit working-copy planning, approval-gated application,
  provenance, conflict, compile, validation, save-risk, and review artifacts.
- Include Windows and Ubuntu CI on Python 3.10–3.12 with Java 17.

### Alpha limitations

- Migration packs are scaffolds only; no library API transformation is shipped.
- Runtime launching, decompilation, bytecode rewriting, and cross-mod analysis
  are not part of this alpha release.
- Scanner output is evidence for review, not proof that a mod will load or
  behave correctly.
