**S-series implementation (owner 2026-10-24: "plan S series implementation then proceed to start S1").**
[Implementation plan](docs/S_SERIES_IMPLEMENTATION_PLAN.md) translates S1-S4 into dependency-ordered slices. S1 starts with the compatibility/policy map and read-only workspace boundary; [progress and handoff](docs/S1_PROGRESS.md) records evidence and next work. S1 remains IN_PROGRESS; qualification, real pilot/live, rights, save changes and finalization gates stay open. S2-S4 are planned, not implemented.

**85. Automation and fewer tokens per task (owner-approved 2026-10-22).** From this session's hand work. Nothing below is
built yet; LIVE TEST NOT PERFORMED.
- 85.1 Live-batch command: `live-batch plan` turns LIVE_PENDING gates (`gates.json` needs, `board --live-pending` blocks) into
  a run plan; `live-batch run` performs it unattended (rig-up, probe-group live with the gate's launcher, report); `live-batch
  summary` writes a compact per-run verdict file with the next `record` / `baseline-accept` / `revise finalize` commands, and
  can notify when done. Replaces hand-written PowerShell runners (the 2026-10-22 runner skipped every run through a
  return-value bug). Done when the 2026-10-22 batch can be reproduced from gates.json alone.
  Environment bundles (owner 2026-10-22: "going forward we will need to bundle the various environments in live testing"):
  a named bundle is a list of launch environments (launcher, Java, pre-patcher on/off), e.g. `standard` = FR Java 25, FR Java
  28 and direct Java 28, each with and without the pre-patcher (the six-launch Ironclads matrix of 2026-10-22). A gate names
  a bundle instead of one launcher; `live-batch plan` expands it, stages each candidate once and runs it through every
  environment before moving on, and records the gate PASS only when every environment passes (per-environment results kept
  in the run records). Archive-eligible runs use the `standard` bundle unless the gate says otherwise.
- 85.2 Refactor-review evidence: one command that produces item 83 section 6's evidence for a PR as JSON (test counts
  before/after, skips, coverage, CLI golden hash, rename similarity, wheel file list, Salvor suite against the branch). Done
  when a refactor PR's review reads that one file.
- 85.3 Workspace brief: one page per workspace (versions, changed files, open findings, accepted baselines, past live runs,
  earlier reviews and decisions such as reports/ASTRA_LIVE_REVIEW.md), printed before any investigation. Done when the EPTA
  Alicerce/narcepolis question would have been answered from the brief.
- 85.4 Crash intake: given a player's starsector.log and enabled_mods.json, name the failing mod and stack, match it to a
  workspace and propose the gate that reproduces it. Done when a recorded crash log is matched to its workspace and gate.
- Harness fixes from the same batch: BUGS.md LIVE-001 (report attribution), LIVE-002 (total conversions and the combat
  stage), LIVE-003 (pre-patcher drift), LIVE-004 (stale extras in rig copies).

**84. Feature tracing and transplanting (owner-approved 2026-10-22; long term).** Goal: BridgeForge can pick a mod apart and
trace every feature end to end (data ids, assets, code, hooks, runtime behaviour), and can transplant a named feature from one
mod into another with its dependencies, id remapping, conflict and save checks, live validation and recorded provenance. Design
note: [docs/FEATURE_TRANSPLANT_PLAN.md](docs/FEATURE_TRANSPLANT_PLAN.md). Rules: bytecode stays authoritative and decompiled
code is a reading aid; no research finding becomes a migration or transplant rule automatically (item 82's sequence: finding ->
validated pattern -> candidate -> approved rule); a gate is never upgraded without recorded evidence; starts after item 83's
refactor (B3 at least), because T0 depends on the package layout. Nothing below is built; LIVE TEST NOT PERFORMED.
- T0 Feature graph. Builds one queryable per-mod graph joining every id (hull, weapon, hullmod, ship system, faction, market,
  rules.csv entry, sprite, sound, string) to the code that creates, reads or registers it, and to what calls that code.
  Reuses Atlas (census, classfile, exemplars), the D-series (archaeology, behavior-map) and scanner facts, merged per concept
  as item 82.2's reconciliation decides; the 82.8 method map. Done when `research report` answers questions from the graph
  instead of by re-scanning.
- T1 Feature boundaries. Builds the named-feature record: its files, classes, ids, memory keys, scripts, listeners and hook
  points, produced by `research report` and stored as a reviewable record. Reuses T0, `research report` (82.1), REMOVALS
  records. Done when the Templar Crusade and SEEKER station modules each have a boundary record a person agrees with.
- T2 Runtime trace. Builds probe stages that confirm a feature's entry points and hooks fire, with the evidence linked back
  into the graph (STATIC -> OBSERVED). Reuses the probe mod, `probe-group live`, live records, gates.json scheduling and
  `board --live-pending`. Done when one feature's hooks are OBSERVED in a recorded run.
- T3 Data-only transplant. Builds dependency closure (assets, CSV rows, settings keys, library dependencies), id and
  namespace remap, a collision check against the target, and install into a target workspace through `revise`. Reuses
  scanner id indexes, content parity, `revise prepare/finalize`, the archive gate. Done when one EPTA ship line moves into a
  test mod, then builds, boots and passes a live gate.
- T4 Code transplant planning. Builds the plan for code-backed features: decompile the feature's classes, remap packages,
  list the hook points to adapt (ModPlugin onNewGame/onGameLoad, listeners, rules.csv, economy) and rebuild against the
  target's classpath. Reuses `decompile-jar`, 82.7-82.9 (readable code, method map, `research diff`), `rebuild-jar`,
  `bytecode-inspect`. Adapting the hooks is human or agent work that BridgeForge checks; never automatic. Done when one
  code-backed feature is transplanted into a test mod and passes a live gate.
- T5 Save safety. Builds the answer to what an existing save needs when a feature is added or removed. Reuses the save tools
  (save-doctor, save compatibility, fingerprints), migration packs (docs/MIGRATION_PACK_CONTRACT.md), REMOVALS and
  `revise migration`. Done when adding and removing the T4 feature both load an existing save cleanly in a live run.
- T6 Provenance and permission. Builds a provenance record for every transplanted file: source mod, version, file hash,
  author and licence. Reuses release_policy.json and the archive gate; without the author's permission the result stays
  LOCAL_ONLY. Done when the archive gate refuses a transplant with missing provenance.

**83. Structural refactor across the repos (owner-approved 2026-10-22).** Reorganisation only, no behaviour change: BridgeForge's
flat 291-module package into subpackages, `fixers.py` split, docs/roadmaps consolidated, command audit and grouping with aliases,
test-speed split; Project Go GUI shell split; optional VoidSmith splits; Salvor import updates. Plan, rules and review evidence:
[docs/REFACTOR_PLAN_2026-10.md](docs/REFACTOR_PLAN_2026-10.md). Executed by a separate agent; each PR reviewed against its section 6.

B0 implementation checkpoint 2026-10-22 (merged in PR #64, `f252b033`): recursive source inventories, package-relative
audit/fingerprint identities and nested test selection are implemented. Covered by
[tests/test_source_paths.py](tests/test_source_paths.py) and the existing audit/registry/merge-train tests;
2,602 tests, OK (12 skips unchanged), hermeticity PASS, coverage 83.06% (baseline 82.46%).
CLI golden/generated docs unchanged. Search inventory, fingerprint refresh and later move obligations:
[docs/REFACTOR_B0_AUDIT.md](docs/REFACTOR_B0_AUDIT.md). B1 onward remains pending; LIVE TEST NOT PERFORMED.

B1 implementation checkpoint 2026-10-22 (owner-approved after review fixes; merge pending CI): earlier roadmap pages and the completed October 18
audit moved to [docs/archive/](docs/archive/README.md); ROADMAP-3 is the active backlog. Archive navigation and current
entry points are repaired; the still-cited architecture assessment stays current. Legacy roadmap-lint paths still check
all 336 item keys with the unchanged evidence baseline, covered by tests/test_roadmap_lint.py.
Validation: 2,603 tests, OK (12 skips unchanged), hermeticity PASS; coverage 83.07%; gates lint has zero contradictions.
Companion citation PRs: [VoidSmith #13](https://github.com/Exxec/Project-VoidSmith/pull/13),
[Salvor #12](https://github.com/Exxec/Project-Salvor/pull/12), [Go #10](https://github.com/Exxec/Project-Go/pull/10).
Review fix: root numbering resumes after the archived page count, preserving future ROADMAP-4.md and later pages;
the relocation test detects an unevidenced Done claim on page 4. Companion follow-ups use the stable hardening plan
and merge after B1 (the original citation PRs were already merged).
No pending owner/live/research gate is closed by this archive step.

B3 checkpoint 2026-10-23: research independently rechecked (78 tests); Atlas continued in an isolated
review worktree, 2612 tests, 12 unchanged skips, coverage 83.1088957%, hermeticity PASS.
See [Atlas evidence](docs/REFACTOR_B3_ATLAS_AUDIT.md) and [stack](docs/REFACTOR_STACK.md).
Review/merge and remaining B3 families are pending; LIVE TEST NOT PERFORMED.

B3 corpus checkpoint 2026-10-23: six modules moved with import-only AST changes, 2612 tests,
12 unchanged skips, coverage 83.1088957%, hermeticity PASS; Salvor 208 tests (4 unchanged skips).
See [corpus evidence](docs/REFACTOR_B3_CORPUS_AUDIT.md). Local dependent branch only; escalation
is the next family. B3 and owner review/merge remain open; LIVE TEST NOT PERFORMED.

**B3 implementation checkpoint 2026-10-23:** all planned families now live in subpackages on the local stacked branches,
with consumer facades and preserved history. Full per-family suites, coverage, CLI, wheel and installed Salvor checks pass.
See [completion evidence](docs/REFACTOR_B3_COMPLETION.md) and [stack](docs/REFACTOR_STACK.md).
Owner review/merge, B4-B6 and all live gates remain open; LIVE TEST NOT PERFORMED.

B4/B5 checkpoint 2026-10-23: owner chose to retain the current CLI; grouping/deprecations declined. B5 fast/slow unittest CI partitions implemented and locally validated; [evidence](docs/REFACTOR_B5_TEST_SPEED.md). Owner review/merge, hosted CI and B6 remain open.

**82. Research that serves revivals: consolidate, compare, promote (owner-approved 2026-10-21).** Not a new research
architecture. S1 stays the critical path; runtime evidence is the limiting resource. Guiding rule: every research
capability must resolve a question from an active revival, eliminate repeated manual investigation, or improve the
reliability of existing evidence. Success criterion: a real question that previously needed manual inspection of several
mods is answered by `research report` with the relevant evidence, contradictions and next test, without invented
conclusions.
- P0 82.1 Comparative research report, read-only, with a question contract:
  `research report FEATURE --case WORKSPACE --question TEXT`. Answers: what feature, which mods implement it and how,
  which similarities/differences are supported, which conclusions remain hypotheses, which experiment (or existing gate)
  would resolve the important unknowns. Every claim carries STATIC / OBSERVED / VALIDATED and its evidence location.
- P0 82.2 Evidence reconciliation before any merge of code: the report consumes Atlas (census, exemplars, migrations)
  and the D-series (archaeology, behavior-map, hypotheses, probe-baseline/behavior-diff) independently and tabulates
  agreement: both detect (corroborating static evidence, not independent validation: same code), Atlas only
  (D-series coverage gap?), D-series only (Atlas blind spot?), both but different (semantic disagreement). Disagreements
  stay as evidence; the counts become the basis for deciding later which stack is authoritative per concept.
  - 82.1 and 82.2 progress 2026-10-22: `research report FEATURE --case WORKSPACE --question TEXT [--write DIR]` implemented
    (`bridgeforge/cmd_research.py`, `research_*.py`; `tests/test_research_report.py`, synthetic fixtures only). Read-only (the atlas
    database is opened `mode=ro`, `--write` inside the workspace is refused). Reuses `atlas.index_mod`, `atlas_migrations.mine`,
    `lookup.load_graph`, `behavior_discovery.build_behavior_model`, `dropped_sweep.check_workspace`, `removals`, `live_ledger.read_runs`
    and `gates.load_gates`. Missing inputs are listed with the producing command; archaeology is built in memory (about 25 s per tree)
    unless `--no-build`. A root-level `reports/` folder of a tree is BridgeForge's own output and is excluded from concept evidence.
    First pilot (Templar Crusade, 82.3 groundwork): `bridgeforge-state/research/templar-crusade/` (git-ignored).
- P1 82.3 Active-case pilots: Templar Crusade first (removed vs replaced vs redistributed vs re-created: the
  semantic-classification problem behind the dropped-feature false positives), then SEEKER station modules (does the
  workflow generalize). Stopping condition per investigation, e.g. Templar is complete when the report identifies the
  relevant Crusade implementations, explains the apparent feature changes, lists unresolved differences and ties each
  needed runtime test to an existing gate. No need to explain every class.
- P1 82.4 Knowledge promotion: extend existing records (R4 standing rulings, the RC8 behaviour facts, REMOVALS,
  exemplars) with status STATIC / OBSERVED / VALIDATED, an applicability predicate, supporting evidence, counterexamples
  and invalidation conditions, so the question "does this still apply here?" can be answered. The statuses are not a
  ladder: an API-signature claim can be VALIDATED from authoritative static evidence; a fleet-spawning claim needs
  runtime evidence. VALIDATED means a defined acceptance test, including negative cases, within a declared scope.
- P2 82.5 Runtime scheduling: research experiments are gates in `gates.json` (needs.scenario), so `board
  --live-pending` batches them with revival gates in the same rig sessions.
- Later 82.6 Active research selection, once there is enough empirical data to measure uncertainty against; corpus
  acquisition (multiple releases of the same mods) for version timelines.
- P1 82.7 Readable code in research reports (2026-10-22). `decompile-jar` (Vineflower 1.12.0) and `rebuild-jar` exist but
  serve revisions only; research reads class files directly (`atlas_classfile`). `research report` decompiles the classes
  a question touches into git-ignored `bridgeforge-state/research/<case>/decompiled/<jar-sha256>/`, records the jar hash
  and Vineflower version, and quotes the relevant methods. Bytecode stays authoritative; decompiled Java is a derived
  reading aid (STATIC), never evidence of runtime behaviour, never copied into a mod.
- P2 82.8 Method link: run Vineflower with bytecode-source mapping so each decompiled line range maps to the
  `class#method descriptor` that `bytecode-inspect` and Atlas use; a finding made in readable code points at the exact
  bytecode method, and vice versa.
- P2 82.9 Readable version diffs: for a migration pair, diff the decompiled text only of methods whose bytecode changed
  (`bytecode-diff` decides what changed; the decompiled diff explains it). No second decompiler (CFR) until two readings
  of one method disagree in a way that matters; Recaf stays a manual tool.
  - 82.8 and 82.9 progress 2026-10-22: Vineflower 1.12.0 options `-bsm=1` (bytecode-source-mapping) and `-dcl=1` (dump-code-lines) give
    (original line, decompiled line) pairs, but only in the extra field of an archive entry and only when the input is an archive too, so
    `research_decompile.run_vineflower` packs, decompiles and unpacks a temporary jar. `research_methods.py` joins the pairs with the bytecode
    helper's per-method line tables into `<class>.methods.json` (`a/b/C#name descriptor` -> decompiled range, else UNMAPPED with the reason) beside
    the cached `.java`; `lookup_line` and `lookup_identity` go both ways. `research diff OLD NEW` (a `research` subcommand: it shares the
    decompiler cache and `--write` rules of `research report`) uses `bytecode_diff.changed_methods` (per-method body digest) to pick the methods
    and diffs only their decompiled text. Tests: `tests/test_research_diff.py`. Limits found: a constructor Vineflower hides, or a method without a
    line table, is UNMAPPED; a compiler or debug-info change shows as a bytecode change whose decompiled text is identical (SAME_TEXT) or differs in
    local variable names only.
- P1 82.10 Release inventory as a command: `corpus releases ROOT...` scans folders and .zip/.7z/.rar archives for
  mod_info.json, writes releases.csv and RELEASES.md (copies per mod id, versions, game versions, forum thread and repo
  links from .version files) and a pairs queue for `atlas migrations --pairs-from`. Replaces the 2026-10-22 one-off
  script (`bridgeforge-state/release-inventory/`: 718 mod ids, 200 with two or more versions) and starts 82.6's corpus
  acquisition now.
- P2 82.11 Author changelogs as hints: parse the changelog shipped in each mod release (CHANGELOG.txt, changelog.md and
  similar) per version; `research report` quotes lines naming the feature, labelled AUTHOR CLAIM (weaker than STATIC:
  what the author says changed, not what the code shows). For Templar, a changelog line saying the Crusade moved or was
  cut is the fastest hint to confirm or refute in code.
- P2 82.12 Old game API: `api-diff` and `api how` need an older `starfarer.api.jar`. Owner: locate old starsector-core
  installs (0.95.1a, 0.96a, 0.97a); then run `api-diff` once per step to RC8 and let `research report` and `atlas
  migrations --old-api/--new-api` use the results, so migration proposals rest on the authoritative API change, not
  only on mod-pair co-occurrence.
- Prohibited: a research conclusion never turns into a migration rule automatically. Sequence: research finding ->
  validated pattern (conditions) -> migration candidate (can it safely guide an intervention?) -> approved deterministic
  rule (explicit approval, safety checks, regression evidence). Learn API patterns from other mods, never copy their code
  without the usual attribution and permission rules.

**80. Less hand work across the projects (owner 2026-10-21: "work them all in your preferred order").** Order: 80.1, then
80.2 with 80.6, 80.3, 80.5, 80.4, 80.7, 80.8.
- 80.1 **Built offline, merged (#41, #47, #51, #53); live pending where it needs the rig.** Merge-friendly changes: `changelog.d/` fragments assembled at release (no PR edits CHANGELOG.md); generated files
  (CLI golden, COMMANDS.md, CHECKS.md) regenerated on conflict or by CI; pre-push runs the cross-cutting tests (probe
  contract, safeio ratchet, docs index, CLI golden) plus the tests of touched modules; a `merge-train` command.
- 80.2 **Built offline, merged (#43); live pending where it needs the rig.** Rig-session planner: `board --live-pending` gathers pending live gates from every repo, groups them by rig
  configuration and prints one session plan with commands; results are written back as PASS/FAIL/NOT_TESTED (with 79.7).
- 80.3 **Built offline, merged (#45); live pending where it needs the rig.** Archive gate wired: `archive` and `revise finalize` run dropped-features, content parity and the orphaned-backup
  check and refuse unexplained drops; a passing live run with probe 0.3.x offers `archive --refresh`.
- 80.4 **Built offline, merged (#44); live pending where it needs the rig.** `decision apply DRAFT` (77.20): ticked boxes become baseline keys, REMOVALS entries, roadmap lines and rig steps.
- 80.5 **Built in Salvor, merged (Project-Salvor PR #7); first nightly pin PR not yet observed.** Pin autopilot: Salvor tests nightly against BridgeForge main and opens a pin-bump PR when green; shared-fixture
  drift with Project Go turns blocking once Project Go updates.
- 80.6 **Built offline, merged (#43); live pending where it needs the rig.** Status generated from `gates.json` per repo (R7): status tables and the rig plan come from it; a lint fails CI when
  a status doc contradicts it.
- 80.7 **Built offline, merged (#46); live pending where it needs the rig.** Review triage: VoidSmith's 726 calibration rows and BridgeForge's escalation packets grouped by the reason they
  wait, so one decision clears a group.
- 80.8 **Built offline, merged (#48); live pending where it needs the rig.** Agent hygiene preflight (77.13): untracked code, unexpected edits to tracked files and broken builds listed before an
  agent session ends or a commit is made.
- 80.9 **Built (PR pending merge, pairs with Project Go H3); hosted CI proof is this PR's own run.** Real-manifest contract check (2026-10-22): next to the shared-fixture comparison, CI imports
  an actual coverage manifest exported by Project Go from a fixture mod, so a producer change that breaks the consumer
  fails CI instead of being found by hand.

**81. Dissection: research from current mods (owner 2026-10-21: "throw current mods at bridgeforge and see if we can
glean more research").** Read-only over the player's installed mods and any folder given, built on `atlas`, `api-diff`,
`corpus-index` and `provider-index`; every result is labelled STATIC (what code references, not what runs).
- 81.1 **Built offline, merged (#42); live pending where it needs the rig.** API usage census: which RC8 API classes/methods each mod's jars and loose scripts call; `api how SYMBOL` links an
  `api-diff` removal to the replacements working mods use, with example files.
- 81.2 **Built offline, merged (#50); live pending where it needs the rig.** Migration mining: where two versions of a mod exist, cluster the API replacements between them into candidate
  rewrite rules with a count of independent mods (R4 needs three before a ruling).
- 81.3 **Built offline, merged (#42); live pending where it needs the rig.** Save-risk census: persistent-data keys, scripts added on every load (duplicate-script risk), readResolve, transient
  fields, per mod.
- 81.4 **Built offline, merged (#42); live pending where it needs the rig.** Library census: LazyLib, MagicLib, GraphicsLib and other library calls and the versions they need.
- 81.5 **Built offline, merged (#50); live pending where it needs the rig.** Feature exemplar index: working implementations of raids/FGIs, intel, custom entities, rings, station modules,
  for recreation work.

**Hygiene review 2026-10-19 (owner: "perform hygiene check then check roadmap for any worthwhile additions. implement if able then commit/push").** Item 77.3's lock-test timeout is implemented: the three live psutil scans query only their real fixture PIDs in a disposable subprocess with a 30-second timeout; fixture-child shutdown also has a deadline and kill/reap fallback. A regression verifies timeout propagation as a failure. Focused validation: 11 tests pass. This bounds test execution, not the production `who-locks` command, and supplies no game evidence. See `tests/test_locks.py`.

**78. Probe enhancements (owner 2026-10-20: "add and work them all").** The probe proves boot, id resolution and
combat, but missed a whole missing rules.csv (FIX-001), never proves a save reloads (R6 has no emitter, Project Go's
SAVE_RELOAD stays NOT_TESTED) and needs hand-written hooks per feature. In work 2026-10-20, offline (LIVE TEST NOT
PERFORMED until the next rig session):
- 78.1 Manifest id echo: the probe logs the run manifest id first; the evaluator refuses a mismatch (R1 trust).
- 78.2 Save-and-reload fingerprint: per-mod sector fingerprint before `cmdSave()` and after reload, compared; sets
  `milestones.reload_after_save` only when observed equal; becomes R6's in-game evidence emitter and covers SEEKER SK-6c
  and part of Salvor R4.
- 78.3 Live content parity (77.17): per-mod loaded counts against counts taken from the candidate before launch.
- 78.4 Declarative per-mod scenarios: `reports/PROBE_SCENARIO.json` (settings for the rig copy, steps, expected log
  lines with deadlines), so rig steps 13-15 and future recreations need no probe code.
- 78.5 One probe: fold Salvor's `salvor_rig_probe` load/save/day stages into this probe as a `salvor` profile (after
  78.2 lands); Salvor's `rig-build-probe` builds that profile.
- 78.6 Clean exit: the probe writes a done marker; the harness closes the window and records a natural exit by default.
- 78.7 "What was exercised" per mod; a mod with nothing exercised is flagged HOLLOW.
- 78.8 Campaign frame time under load per day (`campaign_perf`), for the Crusade and SPW.

**79. Same treatment for other components (proposed 2026-10-20).** The probe gaps have counterparts elsewhere:
- 79.1 Scanner coverage report: per mod, which checks actually ran on which files (a scan can be as hollow as a probe
  run); unread file types listed instead of silently skipped.
- 79.2 Offline save fingerprint: Salvor and VoidSmith compute the same fingerprint sections from a save's XML, so a
  repaired or edited save can be compared with the probe's in-game fingerprint (78.2) and with its own original.
- 79.3 VoidSmith Save Workshop: every written copy carries an expected-fingerprint file; the probe's reload compares
  against it, closing "one Workshop copy loaded in game" and the capacity recompute question in one run.
- 79.4 Duel, raid and capacity sub-mods: the same manifest echo, done marker and scenario format as the main probe.
- 79.5 Project Go assurance import: read the new record blocks (fingerprint, content parity, scenario, exercised) as
  gate evidence; a HOLLOW member never passes CAMPAIGN.
- 79.6 SPW: map `campaign_perf` and combat-perf into `performance-report.json` so revivals carry a performance
  baseline (SPW roadmap item 5).
- 79.7 **Built offline, merged (#49); live pending where it needs the rig.** Rig harness: one launcher path (probe-group live, bf-test.ps1, boot-test) with the same manifest, exit and
  done-marker handling, instead of three.

**Owner follow-ups 2026-10-20 ("add both to roadmap. We should reassess other mods to see if they dropped any features").**

**77.14 Accept a single finding outside a packet.** `escalation accept` only matches findings already in an escalation
packet, and `scan --write-baseline` accepts every current finding at once. The Templars 0.9.8f `port-dropped-feature`
acceptance had to add its three keys by hand with `baseline.finding_dict_baseline_key`. Add `baseline-accept-finding
<workspace> <FINDING_ID[:FILE_PART[:EVIDENCE_PART]]> --reason` that adds only the matching keys, writes the reason to
`reports/ESCALATION_REVIEW.md` like `escalation accept`, and refuses when nothing or more than the named findings match.

**77.15 Templars Requisitions submarket (proposed recreation).** `TEM_MarketPlugin` ("Requisitions": the Templar
requisitions center, a MilitarySubmarketPlugin with Templar-only stock and commission rules) existed in 0.9.8f and was
removed upstream in 0.9.9e together with its `submarkets.csv` row, so the Templars 0.9.8f port lost it by inheriting the
newer base, not by a BridgeForge change. Owner decision pending: re-create it for RC8 (like the Crusade, a separate
`jars/` class plus the data row) or accept the upstream removal. `TEM_Radiated` (the Irradiated World condition) was
removed the same way and has no gameplay worth restoring unless a world uses it.

**77.16 Dropped-feature sweep across the queue (2026-10-20, report-only).** `scan_port.dropped_features(old, new)` was run
against each workspace's `original/` download (308 of 316 had one; local report in the session scratch,
`dropped-sweep/SWEEP.md`). Results: 19 workspaces with dropped items, 38 with port wording but no drops, 59 with only
strip/remove wording, 200 with nothing. Reviewed so far:
- **All the Domain Drones: real loss, shipped (BUGS.md FIX-001).** The whole `rules.csv` (430 triggers) is missing
  from `working/` and from both archived zips; only the fixer backup remains.
- **Yunru family (7 workspaces, 119 classes each): false positive.** Each `original/` holds the whole 9-part Yunru Core
  pack, so one part's working copy looks like it dropped the other eight. The sweep must compare with the matching
  sub-folder.
- **Templars 0.9.8f:** the known Crusade loss, which confirms the check works.
- Still to review by a person: Xenoargh AI Overhaul (53 classes) and FX Core (52), likely the owner-approved fold into
  RevenantLib; Ironclads (4 classes, 25 rules.csv triggers); SEEKER (5 classes); Better Deserving S-mods (4 classes);
  Mirfak Parcel Service (3 settings, 1 rule); and the remaining rows. Next: make the sweep a command (`dropped-features
  --queue`) that matches sub-folders, records intended removals (strip plans, RevenantLib folds) so they stop showing,
  and runs before `archive`; then review the remaining rows. Every confirmed loss gets a BUGS.md entry and a recreation
  or restore item.
- Built 2026-10-20: `dropped-features WORKSPACE | --queue DIR [--write DIR]` (old tree: PORT_SOURCE, else the
  `original/` mod root with the same mod id, else the only root, else UNDETERMINED) and `reports/REMOVALS.json` (77.19).
  Real queue: 11 DROPS_UNEXPLAINED, 9 UNDETERMINED, 296 CLEAN; all Yunru parts CLEAN; All the Domain Drones CLEAN after
  the FIX-001 restore. Unexplained to review: Xenoargh AI Overhaul (53 classes), Xenoargh FX Core (52), Templars 0.9.8f
  (31, decided), Ironclads (4 classes, 25 rules), SEEKER (5), Better Deserving S-mods (4), Mirfak Parcel Service (4),
  AI-War (2), Blackrock Drive Yards (2 settings), Maelstrom Imperium Unofficial Expansion (2). Not yet run before
  `archive`; strip and fold emission into REMOVALS.json waits for the code that applies a strip or retires a folded mod.

**Automation, gap coverage and hand-work reduction (proposed 2026-10-20, owner: "if there is further automation, gap
coverage or things to make hand work easier please add to roadmap").** Each closes a gap this session hit by hand.

**77.17 Live content parity (gap that let FIX-001 ship).** A LIVE_VALIDATED run proved boot and campaign load while the
mod's whole `rules.csv` was missing. Extend the probe's `content-ids` milestone to count what the game loaded per mod
(rules triggers, hulls, weapons, wings, industries, conditions, submarkets, planets/systems added) and compare with
counts taken from the candidate's `working/` data before launch; a shortfall FAILs the run with the missing ids.

**77.18 Archive content parity.** `archive-preflight` compares the archive's file list with `working/` and with
`original/` (by sub-folder for multi-mod packs): a data or script file in `original/` and absent from the archive needs a
recorded removal (77.19) or the archive is refused. Run `done-audit --content-parity` once over all 160 `Done/`
archives; each confirmed loss becomes a BUGS.md entry.
- Windows portability follow-up, 2026-10-20: resolve tool-owned materialization paths before guarded cleanup, and mark
  comparison errors UNDETERMINED rather than CLEAN. Both aliased-temp and failed-comparison regressions were reproduced
  before the fix; `tests.test_content_parity` covers them. Full suite: 2,314 tests, zero failures, 13 skips; hermeticity PASS.
- First pass done by hand 2026-10-20 (owner: "run a scan over all archived mods including ironclad"; static, offline;
  each shipped zip against its own `original/`; local report `done-audit/DONE_AUDIT.md` in the session scratch).
  154 folders: 124 CLEAN, 20 REVIEW, 5 LOSS_SUSPECTED, 5 UNDETERMINED; no `.bak` or orphaned fixer backup shipped.
  - **All the Domain Drones 0.6: real loss** (FIX-001; restore done in `working/`, live run and refresh pending).
  - **Templars 0.9.8f:** decided 2026-10-20 (Crusade re-created; reports/submarkets/console CSVs follow 0.9.9e).
  - **Roider Armatura 0.2: intended retirement, unrecorded.** The Dragline (ship, variant, `ship_data.csv` row,
    IndEvo whitelists, title-screen variant) was moved together to `scratch/retired/`; nothing shipped references it;
    its sprite was left in `graphics/`. Needs a REMOVALS.json entry with the reason, and the sprite removed or kept.
  - **SEEKER 0.3.0: owner decision needed.** The shipped mod lacks the "twig" campaign subsystem (5 classes:
    `SKR_PersistentRoot`, `SKR_PersistentRootShip`, `SKR_CampaignTWIGEntity`, `SKR_TwigCampaignTracker`, `MemKeys`), the
    `ART_dimention_armor` weapon and `data/config/twig/`. The workspace escalation flagged the persistent-root class as
    save-risky; no record says the removal was decided. Compare with `Done/SEEKER-0.6` before deciding.
  - **Ironclads v.11+bf.1: intended (REVIEW).** SystemBountyEvent replaced by RC8's SystemBountyManager (owner's
    faithful-route decision 2026-10-04); FleetSpawner/TimeManager dead code reachable only through Barnard, whose
    generation was already commented out in the original. The 25 rules.csv triggers come from cutting a 0.7 vanilla
    copy of rules.csv down to Ironclads' own 170 rows; most have the same id in RC8, about 16 do not (comm-relay
    sniffer, `dialogHegRelayInterference_*`, `cargoScanSuspicious`, `flavorTextMarketUmbra`) and were not reviewed one
    by one: owner confirmation advised. REVIVAL_PLAN says FleetSpawner/TimeManager were "left as shipped" but they are
    not in the zip (doc fix). The zip ships a stale `jars/IroncladsEcon - копия.jar` (remove on the next refresh).
  - REVIEW, likely intended: Xenoargh AI Overhaul (53 classes) and FX Core (52), the RevenantLib fold; EPTA Consortium
    (36) and 2.1.3 (14), Nomads (3), Neutrino 1.8.9 and Nostalgia (2 each), Another Random SWP and Tritachyon (1);
    source-only omissions (Flu-X, Bricky Construction, RevenantLib `.java`); junk shipped (`.old`, copy files) in
    Broken Star, Exigency 0.8, Jackundor's Advanced Arms, Leon Heavy Industries, Maelstrom Superweapons (older), Sylphon,
    Neutrino 1.8.9.
  - UNDETERMINED: Arkgneisis (`ArkLeg_dev`), BF-Legacy-Fleets, Nightcross, Omega Trauma (no original with the shipped
    id); Station Augments 2.4.3+bf.1 has no zip and no ARCHIVE_NOTE.
  - Next: write REMOVALS.json entries for the intended rows so they stop showing; add the junk-file and
    copy-of-jar check to `archive-preflight`; turn this pass into `done-audit --content-parity --write DIR`.
  - **Resolved the same day (owner decisions 2026-10-20; REMOVALS.json written in each `working/reports/`, local):**
    - SEEKER: the "twig" classes were adapters for the external Twig Library, which no longer exists; the Betelgeuse was
      already rebuilt on vanilla station modules (`docs/fable-solutions/SEEKER-twig-to-ship-modules.SOLUTION.md`,
      2026-09-09). Owner accepted it as re-created; per-segment supply drain, repair rates and 50% revive left out
      (can be re-added later; `In operation/SEEKER/working/reports/TWIG_RECREATION_PLAN.md`). Module save/reload check
      is LOCAL_HANDOFF 0b item 15.
    - Ironclads: all 25 dropped triggers (161 rows) verified as the 0.7 vanilla copy, 0 Ironclads-specific, none
      restored; the 33 per-system world scripts were never generated in the original either (its SectorGen.java
      comments out all but Lomonosov, Shington, Nexus and Centronom). The stray `IroncladsEcon - копия.jar` moved out
      of `working/`. Now EXPLAINED 87/87.
    - Xenoargh AI Overhaul and FX Core: lombok runtime classes stripped (no shipped class references `lombok/`), and AI
      Overhaul's own TravelDriveStats replaced by vanilla's. Not a RevenantLib fold.
    - Better Deserving S-mods (dead code upstream), AI-War (superseded upstream by AIW_*), Maelstrom Imperium Unofficial
      Expansion (copies of its dependency's classes), Mirfak/Blackrock/Seafood (design-type keys renamed by the English
      translation; Mirfak's "rule" was a comment row): all EXPLAINED. Roider's Dragline is file-level, which REMOVALS
      does not cover yet (77.19 extension: a `files` category).
    - Queue now: 1 DROPS_UNEXPLAINED (Templars 0.9.8f: exactly the open C4 reputation stages and the console command),
      9 UNDETERMINED (no original with the shipped id), the rest EXPLAINED or CLEAN.

**77.19 Recorded removals.** Strip plans, RevenantLib folds, renamed ids and upstream removals (Templars 0.9.9e) write one
line each to `reports/REMOVALS.json` (item, reason, decision source). The dropped-feature sweep (77.16), archive parity
(77.18) and the escalation sheet read it, so intended removals stop showing and unexplained ones stand out.

**77.20 Apply an owner decision draft.** Decisions are drafted as Markdown with checkboxes and then applied by hand
(baseline keys, the reason in ESCALATION_REVIEW.md, ROADMAP_STATUS and LOCAL_HANDOFF lines). `decision apply DRAFT`
reads the ticked boxes from a structured block in the draft and performs the matching actions (77.14 accept, schedule a
roadmap line, add a rig step), printing what it changed. Unticked boxes do nothing.

**77.21 Natural exit everywhere.** `tools/bf-test.ps1 launch` and `boot_test` still end the game with `taskkill /T /F`;
route them through `exit_observation` so every live record can carry NATURAL/KILLED, not only `probe-group live
--natural-exit`.

**77.22 Evidence queue and rig-session planner.** `board --live-pending` gathers every LIVE PENDING / NOT_RUN gate from
BridgeForge, Salvor, VoidSmith, SPW and Project Go status files (via a small machine-readable gate list per repo, R7),
groups them by rig configuration (install, Java, launcher, LunaLib, enabled set) and prints one session checklist with
the exact commands. Today the checklist is assembled by hand from five roadmaps.

**77.23 Shared fixtures stay identical and line-ending proof.** The runtime-context fixture hash failed on Ubuntu CI
because the Windows working copy had CRLF. Mark hashed fixture trees `-text` in `.gitattributes` (both here and in
Project Go), and add a CI job that fetches Project Go at a pinned commit and fails when the shared
`fixtures/translation-conformance` and `fixtures/runtime-context` differ by a byte.

**77.24 Post-write verification for every backing-up writer.** FIX-001's guard (a written file must exist with the planned
bytes, else stop with the backup kept) applies to `relink`, `patch-jar-class`, `translate-apply`, `revise finalize` and
archive staging too; one shared helper in `safeio` and a ratchet test like the safe-write one.

**77.25 Pre-commit lints what is committed.** The pre-commit hook runs `ruff check .` over the whole folder, so untracked
agent scratch blocks unrelated commits (2026-10-20 needed `.gitignore` entries). Lint the staged and tracked files in the
hook and leave whole-directory lint to 77.13's preflight report. Also track `tools/precommit-check.ps1` and
`tools/prepush-check.ps1`: `/tools/*.ps1` ignores them, so worktrees and fresh clones get hooks that call a missing script.

**77.26 Test hermeticity: reference-rig manifests.** `test_shadow_triage...test_without_a_reference_core_the_fixer_behaves_as_before`
passes in a fresh worktree and fails in the owner's checkout, because `reference_rigs.reference_core_for_game_version`
reads the repository's local, ignored reference-rig manifests. Tests must pass `repo_root` (or a fixture root) so local
rigs cannot change their result; the suite's existing "Test hermeticity FAIL" check should catch this class.

**77.27 Hand removals leave a record (FIX-001's cause).** Files moved into hand-made `scratch/removed/` folders
(All the Domain Drones' repaired rules.csv, Aivon's special_items.csv, Yellowjackets' tpc.wpn) carry no reason, so a
mistaken move shipped. Add `remove WORKSPACE PATH --reason` that moves the file to `scratch/removed/<date>/`, writes a
`REMOVALS.json` entry (77.19) and refuses when the path is a data file the mod's own content references without a
replacement; `fixer-backup-orphaned`'s sibling check flags any `scratch/removed/` file without a REMOVALS entry.

**77.13 Proposed hygiene preflight (S4 supportability; scope/design still pending).** This audit found 21 Ruff errors in pre-existing untracked agent scripts, including syntax errors, while the isolated tracked checkout passed Ruff. Add a read-only preflight that reports tracked modifications, untracked code, ignored local evidence, interpreter/dependency availability and separate tracked-tree versus whole-directory lint results. It must never delete/move files, suppress whole-directory failures, stage unrelated work, or traverse private mod/save inputs. Reuse Git's file inventory and Ruff rather than inventing a second linter. Validate on synthetic dirty/untracked/ignored fixtures, filenames with spaces and Unicode, and missing tools; unavailable checks report INCOMPLETE. A future cleanup needs explicit file-level scope. This supports item 77.7's worktree rule without discarding agent work or hiding failing scripts.

## Translation-schema slice of 77.3 (owner continuation, 2026-10-19)

Further owner continuation: "Repeat for all next phases if able." Runtime-context fields in `run_manifest` and
`write_run_record` are now implemented and fixture-tested against Go, with unknown exits null. Actual interactive exit
observation and a BOUND live run remain pending. Project Go gained an opt-in copied real-mod measurement task and safe
explicit evidence capture; FlowerGod requires 712 reviews after 908 policy approvals. GUI owner review and JSON-key
consumer evidence remain open. No release or archive is authorized by these implementation receipts.

Owner: "If able continue same process in next phase." Implemented the next Project Go schema-alignment slice of 77.3;
this does not schedule the other recommendations or change S1-S4. It supplies a source-bound, fixture-tested translation
contract that a later reproducible revival case can consume.

Schema v1 is retained with additive text-line/class kinds and optional role/group metadata. The original conformance
corpus stays intact; two new shared JSON fixtures cover exact text/class bytes and protected/linked behaviour. BridgeForge
validates identities before application and stages linked copies; linked in-place use is refused. Project Go validates the
metadata and tests both shared fixtures. See `fixtures/translation-conformance/SCHEMA_V1_EXTENSIONS.md` for boundaries.
Tests: `test_translation_extended_kinds`, `test_translation_roles`, `test_translation_extension_conformance` plus the
existing translation/conformance/batch tests; Project Go `TranslationExtensionConformanceTest` and full Gradle build.
Source/static/package validation is separate from runtime: LIVE TEST NOT PERFORMED. No schema-2 migration, release,
real-mod acceptance or runtime-record change is included.

<!-- page-nav:start -->
> Page 3 of 3 of the BridgeForge roadmap. Previous: [ROADMAP-2.md](docs/archive/ROADMAP-2.md). Newest entries: [ROADMAP-3.md](ROADMAP-3.md).
<!-- page-nav:end -->

## Proposed ideas (2026-10-06, owner asked for per-project ideas; proposed, not approved) (continued)

70. **Hardening BridgeForge overall (owner 2026-10-12: 'plan any possible hardening').** **Partly implemented; original plan: `docs/HARDENING_PLAN.md`.** Grounded in measurements (cli.main() is 2,852 lines; 182 non-atomic `write_text` sites against one atomic writer; 47 delete sites; 186 workspace accepted-finding baselines; ruff checks only syntax and pyflakes) and in the defect classes of 2026-10-11/12: shared generated launcher files and an agent flag after the main class, `merge_configs` silently dropping keys, accepted baselines hiding Zorg's port bugs, archives not tied to the tested files, stale Atlas cache key, predictions treated as findings. Five phases: H1 small and high value (atomic writes, guarded deletes, launcher self-test, config contract tests, baseline hygiene, archive guard, rig control, known-failure baseline), H2 (split cli.py and scanner.py behind golden snapshots, lint and types, untrusted-input limits, test reliability), H3 evidence discipline (prediction ledger, live ledger, roadmap-lint, base-rate checks), H4 portability (line endings, long paths, pip-audit, snapshots), H5 agent guardrails. Four owner decisions listed in the plan.
    - 70 progress 2026-10-12 (H1.1, H1.2, H1.4, H1.5, H1.6, plus regression findings): `bridgeforge/safeio.py` (`atomic_write_text/json`, `safe_rmtree/safe_unlink` refusing paths outside the stated roots, the roots themselves and links out of them); 11 state writers use it (mod changelog, group config, enabled_mods, workspace manifest, baselines, archive note, group plan) and 12 tree deletes (3 left, in escalation and java_matrix); `tests/test_safeio_ratchet.py` with `tests/safeio_baseline.json` lets bare `write_text` (171 left, was 182) and `shutil.rmtree` only shrink. `tests/test_probe_contract.py`: every probe config key Python writes is read by `ProbeConfig.java` (or listed Python-only), every key it reads is written, `merge_configs` keeps every member key, setup kinds match both sides. `bridgeforge/baseline_audit.py`: baselines carry a stamp (mod version, date) and per-key reasons; `baseline-audit` lists OK/STALE_VERSION/UNSTAMPED/NO_BASELINE (real queue: 189 unstamped, 124 none); `baseline-accept` re-stamps with a written reason; `archive_gate` refuses a stale or unstamped baseline unless `reports/SHIPPED_CHANGES.json` has a written `baseline` reason (owner decision 2026-10-12). `archive_mod` writes `Changes since the previous archive` (files and, inside changed jars, classes) into every ARCHIVE_NOTE (the live-result-current gate, 36.11, already covered 'shipped files are the tested ones'). Regression pass REG-20261012 findings: with mission-fleets and class-sweep now merged into group configs, their FAIL lines had no owner and whole groups read UNCLEAR; group_members now carries missions and classes, summary lines are skipped, a class-sweep NoClassDefFoundError naming a disabled well-known library (Console Commands, LunaLib, MagicLib, LazyLib, Radar) is an optional integration, not a failure, and `probe-group regress --rejudge SOURCE` re-judges saved logs with no game. Real results so far: Aivon-Republic's missions name two variants that do not exist (aiv_marabeth_standard, aiv_rostell_FS). Tests: `tests/test_safeio.py`, `test_safeio_ratchet.py`, `test_probe_contract.py`, `test_baseline_audit.py`, `test_archive.py`, `test_probe_group.py`, `test_regress.py`.
    - 70 H1.3 and H1.8 built 2026-10-12: `env_check.verify_rig_launchers` reads what every rig launcher really passes to java and fails `java-matrix setup` on `agent-after-main-class` (a `-javaagent` after the main class is an application argument), `prepatcher-not-last-agent`, `argfile-missing`, `prep-launcher-without-agent`, `plain-launcher-with-agent` and `argfile-shared-between-variants`; `env-check` now counts only agents before the main class and resolves `%RT%` argument files for a relative launcher path (it did not). `tests/known_failures.json` + `test_guard`: a known environmental failure (`test_child_with_cwd_inside_target_is_found`, expires 2026-11-12, reason recorded) no longer fails the full run, a second failure, an expired entry or an unnamed failure still does, a now-passing entry is reported, and `--suite-line` names it. Tests: `tests/test_launcher_selftest.py`, `tests/test_test_guard.py`.
    - 70 H3.2 and H3.3 built 2026-10-12: `bridgeforge live-ledger [--mod M] [--attention]` reads the existing run records (`In operation/_live/*.json`) and regression passes (`_regress/*.json`) into one list per mod (last PASS with version, last run, mods whose latest run was not a PASS); `bridgeforge roadmap-lint` fails when a ROADMAP item marked Done names no test file, `Tests:` line, live test id or docs/ evidence file (329 items; 3 given evidence, 1 stub tolerated in `tests/roadmap_lint_baseline.json`, which may only shrink). Tests: `tests/test_live_ledger.py`, `tests/test_roadmap_lint.py`.
    - 70 H3.1 and H3.4 built 2026-10-12: `docs/atlas_predictions.json` (committed evidence) records what live runs showed about forecast findings; `bridgeforge atlas outcome RULE --mod M --id ID --outcome confirmed|refuted|inconclusive --run TEST --note ...` appends one (a run id and a note are required), `atlas precision` reports the hit rate per rule, and `atlas forecast` annotates matching findings `[prediction confirmed by RUN: ...]`. Seeded with the two decided cases: ATLAS-READS-REPLACED DNEEP x AoTD `farming` confirmed (GRP-DNEEP-SUPPLY-BEFORE-20261011) and Arkgneisis x AoTD `orbitalworks` refuted (GRP-ARK-AOTD-J28FRP-20261012): 1 of 2 held so far. `save-doctor --cycles` now reports the base rate with every MEMORY_CYCLE (cycles among N condition markets, how many share a memory), so a culprit is not named from one cycle alone. Tests: `tests/test_atlas_predictions.py`, `tests/test_save_cycles.py`.
    - 70 H1.7, H2.3, H2.4, H5 built 2026-10-12: `install --also-enable` and `rig-reset` (`tests/test_rig_control.py`); ruff now also runs flake8-bugbear (`B`, four noisy rules ignored in pyproject); `bridgeforge/zipsafe.py` `read_limited` bounds every jar entry read in the atlas, scanner and archive (`tests/test_untrusted_input.py`, including hostile-jar atlas build); `bridgeforge agent-diff-check BRANCH` lists files a branch deleted or cut by more than a fifth before merge (`tests/test_agent_diff_check.py`).
    - 70 H5.4 done 2026-10-12 (owner request): `CLAUDE.md` (layout after the cli.py and scanner.py splits, a Hardening rules section, the mission-variant lesson), the local `AGENTS.md` mirror, `docs/LOCAL_HANDOFF.md` section 0 and the memory index were brought up to date; each named command, file and count was checked against the repo that day.
    - 70 H4 part built 2026-10-12: `rig-doctor` gains an `environment` check (WARN when Windows `LongPathsEnabled` is off or the rig or repository path is non-ASCII; `tests/test_rig_doctor_environment.py`); CI gains a `Dependency audit` job (`pip-audit`). Still open in H4: LF policy and renormalize (done later the same day) and the snapshot trigger.
    - 70 H2.5 part built 2026-10-12: `.github/workflows/weekly.yml` runs the whole suite in reverse order every Monday (`tests/run_reversed.py`) and writes the time to the job summary; first result not yet seen. The `test_locks` failure stays in `tests/known_failures.json` with its expiry.
    - 70 regression pass REG-20261012 done 2026-10-12 (all 39 groups of the validated mods, Java 25 direct launcher, probe 0.2.27): the first judge read 71 items as needing a look, 16 after `--rejudge`, 6 after the judge fixes (sweep artefacts, Nexerelin and Second-in-Command integrations, `Cloak AI` debug prints as chatter; `tests/test_probe_group.py`). Real findings: Aivon-Republic, Sylphon-RnD and The Silent Armada had missions naming variants RC8 lacks (Fatal when the mission starts); fixed (`+bf.1`, `+bf.1`, `+bf.2`), live PASS (REG2/REG5/REG6) and re-archived. Two harness faults behind LIVE_STUCK, both fixed in `bridgeforge/live_run.py`: a probe row listed by the replacer and the probe mod counted twice (Ironclads, rerun REG3 PASS) and 40 wheel ticks short of the bottom of a 58-mission list (group 10, rerun REG4: 7 PASS plus the Silent Armada finding; `tests/test_live_run.py`). Open: Vayra's Ship Pack (`ii_*` variants) and Kadur Remnant (SWP and SEEKER variants) report missing mission variants that look like references to mods not in their group; not yet confirmed. `baseline-accept --all-unstamped` started the 90-day clock for 189 baselines. `audit-explain` now refuses a path without `working/` (it had created a stray folder).
    - 70 H4 (snapshot) and H2.1 (part) built 2026-10-12: `bridgeforge state-snapshot --to DIR` is an append-only copy of `Done/`, `bridgeforge-state/`, every `In operation/*/working` and the Claude memory folder (changed files keep the older version under `versions/<stamp>/`, nothing is deleted, per-source progress, resumable; `tests/test_state_snapshot.py`); `bridgeforge/cli_commands.py` registers commands that live in their own module and `tests/test_cli_golden.py` pins the `--help` hash of all 220 commands before the rest of the `cli.py` split (full suite before it: 1858 tests, OK (skipped=1), 322 s).
    - 70 H2.1 done 2026-10-12: `bridgeforge/cli.py` is 60 lines; every command's parser and handler moved verbatim into 12 `cmd_*.py` modules (253-640 lines) registered in `cli_commands.COMMAND_MODULES`, by an agent in a worktree, merged after `agent-diff-check` showed only the intended shrink. `tests/test_cli_golden.py` hashes the `--help` of all 220 commands and passed after every group; the two dead `*-local` argv rewrites (their parsers were removed in a565e81b) were deleted. Full suite on the merged tree: 1865 tests, OK (skipped=1), 276 s.
    - 70 H2.2 done 2026-10-12: `bridgeforge/scanner.py` is 615 lines (`scan_mod`, `_scan_jars` and a re-export block); 20 `scan_*.py` modules (213-737 lines) hold the checks, cut by AST so no code was retyped. A behaviour golden over 60 `In operation/*/original` mods (about 2,500 findings, order included) was identical after each of three commits. `_scan_jars` stays because tests rebind the jar-limit constants on `scanner`. 210 finding ids across 24 modules.
    - 61/62 first live run 2026-10-12: the matrix had never clicked the launcher (added 2026-10-11), so three of four variants hung at it; fixed (`auto_click=True`, asserted in `tests/test_java_matrix.py`). `java-matrix mass --preset compare --bundle 4` over the 150 archives (6,148 s): 137 SCREEN_PASS, 13 NEEDS_LUNALIB (Fast Rendering variants only; RC8-33), none environment-sensitive between Java 25 and 28 or direct and Fast Rendering, none failing everywhere. The Fast Rendering race hypothesis from the tester's log is not supported by this run.
    - 60g(5) measured 2026-10-12 with a temporary copy of the Seeker workspace carrying the pre-fix jar from `SEEKER-0.3.0-0.98a+bf.4.zip` (copy deleted afterwards, rig restored): the probe mission and the `seeker` duel did not reproduce the wreck re-dying (peak hulks 1, frame 17 ms), but the `overwhelm` duel (forced kill at 45 s) did: frames 17 ms before the kill and 2,875 ms on average after it, worst 7,748 ms, 2,340 hulks and 2,403 ships by the time the duel plugin's `real-time-after-kill` cap ended it at 98 s real (`PROOF-DUEL2-20261012`). So the bf.4 jar reproduces RC8-27 under the duel; the probe's own combat-perf runaway stop was not exercised, because the probe's mission never destroys Bone-Breaker. **Closed 2026-10-12 (second run):** `probe-group duel` gained `ubique` (SEEKER's Ubique, ART_vectorCruiser_prototype, overwhelmed; Phased Mainframe) and `probestop` (the overwhelm duel with the probe's own `BfProbeCombatPlugin` attached). Pre-fix bf.4 jar: Ubique after its destruction 658 ms frames, 722 ships and 2,089 projectiles (`UBQ-PREFIX-20261012`); bf.5 jar: 18.9 ms, 8 ships, 41 projectiles (`UBQ-FIXED-20261012`); the Bone-Breaker overwhelm on bf.5: 17 ms, 8 hulks. `probestop` on the bf.4 jar: the probe logged `combat-perf|FAIL|runaway|hulks=441 ships=475` and ended the combat at 46 s, where the duel plugin alone had let it reach 2,340 hulks at 98 s (`PROBESTOP-20261012`). So 0.2.24's runaway stop is proven live and both patched hull mods are confirmed fixed. Rig restored; the duel mod's mission list now has five rows.
    - Mission guards 2026-10-12 (owner: a mission that is player-facing must require its dependency, be guarded, or be hidden): a mod's variants inside `if (otherModEnabled) { }` are no longer reported as missing references (`probe_config._mission_fleet_refs`, `tests/test_mod_guarded_missions.py`); Vayra's Ship Pack's `bearsfruit` case blocks are guarded by its faction picker (accepted in `reports/probe_accepted.json` with the evidence). Real defects found and fixed: Kadur Remnant `vayra_k006` pooled Vayra's Ship Pack cruisers unconditionally (now guarded, 3.2.3support6+bf.1), and Vayra's Ship Pack declared no dependencies although its plugin stops at load without LazyLib (1.2.3+bf.1, which a solo run exposed because groups share libraries). The scanner now reads `getScriptClassLoader().loadClass(<library class>)` with a throwing catch as a required library. A sweep of every working copy found the same pattern in four unarchived mods (Concordance of Protection Syndicate, Foundation of Borken, Pearson Exotronics; Neutrino tomatopaste gets LazyLib through MagicLib), to be declared when they are revived. Both mods live PASS and re-archived.
    - Zorg18 V18+bf.9 (owner screenshots 2026-10-12): bf.8's Zeta change was wrong. ZorgGen's two constants (star corona -10000; Zeta I radius 0, orbit 100, 5000 days) are bf.7's again, so the ring bands, which orbit Zeta I, circle the star ball and not a planet 5000 units away (only those two constants differed between bf.7 and bf.8, javap diff). With Nexerelin the Zorg started neutral to everyone because its New Game resets relations after `onNewGameAfterEconomyLoad`: the Bf plugin now also runs after the time pass and `data/config/exerelinFactionConfig/zorg.json` sets `hostileToAll` 3 (Nexerelin `DiplomacyManager.handleHostileToAllFaction`: -1.0 to all, including the player); live day-1 log `BF-ZORG|relations` 23 of 23 hostile, player -1.0 (ZBF9C-NEX-20261012). Zeta I and II had never had markets in any version (only the Unimatrix station did); owner asked for the same market as Unimatrix, so the Bf plugin turns each planet's condition-only market into a size 10 Zorg colony (population, spaceport, Hive Exchange), new games only; the first attempt created nothing because a planet's `getMarket()` is already a condition-only market (live ZBF9D), the second works (ZBF9E-NEX-20261012: three Zorg markets, submarket stock OK). Same version, re-archived. Not live-tested: a player commissioned with the Zorg through Nexerelin.
    - Crash report 2026-10-13 (owner, Epta Consortium 2.0.3 in a modpack with Starpocalypse and Crab Shack): opening a market sorts its stock, RC8 runs each ship's hull mods' `advanceInCampaign`, and a stocked ship has `getFleetData().getFleet() == null`, so `seven_AIcoreRefunder_alphacore` (and beta, gamma) threw a NullPointerException at `member.getFleetData().getFleet().equals(...)`. The three classes in `jars/ChangingNexus.jar` were patched with the null guard the mod's own `seven_AIcoremod_*` already use (`patch-jar-class`; patched jar copied to the owner's Downloads as `ChangingNexus-refunder-fix.jar`; Epta is not archived). New check `hullmod-fleet-dereference-unguarded` (REVIEW, tier mechanical, `scan_combat.py`, `tests/test_hullmod_fleet_dereference.py`) finds the pattern in a hull mod's `advanceInCampaign`; it flags the original Epta (3 files) and nothing else in the 300 working copies. Not live-tested: opening a market with the patched jar.
    - 2026-10-13 (owner: Templars 0.9.8f through BridgeForge, archive it and 0.9.9e, and Epta Consortium too). **Epta Consortium 2.0.3 archived** (EPTA2-20261013): besides the refunder fix, the three combat spawns (defense funnels, NAS phase and gregariousness copies) now give the spawned ship a captain with a personality (the existing fixer's change, applied to the jar's sources and patched in); the remaining findings were accepted with evidence; the live run's two probe FAILs (a hidden faction with no ships or markets, a system 2.0.3 never generates) are accepted in the mod's `probe_accepted.json`. The owner's modpack runs Epta 2.1.2 with `EptaConsortium.jar`, so the refunder fix was also built for that jar (`Downloads/EptaConsortium-2.1.2-refunder-fix.jar`); the first Downloads jar is for 2.0.3 only (renamed `ChangingNexus-2.0.3-refunder-fix.jar`). **The patcher had let a class change its superclass**: with `import ...combat.*` and another rig mod's `data/hullmods/BaseHullMod` on the compile classpath, javac chose the same-package class and the patched `seven_defensefunnels` failed to load (EPTA-20261013); `patch-jar-class` now refuses a changed superclass or interface list (`tests/test_jar_patch.py`), and the source names the type explicitly. **Templars 0.9.9e archived** (TEM099E-20261013, PASS; was set aside on 2026-09-28 as superseded by Templars 2.5.1, archived now at the owner's word). Two scanner false positives fixed: `setCustomDescriptionId("star_antioch")` is not a star type (`tests/test_total_conversion_scans.py`), and RC8 still has the `StarAge` overload of `Misc.addNebulaFromPNG` (`tests/test_signature_rewrites.py`). **Templars 0.9.8f** (April 2018, the 0.8.1a era) **ported onto 0.9.9e's code and archived** (owner choice; TEM098F2-20261013 PASS; the first run built empty Templar patrols until 0.9.9e's `default_ship_roles.json` came along, and the hull, weapon and wing rows needed 0.9.9e's tags). It needed a real port: `relink` reports NEEDS_PORT with 12 members RC8 removed (old economy connections and demand, `FleetFactoryV2`, `getCompositionDoctrine`, the 0.7 `addMarket`/`addCondition`/`RepActionEnvelope` forms) plus the removed event system its Crusades use. Zorg in a Nexerelin random sector (ZRAND-NEX-20261013, `corvusMode` false preset in the rig's Nexerelin setup file, restored afterwards): Zeta is generated with all three markets and 23 of 23 factions hostile, player -1.0, at the sector's edge (10 light-years from the nearest market); Templars instead skips its own system there and Nexerelin builds Antioch for it (`enableAntioch`).
    - CI was red on every push from 2026-10-12 to 2026-10-13 and nobody looked (owner: 'add to queue a look at GitHub CI errors'). Causes, all CI-only: the `--help` golden hashed argparse's formatted text (laid out differently per Python), then defaults holding this machine's home folder and the checkout path, then Python 3.10/3.11 marking a `nargs='*'` positional required; `docs/COMMANDS.md` carried the home folder and a Windows path; `safeio` missed junctions on Python 3.10/3.11 (no `Path.is_junction`). The golden now compares each parser as data with paths normalised, the docs render `~` and forward slashes, and junctions are read from the reparse-point attribute. CI green on all twelve jobs (run after commit 'Fix CI golden: a nargs=* positional'). Lesson: after a push, `gh run watch` the run; a local suite on one Python does not prove the matrix.
    - **Epta Consortium 2.1.2+bf.1 archived** 2026-10-13 (owner: 'package epta for now'; folder labelled 2.1.3, embedded version 2.1.2), from the workspace another session prepared (refunder guards and spawned-captain patches, five jar classes replaced, all else byte-identical; checked with javap). Brought into the standard path: report and baseline moved into `working/reports` by revive, 22 escalations re-checked against 2.1.2 sources and accepted with evidence (14 carried from 2.0.3; new: cosmetic frame counters in seven_FluxOverwhelmingCompensation, the unreachable Alicerce generator, carrier bays from seven_fllightdeck_overhauling, the seven_megfunnel CSV tail, officer list in memory, three saved scripts holding a market); the '[BF r1]' name tag dropped (2.0.3 keeps the original name). Live EPTA213-20261013 PASS with probe_accepted Narcepolis patrol and Alicerce (as 2.0.3); the probe's save checked with `save-doctor --cycles`: no cycle. Open, not proven: the Artifact 667 bounty generated live, a save reload, a Nexerelin run. Found on the way: `save-doctor`/`save-compat` read XStream element names literally, so a class with `_` in its name (saved as `__`) was CLASS_UNRESOLVED and the save WILL_LIKELY_FAIL; element names are now decoded (`_decode_element_name`, `tests/test_save_doctor.py`).
    - 63 step 5 (re-prove item 38 against the Toolbox Scheduler Fork: javap and live checks of the six overridden industries and the temporary-market pattern) is deferred to later by the owner (2026-10-12); `docs/AOTD_COMPAT_PLAN.md` step 5 stays the spec. Steps 6 and 7 are done or recorded; 60g(5) is closed above.
71. **Templar Holy Crusade re-created for RC8 (owner 2026-10-13: 'is it possible to re-create the Templar crusade system in terms of RC8? design plan').** **Plan only: `docs/TEMPLAR_CRUSADE_PLAN.md`.** Feasible: RC8's `GenericRaidFGI` (fleet-group intel with prepare, travel, payload and return stages) is what vanilla's Persean League and Sindrian Diktat punitive expeditions and the Knights of Ludd takeover use; `RecentUnrest`, market accessibility, `FleetFactoryV3`/`FleetCreatorMission` and the RC8 `RepActionEnvelope` replace the removed 0.8 event system, `RecentUnrestEvent`, trade connections and `FleetFactoryV2` (javap 2026-10-13). Proposed as a separate companion mod (`tem_crusade_bf`) so no Templars archive changes; 0.9.8f's scheduler, target pick, timings, morale formula, six endings, unrest table and player reputation rules are kept. Phases C1 to C5 (about two days) and five owner decisions are in the plan. Not started.
    - Owner decisions 2026-10-13 (plan section 6): built into the Templars versions, not a companion: the 0.9.8f port, 0.9.9e and the newer Maelstrom Templars Expanded 2.5.1 (0.98 modpack V6.2), through one RC8-API-only jar `jars/TEM_Crusade.jar` that each version lists and calls from `TEMModPlugin.onGameLoad`; accessibility -20%; stability -3 plus a 5 to 10% chance per target market of one industry disrupted on a Templar victory; defenders: response fleets by default, `MilitaryResponseScript` behind `defenderMode`, both tried live.
    - C1 to C3 and the debug mode built 2026-10-13 (plan section 5a): `jars/TEM_Crusade.jar` (source in `In operation/_shared/TEM_Crusade`, shipped in each version's `jars/src`), wired into Templars 0.9.8f port, 0.9.9e and the newer Maelstrom Templars Expanded 2.5.1 (taken in from the 0.98 modpack V6.2 as workspace `Templars-Maelstrom-Expanded`; revive UNATTENDED_DONE after its nine escalations were re-checked against the 2.5.1 sources and accepted with the 0.9.9e reasons). Design change found reading `FGRaidAction`: vanilla already moves, fights, autoresolves and calls the target's patrols; the Crusade's effects sit in `doCustomRaidAction`, so `defenderMode military` is vanilla alone. Live, short stages, both clean in `log-triage` (FATAL 0, MOD-ERROR 0, no attributed exception): **TEMCRUSADE-099E-R1** (0.9.9e, `response`): launched from Ascalon on day 0 against Westernesse (4 Persean markets, 8 fleets), 4 response fleets (178 to 200 points, 20 to 29 ships), condition on 4 markets, 3 of 4 carried, no disruption (8% roll), `end_bad`, unrest 2, condition off. **TEMCRUSADE-251-R1** (2.5.1, `military`, probe save with the Crusade running: `cmdSave returned true`): Naraka (2 markets, 6 fleets), both carried, crusaders lost 21%, `end_crushed`, unrest 3, condition off. Run 1 showed the crusaders are an unspawned route away from the player (`crusaderFleets=0`), so the crushed/defeat split now reads the route's damage (`damageTaken`). One run per mode on different targets cannot say whether the response fleets matter; 200-point response fleets look strong for a balance pass. Open: loading a save with a Crusade in it, player reputation (C4), a run with the player present (spawned fleets), version bumps (`+bf.N`) and re-archive of the two archived versions, live run and archive of 2.5.1.
72. **Lost-feature detection and a re-creation escalation (owner 2026-10-13: 'can we add some sort of fixer/automation or an escalation protocol for things like this in terms of other mods?').** The Crusade was lost without any error: RC8's `starfarer.api.jar` still has `CampaignEventManagerAPI`, `CampaignEventPlugin`, `BaseEventPlugin`, `RecentUnrestEvent` and `SectorAPI.reportEventStage` (javap 2026-10-13, RC8 vs 0.8.1a: the events package went from 90 to 60 entries), so a mod built on the 0.8 event system compiles and links, while RC8's `data/campaign/events.json` runs only `rep_tracker` and `nearby_events` (all other vanilla events commented out). `FleetFactoryV2` is gone (FleetFactoryV3 replaces it). Planned:
    - (a) Finding `legacy-event-system` (MANUAL, never auto-applied): a mod that registers events in `data/campaign/events.json`, subclasses `BaseEventPlugin`/implements `CampaignEventPlugin`, or calls `startEvent`/`primeEvent`/`reportEventStage`; evidence names each event id and class. Its explanation gives the RC8 replacement table (`GenericRaidFGI`/`BaseIntelPlugin` for staged events and reports, `RecentUnrest` for unrest, `FleetFactoryV3`, market accessibility for trade effects), from `docs/TEMPLAR_CRUSADE_PLAN.md` section 2. Needs a live proof first: does RC8 still advance a mod-registered event plugin (probe check, row in `docs/RC8_BEHAVIOUR.md`)? The finding's wording depends on it ("never runs" or "runs, but its messages and reports have no UI").
    - (b) Finding `port-dropped-feature` (REVIEW): when a workspace is ported onto another version's code (as Templars 0.9.8f onto 0.9.9e), list what the old version had and the new lacks: classes by package, `events.json` ids, `reports.csv` ids, settings and options keys, `rules.csv` triggers. A dropped feature is reported, not restored.
    - (c) Escalation packet kind `recreation`: for (a) or (b), a plan skeleton in the shape of the Crusade plan (old mechanics, RC8 replacement for each, design, tests, phases, owner decisions), filled from the finding's evidence; the owner decides whether to build it. A sweep over `Done/` lists every archived mod with either finding.
    - **Status 2026-10-18: E4 built, E3 not built; live pending.** (b) `port-dropped-feature` (REVIEW) is `bridgeforge/scan_port.py`, driven by a per-mod `working/reports/PORT_SOURCE.json` (format: `docs/PORT_SOURCE_FORMAT.md`) and covering classes by package, `events.json` and `reports.csv` ids, settings keys and rules triggers; (c) the `recreation` escalation packet skeleton is implemented with it (item 73 E4). Tests: `tests/test_scan_port.py`. No real port record has been written yet, so no archived mod has been reported by this check; writing Templars 0.9.8f's record and rescanning is LOCAL_HANDOFF 0b item 9 (OBSERVED result still to come). (a) `legacy-event-system` (E3) is not built: it waits on the live proof of whether RC8 advances a mod-registered event plugin, and on the owner choosing per mod after the E4 sweep (AUTOMATION_PLAN decision 5).
73. **Less hand work: fixers, checks and automation (owner 2026-10-14: 'design a roadmap plan for further automation, fixers, checks and anything that would let bridgeforge do more in terms of hand work').** **Plan: `docs/AUTOMATION_PLAN.md`; implemented offline 2026-10-18 except B3 and E3 (status entry below).** Measured with `finding-stats` over stored scans (300 of 316 workspaces): hardest tier none 94, auto 21, input 37, decision 56, inspect 3, code 89; 115 unattended, and applying every mechanical fixer adds none, so the gain is now in the input, decision and code tiers. Largest blockers: `description-missing` (86 mods, the only blocker for 27), `content-reference-unresolved` (7), `obfuscated-internal-api-use` (5), `preset-entry-drops-vanilla-fields` and `settings-json-override-breadth` (4 each); 662 escalation packets and 102 hand-written escalation reviews. Many stored scans predate later fixes, so phase A re-measures first. Phases: A measure (fresh scan, stale-scan report, why auto-tier findings stay open, ledger promotion report), B fixers from verified agent fixes (generation guards, compile rewrites, detach-before-save template, preset merge, wing OP and weapon rows, import resolution from the provider index), C decisions answered once across the queue (decision sheet, precedent in packets, substitution proposals, settings classification), D drafted input (descriptions from other versions and sibling mods first, translation memory, shadowing triage), E self-reviewing escalation (generated review sheet, auto-accept when every gate passes, item 72's `recreation` and `port-dropped-feature`), F checks for hand-found crash classes (hyperspace market, saved live references, provider renames beyond industries, out-of-group mission variants, mission maps, obfuscated members), G live testing without a person (generic New Game driver, overnight regression, `rig-up`, watchdog, group accept, raid scenario mod), H archive chores (rest of 60b, `revise` for `+bf.N`, migration packs). Owner decisions 2026-10-14: crafted description drafts yes, standing approvals from agreeing rulings yes, auto-accept of agent changes that pass every gate yes; and (owner: 'follow your recommendations') overnight unattended runs on the dedicated rig yes, reporting only; lost-feature plans chosen per mod after the E4 sweep. Same day: `AGENTS.md` rewritten as version 2 (the old one kept in `bridgeforge-state/agents-md-history/`): the current `revive`/escalation/`accept`/`archive` pipeline, confidence vs tier vs complexity, what may run without a person, escalation-agent rules from the review flags, sister projects; it points to `CLAUDE.md` instead of mirroring it. The plan was rewritten the same day as an implementation spec (files, behaviour, tests, done-when per item) so any AI can build it. (Status when written: not started; see the 2026-10-18 entry below.)
    - **Specification revised 2026-10-17 (owner: 'ok add/modify roadmap with these recommendations and if possible a plan on how to implement for other agent.').** Item 75's `docs/ROADMAP_IMPLEMENTATION_HANDOFF.md` refines A2, B1/B4/B6, C1, D3, E2, G5 and H2. Content fingerprints precede authoritative A1 measurement; R1-R4 precede E2 activation. Existing supporting commands do not mean these extensions are built. Current summary: `docs/ROADMAP_STATUS.md`.
    - **Implemented offline 2026-10-18; live pending.** Built and unit-tested without the game; no rig run, no real-queue `revive` and no archive of a changed mod has happened, so every "done when" that names the queue or a live run is still open (they are LOCAL_HANDOFF 0b items 1-12). A: A3 `auto-open` (one reason per open auto-tier finding, first match wins, read-only; `tests/test_auto_open.py`); A4 `finding-stats --promotion DIR` (promotion shapes with a before/after example; `tests/test_promotion.py`); A2 is superseded by item 75 R2. A1's fresh scan was run 2026-10-14 (100 of 316 workspaces unattended, local `bridgeforge-state/finding-stats/2026-10-14`) and has not been repeated. B: B1 generation and orbit guards (`tests/test_fixers_guards.py`), B4 preset field merge (`tests/test_fixers_presets.py`, approval-only after the merge fix), B5 `value-proposals` (`tests/test_value_proposals.py`), B6 evidenced or approved weapon rows, B7 import resolution from the provider index in `revive` packets (`tests/test_revive_imports.py`); **B2 Done 2026-10-18** as a decision: no rewrite rule was added because no RC8 member was involved (reason in `signature_rewrites.py`, `tests/test_signature_rewrites.py`); B3 (detach-before-save template) is not built. C: C1 `escalation sheet` with precedent and standing rulings that need a versioned semantic predicate (`tests/test_escalation_sheet.py`), C2 precedent in packets (`tests/test_escalation_sheet.py`), C3 `substitution-proposals` and the `content-reference-substitute` fixer (`tests/test_substitution_proposals.py`, `tests/test_substitutes.py`), C4 settings override classification (`tests/test_settings_keys.py`). D: D1 `descriptions draft` (`tests/test_descriptions_draft.py`), D2 translation memory reuse in `translate-batch` (`tests/test_translate_batch.py`), D3 `shadow-triage` with removal only on owner approval (`tests/test_shadow_triage.py`). E: E1/E2 report-only eligibility in `escalation review`, `--auto-accept` refuses (`ENABLED = False` in `escalation_policy.py`; `tests/test_escalation_auto_accept.py`, `tests/test_escalation_review.py`), E4 as under item 72, E3 not built. F: F1 `market-on-hyperspace-entity`, F2 compiled saved-object references, F3 provider renames for hull mods, commodities and conditions, F4 `mission-variant-not-defined`, F5 `mission-map-reference-missing`, F6 obfuscated members classified against RC8's core jars (`obfuscated-internal-api-resolved`) (`tests/test_market_on_hyperspace_entity.py`, `tests/test_saved_object_compiled.py`, `tests/test_provider_renamed_ids.py`, `tests/test_mission_variant_not_defined.py`, `tests/test_mission_map_reference_missing.py`, `tests/test_obfuscated_members.py`). G: G1 generic New Game fallback (`tests/test_new_game_generic.py`), G2 `probe-group regress --changed-since` (`tests/test_regress_changed.py`), G3 `rig-up` (`tests/test_rig_up.py`), G4 launch watchdog `LAUNCH_NO_PROCESS` (`tests/test_launch_watchdog.py`), G5 `probe-group record --accept` (`tests/test_probe_group.py`), G6 the `bf_raid` mod and `raid_run.py` (`tests/test_raid_run.py`); H2 is superseded by item 75 R5. H: H1 aggregate proof test for `audit-explain --auto` (`tests/test_explain_proofs.py`; the real-queue run is LOCAL_HANDOFF 0b item 10), H3 migration evidence required when a revision drops ids or classes (`revision_renames.py`, `tests/test_revision_renames.py`, `revise migration`). B-fixer sweeps over all 316 workspaces are recorded in the commit bodies (PREDICTED effect on the queue until `revive` runs on it). Open owner decision: whether `revive` should try the REVIEW-only fixers (B1, B4) before packeting. Merged suite 2026-10-18: 2211 tests, only the known `test_locks` intermittent failing.

74. **Zorg18 and EPTA owner follow-up (2026-10-17).** Owner decisions and acceptance steps: docs/OWNER_MOD_FOLLOWUP_2026-10-17.md. Scope: unhide Zorg Zeta planets and provide their markets in existing saves as well as new games; replace EPTA campaign-map station with the standard orbital station and correct its base version from 2.1.2 to 2.1.3. Working revisions only; live acceptance and archiving pending.

75. **Trust prerequisites and long-term roadmap refinement (owner 2026-10-17: 'ok add/modify roadmap with these recommendations and if possible a plan on how to implement for other agent.').** **Specification; R1-R6 and R8 implemented offline 2026-10-18 (entry below), every live gate pending.** Agent-ready plan: `docs/ROADMAP_IMPLEMENTATION_HANDOFF.md`; current summary: `docs/ROADMAP_STATUS.md`. Extends items 70/73, preserving their scope and evidence gates.
    - R1: pre-launch staged mod/dependency/probe/launcher identity, log binding and drift refusal across standalone/group acceptance.
    - R2: registered scans with content/context fingerprints; legacy/unknown and incomplete evidence cannot be current.
    - R3: explicit validation applicability and outcomes before auto-acceptance; missing checks remain incomplete; protect application against stale/concurrent edits.
    - R4: semantic standing-ruling predicates, conflicts/revocations and narrow fixer refusal cases; balance and save changes remain owner decisions.
    - R5: prepare once, test exact candidate, finalize without changing tested bytes; recoverable journal and preserved archives.
    - R6: reusable copied-save upgrade/save/reload/repeat scenarios, including ownership and removed-colony cases; proxy checks stay separate from live proof.
    - R7: reconcile current statuses and per-level evidence while preserving history; report mechanical throughput, review burden and live-qualified/shipped outcomes separately. Initial summary added; detailed audit pending.
    - R8: isolated snapshot restore, hash/environment checks and CLI/rig qualification before machine cutover.
    - **Order:** schemas/current-state audit; R2/A2 then A1/A3, with R1 independently; R4 and R3 report-only, then E2 only after R1-R4 pass; R5/R6 before automated revision or migration acceptance; R8 before snapshot-based cutover. Continue safe draft/report work meanwhile. Each contract names files, negative tests, acceptance and live handoff requirements. Planning approval does not authorize publication or untested archives.
    - **Implemented offline 2026-10-18; live pending.** R1: `run_manifest.py` and `run-manifest prepare|release|check` bind a run to the files staged in the rig; `accept` needs `--rig` and a manifest, group and standalone acceptance share one evaluator, legacy runs read provenance UNKNOWN; the startup-marker echo of the manifest id is not built (`tests/test_run_manifest.py`, 22 tests). R2: `scan_registry.py`, `scan-registry.json`, CURRENT/STALE/UNKNOWN/INCOMPLETE by input content, `finding-stats --rescan-stale` (`tests/test_scan_registry.py`, 16); the real queue reads UNKNOWN until that has run. R3: `escalation_policy.py` gates with PASS/FAIL/INCOMPLETE/NOT_APPLICABLE, report-only, `--auto-accept` refuses until R1/R2/R4 have live evidence and an `AUTO_ACCEPT_POLICY.json` exists (`tests/test_escalation_auto_accept.py`, 20). R4: versioned semantic predicates for standing rulings (three independent mods) and fixer refusals for C1, B1, B4, B5, B6, D3; proposals never edit mod data; stale approvals are refused. R5: `revise prepare|finalize|status|migration` with a journal; never edits tested bytes, no push (`tests/test_revise.py`, 14). R6: `save-upgrade plan|evaluate`, eight cases, PROXY_ONLY and LIVE_PENDING kept distinct from VERIFIED, no in-game evidence emitter yet (`tests/test_save_upgrade.py`, 13). R7: initial table in `docs/ROADMAP_STATUS.md`, updated 2026-10-18; the per-sub-item audit of item 70 is still open. R8: `snapshot-restore-check`, best verdict RESTORED_OFFLINE, `recoverable` stays false without the rig step (`tests/test_snapshot_restore.py`, 8). Live acceptance of each is LOCAL_HANDOFF 0b, R1 first (items 1-5); the Zorg bf.9 to bf.10 save-upgrade run and a real restore remain unrun.

**Documentation/source audit 2026-10-18 (S1 / item 75 R7):** `docs/archive/DOCS_AUDIT_2026-10-18.md` records the owned-document/GitHub checks and corrected entry points/status claims. **Open S1 blocker DOC-001:** current `archive --refresh` deletes the prior archive despite the preservation contract. Do not use standalone/group refresh on known-good artifacts until preservation and failure/retry tests are fixed. See `BUGS.md`; documentation changes do not close the implementation issue.
**Update 2026-10-18: DOC-001 fixed** (`3304c1d1`): `archive --refresh` and `probe-group record --archive --refresh` move the old archive to `Done/_replaced-<date>/<Mod>[-N]` and restore it if the new write fails (`tests/test_archive_preserves.py`, 5 tests, plus the group-path assertion in `tests/test_probe_group.py`). Not yet exercised on a real `Done/` archive: the first real refresh is the check. The paragraph above is kept as the record of what the audit found.

76. **Bounded execution and analysis reuse (S2; owner 2026-10-18: 'add to roadmap. Anything else like this we can improve or add?').** **Plan only:** `docs/EXECUTION_EFFICIENCY_PLAN.md`. Extend existing `revive-queue --jobs` and Java matrix `--parallel`, not a new distributed platform. E1 measures bottlenecks/resources; E2 reuses content/context-bound facts and recomputes affected work; E3 runs independent analysis under bounded resource/write ownership; E4 integrates cancellation, input-bound resume and bottleneck reporting. S1 supplies case identities, ownership and serial timing; S2 owns throughput delivery. Compare serial/cold/warm/parallel results and recovery controls before changing defaults; preserve qualification, owner review and live limits. Proposed adjacent improvements are analysis reuse, selective recomputation, backpressure, duplicate-work coalescing and observable recovery. No application implementation, expanded live concurrency or new policy is authorized by this planning entry.

77. **Recommendations after items 73 and 75 (2026-10-18; owner: "take a look at roadmaps and add recommendations as well as long term recommendations").** **Proposed, not approved; nothing here is scheduled.** Grounded in the state recorded in `docs/ROADMAP_STATUS.md` (items 73/75 implemented offline, every live gate pending) and the proposed S1-S4 strategy (`docs/STRATEGIC_ROADMAP.md`, `docs/VISION.md`); it does not change that strategy or any owner decision.
    - **Near term, in order (turn offline work into evidence):**
      - 77.1 **R1 live proof first** (`docs/LOCAL_HANDOFF.md` 0b item 1). Acceptance now fails closed without a bound run, so until one bound run passes and one edited candidate is refused, no new archive can be accepted. This is the single most valuable next hour of rig time.
      - 77.2 **Register the queue** (`finding-stats --rescan-stale --vanilla-core ...`, 0b item 2) and publish the first authoritative counts as CURRENT / STALE / UNKNOWN buckets. Every later measure (unlocks, review burden, auto-open reasons) depends on fresh, fingerprinted scans.
      - 77.3 **Small code follow-ups** that unblock the sister projects: `manifest.java_version` and `process_exit_code` in run records (Project Go's runtime gates); accept Project Go's new schema-v1 unit kinds and fields, or agree a schema 2 with Go and shared conformance fixtures; a public installed-mods function for Salvor; a hard timeout for `test_locks` so a hung `open_files()` fails instead of stalling a suite (`docs/ROADMAP_STATUS.md`, cross-project follow-ups).
      - 77.4 **Owner decisions waiting:** whether `revive` should try REVIEW-only fixers (B1 guards, B4 preset merge) before packeting; a command and approval flow for B6 weapon-row drafts; whether to build B3's detach-before-save template now that F2 finds 29 compiled cases.
      - 77.5 **First revision through `revise prepare` -> bound live run -> `revise finalize`**, on Zorg bf.10 or EPTA 2.1.3+bf.2 (item 74), with the R6 save-upgrade scenario for Zorg. That one run exercises R1, R5 and R6 together and closes item 74.
      - 77.6 **Release 0.4.0 after 77.1-77.5.** Source is 0.3.0 with 300+ commits since `v0.3.0` and no GitHub release for it; 0.4.0 is warranted by items 73/75, but tag it only once R1 has live evidence. Salvor pins `bridgeforge>=0.3,<0.4`: widen its range in the same change, after its provider contract test passes on 0.4.0.
      - 77.7 **Local agent hygiene.** Agents work in a git worktree, never in the main checkout; run `agent-diff-check` before merging; leave no untracked scripts in the checkout (the 2026-10-18 leftovers made the pre-commit hook fail for every commit there). Keep every document under 64k tokens, paged with next-page notes (owner 2026-10-18; `ROADMAP.md` and VoidSmith's work log were split that day).
    - **Long term, by proposed release:**
      - 77.8 **S1, reproducible revival case.** Build the case record on what now exists: R1 manifests (what ran), R2 registry (what was scanned), the escalation ledger and rulings (what was decided), R5 journals (what shipped). The gap is one object that ties them per mod version; `docs/ARCHITECTURE_GAPS.md` G1/G2 describe it. Measure S1 by "a second person can replay why this archive is what it is".
      - 77.9 **S2, bounded production lane.** Item 76's measured parallelism plus item 73's metrics: track review minutes per mod, false-positive and refusal rates per check and fixer, and promotion of recurring agent fixes, not just cleared finding counts. A fixer or check that never fires on real data, or always refuses, should be retired or narrowed.
      - 77.10 **S3, behaviour and upgrade qualification.** Make R6 scenarios and soak runs routine for every revision that touches campaign state; grow `docs/RC8_BEHAVIOUR.md` only from observed runs; give the probe a startup marker that echoes the manifest id (R1 slice 2, not built) so log identity stops depending on paths and timestamps.
      - 77.11 **S4, supportable kit.** Prove a restore on a second machine with R8 before any cutover (item 64); move the rig harness behind a documented, scripted setup so the live gates are not tied to one workstation; keep the agent contract (`AGENTS.md`) and `CLAUDE.md` current with each release.
      - 77.12 **One evidence model across the four projects.** BridgeForge's run records, RC8 behaviour rows and translation method are already consumed by Project Go, Salvor and VoidSmith. Version those contracts (run record, translation schema, save-module API), give each a shared fixture that both sides test against, and change them only in both repositories at once. That is what keeps the sister tools from drifting apart as each grows.

<!-- page-nav:start -->
> End of the last page.
<!-- page-nav:end -->

Item 83 B6 documentation checkpoint 2026-10-23: current package map, module placement, shim retirement and CLAUDE paths documented in [ARCHITECTURE.md](ARCHITECTURE.md); [B6 evidence](docs/REFACTOR_B6_CLOSEOUT.md) records validation/publication and remaining gates. B0/B1/B2/research are merged (#64/#65/#72/#73). The rest of the stack and applicable cross-repository work remain open; item 83 is not Done.

Item 83 publication checkpoint 2026-10-23: remaining B3 families, B4 audit and B5 are pushed with green hosted push CI; B6 documentation passes the full local suite (2,619 tests, 12 skips). [Stack ledger](docs/REFACTOR_STACK.md) records exact tips/runs. Draft PR creation requires owner approval; review/merge and item 83 completion remain pending.
