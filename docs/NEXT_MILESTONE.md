# Next milestone proposal: one reproducible revival case

S1 of the [strategic roadmap](STRATEGIC_ROADMAP.md). Proposed for owner review, 2026-10-17; implementation has not begun.
Factual status 2026-10-18: S1's shared case/qualification contracts are not built; the item 75 building blocks it reuses (R1, R2, R5) and the DOC-001 fix exist offline with live gates pending ([ROADMAP_STATUS](ROADMAP_STATUS.md)).
This is the next significant product objective, not a request to finish every item in the tactical backlog.

## Outcome

An operator can take a preserved legacy mod through analysis, selected repairs/review, candidate preparation,
applicable qualification and an authorized local archive using one reproducible case, across either current workspace
form. The record explains every transition and remaining limitation without requiring chat history or manual status edits.

This outcome advances the long-term purpose directly: it turns existing individual tools into a dependable revival
workflow and establishes what later automation must preserve. Adding more fixers first would leave competing workspace,
candidate and acceptance concepts intact; that would make future unattended execution harder to reason about.

Scope is one supported lane and a representative pilot, not every mod. Existing-save migrations remain human-routed;
S1 records their requirements and correctly blocks missing proof, rather than trying to implement S3 in advance.

Concrete prerequisite identified 2026-10-18: DOC-001 (`BUGS.md`) records that archive refresh currently deletes the
previous artifact despite the owner preservation contract. This blocks relying on that path for S1 finalization.
Fix preservation and its failure/retry tests within the milestone; do not use refresh on known-good archives meanwhile.
This addendum records evidence and a blocker within S1; it does not change strategic direction or start implementation.

**Update 2026-10-18:** DOC-001 is fixed (`archive --refresh` moves the old archive to `Done/_replaced-<date>/`,
`tests/test_archive_preserves.py`); it has not been exercised on a real `Done/` archive. The shared case and qualification
contracts of S1 are still not implemented. Items 73 and 75 (R1-R6, R8) were implemented offline the same day; see
`ROADMAP_STATUS.md`.

## Evidence that selects this milestone

The [assessment](ARCHITECTURE_GAPS.md) establishes two working workspace APIs (E04), rich independent tools (E03-E09),
different qualification/release contracts (E10/E11), and strong automated verification infrastructure (E14). It does
not establish a common end-to-end case lifecycle. The latest Zorg/EPTA work also required manual selection of commands,
scope, artifact locations and pending live gates. These are integration problems with strategic consequences.

## Proposed deliverables

1. **Workspace view:** a validated descriptor of original, working, reports, checkpoints and selected source authority,
   adapting both `workspace-manifest.json` workspaces and `intake`/`revive` workspaces. Reject ambiguous layouts.
2. **Case record:** case identity, target context, candidate identity, decisions, referenced artifacts and operation
   receipts. Keep irreplaceable decisions distinct from rebuildable indexes or generated summaries.
3. **Candidate preparation:** freeze the selected file set and environment identities before qualification, including
   dependency closure and source/jar authority. Record changed input relationships and invalidated evidence.
4. **Qualification view:** evaluate applicable evidence under an explicit profile, preserving compile/static/package,
   dependency/API, save and live dimensions. A candidate is not accepted merely because all recorded checks happen to pass.
5. **Coherent operator flow:** adapt existing commands behind a small orchestration surface; show next required action
   and why. Propose exact new CLI spelling in an implementation design review, not as if it already exists.
6. **Recoverable finalization:** use the selected existing archive/release machinery only after matching evidence and
   permissions, with no change to tested candidate bytes. Preserve previous archives and resumable operation receipts.
7. **Pilot evidence and baseline:** demonstrate the workflow, intentional refusals, interruption/retry behavior and
   operator effort. Produce a concise guide another agent/maintainer can follow independently.

## Architecture and data contract to agree first

Keep the modular monolith and use local versioned records. Introduce only small contract/adapter modules where the
current seams require them; names below are conceptual, not a mandate for a framework or a database.

| Concept | Required information and rules |
|---|---|
| WorkspaceView | Format/version, validated paths, original identity, authority selection, capabilities and unavailable paths; opening a case must not move data |
| Case | Stable case ID, workspace reference, owner-approved scope, chosen target profile, decisions and referenced candidate/receipt IDs |
| Candidate | Exact selected path/hash manifest, file-set algorithm version, predecessor, build/source authority, tool/rule/policy context and explicit dependency/core/launcher identities |
| ValidationReceipt | Schema, subject identity, check/scenario kind, applicability/reason, tool/profile identity, inputs and outputs, timestamps/run ID, outcome and evidence paths/digests |
| Decision | Exact scope/predicate, owner/standing authority, reason, evidence, date and supersession/revocation; no approval inferred from untouched suggestions |
| Qualification | Required obligations for the declared use, receipt references, unresolved items, authorized deviations and per-dimension outcomes |
| OperationReceipt | Intended transition, before/after identities, locks/checks, durable completion or recovery status; a label cannot replace revalidation |

Use PASS/FAIL/INCOMPLETE/NOT_APPLICABLE for validation, with applicability reasons; treat legacy unknown provenance as
unknown rather than converting it to PASS. Preserve the distinction between finding confidence, automation tier and
whole-case complexity. Existing data can remain in its current files; adapters reference/import it with provenance limits.

Do not force every subsystem's internal dictionary into one new schema. Only require a common envelope at the workflow
boundary and migratable readers for persisted records. Receipts and rendered acceptance annotations should live outside
the frozen candidate when possible; generated documentation cannot mutate the artifact after it was tested.

## Implementation slices and likely touch points

Each slice is reviewable and preserves existing CLI behavior until a documented compatibility decision is approved.

| Slice | Work and existing seams | Required proof |
|---|---|---|
| 1. Contract and policy map | Inventory callers of `workspace_paths`, `intake`, `revive`, `validate`, `release_mod`, `archive_mod`, `archive_gate` and promotion; document current semantics | Explicit compatibility table and owner-reviewed initial qualification profile |
| 2. Workspace/case adapters | `bridgeforge/workspace.py`, `intake.py`, `pipeline.py`, `revive.py`; proposed small shared case/workspace view module | Both layouts open without copying/renaming originals; malformed/ambiguous paths refuse |
| 3. Candidate/receipt spine | `models.py`, `report.py`, `build_tag.py`, `copy_drift.py`, `finding_stats.py`; reuse item 75 R2 identities and scan registration | Stable unchanged identities, changed bytes/context invalidate, incomplete legacy evidence remains visible |
| 4. Qualification integration | `validate.py`, `live_accept.py`, `live_trust.py`, selected `release.py`/`archive.py` caller paths, `cmd_*` adapters | Identical declared scope/input yields the same obligations and outcome across the supported entry points |
| 5. Prepare/run/finalize | `probe_group.py`, `live_run.py`, build/rig helpers, selected archive flow; apply bounded item 75 R1/R5 requirements | Real staged-input/run identity, post-test mutation refusal, no final version bump, safe retries |
| 6. Operator flow and pilot | CLI registry, existing status/dossier views, focused guide and tests | Pilot matrix, independent handoff and measured operator baseline; no invented compatibility claim |

Slice 1 must settle the first supported entry points and their contracts. Do not accidentally make an internal utility
signature change a public policy guarantee. A legacy path outside the first lane must either retain its documented
meaning or clearly state that it cannot supply the new qualification—not silently appear equivalent.

## Proposed pilot and acceptance matrix

The following six case roles are proposed evaluation criteria, not a claim those cases already passed. Select actual
private mods and licenses with the owner; keep committed fixtures synthetic. Roles can share a mod only if each scenario
and its independence are recorded. Cover both workspace formats with positive and refusal fixtures.

| Role | Purpose | Expected acceptance behavior |
|---|---|---|
| P1 data-only, known providers | Baseline usable case | Compile can be justified NOT_APPLICABLE; applicable package and observed-use requirements still apply |
| P2 loose Java with evidenced narrow repair | Compile and review continuity | Full applicable RC8 loose-script compile evidence tied to candidate; owner review where required |
| P3 jar with loose source of uncertain authority | Prevent false fixes | Refuse unsupported source-only success or require evidenced packaged-class authority/verification |
| P4 missing/conflicting dependency | Resolution boundary | Produce an explicit unresolved provider decision; no phantom successful qualification |
| P5 existing-save/persistent campaign change | Risk/upgrade boundary | Follow higher-capability/person routing and require upgrade evidence; no auto-acceptance from a clean scan |
| P6 previously qualified candidate changed afterward | Maintenance/negative control | Old run remains historical; current acceptance/finalization is refused until relevant evidence is renewed |

Before implementation, record the current commands, manual edits, active review minutes, elapsed work, blockers and
available evidence for the pilot. Exclude time waiting for the owner from active work while still reporting it as elapsed
delay. Reuse immutable input copies, not already-fixed working copies, to measure repair outcomes.

Also record per-stage serial elapsed time and the identities/ownership needed to resume safely. These are prerequisites
for S2's [bounded execution and reuse](EXECUTION_EFFICIENCY_PLAN.md), not a scheduler or concurrency expansion within S1.

Completion requires:

- Synthetic contract/integration tests for both layouts, semantic status applicability, traversal/junction boundaries,
  changed same-version files/dependencies/core/rules, old/wrong logs, missing tools and partial/interrupted evidence.
- Operation failure injection and retry: originals/prior archive survive, no duplicate application or changelog entry,
  concurrent/stale updates refuse, and a completed receipt matches actual artifacts.
- Both positive and deliberate-negative pilot outcomes match the matrix. Existing CLI goldens and relevant archive,
  release, workspace, intake, escalation and scenario regression tests pass without weakened gates.
- At least one eligible pilot runs its applicable new-game/campaign/combat checks on the isolated rig with exact staged
  identity, then finalizes matching bytes; a deliberate drift case refuses. Do not count this as save-upgrade proof.
- Another agent/maintainer can explain and resume a case from artifacts plus the guide, without this conversation.
- Publish the measured baseline and residual limitations for owner acceptance. No minimum automation percentage is
  required: a coherent reviewed flow is the S1 benefit.

If the rig or required licensed inputs are unavailable, offline slices can be IMPLEMENTED with LIVE PENDING. S1 as an
operational outcome remains incomplete. This is a meaningful evidence boundary, not a reason to label the entire plan done.

## Explicit non-goals and scope controls

No new general save editor, GUI, cloud service, arbitrary semantic rewrite engine, new game target, broad recipe
expansion, automatic E2 activation, new recurring agent service or migration of all existing archives. Do not replace
the original/working layouts or make SQLite the authority for decisions. Do not solve all item 70/73/75 subtasks first.

Optional quality work belongs in this milestone only when it is necessary for an accepted case/receipt transition or
an observed blocker. Maintain existing safety tests and fix actual regressions; do not turn the pilot into an indefinite
hardening program. Separate original feature recreation and gameplay decisions into owner-approved scope.

## Dependencies, risks and human decisions

Needs the preserved pilot inputs, reference core/compiler/provider access, reviewer/rig availability, the existing
workspace/scan/build/escalation/probe tools, and unchanged legal/source-preservation rules. No particular model vendor
or sister-project runtime dependency is required.

Main risks are conflicting existing policy, insufficient pilot diversity, expensive fingerprinting, accidental API
breaks, ambiguous source authority, unavailable real scenarios and an overly ambitious first workflow surface.
Use compatibility adapters, bounded profiles, explicit refusals and small vertical demonstrations. Do not choose
targets based only on easy cases, and do not weaken evidence to make difficult cases appear supported.

Owner approval is needed before implementation for:

1. S1 as the next product milestone and the initial supported operator flow/profile.
2. Pilot access, reviewer/rig capacity and desired local archive versus distributable-release scope.
3. Any required compatibility/deprecation choice when existing release paths intentionally differ.

Existing approval rules still govern per-mod gameplay/save changes, license decisions and outward publication.
Planning approval is not one of those approvals. No dates or staffing assumptions are assigned here.

When approved, start slice 1: read current contracts and produce the compatibility/profile map before changing code.
Then demonstrate one complete vertical case early, extend to the pilot matrix, and measure the result. For tactical
details and validation conventions, reuse [item 75's handoff](ROADMAP_IMPLEMENTATION_HANDOFF.md), the
[automation plan](AUTOMATION_PLAN.md), `CLAUDE.md` and the local agent contract.
