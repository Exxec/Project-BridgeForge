# Sister repository interoperability designs (2026-09-27)

These are proposed contracts, not implemented features. Each producer remains useful alone. Inputs from another repository are untrusted, read-only files; outputs stay in a selected artifact directory. No game or mod source is copied into a repository.

## 1. SPW performance evidence into BridgeForge

**Owner:** BridgeForge consumer; Performance Workbench producer. BridgeForge already has `bridgeforge/spw_bridge.py`, whose permissive key aliases predate a stable SPW export. SPW has `reproducibility.json`, inventory and analysis artifacts, and a comparison gate.

**Contract:** SPW exports a versioned `performance-report.json` plus its artifact hashes and environment fingerprint. BridgeForge accepts only supported versions, verifies available hashes, and records the exact source path/hash, SPW version, capture level, mod identity, enabled state, attribution confidence, CPU unit, sample count, startup metric definition, and limitations. Unknown fields remain visible; missing required fields produce `UNKNOWN` evidence rather than zero. A performance delta requires two SPW captures that SPW marks comparable; a single report is context only. No automatic revival verdict or fixer follows from performance evidence.

**Work order:** Freeze the schema from one neutral synthetic SPW fixture; add producer export and schema tests; update `spw_bridge.py` to parse that exact version while retaining legacy best-effort imports as explicitly unverified; attach the normalized evidence to BridgeForge's revival report; add a two-capture comparable/incomparable fixture pair.

**Exit:** A real SPW export round-trips through BridgeForge with matched hashes and mod identity. Unsupported versions, corrupted hashes, missing metrics, ambiguous ownership, and incomparable captures yield limitations and never a performance improvement claim.

## 2. Project Go localization coverage into BridgeForge

**Owner:** Project Go producer; BridgeForge consumer. `bridgeforge/translation.py` already emits Project Go translation-memory JSON. Project Go's extractor has CSV/JSON gap auditors and file/JAR coverage records.

**Contract:** Project Go exports a versioned, counts-and-identifiers coverage manifest for one selected mod root: source archive/root hash, extractor version, file path, content kind, supported/extracted/skipped counts, skip reason, and optional stable string locator. BridgeForge consumes it read-only and joins by exact source hash and normalized relative path. It reports `covered`, `gap`, or `unknown`; a mismatch cannot be silently compared. Text and translations are excluded by default, with user-local detailed reports kept outside source control. Do not merge the Java extraction logic into Python.

**Work order:** Agree on synthetic fixture and locator rules; export manifest in Go; add BridgeForge importer and report section; test changed-root, corrupt/partial JAR, unsupported kind, and zero-entry cases. Retain BridgeForge's independent leftover-text check as a separate signal.

**Exit:** A matching manifest identifies uncovered supported strings without editing either mod; mismatched hashes or partial extraction explicitly block a complete-coverage claim.

## 3. Release evidence contract for VoidSmith and Project Go

**Owner:** each release pipeline. BridgeForge's provenance and release gates are design references, not code dependencies. VoidSmith already verifies supplied portable archives; Project Go already has exact-source release checks.

**Contract:** Define common evidence *fields*, with repo-specific producers: commit/tag, clean build input state, toolchain and dependency-lock fingerprints, artifact filename/size/SHA-256, embedded version, package inventory/hash, test and native acceptance results, and separately verified remote asset hash. Gate states are `PASS`, `FAIL`, `NOT_RUN`, or `UNKNOWN`, each with evidence location and date. A tag or CI run never substitutes for observing the published asset. No cross-project release helper package is required.

**Work order:** Inventory each pipeline's present evidence; create a mapping and list only missing fields; add synthetic manifest verification fixtures; wire missing checks into existing release tooling; verify one candidate artifact per repo before changing release wording.

**Exit:** For a candidate release in each repo, a reader can trace the exact source revision to the local build and downloaded asset, and can distinguish offline, native, live, rights, and publication gates without inferred success.

## 4. Shared mod identity/inventory exchange

**Owner:** SPW producer; VoidSmith and BridgeForge consumers. This is an interchange schema, not shared runtime code.

**Contract:** A versioned local JSON inventory records selected install fingerprint, observed mod directory, declared ID/version, enabled/disabled state and evidence source, metadata/JAR hashes, duplicate-ID groups, and parse warnings. Paths are local evidence, not portable identity. Consumers join only when ID plus root/hash are unambiguous; disabled and duplicate IDs remain distinct. The neutral distributable schema and synthetic fixtures contain no real mod/game data.

**Work order:** Compare current inventory fields in all three repos; publish the smallest schema and neutral fixtures in SPW; add optional import in VoidSmith and BridgeForge; retain each tool's native scan as fallback; test duplicate IDs, renamed-disabled metadata, stale enabled list, missing metadata, and changed install.

**Exit:** The three tools agree on identity for a synthetic install; ambiguous cases stay ambiguous and no consumer changes its source scan or recommendation from inventory alone.
