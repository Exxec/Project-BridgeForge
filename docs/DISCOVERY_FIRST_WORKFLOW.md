# Discovery-first workflow (roadmap P9 v2, D0-D6)

BridgeForge discovers and records a mod's known behaviour before modernization.
All generated stages work without a language model. Model review is optional
annotation; it never replaces the deterministic crawl or changes source.

## Evidence locations

For a convention-layout revival, keep generated evidence in
`In operation/<Mod>/reports/discovery/`. Keep human decisions in
`In operation/<Mod>/reports/expected-changes.json`. Neither belongs inside the
packaged `working/` directory. For experiments, use an ignored `artifacts/`
directory.

## D0: archaeology

```powershell
py -3 -m bridgeforge archaeology <working-or-original-mod> `
  --output <reports/discovery> [--save-aliases <save-compat-evidence.json>]
```

Outputs `archaeology/architecture.json`,
`archaeology/cross_reference.json`, and `ARCHITECTURE_MAP.md`. The graph joins
parsed Java imports and strings, class-file constant-pool references, lenient
JSON, CSV, Starsector data files, JAR resources, scanner findings, lifecycle
hooks, and registrations. Persistent fields are candidates until real-save
alias evidence confirms their class. Source/package overlap is an inventory,
not an equivalence claim.

`NO_KNOWN_REFERENCE` always lists checked and unverified domains and explicitly
is not a dead-code verdict.

## D1: behaviour and risk model

```powershell
py -3 -m bridgeforge behavior-map `
  <reports/discovery/archaeology/architecture.json> `
  --output <reports/discovery>
```

`risk-register` is an equivalent entry point when the risk view is the user's
starting task. Both produce:

- `behavior.json` and `BEHAVIOR_MAP.md`
- `risks.json` and `RISK_REGISTER.md`
- `hypotheses.json`
- `unknowns.json` and `UNKNOWN_BEHAVIORS.md`
- `coverage_seed.json`

IDs are content-derived and stable for unchanged entry points. Generated
unknowns begin as `PRESERVE UNTIL EXPLAINED`; a modernization must not erase or
silently resolve them.

To add these views to a normal dossier:

```powershell
py -3 -m bridgeforge dossier <mod> --discovery-dir <reports/discovery>
```

## D2: no-verdict runtime baseline

Capture observations through the probe, save tools, or an isolated reference
rig. Then import the capture without assigning pass/fail:

```powershell
py -3 -m bridgeforge probe-baseline <observations.json> `
  --build <original-or-rN> --scenario <scenario-id> `
  --reference-kind old-game-rig --output <baseline.json>
```

The input must contain `observations`, each with `observation`, `subject`, and
either a `fields` object or `field`/`value`. `behavior_id` is optional but is
needed for D6 coverage attribution. The baseline records the input SHA-256 and
has a null verdict. Baseline creation never launches a game.

## D3: adversarial test synthesis

```powershell
py -3 -m bridgeforge hypotheses <reports/discovery/hypotheses.json> `
  --tests --output <reports/discovery/tests.json>
```

Tests remain `PROPOSED`. They include repeat-trigger, save/load, and declared
compat-set variants plus acceptance and stop conditions. A reviewer may refine
them before execution.

## D4: modernization breadcrumbs

Add the expected change in the same phase as the source/data edit:

```powershell
py -3 -m bridgeforge expect add <reports/expected-changes.json> `
  --mod-id <id> --id EXP-<MOD>-001 --build r1 --layer runtime `
  --summary "..." --why "..." --observation <kind> --subject <subject> `
  --field <field> --change from_to --from <old> --to <new> `
  --link risk=<RISK-id> --link test=<TEST-id>
```

New entries are `PROPOSED`. `expect approve ... --by <owner> --on <YYYY-MM-DD>` changes only a
proposed entry to `APPROVED`; `expect retire ... --by <owner> --why "..."`
preserves superseded history. Each edit creates a recoverable
`.before-last-edit` copy. `expect check` rejects duplicate ids, missing fields,
invalid matchers, missing approval/retirement provenance, missing
RISK/HYP/TEST breadcrumbs, unknown supplied links,
and unknown supplied builds. Broad `any` matchers remain visible warnings.

## D5: differential validation

```powershell
py -3 -m bridgeforge behavior-diff <reference-baseline.json> <new-baseline.json> `
  --before-map <original-architecture.json> `
  --after-map <working-architecture.json> `
  --expected <reports/expected-changes.json> `
  --output <reports/discovery/behavior-diff.json>
```

The diff reports `UNCHANGED`, `EXPECTED_CHANGE`, `PENDING_APPROVAL`,
`UNEXPLAINED_CHANGE`, `MISSING_OBSERVATION`, `NEW_BEHAVIOR`, and
`EXPECTED_BUT_ABSENT`. The last category catches an approved fix that did not
actually occur.

Run the standalone behavior gate with:

```powershell
py -3 -m bridgeforge release-behavior-evaluate <behavior-diff.json> `
  --risks <risks.json> --unknowns <unknowns.json>
```

## D6: coverage and release

```powershell
py -3 -m bridgeforge coverage <behavior.json> `
  --baseline <baseline.json> --diff <behavior-diff.json> `
  --tests <tests.json> --unknowns <unknowns.json> `
  --output <reports/discovery/coverage.json>
```

Coverage has static, runtime, save/load, compat, and human columns. It reports
counts, never a percentage, and emits residual actions only for open rows.

The CLI `release` command now requires `--behavior-diff`; pass
`--behavior-risks`, `--behavior-unknowns`, and `--expected-changes` so open
HIGH risks, preserved unknowns, unexplained deltas, invalid decisions, or
unapproved changes block packaging. Approved expected changes are grouped by
build in the generated release note.

## Interruption-safe checkpoint

After each phase, update `docs/D_SERIES_IMPLEMENTATION_STATUS.md` for tooling
work or the revival's `reports/REVIVAL_PLAN.md`/`REVIVAL_REPORT.md` for a mod.
Record exact artifact paths, input hashes, command results, open risks, and the
next command. Generated state never substitutes for an owner decision.
