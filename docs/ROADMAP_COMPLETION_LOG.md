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

## P11 tranche: implemented, publication verification pending

Python/CI tranche pushed as `ebc42466fcb60cc5d1c173f56735b35cc07f61ca`.
The general tools/*.ps1 ignore rule required an explicit exception for the canonical
monitor; the following publication commit includes that script. Verify CI on the
final publication SHA, not the intermediate Python-only commit.

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
  match checkout bytes exactly. Exact-SHA CI: pending publication checks.

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
