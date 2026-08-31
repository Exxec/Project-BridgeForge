# Project Bridgeforge roadmap

Bridgeforge follows the project charter in `docs/PROJECT_CHARTER.md`: understand first, modify second, validate always. The original mod is never changed in place.

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
- **V0.3:** AST-based Java source migrations; no regex source rewrites.
- **V0.4:** JDK/dependency selection and compile validation.
- **V0.5:** scoped agent handoff bundles for ambiguity only; Bridgeforge remains the planner and validator.
- **V0.6:** runtime smoke validation and log collection.
- **V0.7:** save-risk analysis.
- **V0.8:** migration-pack/plugin ecosystem, including separate library-migration and library-adoption recommendations.
- **V0.9:** modernization-opportunity analysis; no automatic adoption.
- **V1.0:** repeatable scan → diagnose → plan → apply → compile → review → validate → report pipeline.
