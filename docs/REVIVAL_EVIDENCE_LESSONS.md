# Revival Evidence Lessons

The Flu-X and Vacuum revivals established a practical completion contract for BridgeForge:

- compilation, static checks, dependency checks, package checks, save checks, and live testing answer different questions and must remain separate;
- a completed directory and its release ZIP need byte-level attestation, not an assumption that a copy or packaging command succeeded;
- final reports can drift from plans and paths as work moves from `In operation` to `Done`;
- runtime discoveries should become reusable static checks where evidence is deterministic, while behavioral conclusions remain live-test or review items;
- known-good outputs must not be replaced by an incomplete candidate.

Use `bridgeforge revival-audit <candidate> --archive <release.zip>` as the final read-only gate. It verifies that `reports/REVIVAL_PLAN.md` and `reports/REVIVAL_REPORT.md` exist, checks all required validation categories and the single completion status, reports stale plan/path state, and compares every candidate file with the ZIP by size and SHA-256. The command neither edits nor packages the candidate.

An audit result has three levels:

- `PASS`: report contract complete and supplied ZIP exactly matches;
- `REVIEW`: no blocking contradiction was found, but an archive was omitted or report bookkeeping is stale;
- `FAIL`: required evidence/status is missing or package content differs.

The completion status is deliberately strict: exactly one standalone recognized
status must be the report's final non-empty line. Repeated statuses and reports
that append new narrative after an old status fail the audit instead of silently
selecting a convenient value.

This gate establishes evidence consistency and package identity. It does not convert static evidence into runtime proof and does not decide whether unresolved review items are acceptable for a particular release.

The scanner also treats a CSV row with more fields than its header as a deterministic `csv-row-extra-columns` MANUAL finding. Vacuum's live boots showed why this matters: spilled descriptions and hullmod rows can be syntactically readable while values land in the wrong loader columns. BridgeForge identifies the exact row but does not guess how its text should be reassembled.

Broken Star exposed a separate dependency-authority gap: source can import a library directly even when `mod_info.json` does not declare it. BridgeForge now records `source-library-dependency-undeclared` as REVIEW evidence for recognized libraries, including modern `org.magiclib` imports and Nexerelin's `exerelin` package. The detector does not automatically add the dependency because an integration may be optional or intended to degrade gracefully.

The later batch added three more read-only checks. `local-weapon-spec-unregistered`
records a `.wpn` file absent from the mod's own `weapon_data.csv` as REVIEW
because another provider may register an intentional override. The critical
`variant-id-in-weapon-slot` finding detects a local ship variant assigned in a
variant's `weaponGroups` map; repair remains MANUAL until the hull slot proves it
is a station module. Target-bound `target-interface-method-missing` contracts now
cover the observed 0.98a `OnHitEffectPlugin`, `AutofireAIPlugin`,
`ShipSystemStatsScript`, and `HullModEffect` expansions. These contracts catch
known incoming obligations that outgoing bytecode linkage cannot see, but a full
compile remains required for interfaces not yet modeled.
