# Current roadmap view

Reconciled 2026-10-17 for the owner-approved planning update. This is a compact index into the authoritative
`ROADMAP.md`, not a replacement history. Historical test/run claims below are attributed to their recorded evidence;
this documentation pass did not rerun the suite, launch the game or requalify releases.

| Item | Implementation | Validation / shipping evidence | Next step |
|---|---|---|---|
| 61 Java/launcher matrix | Built; later fixes recorded | ROADMAP 70 continuation records first live use on 2026-10-12; `tests/test_java_matrix.py` | Preserve run identities under 75 R1; do not retain the old "no live run yet" headline |
| 62 mass environment testing | Built | ROADMAP 70 records the 150-mod 2026-10-12 pass: 137 SCREEN_PASS, 13 NEEDS_LUNALIB; boot evidence, not full gameplay acceptance | R1 provenance and environment-based retest selection |
| 70 hardening | Partly implemented; remaining work open | ROADMAP 70 dated sub-items; safeio, baseline/archive checks, CLI/scanner split, snapshot and evidence tooling have existing implementations; this is not a claim all H1-H5 gates passed | Audit remaining sub-items individually under R7; use R1/R2/R8 for strengthened requirements |
| 72 lost-feature detection/recreation | Planned extensions; supporting tools exist | `docs/AUTOMATION_PLAN.md` E3/E4; event advancement proof remains a separate live gate | E4 evidence sweep; owner chooses recreations; no automatic restoration |
| 73 less hand work | Planned extensions over existing tools | `docs/AUTOMATION_PLAN.md`; original counts dated 2026-10-14 | R2/A2 before authoritative A1; R1-R4 before E2 activation |
| 74 Zorg/EPTA | Working revisions implemented | `docs/OWNER_MOD_FOLLOWUP_2026-10-17.md`: Zorg 119 proxy assertions + package audit; EPTA scoped audit + static scan | LIVE PENDING: copied-save upgrade/reload and campaign visuals; new revisions not archived |
| 75 trust refinements | Specification only | `docs/ROADMAP_IMPLEMENTATION_HANDOFF.md`; no R1-R8 implementation claimed | Follow dependency order below |

Item 75 work contracts:

| Work | State | Dependency / acceptance boundary |
|---|---|---|
| R1 run-input provenance | Planned | Shared schemas first; offline tests plus actual rig negative/positive proof |
| R2 scan registration/freshness | Planned | Input schema; precedes authoritative corpus measurement |
| R3 auto-accept policy | Planned | Report-only first; E2 activation after R1/R2/R4 |
| R4 semantic rulings/fixer refusals | Planned | Existing ruling storage; no balance/save authorization expansion |
| R5 revision lifecycle | Planned | R1 and existing release gates; prepare/test/finalize |
| R6 save-upgrade scenarios | Planned | R1 evidence; real load/save/reload separate from proxy tests |
| R7 detailed status reconciliation | Initial summary provided; detailed audit pending | Per-sub-item implementation and validation fields require their own evidence |
| R8 restore exercise | Planned | Existing snapshot tooling; isolated restore and CLI/rig qualification before cutover |

Update this index when implementations or evidence change. Record source, compile, static, package, dependency/API,
save compatibility, live acceptance and shipping separately; use UNKNOWN/INCOMPLETE/NOT_APPLICABLE where appropriate.
An implemented command does not prove its live acceptance criterion. Local-only reports must be labeled as such.
The detailed per-sub-item status audit and any machine-readable status/lint extension remain R7 work.
