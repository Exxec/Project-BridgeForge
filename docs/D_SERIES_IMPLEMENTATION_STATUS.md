# D-series implementation status

This is the durable handoff record for roadmap P9 v2 stages D0-D6. Update it
after every implementation or validation phase so work can resume safely after
an interrupted agent session.

## Goal

Implement the behaviour-discovery pipeline described in `ROADMAP.md` without
weakening BridgeForge's read-only evidence boundaries or inferring that code or
data is dead.

## Fixed roadmap requirements

- D0: deterministic archaeology, cross-reference, lifecycle, persistence, and
  source/package-authority evidence.
- D1: behaviour map, risk register, hypotheses, unknown-behaviour ledger, and
  coverage seed. Optional model review must not be required.
- D2: no-verdict runtime baselines tied to a build and scenario.
- D3: proposed, adversarial test records derived from hypotheses.
- D4: modernization breadcrumbs linking changes to RISK/HYP/TEST ids.
- D5: differential validation with expected-change approval semantics.
- D6: counts-only coverage and residual-human-test output, plus a release gate.
- Dossier: present architecture, behaviour, risks, unknowns, coverage, and
  recommended tests without truncating evidence.

## Delivery phases

| Phase | Scope | State | Last validation |
|---|---|---|---|
| 0 | Recover requirements; establish durable handoff | COMPLETE | Roadmap and repository inspected at `c881d4ef` |
| 1 | D0 archaeology and cross-reference artifacts | COMPLETE | Focused D0 tests pass |
| 2 | D1 behaviour, risk, hypotheses, unknowns, coverage seed | COMPLETE | Focused D1 tests pass |
| 3 | D2 baseline import and D3 test synthesis | COMPLETE | No-verdict/hash and adversarial-test tests pass |
| 4 | D4 expected-change validation and breadcrumbs | COMPLETE | Add/approve/retire/check lifecycle tests pass |
| 5 | D5 behaviour diff and release behaviour evaluation | COMPLETE | Expected/absent delta and release-gate tests pass |
| 6 | D6 coverage, dossier integration, and release gate | COMPLETE | Counts-only coverage and dossier/release tests pass |
| 7 | Pilot fixtures, regression suite, docs and roadmap closure | COMPLETE WITH EXTERNAL SUITE CAVEAT | Original Exigency/SEEKER pilots pass; 570 unaffected tests and 39 focused tests pass |

## Current repository state

- Start commit: `c881d4ef` (`main`, equal to `origin/main`).
- Working tree was clean at goal creation on 2026-09-11.
- The authoritative D0-D6 specification is the P9 v2 section in root
  `ROADMAP.md`; `docs/ROADMAP.md` is an older tranche-level roadmap and does not
  define the D-series.
- `docs/EXPECTED_CHANGES_FORMAT.md` is the existing D5 design contract.

## Resume next

Tooling implementation is complete. P10's offline registration, verification,
era-set, and old-save baseline bridge are now implemented. The next D-series
work requires the reference-rig sessions: capture original/revived observations, import D2
baselines, decide open risks/unknowns, then execute D5/D6. Do not claim live D2
validation: no game was launched in this tooling implementation session.

## Decisions and deviations

- D2 is a no-verdict importer for observations captured by the existing probe,
  save tools, or a reference rig. It deliberately does not launch a game.
- CLI `release` requires D5 behavior evidence. The Python `release_mod` API
  retains an opt-in `require_behavior_evidence` switch so existing callers can
  migrate without an unannounced API break; the user-facing workflow enforces
  the new gate.
- Pilot evidence is stored under ignored `artifacts/d-series-pilot/`, not in an
  original, working mod, or known-good `Done` release.

## Validation log

- 2026-09-11: `git status --short --branch` showed clean `main...origin/main`.
- 2026-09-11: root `ROADMAP.md` D0-D6 and
  `docs/EXPECTED_CHANGES_FORMAT.md` reviewed.
- 2026-09-11: 29 focused behavior-discovery, dossier, and release tests passed.
- 2026-09-11: initial Exigency and SEEKER D0/D1 CLI pilots completed without
  modifying their selected inputs.
- 2026-09-11: the untouched-original pilot exposed a legacy CSV row with a
  `None` extra-column key. D0 now handles it deterministically and the fixture
  covers the bug class.
- 2026-09-11: final original-input pilot metrics and known-surprise analysis
  recorded in `docs/D_SERIES_PILOT_REPORT.md`.
- 2026-09-11: 570 tests outside the two environment/process-sensitive modules
  passed (1 skipped). The full 581-test attempt had six unrelated existing
  Windows failures: four boot-test child processes retained temp-log handles,
  and two probe builds failed in the local JDK with `Fatal Error: Cannot close
  compiler resources`. D-series, dossier, release, and constant-pool focused
  validation passed 39/39 after implementation. These failures belong to the
  separately planned P11 tool-hygiene work; no D-series test failed.
- 2026-09-11: `compileall` and `git diff --check` passed. Runtime package
  version now matches `pyproject.toml` at `0.2.0`.
- 2026-09-12: after the P10 offline tranche, all 579 tests outside the two
  previously identified environment/process-sensitive modules passed (1
  skipped). The full 589-test run retained the same six external failures.
