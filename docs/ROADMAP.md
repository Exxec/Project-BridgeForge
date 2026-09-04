# BridgeForge roadmap

## Completed evidence foundations

- Read-only mod, JAR, bytecode, source, JSON-tolerance, dependency, and
  campaign-identity analysis.
- Copy-only workspaces, review-gated source/bytecode changes, build-profile
  evidence, and explicit runtime-smoke profiles.
- Cross-mod, release-lineage, corpus, and explicit local-library API reports.

## Current hardening tranche

1. Archive preflight reports extraction hazards and mod-root ambiguity.
2. Explicit archive staging records a hash-backed sidecar manifest and never
   writes into the archive or staged mod directory.
3. Corpus audits expose deterministic file/JAR budgets and aggregate observed
   workload, including skipped-budget rows.
4. Library API inventories are schema-validated before matching; malformed,
   stale-schema, or tampered reports are rejected rather than interpreted.
5. CLI safety paths have direct regression coverage alongside library-level
   tests.

## Intentionally blocked pending verified evidence

- MagicLib, LazyLib, AshLib, and other library migrations remain scaffolded or
  research-only until their evidence contract is complete.
- Reflection, wildcard imports, bytecode-only references, runtime behavior,
  and save compatibility remain review evidence, not automated conclusions.
