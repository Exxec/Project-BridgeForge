# Project Bridgeforge roadmap

Bridgeforge follows the project charter in `docs/PROJECT_CHARTER.md`: understand first, modify second, validate always. The original mod is never changed in place.

## Post-1.0 research and gated automation

### Deferred migration findings from the 0.98a corpus audit

These are scanner-supported, review-gated migration tracks. They are intentionally
not automatic fixes: the audit establishes candidates, not authorial intent.

1. **Runtime placeholders:** classify reachable `UnsupportedOperationException`
   and equivalent stub paths, then require a source-level replacement and compile
   validation before proposing a migration.
2. **Configured class integrity:** reconcile configured plugin/script class names
   with the packaged JAR and source layout; distinguish obsolete configuration from
   an accidentally omitted class.
3. **Campaign spawn registration:** inspect disabled or commented-out registration
   paths and propose restoration only after validating lifecycle timing, campaign
   conditions, and duplicate-spawn safeguards.
4. **Target-bytecode compatibility:** detect classes beyond the selected Java/
   Starsector profile and provide a working-copy rebuild plan using the appropriate
   source and dependency evidence.
5. **Campaign-state coupling:** review persisted live objects, external memory
   keys, and hard-coded system/entity identifiers; propose resilient lookup or
   compatibility strategies only where the mod's intended content contract is
   evidenced.
6. **Target interface contracts:** detect active source implementing known
   target-engine interfaces while missing newly mandatory methods. Require a
   source-level implementation and compile validation; never generate behavior
   automatically from the signature alone.
   **Status: initial 0.98a `LevelupPlugin` contract check implemented after
   reproducing Edmund's Church 2.5's Janino load failure.**

### Audit-derived capability gaps

The 2026-09-01 archive and installed-mod corpus audits showed that several
existing signals need stronger context before they can drive a useful migration
plan.

1. **Reachability-aware finding triage:** correlate source and bytecode findings
   with configured entry points, plugin registration, and known campaign/mission
   callbacks. Rank likely-reachable stubs and obsolete APIs above dead code,
   examples, and inactive sources, while retaining the raw evidence.
   **Status: configured-entry-point and bounded unambiguous local-call evidence
   implemented; full call-graph analysis remains research.**
2. **Packaged-versus-source reconciliation:** classify a missing configured class
   as absent from the packaged JAR, present only in source, supplied by a
   dependency, or genuinely unresolved. Generate a rebuild/package diagnosis
   rather than treating every mismatch as the same defect.
   **Status: source-only, packaged, and unresolved classification implemented;
   explicit local API inventories can now attribute configured classes without
   asserting that unselected dependencies are absent.**
3. **Content-identifier ownership and resolution:** build a mod-local/vanilla/
   external identifier index for systems, entities, variants, factions, and
   memory namespaces. Use it to distinguish intentional self-references from
   brittle cross-mod or vanilla assumptions, and detect unresolved references.
   **Status: source-defined and mod-prefix attribution implemented for campaign
   system/entity lookups, with an optional explicit registry workflow; no global
   vanilla or external-mod registry is assumed.**
4. **Mission assembly validation:** statically resolve mission fleet/member,
   variant, ship, weapon, and map references across both historical mission
   layouts. Flag missing local members separately from references supplied by a
   dependency; add an opt-in mission smoke scenario where runtime support exists.
   **Status: local ship/fighter-wing, mission-variant hull, and mission-variant
   weapon resolution implemented; maps and runtime launch remain future work.**
5. **Dependency compatibility matrix:** extend external API-import evidence with
   declared dependency versions, bundled-library ownership, and verified local
   API inventories. Report version skew and unavailable API symbols without
   proposing substitutions unless a migration-pack contract exists.
   **Status: declared dependency versus direct API-import evidence plus opt-in
   local class and unambiguous method-name inventory checks implemented;
   overload, runtime, and load-order verification remain gated.**
6. **Scenario-based runtime smoke profiles:** add opt-in, user-authored profiles
   for campaign load, mission launch, and custom-UI interaction markers. They
   must execute only in a staged working copy and must never claim runtime health
   from static analysis alone.
   **Status: scenario labels, per-scenario log assertions, and stale staged-mod
   protection implemented; game launch orchestration remains explicitly
   user-authored and opt-in.**

### Current completion map (priority order)

1. **Transactional recovery fault injection:** simulate a failure during a later migration write and prove that every earlier write is restored.
2. **Legacy JSON policy:** verify target-engine behavior for trailing commas and other observed historical syntax before changing classification or normalization behavior; retain `MANUAL` findings until the evidence exists.
3. **Cross-platform CI matrix:** run install and unit tests on Windows and Ubuntu with supported Python versions and Java 17.
4. **Opt-in corpus comparison runner:** scan user-approved local mod corpora and compare only aggregate results to sanitized baselines; keep paths and mod content out of Git and CI.
5. **Verified migration-pack contracts:** require provenance, before/after fixtures, compile validation, idempotence, conflict checks, and save-risk assessment for every MagicLib, LazyLib, or AshLib mapping.
6. **Containment and symlink security coverage:** test altered plans/manifests, symlink escapes, and archive member traversal names.
7. **Archive-intake coverage:** add bounded handling/tests for wrapper-directory layouts, corrupt archives, entry-count and compression-ratio limits, and missing metadata.
8. **Deterministic provenance coverage:** prove hashes are stable for unchanged inputs and change only with relevant content.
9. **Deferred test-suite hygiene:** split `tests/test_scanner.py` by concern only when it becomes a demonstrated maintenance burden; this must not displace product work.

- **Completion definition:** all items above have deterministic tests, documentation, and machine-readable artifacts where applicable. Research tracks below remain gated until their stated evidence and safety prerequisites are met.

**Current status: completed 2026-08-31.** The test-suite split was assessed and deliberately deferred under its documented maintenance threshold; all other completion-map items are implemented and covered by local and cross-platform CI verification.

### Corpus expansion strategy

- **Legacy campaign/code specimens:** prioritize Vayra's Sector, then one of Blackrock Drive Yards or Dassault-Mikoyan Engineering. Use them for analysis and evidence quality, never automatic migration.
- **Modern controls:** maintain known-working current specimens (starting with Nexerelin and a library-dependent modern mod) to measure false-positive rates and confirm Bridgeforge can recognize health.
- **Version lineage:** collect old/current releases of a maintained mod such as Ship/Weapon Pack or Nexerelin. Treat maintainer-driven differences as evidence for what changed, what remained intentional, and which scanner assumptions are false.
- **Dependency archaeology:** compare historical/current LazyLib, MagicLib, and optionally GraphicsLib releases. Library migration rules may use this evidence only through the verified migration-pack contract.
- **Library usage attribution:** report whether each known library is declared, bundled, imported, source-called, or bytecode-referenced; flag declared-but-unreferenced dependencies for review. This is evidence only: it must not remove, upgrade, or migrate a library without verified API-specific examples and compile/runtime validation.
- **Binary-only restraint specimen:** retain one source-less, old-bytecode mod to verify package/class inventory, dependency evidence, and graceful `UNKNOWN` handling without decompilation or speculative reconstruction.

### Evidence intake (2026-08-31)

- **Vayra's Sector archive:** a 492-file legacy campaign specimen with a JAR, non-UTF-8 CSVs, verified trailing-comma cases, and other parser-tolerance ambiguity. It is evidence for intake classification, not a migration source.
- **Ship/Weapon Pack source lineage:** the public master branch is reachable and its source tree places `mod_info.json` under `src/`; use old/current maintainer releases to distinguish source-checkout layout from a distributable mod layout.
- **Nexerelin modern control:** the public repository provides maintained 0.12.2-series tags and a large current source/data tree. Use it to measure modern false positives, especially historically loose JSON syntax.
- **LazyLib and MagicLib dependency archaeology:** both public repositories are source/build layouts, not generic migration templates. LazyLib keeps its distributable metadata below `mod/`; MagicLib contains built artifacts as well as source. Keep scans attributable to the selected root and require release-specific before/after evidence for every pack rule.

These sources are retained as external, user-approved evidence only. Bridgeforge does not vendor them, execute their code, or infer transformations from apparent API similarity.

- **Cross-mod analyzer:** construct a read-only dependency and API-use graph across a selected set of mods, including duplicate libraries, package/class ownership, declared dependencies, and version-skew findings. Reports must remain attributable to each source mod and machine-readable.
  **Status: explicit-set dependency, duplicate-class, and campaign-ID ownership graph implemented; global discovery and runtime load-order analysis remain out of scope.**
- **Bytecode rewriting:** investigate narrowly scoped, reversible bytecode transformations in working copies only. Every transform must be deterministic, generate a class-level patch/provenance record, retain the original class, and require explicit review/approval before it can be applied.
- **Decompiler integration:** add an optional local decompiler adapter for review artifacts when source is absent. Decompiled output is evidence only: it must never be treated as authoritative source or automatically recompiled/replaced without an explicit user workflow.
  **Status: hash-bound, explicit-execution adapter plan implemented; output is retained as untrusted review-only evidence.**
- **MagicLib/AshLib adoption:** develop evidence-backed migration packs for manual and review-gated adoption of MagicLib, LazyLib, and AshLib. Do **not** add transformations merely because APIs appear equivalent: every mapping must come from verified examples and documented behavioral evidence. Automatic adoption is a later, opt-in research track and may proceed only for a small allowlisted set of semantics-preserving mappings with compile, conflict, and save-risk validation; all other adoption remains recommendation-only.

## Product boundary

Bridgeforge modernizes legacy mods. It does not profile performance. The related, independent **Starsector Performance Workbench** is specified in [docs/PERFORMANCE_WORKBENCH_DESIGN.md](docs/PERFORMANCE_WORKBENCH_DESIGN.md); the only planned interchange is a small set of versioned JSON schemas.

## First 10 implementation phases — V0.1 scanner

1. **CLI and target profile** — accept a mod directory and explicit Starsector/Java targets.
2. **Safe intake** — validate the input directory and scan it read-only.
3. **File inventory** — record files, sizes, and relevant layout areas.
4. **Metadata analysis** — parse `mod_info.json` and declared dependencies.
5. **JAR/bytecode analysis** — inspect archives and class-file major versions without loading code.
6. **Dependency analysis** — identify bundled libraries, duplicates, and likely obsolete runtime copies.
7. **Source inspection** — collect imports and flag a small, data-driven set of known legacy APIs.
8. **Asset/config validation** — check JSON and CSV structure in Starsector data areas.
9. **Environment inference** — estimate source Starsector and Java eras with recorded evidence.
10. **Artifacts and reporting** — emit `MODERNIZATION_REPORT.md` and `bridgeforge.compat.json`.

**Status: implemented locally.** The V0.1 scanner is deliberately read-only and has no automatic migration, bytecode rewrite, or AI dependency.

## Subsequent releases

- **V0.2:** working-copy generation, safe deterministic metadata/config fixes, checkpoints, and patch manifests. **Status: initial workspace, plan, approval, patch, and rollback foundation implemented; migration-pack coverage remains deliberately minimal.**
- **V0.3:** AST-based Java source migrations; no regex source rewrites. **Status: parse-only JDK AST import/method evidence and review-gated, AST-confirmed import replacement foundation implemented.**
- **V0.4:** JDK/dependency selection and compile validation. **Status: JDK-profile capture, command preview, controlled `javac` execution, diagnostic classification, non-applying compile feedback, and deterministic output-copy JAR packaging implemented.**
- **V0.5:** scoped agent handoff bundles for ambiguity only; Bridgeforge remains the planner and validator. **Status: bounded review-bundle artifact generation implemented.**
- **V0.6:** runtime smoke validation and log collection. **Status: reference-integrity, structural, and compile-result validation are implemented; runtime execution remains opt-in and can require configured log markers inside the selected working directory.**
- **V0.7:** ~~save-risk analysis.~~ **Closed:** save compatibility is not a Bridgeforge compatibility target across Starsector patches. The existing static identifier-diff report remains optional review context only; it must not be presented as a path to save migration or compatibility.
- **V0.8:** migration-pack/plugin ecosystem, including separate library-migration and library-adoption recommendations. **Status: discoverable, validated bundled pack registry and pack-selectable planning implemented; ecosystem rules remain deliberately empty until evidence-backed mappings are added.**
- **V0.9:** modernization-opportunity analysis; no automatic adoption. **Status: static, report-only adoption candidates implemented with explicit high behavioral risk and no automatic change path.**
- **V1.0:** repeatable scan → diagnose → plan → apply → compile → review → validate → report pipeline. **Status: orchestration command and final workspace modernization report implemented.**
