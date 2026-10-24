# S1 contract and policy map

Source review 2026-10-24 on B6 base `8736e13a`. This is slice S1.1, preceding new adapter code. Existing functions already solve physical workspace management, file selection, scan identity and live provenance; the missing slice is a common read-only boundary. Do not replace those functions or silently merge their policies.

| Current entry / callers | Layout and effects | Semantics retained / S1 boundary |
|---|---|---|
| `workspace.workspace_paths`; build, pipeline, validate, conflicts, doctor, interface, migrate, opportunities, provenance, review, runtime, save/save_risk | Manifest schema 1; reference/working paths; opens without writes | Existing tuple/dict return and permissive legacy API unchanged; new WorkspaceView validates its own stricter supported boundary |
| `intake.intake_archive` | Convention `original/archive`, `original/extracted/<selected_root>`, `working`, `reports/intake.json`; copies then scans/reports | ASSESSMENT_REQUIRED; selected root is recorded, not proof of source/jar authority, compile or behavior |
| `revive.revive`, packet/ledger callers | Convention `working`, `reports`; can apply approved fixers | Existing owner/standing policy and confidence/tier/complexity distinctions unchanged; view opening never invokes revive |
| `validate.validate_workspace` via CLI/pipeline | Manifest layout; writes validation.json/report | Reference versus checkpoint, scan severity, full compile coverage; runtime NOT_CONFIGURED unless separate profile. This is not current live acceptance |
| `release.release_mod` via archive CLI and promotion | Direct mod + explicit original/baseline; dry run by default, writes only on apply with passing gates | `require_behavior_evidence=False` at library default; CLI/promotion pass True. Preserve distinction; never infer caller-equivalent qualification |
| `archive.archive_mod` | Convention working/original/reports into Done; refresh preserves/reinstates prior archive on failure | Primitive packaging contract differs from guarded CLI; do not promote it into a qualification API by wrapping it |
| `live/live_trust.archive_gate` via `cmd_archive` and `probe/probe_group` | Evaluates current live provenance and shipping explanations | Existing gate remains authoritative; S1 receipts cannot manufacture CURRENT from unknown/old/wrong runs |
| `promote.promote_mod` | Convention workspace; evidence/routing audit, behavior required, staged release into Done | Explicit source/compile/static/package/dependency/API evidence; live required except READY_FOR_LIVE_TEST path. S1 must expose this difference rather than rewriting labels |

## WorkspaceView v1 boundary

A frozen, in-memory descriptor records the physical root, dialect, original container, selected original mod, working mod, optional reports/checkpoints, selection source, and unavailable capabilities. It stores no PASS/acceptance or durable case ID. All provenance is UNVERIFIED until later exact-input hashing/receipts establish it. No JSON, directories, reports or input bytes are written by opening.

Manifest paths must be schema-1, contained, physical relative paths and disjoint roles. Convention layout is `original` + `working`; intake's selected root may identify the original mod only when its schema/mode/path are supported. Older nested originals need an explicit relative selection. Explicit original selection takes precedence over intake selection; unconsumed intake/legacy report data remains unverified. Mixed dialects, malformed path-defining records, absolute/drive/UNC/traversal paths, missing mod roots, junctions/symlinks and overlaps refuse. Optional reports/checkpoints are reported unavailable rather than created. This validates selected path boundaries, not every nested mod payload, hash integrity, source-versus-jar authority or concurrent filesystem mutation; later candidate freezing must revalidate those.

## Initial qualification profile design (not enforced)

`rc8-local-new-game/v1`: a local-maintainer, new-game scope on the declared RC8 core/provider/launcher context. Required dimensions: source authority and review/routing; exact candidate/package identity; structural/static checks; compile (only NOT_APPLICABLE with evidenced absence of active applicable sources); dependency/API resolution; observed applicable new-game/campaign/combat obligations; licence/local-only restrictions for selected finalization. Save upgrade is outside this scope and remains explicitly unresolved where required. An absent receipt is INCOMPLETE, not NOT_APPLICABLE. An old receipt without matching identity remains unknown/stale, not PASS.

No new profile is made active and no caller policy changes in S1.1/S1.2. Before S1.4 enforcement, review the exact required checks/scenarios, applicability rules and selected caller(s); before S1.5 local finalization, review preservation/retry/rights behavior. Public distribution is a separate authorization. Existing archive/acceptance/auto-accept gates remain unchanged.
