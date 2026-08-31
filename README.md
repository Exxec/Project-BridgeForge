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

`compile` runs only that recorded profile and writes raw output plus classified diagnostics. `compile-feedback` links those diagnostics to already-planned rule candidates and explicitly performs no automatic modification.

`validate` verifies the immutable reference, structurally re-scans the working copy, and records runtime validation as unconfigured unless an explicit launch profile exists. `save-risk` compares original and working content for changed persistent-identifier-shaped fields; it is a conservative warning, not proof of save compatibility.

## Integrity and automation artifacts

`doctor --json` provides machine-readable local-tool, workspace, and migration-pack compatibility checks. `conflicts <workspace>` writes `conflicts.json` and detects planned-edit conflicts plus duplicate class entries across bundled JARs. `provenance <workspace>` writes `provenance.json`, containing deterministic SHA-256 hashes for the original reference, working copy, and relevant generated artifacts.

`corpus-compare <mod-directory> --baseline <baseline.json>` is an explicit local-only comparison against a sanitized baseline. It reports fingerprint and finding mismatches as JSON and neither stores the selected path nor copies mod content into the repository. See [docs/JSON_COMPATIBILITY_POLICY.md](docs/JSON_COMPATIBILITY_POLICY.md) for the verified trailing-comma JSON policy and [docs/MIGRATION_PACK_CONTRACT.md](docs/MIGRATION_PACK_CONTRACT.md) for the evidence required before a library migration rule can load.

`release-evaluate <before-directory> <after-directory>` compares two explicitly selected releases without modifying either. Its machine-readable report distinguishes byte-identical content continuity and scanner-finding deltas from bytecode and runtime evidence; it never claims behavioral or save compatibility without an explicit runtime test.

## Safety

Scanning is read-only with respect to the selected mod directory. Generated artifacts are written only to `--output`.
