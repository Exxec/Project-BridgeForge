# Starsector Performance Workbench

## Purpose and boundary

The Starsector Performance Workbench (SPW) is an independent, offline, runtime-profiling and benchmarking utility. It answers: **what is slow, when, and with what evidence?** Its pipeline is:

```text
inventory → capture → normalize → attribute → analyze → compare → report
```

SPW does not modernize, rewrite, patch, decompile, or otherwise modify mods. Those are Bridgeforge responsibilities. Bridgeforge does not profile performance. Either program must remain useful when the other is absent.

## Design inputs from the local projects and installation

This design incorporates patterns observed in the two existing local projects:

- **Project Forge / VoidSmith:** source inputs are untrusted and read-only; parsing, normalized data, provenance, adapters, validation, analysis, and export stay separate; unknown data is explicit rather than guessed.
- **Project Go / SSMT:** use explicit user-selected paths, immutable source / generated-output boundaries, checkpointed workflows, Java/Gradle packaging, and clear diagnostics instead of silent repair.
- **Installed mod ecosystem:** the inspected installation contains 155 mod directories, 119 directories with JARs, 94 with Java source, and 138 JAR files. A large majority of parseable declarations target the 0.98 release-candidate corridor, while dependency declarations range from none to several per mod. Directory and archive coexistence, duplicate versions, nonstandard metadata, and bundled shared libraries must be normal inputs—not exceptional failures.

No game or mod data, names, extracted entity lists, captures, or benchmarks are part of this repository or the distributable application. SPW reads them only at runtime and writes results to an explicit local output directory.

## Safety and privacy contract

- Never change Starsector, a mod, its JARs, game settings, JVM launch configuration, or save files.
- Treat mod paths and metadata as untrusted input. Resolve and validate every path before reading it.
- Do not execute mod code to inventory it. Static ownership analysis must not class-load mod classes.
- A capture is opt-in and bounded by a selected launch profile, duration, output directory, and size policy.
- A report states evidence and confidence. It must never claim a mod caused a slowdown solely because its name appears in a stack.
- Default reports are local. Export/redaction is explicit because profiles can expose local paths and mod names.

## Core model

```text
Starsector installation
  ├─ environment inventory
  ├─ selected launch profile / runtime
  ├─ mod inventory + JAR ownership index
  └─ optional JFR capture
             ↓
event normalizer → stack-frame resolver → attribution engine
             ↓
CPU / blocking / allocation / GC / memory / startup analyzers
             ↓
baseline comparison + PERFORMANCE_REPORT.md / performance-report.json
```

### Key records

| Record | Required fields |
| --- | --- |
| `EnvironmentSnapshot` | schema version, selected game path, runtime/JDK, launcher profile, enabled-mod configuration hash, timestamps |
| `ModInventoryEntry` | opaque local ID, relative root, metadata parse status, content hash policy, JAR paths |
| `JarOwnershipEntry` | normalized JAR path, owner candidates, package prefixes, class index status, confidence |
| `CaptureDescriptor` | capture type, JVM/JFR settings, start/stop, duration, size, incomplete reason |
| `Attribution` | event/stack evidence, mod/JAR/package/class candidates, confidence, ambiguity reason |
| `BenchmarkRun` | scenario manifest hash, run settings, summary percentiles, environment snapshot hash |

An ownership result can be `EXACT`, `LIKELY`, `AMBIGUOUS`, `UNOWNED`, or `UNKNOWN`. Shared library frames must not be automatically attributed to the mod that happens to call them.

## Architecture decisions

### 1. Inventory is read-only and tolerant

Parse `enabled_mods.json`, directory metadata, JAR manifests, JAR class indexes, archive candidates, and runtime/launcher details. Preserve malformed or unavailable metadata as findings with raw location evidence; do not discard the mod or invent a replacement ID. JAR ownership must support multiple candidates, because a populated installation can contain bundled duplicate libraries and multiple releases.

### 2. JFR is the initial capture mechanism

V0.1 uses Java Flight Recorder where the **actual launched JVM** supports it. SPW must detect the runtime used by Starsector rather than assuming that the system JDK is the game JVM. If JFR cannot be enabled, report the limitation and offer no fake substitute. Process attachment and JVM arguments are explicit user actions.

### 3. Attribution is evidence-ranked

Resolve a sampled frame in this order: exact class-to-JAR index, package prefix, JAR manifest/metadata, source layout evidence, then unknown. Report both the raw frame and the attribution path. Never map common dependencies (for example shared utility libraries) to one content mod without direct evidence.

### 4. Comparisons are controlled experiments

Baselines compare only runs whose environment snapshots are compatible: same game/runtime profile, selected mod configuration, scenario manifest, capture settings, and benchmark duration. Differences outside tolerance produce `NOT_COMPARABLE`, not a percent-improvement claim.

## Roadmap

1. **V0.1 — Environment inventory and JFR capture.** Detect installation, selected runtime/launch profile, enabled mods, metadata status, JAR ownership candidates, thread inventory; emit `environment.json`, `mod-ownership.json`, `profile.jfr`, and a basic report.
2. **V0.2 — Startup profiling.** Attribute launcher-to-main-menu time, class loading, resource parsing/loading, mod/dependency initialization.
3. **V0.3 — CPU and thread analysis.** Analyze sampled CPU, thread states, blocked time, locks, executor waits, and thread lifecycle.
4. **V0.4 — Allocation and GC analysis.** Report allocation rate, allocating frames, GC frequency/pause time, heap trends, and per-frame churn candidates.
5. **V0.5 — Mod attribution.** Harden class/JAR/package/dependency resolution and ambiguity reporting; add ownership-map regression fixtures.
6. **V0.6 — Retention mode.** Analyze long-session heap, class/thread/direct-buffer counts, high-water marks, and repeated-transition cleanup evidence.
7. **V0.7 — Combat benchmark mode.** Use an explicit, user-created scenario manifest; report frame-time mean/median/p95/p99, spikes, CPU, GC, and allocations.
8. **V0.8 — Baseline comparison.** Compare compatible vanilla/modded/suspect-disabled/patched runs and produce significance-aware delta reports.
9. **V0.9 — Rendering diagnostics.** Add advanced, optional render-thread and GL-stall observation. RenderDoc integration remains optional and best-effort.
10. **V1.0 — Diagnosis pipeline.** Deliver a repeatable inventory → capture → attribute → analyze → compare → report workflow with reproducibility metadata.

## Report language

Each conclusion contains a bottleneck category, raw evidence, attribution, confidence, and limitations. Example:

```text
Primary bottleneck: main-thread CPU
Likely owner: <local mod identifier> / <JAR>
Evidence: 31% sampled CPU across 3 compatible runs
Attribution: exact class-to-JAR index
Confidence: HIGH
Limitations: causation has not been experimentally isolated
```

## Bridgeforge interoperability

The only planned shared surface is a small, independent `shared-schema` package or copied JSON Schema documents:

```text
environment.schema.json
mod-inventory.schema.json
jar-ownership.schema.json
report-metadata.schema.json
```

SPW may emit a performance finding that Bridgeforge presents as a **modernization opportunity**. Bridgeforge may provide a patched-build identifier that SPW uses as a comparison label. Neither tool imports the other’s codebase, requires the other at runtime, or treats performance evidence as proof that a migration is behaviorally correct.

