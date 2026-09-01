# Changelog

## Unreleased

Work landed since the `v0.1.0-alpha.1` tag; the package version has not yet
moved past 0.1.0.

- Add a review-gated bytecode inspection, diff, plan, and apply workflow
  bounded to pinned-ASM class/JAR symbolic remaps written to a separate
  output copy (`bytecode-inspect`, `bytecode-diff`, `bytecode-plan`,
  `bytecode-apply`); see `docs/BYTECODE_BOUNDARY.md`.
- Add read-only ZIP archive intake (`archive-preflight`, `archive-stage`)
  that reports traversal, symlink, duplicate-member, and mod-root ambiguity
  evidence before any extraction, and never writes beside the input archive.
- Add read-only, budget-bounded multi-mod corpus auditing (`corpus-audit`)
  and two-directory release comparison (`release-evaluate`).
- Add local, review-only library API inventory/match research tooling
  (`library-api-inventory`, `library-api-match`) and an opt-in local
  library registry (`--library-registry`) that auto-resolves a mod's
  declared dependency IDs to local JARs for compile validation.
- Add deterministic output-copy JAR packaging after a successful compile
  (`package-jar`), with an input/output SHA-256 manifest confirming the
  source JAR was preserved.
- Bytecode rewriting is therefore no longer an alpha-1 limitation: it is
  available as a narrow, review-gated remap of exact same-descriptor
  symbols only. Library API *transformation* and cross-mod dependency
  graphing remain unimplemented; see the roadmap.

## 0.1.0 — Alpha 1 — 2026-08-31

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
