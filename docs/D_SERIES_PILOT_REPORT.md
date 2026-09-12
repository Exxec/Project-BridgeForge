# D0/D1 pilot report: Exigency and SEEKER

Date: 2026-09-11

Status: **OFFLINE PILOT COMPLETE; LIVE D2 EVIDENCE NOT CAPTURED**

## Inputs and safety

- Exigency used the untouched `Exigency 0.7.2.zip` (SHA-256
  `d7d9196b429b79c1d01ce25a0b04519982cbe47804da1cce45c5a9e11d8d2a80`).
  `archive-preflight` approved staging and the selected wrapper root was copied
  to ignored `artifacts/d-series-pilot/Exigency-original-stage/`. The archive
  was not modified.
- SEEKER used the untouched folder under `Done/SEEKER/original/` directly and
  wrote reports only to ignored `artifacts/d-series-pilot/SEEKER-original/`.
- No source mod, working copy, test rig, save, or known-good release was
  modified. No game was launched.

## Deterministic results

| Input | Manifest SHA-256 | Files | Nodes | Edges | Scanner findings | Behaviours | HIGH risks | Hooks | Registrations | Possible duplicate registrations |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Exigency 0.7.2 original | `61a6e692665bc01fdb0ac1bc7807679eb17b22804e880761cf5d826bab4e708a` | 199 | 2996 | 11155 | 104 | 167 | 29 | 3 | 12 | 2 |
| SEEKER 0.65.2a original | `52b53ac581fea978317ecb24d111875c14f6fe19b078cfe1689f3867e5ff902e` | 227 | 1468 | 6480 | 54 | 148 | 13 | 2 | 7 | 1 |

The manifest is calculated from sorted relative paths and per-file SHA-256
values for every D0-selected input. Re-running D0/D1 against unchanged inputs
produced the same content-derived ids and counts.

## Known-surprise acceptance check

| Historical surprise | Would D0/D1 raise it before modernization? | Evidence |
|---|---|---|
| Exigency faction load NPE from wing ids in `shipRoles` | **Yes, direct** | Multiple `shiproles-wing-id` MANUAL findings and faction data behaviour/risk records. |
| Exigency missing known lists | **Yes, direct** | `faction-known-lists-missing` for Exigency and Exipirated factions. |
| Exigency RC8 sandbox failure | **Yes, direct** | `script-sandbox-forbidden-api` MANUAL findings on the shipped JAR. |
| Exigency Avesta movement/registration uncertainty | **Yes, bounded hypothesis** | Avesta-related runtime registrations are mapped; duplicate-registration and persistence/save-load observations are generated. Bytecode alone does not establish the intended coordinates. |
| SEEKER sensor-drone class treated as unused/missing | **Yes, preservation gate** | The `.system` file is a data-driven behaviour entry and its class reference remains an explicit MANUAL/unknown item, so it cannot be removed as dead code. Target vanilla ownership still needs evidence. |
| SEEKER/AI Tweaks module-captain personality NPE | **Not direct in the untouched input** | The original lacks the later module-risk signal; the revived-build pilot does emit `module-captain-personality-risk`. D5 static diff is therefore required to catch the newly relevant modular-hull state. |
| SEEKER bundled-source versus shipped-JAR authority problem | **Partially** | The selected original contains no comparable source provider, so D0 reports 114 package-only classes and refuses an equivalence claim. It cannot diff source bytes that are absent. |

Result: the pilot directly surfaces four historical bug classes, creates a
preservation/test gate for Avesta and the sensor-drone behavior, and exposes one
issue that becomes visible only when the revived static map is compared. This
supports keeping D5 mandatory rather than treating D0 alone as sufficient.

## Remaining validation

- Capture old-game and revived-build observations through P10 reference rigs.
- Import them with `probe-baseline`, run `behavior-diff`, then build D6 coverage.
- Resolve target vanilla ownership for SEEKER's sensor-drone stats class before
  changing its MANUAL/unknown state.
- Record written decisions for every open HIGH risk and
  `PRESERVE UNTIL EXPLAINED` unknown before any release gate can pass.

## Reproduction

Commands and artifact contracts are in `docs/DISCOVERY_FIRST_WORKFLOW.md`.
Generated pilot artifacts are intentionally ignored; reproduce them from the
hash-identified inputs rather than committing third-party mod content.
