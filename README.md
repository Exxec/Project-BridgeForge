# Project Bridgeforge

An offline Starsector-mod compatibility workbench. Bridgeforge inventories a mod and produces explainable compatibility findings; source migrations remain review-gated, and bytecode support is limited to evidence-backed, exact symbolic remaps written to a separate output copy. It never changes a supplied mod or binary in place.

Bridgeforge is intentionally separate from the proposed [Starsector Performance Workbench](docs/PERFORMANCE_WORKBENCH_DESIGN.md), which profiles runtime behavior and attributes cost to mods/classes.

## Run

Requires Python 3.10+.

```powershell
py -3 -m bridgeforge scan C:\path\to\OldMod --output .\artifacts
```

The command writes `MODERNIZATION_REPORT.md` and `bridgeforge.compat.json` to the output directory. Use `--target-starsector` and `--target-java` to change the default `0.98.x` / Java 17 target profile.

## V0.2 working-copy workflow

```powershell
py -3 -m bridgeforge workspace C:\path\to\OldMod --output C:\work\OldMod-bridgeforge
py -3 -m bridgeforge plan C:\work\OldMod-bridgeforge --target-starsector 0.98a-RC8
py -3 -m bridgeforge apply C:\work\OldMod-bridgeforge --approve metadata-target-starsector-version
```

`workspace` makes an immutable reference and a separate working copy. `plan` creates a diff-backed plan and accepts additional validated JSON rule packs through `--rules`. `apply --safe` modifies only planned `SAFE` rules; `REVIEW` rules always need an explicit `--approve <rule-id>`. `rollback` restores the working copy from a named checkpoint.

Java migration packs can provide a `replace-import` rule. Bridgeforge first parses Java through the selected JDK's compiler API, then replaces only the confirmed import declaration. Method bodies are not rewritten by this V0.3 foundation.

## Build-environment model

`build-plan` records a selected JDK (using its `release` metadata), Java target, API/dependency JARs, discovered source roots, and an exact `javac` preview. It does not compile; that remains a separately controlled step.

`compile` runs only that recorded profile and writes raw output plus classified diagnostics. If a requested API or dependency JAR is missing, `build-plan` records deterministic `compile-validation-unavailable` review findings instead of aborting; `compile` then records `UNAVAILABLE` and the pipeline continues without making a compile-compatibility claim. `compile-feedback` links available diagnostics to already-planned rule candidates and explicitly performs no automatic modification.

After a successful compile, `package-jar <workspace> <working-copy-relative-jar>` creates a deterministic JAR in `package-artifacts/`; it never replaces the input JAR. The accompanying `package-manifest.json` records input/output SHA-256 values and confirms the input was preserved.

## Controlled runtime smoke checks

`runtime-profile` records an opt-in command only. `runtime-smoke` inspects that profile unless `--execute` is supplied explicitly. A profile can constrain validation to a log inside its working directory with `--log-file` and one or more `--expect-log` markers; a zero exit code still fails when an expected marker is absent. This is controlled process/log evidence, not a claim of behavioral or save compatibility.

`validate` verifies the immutable reference, structurally re-scans the working copy, and records runtime validation as unconfigured unless an explicit launch profile exists. `save-risk` compares original and working content for changed persistent-identifier-shaped fields as review context only; Bridgeforge does not support or claim cross-patch save compatibility.

## Integrity and automation artifacts

`doctor --json` provides machine-readable local-tool, workspace, and migration-pack compatibility checks. `conflicts <workspace>` writes `conflicts.json` and detects planned-edit conflicts plus duplicate class entries across bundled JARs. `provenance <workspace>` writes `provenance.json`, containing deterministic SHA-256 hashes for the original reference, working copy, and relevant generated artifacts.

`corpus-compare <mod-directory> --baseline <baseline.json>` is an explicit local-only comparison against a sanitized baseline. It reports fingerprint and finding mismatches as JSON and neither stores the selected path nor copies mod content into the repository. See [docs/JSON_COMPATIBILITY_POLICY.md](docs/JSON_COMPATIBILITY_POLICY.md) for the verified trailing-comma JSON policy and [docs/MIGRATION_PACK_CONTRACT.md](docs/MIGRATION_PACK_CONTRACT.md) for the evidence required before a library migration rule can load.

`archive-preflight <archive.zip>` inspects ZIP metadata without extracting it. It reports traversal, symlink, duplicate-member, wrapper-layout, and mod-root ambiguity evidence. `archive-stage <archive.zip> --output <empty-directory>` extracts only an archive whose preflight has no extraction hazards; it never writes beside or replaces the supplied archive. `corpus-audit` accepts `--max-files-per-mod` and `--max-jars-per-mod` to skip oversized inputs deterministically rather than making partial compatibility claims.

`library-api-inventory <library.jar> --library-id <id> --library-version <version>` records a supplied library identity alongside its class inventory. Without explicit identity/version evidence, `library-api-match` reports that assessment as unverified; wildcard imports, reflection, and bytecode-only references remain review findings rather than missing-API claims.

`release-evaluate <before-directory> <after-directory>` compares two explicitly selected releases without modifying either. Its machine-readable report distinguishes byte-identical content continuity and scanner-finding deltas from bytecode and runtime evidence; it never claims behavioral or save compatibility without an explicit runtime test.

## Bytecode inspection and remapping

`bytecode-inspect <class-or-jar>...` reads class-file bytes through pinned ASM 9.7.1 and emits JSON only; it never defines, loads, or executes a mod class. `bytecode-diff <before>... --after <after>...` compares symbolic class inventories, method opcode sequences, instruction/branch counts, and exception-table counts. `bytecode-plan <input>... --rules <rules.json>` produces review-only exact remap candidates. `bytecode-apply <input> --rules <rules.json> --approve <rule-id> --output <path>` applies only explicitly approved, exact same-descriptor method/field or type-opcode remaps to a distinct output copy; a semantic verifier rejects any other class, method, or instruction change, and JAR application also verifies every unselected archive member is byte-for-byte unchanged. See [docs/BYTECODE_BOUNDARY.md](docs/BYTECODE_BOUNDARY.md).

## Orchestration, review, and opportunity reports

`pipeline <workspace>` runs scan, plan, apply, optional bytecode/compile validation, validate, save-risk, and review-bundle in one auditable step and writes `MODERNIZATION_REPORT.md`. `packs [--root <dir>]` lists bundled migration packs with their ID, status, and scope. `review-bundle <workspace>` writes a bounded `findings.json`, an affected-file list, acceptance-criteria and context notes, and copies of the affected working-copy files, for a scoped human/agent review handoff. `inspect <workspace>` prints the workspace's paths, checkpoints, and planned migrations as JSON. `export-patch <workspace> --output <dir>` copies only the migration manifest, plan, and diff into a standalone patch package; it never includes the original mod. `opportunities <workspace>` reports heuristic, review-only library-adoption signals (MagicLib, LunaLib, AshLib, LazyLib) with no automatic change path.

## Safety

Scanning is read-only with respect to the selected mod directory. Generated artifacts are written only to `--output`.
