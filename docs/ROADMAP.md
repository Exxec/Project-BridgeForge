# BridgeForge roadmap

## Completed evidence foundations

- Read-only mod, JAR, bytecode, source, JSON-tolerance, dependency, and
  campaign-identity analysis.
- Copy-only workspaces, review-gated source/bytecode changes, build-profile
  evidence, and explicit runtime-smoke profiles.
- Cross-mod, release-lineage, corpus, and explicit local-library API reports.

## Current hardening tranche

1. Archive preflight reports extraction hazards and mod-root ambiguity.
2. Explicit archive staging records a hash-backed sidecar manifest and never
   writes into the archive or staged mod directory.
3. Corpus audits expose deterministic file/JAR budgets and aggregate observed
   workload, including skipped-budget rows.
4. Library API inventories are schema-validated before matching; malformed,
   stale-schema, or tampered reports are rejected rather than interpreted.
5. CLI safety paths have direct regression coverage alongside library-level
   tests.

## Next tranche: historical authority packets

Vacuum's revival exposed a reusable gap between ordinary archive intake and a
behavior-preserving migration decision. BridgeForge should be able to assemble
and validate a historical evidence packet without treating prose, filenames,
or compilation as runtime authority.

1. **Evidence-manifest schema.** Record each input's role, stable local alias,
   size, SHA-256, claimed version, provenance kind, trust limit, and whether a
   comparison is sampled or exhaustive. Keep executable inputs read-only and
   keep historical and target installations in separate environment records.
2. **Archive-coverage diagnostics.** Identify paginated topic captures,
   complete print/export archives, canonical URLs, post/message counts,
   edited-post metadata, hidden/spoiler text, and missing companion assets.
   Compare overlapping normalized bodies so a partial page can corroborate a
   complete archive without being mistaken for one. This is local evidence
   ingestion, not a web scraper or a source-code authority decision.
3. **Installer-to-install attestation.** Stream selected installer/archive
   entries to hashes without executing or unpacking over an installation, then
   report `EXACT_SAMPLED_MATCH`, `EXACT_EXHAUSTIVE_MATCH`, `MISMATCH`, or
   `UNVERIFIABLE`. Keep the package label, byte match, and independent vendor
   authentication as three separate claims.
4. **Authority and conflict ledger.** Preserve distinct evidence classes for
   mod source/JAR behavior, historical engine/default data, direct author
   statements or versioned changelogs, community observations, target API or
   engine evidence, and unresolved conflicts. Dated release notes outrank an
   edited evergreen opening post for chronology; executable behavior outranks
   prose for what shipped. Conflicts remain visible and block automatic policy
   selection.
5. **Provider and lifecycle ownership map.** Inventory overlapping classes,
   resource keys, metadata-selected plugins, settings providers, initialization
   phases, and load/combat callbacks across bundled and target libraries. Class
   availability or duplicate-name de-duplication is not behavioral equivalence
   and must not authorize dependency replacement.
6. **Behavior-fixture specification.** When static evidence ends, emit a
   reproducible fixture containing exact input hashes, isolated runtime,
   controlled setup/actions, required observations, acceptance criteria,
   rollback boundary, and stop conditions. Fixture generation must not launch
   the game; execution remains an explicitly authorized MANUAL or external
   workbench step.
7. **Migration-candidate gate.** A rule may advance from evidence to a bounded
   implementation candidate only when historical behavior, target capability,
   invocation/ownership, allowed diff, prohibited changes, and acceptance tests
   are all established. Compiler-error reduction is never an equivalence test.

### Tranche exit criteria

- Reports are deterministic and schema-versioned; path redaction does not
  remove hashes, version claims, comparison scope, or trust limits.
- Tests cover a partial topic page plus complete print archive, edited-post
  chronology, missing assets, a sampled exact installer match, one mismatch,
  and an unauthenticated-but-byte-matching package.
- Tests cover duplicate library classes with different plugin owners or
  initialization phases and prove that no automatic replacement is emitted.
- Conflicting author prose and executable arithmetic remain separate ledger
  entries and force `REVIEW` or `MANUAL` rather than a guessed migration.
- Generated runtime fixtures are inert data, reference immutable inputs, and
  cannot overwrite an installation, source mod, save, or known-good package.

## Lessons from the 2026-09-08/09 revival batch

The Broken Star, Omega Trauma, Edmund's Church, Void-Tec, FlowerGod, SEEKER,
and Exigency assessments expanded the evidence base beyond the earlier Flu-X
and Vacuum work. Source-bearing candidates reached clean compile/package
results; Omega Trauma's source-unavailable core instead reached a zero-break
bytecode-linkage result without a rebuild. Six reached an automated
launcher/main-menu boot; none completed its full interactive behavior matrix.
Exigency also has an independent redistribution-license gate. These are
separate states and must not be summarized as either "untested" or "ready"
without qualification.

- **Compatibility is bidirectional.** Outgoing bytecode linkage can prove that
  referenced target symbols exist, but it cannot detect new abstract methods on
  interfaces implemented by a legacy class. A full compile or an explicit
  interface-obligation walk is required. Compiler diagnostics must be repeated
  until stable because `javac` may reveal only one missing obligation per class
  per pass.
- **Error counts require a build-input identity.** Counts changed materially
  when missing libraries, alternate JAR sets, path handling, or Lombok versions
  changed. Every count must travel with the JDK, target release, source roots,
  classpath hashes, annotation processors, and exact command; the number alone
  is not evidence of progress or complexity.
- **The merged runtime namespace needs its own audit.** A mod file can shadow a
  vanilla file by relative path even when its internal id differs. Conversely,
  a same-name bundled companion may be harmless when it is byte-identical.
  Compare `.system`, `.ship`, `.wpn`, `.variant`, and `.skin` paths against the
  selected target installation and other enabled mods, then classify collisions
  by content and provider ownership.
- **Content validation must run in both directions.** Forward reference checks
  missed orphan `.wpn` files absent from `weapon_data.csv`. Structural parsing
  missed station-module variant ids placed in weapon slots, which produced a
  boot-fatal modal dialog. Validate registrations, consumers, slot kinds, CSV
  widths, target enums such as fighter-wing roles, and unreferenced specs.
- **Source, JAR, and loader authority are different claims.** Reconcile every
  compiled class with the shipped JAR, detect loose-source/JAR duplicates, and
  record which provider the loader actually used. Prefer current public APIs
  over maintaining vendored copies of vanilla classes, but document any
  player-visible behavior intentionally changed by that substitution.
- **A successful log grep is not a successful boot.** Exact `gameVersion`
  matching can silently uncheck a mod. Java fatal errors may appear only in an
  AWT dialog while the wrapper process exits and `java.exe` remains alive.
  Launch evidence must include mod-selection confirmation, direct child-process
  state, main-menu markers, modal/fatal capture, and the exact enabled mod set.
- **Target data is authority for mechanical schema rules.** Preserve loader-
  supported legacy JSON syntax rather than normalizing it. Derive schema and
  conversion rules from the selected target installation or documented owner
  policy, apply them mechanically, and reserve balance or prose reconstruction
  for REVIEW or MANUAL decisions.
- **Technical readiness and release authority are independent.** A clean build,
  package, or live test cannot override asset or redistribution terms. Record a
  legal/distribution gate before creating a release artifact or copying a
  candidate to `Done`.
- **Status documents must be derived, not append-only narratives.** The batch
  left stale statements about remaining compile work and "no live test" beside
  later boot evidence. Preserve chronological evidence in reports, but generate
  the active status board and plan checkboxes from the latest per-gate results
  so contradictory summaries cannot become handoff authority.

## Next tranche: revival-attempt feedback gates

1. **Attempt baseline and change ledger.** At intake, record the immutable input
   hash, working-copy root, Git/worktree state, report versions, and a timestamped
   attempt id. Later reviews can then distinguish new work from pre-existing
   dirty files and repeated or superseded findings.
2. **Build-input attestation.** Extend build evidence with normalized source
   roots, JDK release/hash, complete classpath and processor hashes, target
   release, exact command, compile-pass number, diagnostic count, and output
   class inventory. Reject comparisons between non-equivalent input sets.
3. **Bidirectional API contract check.** Combine outgoing class/member linkage
   with implemented-interface and superclass obligations from the selected
   target API. Treat a clean full-source compile as additional evidence, not a
   substitute for runtime behavior.
4. **Merged-namespace and content-graph audit.** Build a provider map across the
   candidate, target installation, and explicitly enabled dependencies. Check
   relative-path shadowing, duplicate providers, registration tables, consumers,
   slot/value kinds, orphan specs, and target schema/enums without inventing
   missing balance values.
5. **Source-to-package authority gate.** Reconcile source outputs, loose classes
   or sources, bundled JARs, generated classes, manifests, and backup artifacts.
   Require an explicit decision when multiple definitions could load; exclude
   dependency sources accidentally compiled from the classpath.
6. **Launch-observation harness.** Separate `SELECTABLE`, `PROCESS_STARTED`,
   `MAIN_MENU_REACHED`, and `BOOT_FAILED` evidence. Monitor the actual Java
   process, capture dialogs or screenshots where possible, retain stdout and
   game logs, and record enabled dependency versions. Never infer success from
   wrapper exit alone.
7. **Tiered live-validation records.** Track automated boot, campaign creation,
   combat/mission behavior, persistence/save-load, optional-dependency matrices,
   and human observations as separate test ids in a machine-readable gate
   record from which plan, report, and status views are rendered. A partial
   matrix remains `READY_FOR_LIVE_TEST`; skipped rows are not passes. Final
   report parsing must reject missing, repeated, conflicting, or non-final
   completion-status declarations.
8. **Release-rights and artifact gate.** Record redistribution/license status
   independently of technical status. Require a completed report plus exact
   candidate-to-ZIP attestation before `Done`; preserve the prior known-good
   output when either gate fails.
9. **Feedback promotion.** Every deterministic runtime discovery must be
   evaluated for a synthetic scanner fixture and regression test. Behavioral or
   policy discoveries remain REVIEW/MANUAL fixtures with explicit acceptance and
   stop conditions rather than becoming automatic rewrites.

### Implementation progress

- `revival-audit` now rejects duplicate completion statuses and a status that is
  not the report's final non-empty line.
- Scanner content-graph coverage now records local `.wpn` files missing from the
  mod's own registration table and detects local variant ids assigned as weapon
  values. Merged target/dependency provider resolution remains outstanding.
- Target-bound incoming-obligation checks now cover the interface expansions
  observed in `OnHitEffectPlugin`, `AutofireAIPlugin`, `ShipSystemStatsScript`,
  and the refit-picker obligation on direct `HullModEffect` implementations.
  General target-JAR-driven obligation discovery remains outstanding.

### Tranche exit criteria

- A synthetic interface-expansion fixture passes outgoing linkage but fails the
  new incoming-obligation check, proving the two directions remain distinct.
- Reports reject compile-count comparisons whose JDK, dependency hashes,
  processor version, source roots, or target release differ.
- Fixtures cover a different-id vanilla path collision, a byte-identical
  companion file, a module variant placed in a weapon slot, and an orphan spec
  missing its registration row.
- Launch tests cover an exact-version selection mismatch and a wrapper exit with
  a surviving Java process/modal failure; neither may be reported as a pass.
- Status generation represents offline validation, automated boot, interactive
  behavior, persistence, and release rights independently and contains no stale
  superseded claims; final-status tests cover duplicate and non-final status
  lines as well as conflicting status names.
- A release-rights denial blocks distribution and `Done` promotion without
  blocking safe local assessment, compile, or explicitly permitted testing.
- Final audit proves report completeness and byte-identical candidate/archive
  content while retaining `LIVE VALIDATION REQUIRED` wherever the interactive
  matrix is incomplete.

## Protocol for future revival attempts

1. Preserve and hash the original; create a distinct working copy under
   `In operation` and record the attempt baseline.
2. Establish source/JAR authority, redistribution limits, target installation,
   dependency set, and loader providers before estimating complexity.
3. Complete `reports/REVIVAL_PLAN.md`, classify every finding as SAFE, REVIEW,
   or MANUAL, and calculate the authoritative workflow score from observed
   signals rather than age, file count, or a first-pass error total.
4. Run merged-namespace, content-graph, outgoing-linkage, incoming-interface,
   and full compile checks before changing code or data.
5. Implement only approved SAFE work or higher-level approved REVIEW work;
   record every intentional behavior difference from the historical version.
6. Rebuild from attested inputs, reconcile source and package contents, and keep
   the previous candidate and original artifact recoverable.
7. Run automated selection/main-menu boot checks, then the mod-specific human
   campaign, combat, optional-dependency, and save/load matrix.
8. Promote deterministic failures into BridgeForge detectors and fixtures;
   update the current plan/report/status state instead of appending a conflicting
   summary.
9. Run the final report and candidate-to-archive audit. Move or copy to `Done`
   only when the completion status, live-test requirements, package identity,
   and redistribution authority all permit it.

## Intentionally blocked pending verified evidence

- MagicLib, LazyLib, AshLib, and other library migrations remain scaffolded or
  research-only until their evidence contract is complete.
- Reflection, wildcard imports, bytecode-only references, runtime behavior,
  and save compatibility remain review evidence, not automated conclusions.
- Arbitrary forum crawling, automatic gameplay-policy selection, execution of
  historical installers or games, and vendor-authenticity claims without an
  independent checksum/signature source remain out of scope.
