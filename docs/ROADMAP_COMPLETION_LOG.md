# Roadmap completion goal

The active goal is to finish the remaining BridgeForge roadmap in documented,
validated tranches, committing/pushing each completed tranche. Original mods,
historical installs, saves and unrelated checkout changes remain protected.
No unresolved live/manual or research gate is silently treated as complete.

## Handoff: 2026-09-12

- D-series/P10 offline setup and Exigency era dependency recovery: committed as
  `8730c8982f54de97ba2c02a8b71feb6b7df6b3c3`; exact-SHA six-job CI passed:
  https://github.com/Exxec/Project-BridgeForge/actions/runs/34703865601.
- Dedicated installs are under `C:\Program Files (x86)\Fractal Softworks`.
  Runtime observation remains `LIVE VALIDATION REQUIRED`; see
  `P10_REFERENCE_RIG_STATUS.md`. No gameplay was performed by this tranche.
- Next: P11 hygiene, then P12 layout tooling, followed by outstanding acceptance
  evidence/release gates. Post-1.0 research needs an explicit evidence/scope gate.

## P11 tranche: implemented and publication verified

Python/CI tranche pushed as `ebc42466fcb60cc5d1c173f56735b35cc07f61ca`.
The general tools/*.ps1 ignore rule required an explicit exception for the canonical
monitor; the following publication commit includes that script. Verify CI on the
final publication SHA, not the intermediate Python-only commit.
Final SHA `05cec13efe9b35f8fc5077fe26b66d3a5af2376b`: all six CI jobs passed at
https://github.com/Exxec/Project-BridgeForge/actions/runs/34717846238.

SAFE tooling changes only; no individual mod behavior is changed.

- Added a checkout/probe-release end-state guard and wired all six CI jobs to it.
  It also hashes pre-existing dirty files, rather than relying on status alone.
- Added a shared resolved-temp-path test fixture and regression tests.
- Added read-only `who-locks` and a rig-doctor process/lock check: Windows Restart
  Manager for exact files and rig log/config sentinels; psutil for descendant open
  files/current directories, and watcher candidates. Partial visibility is explicit;
  a candidate is not automatically a lock or a stale process. No process is killed.
- Required psutil as a runtime dependency for process-path inspection.
- Updated checkout to v5 and setup-python to v6, the minimal Node24 upgrades
  documented by their official repositories. Windows/Linux matrix unchanged.
- The boot-test launcher already uses `_terminate_tree` in finally cleanup.
  The ignored local `In operation/bf-test.ps1` did lack interruption cleanup:
  added session-PID/start-time-checked tree cleanup and hidden wrapper launch.
  A versioned canonical copy now lives in `tools/bf-test.ps1`; it uses the same
  `In operation/_rig`. No standalone tail/grep monitor is started by either tool.
- Two guard tests and 34 lock/rig/reference tests passed inside the sandbox.
  Actual Windows Restart Manager inspection outside the sandbox succeeded, with
  no rig process candidate found and 362 denied process queries reported.
  First guarded suite was stopped because old rig fixtures repeatedly inspected
  the host; its end-state guard passed. Those fixtures now mock external process
  state. Final guarded suite: **601 tests, OK (skipped=1), 36.978 seconds**;
  checkout/probe release unchanged. Evidence: ignored
  `In operation/_attic/P11-test-suite.log`.
- Focused final regression run: 43 tests passed, including actual Windows Restart
  Manager identification of this process holding an exclusive temporary log file.
- `tools/bf-test.ps1`: PowerShell parser passed; no-launch `selftest` passed
  (window helper compiled, no rig game running). Real gameplay interruption remains
  unexercised; source review establishes finally cleanup, not live-game correctness.
- Shared resolved-temp helper adopted by boot fixtures; external process-path
  state mocked by rig/reference fixtures. Guard regression proves drift fails even
  when tests pass, and preserves test failures when no drift occurs.
- SOURCE REVIEW: narrow tool-only diff. STATIC VALIDATION: suite/parser passed.
  COMPILE: full suite exercised local probe javac successfully. DEPENDENCY CHECK:
  psutil 7.2.2 installed. API SIGNATURE CHECK: real Restart Manager test passed.
  LIVE STARSECTOR TEST: `LIVE TEST NOT PERFORMED`. SAVE COMPATIBILITY: not changed.
  PACKAGE VALIDATION: uv built sdist/wheel under `In operation/_attic/p11-dist`;
  wheel metadata declares psutil, and all four changed Python runtime modules
  match checkout bytes exactly. Exact-SHA CI: all six jobs passed (link above).

### Environment evidence

The prior full sandbox suite had six errors (four boot/log cleanup, two real javac
resource-close errors). The two affected modules passed all 12 tests outside the
sandbox. Restart Manager also returned error 29 in the sandbox. Do not change mod
or launcher behavior to disguise this permission boundary.

### Resume procedure

1. Check `git status`; preserve unrelated `CLAUDE.md`.
2. Local validation is complete; finish package and publication checks.
3. Review diff, commit only tranche files, push, verify CI for that exact SHA.
4. Update this log and P11 status, then implement P12 in small tested phases.
5. Keep live/reference/manual gates open until their evidence is actually captured.

P12 release preflight: GitHub currently has only `v0.1.0-alpha.1`; no v0.2.0
release exists. Do not mistake the package version for a published release.
CI runtime-upgrade evidence: [checkout v5](https://github.com/actions/checkout#checkout-v5)
and [setup-python v6](https://github.com/actions/setup-python#breaking-changes-in-v6)
use Node24. Later major releases are unnecessary for this narrowly scoped upgrade.

## P12A plan: intake, board and layout warnings

Approved scope from the roadmap continuation: SAFE offline tooling only. No mod
source changes, architecture migration, release promotion or install writes.
Revival scoring is not applicable to this tool tranche; an intake is explicitly
`ASSESSMENT_REQUIRED`, not an approved revival plan. The authoritative workflow
and template were read before implementation; actual revival changes still require
their per-mod score, capability routing and completed plan.

- SAFE: intake of a preflight-safe ZIP with one selected mod root into a fresh
  `In operation/<Mod>/{original,working,reports,builds,scratch}`. Preserve archive
  and full upstream extract byte-for-byte; copy only the selected root to working.
  Generate scan/dossier evidence (optional archaeology). Reject collisions, unsafe
  portable paths and ambiguous roots. Stage analysis before publishing; never
  overwrite an existing mod folder, including incomplete attempts.
- SAFE: deterministic board from layout, metadata and explicitly named evidence
  files. Missing/malformed evidence means unknown, never zero risks or readiness.
  Report-declared completion is not independently verified release status. Default
  read-only output; optional generated status files must not replace manual STATUS.
- SAFE: rig-doctor layout warnings for root strays/nonconforming working paths.
  Do not move/delete strays or inspect original/scratch mod contents as active copies.
- REVIEW/MANUAL outside this tranche: promotion and prior-release retention, safe
  Vacuum move after lock checks, v0.2.0 publication and outstanding live evidence.

Validation: focused archive/layout/board/CLI tests, forced-analysis failure and
collision regression tests; read-only actual board/layout check; full guarded
suite; built wheel/source checks; commit/push and exact-final-SHA six-job CI.
Resume at this section after any usage interruption. Preserve `CLAUDE.md`.

### P12A implementation checkpoint

Implemented `intake`, `board`/generated status files and `project_layout` rig check.
Generic dossier output protection remains unchanged. Portable ZIP preflight now
rejects invalid/reserved components, case collisions and file/ancestor collisions;
empty directories are retained. Intake checks stored archive, whole extracted tree
and working bytes after analysis, relocates staging paths in evidence, and publishes
the completion marker last after exclusive reservation. Failure/mutation/collision
tests cover both analysis and controlled publication rollback.

Focused validation: 96 scanner/layout/rig/reference tests passed, followed by 51
focused tests after adding provenance/legacy/marker/output-link coverage. Actual
`board --write` created only STATUS.generated files: 13 rows, with four known
Vacuum root layout findings. Free-form legacy completion reports and absent named
test/risk evidence are reported as unknown/invalid instead of inferred as ready.
No existing mod was intaken, repaired, moved or promoted; no game/install/save write.

Next checkpoint: full guarded suite and package/source proof, then commit/push and
exact-SHA CI. P12B promotion/Vacuum/release remains open.

Full guarded suite passed: **621 tests, OK (skipped=1), 45.340 seconds**;
checkout/probe release unchanged. Log: `In operation/_attic/P12A-test-suite.log`.
Initial wheel matched all five changed runtime modules byte-for-byte. Source
archive inspection found setuptools omitted the shared test helper, canonical
monitor and new workflow doc; added a narrow MANIFEST.in to include those already
public/approved source files (no original mods or local revival-planning material).
Rebuild/inventory checks are required before publication.

SOURCE REVIEW: tool-only diff, original ownership preserved. STATIC VALIDATION:
focused/full suites passed. COMPILE: full suite exercised local probe javac.
DEPENDENCY CHECK: unchanged declared psutil dependency. API SIGNATURE CHECK:
full suite exercised Windows Restart Manager. SAVE COMPATIBILITY: not changed.
LIVE STARSECTOR TEST: `LIVE TEST NOT PERFORMED`. PACKAGE VALIDATION: rebuilt
sdist contains all three required helper/script/doc files; wheel matches all five
changed runtime modules. Isolated installed-wheel `python -I -m bridgeforge board`
passed against the actual repo without source-checkout imports or writes (log:
`In operation/_attic/P12A-installed-board.log`). Package logs/artifacts are in
`In operation/_attic/P12A-package.log` and `p12a-dist`. Exact-SHA CI is pending
commit/push and final publication verification.

P12A publication verified: `9d2f53b39e624cba5da2fa94cc671510fc0ecd2b`, all six
CI jobs passed: https://github.com/Exxec/Project-BridgeForge/actions/runs/34718586654.
Final packages rebuilt from an exact-commit LF checkout; all 96 wheel runtime/data
files and required sdist helper/script/doc assets equal committed blobs.

## P12B plan: guarded promotion and remaining layout/release gates

SAFE tooling scope: a dry-run-default `promote` wrapper around existing release
gates, with required revival report/plan audit, D-series behavior evidence, staged
package validation, exclusive destinations, prior-release retention and rollback.
Do not promote actual mods with missing/incomplete reports or unresolved live gates.
Preserve original/working copies and unrelated Done contents. No mod code changes;
revival complexity scoring remains in the mod's approved plan, not invented here.

SAFE packaging gap: the wheel currently omits bundled release_policy.json; include
it and fail closed if explicit/default policy is missing or malformed rather than
silently granting release permission. This protects Exigency's local-only gate.

Vacuum layout move: inspect exact sources/destinations and locks before authorizing
any move; preserve bytes, record manifests, and never relabel an unvalidated build.
Stop if ownership/lock status or layout role cannot be established safely.
Tool v0.2.0 release: inspect existing tags/releases, exact-SHA CI and package policy
before publishing. No original mod/license-restricted material in tool artifacts.

Validation: promotion dry-run/pass/block/collision/prior-retention/rollback tests;
missing-policy checks; full guarded suite; exact-commit wheel/policy inventory and
installed smoke; commit/push with exact-SHA CI. Preserve CLAUDE.md and new .vscode/.
Promotion implementation is the first checkpoint; live/uncertain gates stay open.

### P12B promotion checkpoint

Implemented `promote` with audited external plan/report evidence, explicit scored
workflow routing, separate affirmative validation labels, mandatory D5 release
gates, staged exact ZIP identity, unchanged input/report hashes, prior-release
retention, per-release report copies and lock-journaled reversible publication.
Negative live-test evidence cannot be hidden behind historical PASS text.
Installed packages include release_policy.json; absent/invalid policy fails closed.
See docs/P12_PROMOTION.md for CLI and interrupted-promotion recovery limits.

Validation: 42 focused tests passed; full guarded suite passed 630 tests (one
environment symlink skip), checkout/probe-release hermeticity PASS. Log:
`In operation/_attic/P12B-test-suite.log`. No actual mod promotion, live test,
original/working mod edit, or layout move performed. Exact-commit package and CI
publication evidence follows in ignored `In operation/_attic/P12B_PUBLICATION.md`.

Next tranche: finish Vacuum layout migration after byte inventories and lock checks.
The old Vacuum root is an earlier modified attempt, not untouched original input;
preserve it under scratch. The Vacuum rig's Java25 BAT still points at the old
Flu-X-rc8-runtime JDK path and needs a documented mechanical path correction when
moving to _rig-vacuum. Tool v0.2.0 tag/release and outstanding live gates remain open.

P12B publication verified: `c8cbbb79a78bb94436a31c37cdfc1bce81504900`, all six
CI jobs passed: https://github.com/Exxec/Project-BridgeForge/actions/runs/34719147496.
All 98 wheel runtime/data files plus required sdist assets match committed blobs;
isolated install confirms bundled Exigency denial. Exact hashes are recorded in
`In operation/_attic/P12B_PUBLICATION.md`.

## P12C plan: byte-attested Vacuum layout completion

Layout-only SAFE scope, no new revival architecture or gameplay implementation:
move the active mod to `Vacuum/working`, earlier modified attempt to
`Vacuum/scratch/Vacuum-earlier-copy`, pre-carrier ZIP to `Vacuum/builds`, and
isolated rig to `_rig-vacuum`. Do not claim earlier files are untouched originals.
Preserve existing HIGH plan/report, all mod bytes, saves and installed core.
Only permitted non-byte-identical changes: the rig launcher shared JDK path and
the rig Vacuum junction target. Mod-facing folder and ids remain unchanged.

Lock diagnostics: no process candidates in all three roots; hundreds of denied
process queries mean absence is not proof of no locks. OS moves stop on failure.
Before/after file SHA256, directory and non-traversed link inventories plus an
intent/completion journal are kept in `In operation/_attic/P12C-vacuum`.
One-shot operation and recovery limitations are recorded beside that evidence.
No promotion to Done or new live validation. LIVE VALIDATION REQUIRED remains.

### P12C layout checkpoint

Completed all four mapped root moves; every file/directory/link inventory matched.
Earlier: 1592 files/134 directories. Working: 1755/148. Rig: 16422/396/two links.
Archive SHA256 matched. Final rig verification allows only the documented BAT
JDK/comment change and Vacuum junction retarget; all other entries match exactly.
No deleted user/mod/game bytes. The old dangling link itself was replaced safely.

`board` discovers Vacuum/working r1, with unknown readiness/test/risk evidence and
an existing non-final report warning. `rig-doctor` has layout/working identity/
dependencies/isolation PASS, overall WARN for absent probe; real-install save
baseline check SKIPPED. No compile/API/save-compatibility/live claim added.
See docs/P12_VACUUM_LAYOUT.md and local inventories/journal for exact scope,
operational verifier correction, validation levels and non-speculative recovery.
Updated ignored In operation/README.md to remove stale move/undo instructions.

Next: v0.2.0 exact-commit tool publication; remaining live/manual gates stay open.
Publication and regression evidence for this checkpoint is recorded under
`In operation/_attic/P12C_PUBLICATION.md` after commit/push.

Full guarded tool suite: 630 tests passed (one environment-dependent symlink
skip), checkout/probe-release hermeticity PASS. No tool runtime module changed
in this tranche. Final docs/package manifest and exact-SHA CI are publication
gates; previous binary tests are not treated as proof of new gameplay behavior.

P12C publication verified: `a45ce62f300d7feb1869443a94fbfd86feefe528`, all six
CI jobs passed: https://github.com/Exxec/Project-BridgeForge/actions/runs/34719606396.
All 98 wheel runtime/data files and six required sdist assets match committed
blobs; installed-wheel moved-layout/license smoke PASS. Final hashes recorded
in `In operation/_attic/P12C_PUBLICATION.md`.

## P12D plan: exact-commit v0.2.0 tool publication

SAFE release-only scope: consolidate the changelog into one dated 0.2.0 section,
commit/push, run full guarded suite and exact-SHA six-job CI, rebuild from a clean
LF exact-commit checkout, verify wheel/sdist blobs and installed version/license
checks, then create the absent v0.2.0 tag and publish wheel/sdist with changelog
notes and SHA256 receipts. No proprietary game, original mod, rig saves, or local
operation trees are release assets. Do not infer live validation from tool release.

Read-only remote preflight: only v0.1.0-alpha.1 release exists; no v0.2.0 remote
tag. Reverify immediately before publishing; never replace an existing tag or
release blindly. Keep exact source SHA, CI URL, asset hashes and release URL in
`In operation/_attic/P12D_PUBLICATION.md` as each phase finishes. Publish a draft
first; verify downloaded draft assets before making the release public.
Update tracked roadmap completion evidence after observable publication.
Overall goal remains unfinished until remaining live/manual/research gates close.

P12D pre-publication full guarded suite: 630 tests passed, one environment symlink
skip, checkout/probe-release hermeticity PASS. Log: P12D-test-suite.log. Runtime
and package versions are both 0.2.0. Commit/tag/package/CI evidence follows in
the per-phase local publication handoff; do not claim publication until verified.

Release package preflight caught a missing source-distribution changelog. Add
CHANGELOG.md to MANIFEST.in and rebuild against a new final release SHA; the
superseded 3eb1fa3 package is not a published artifact. All runtime blobs and
installed smoke had passed; no tag/draft was created before this correction.
