# Probe scenarios

A candidate can carry `working/reports/PROBE_SCENARIO.json` (schema 1). `probe-group install` and `probe-config` read it,
`probe-group record` judges the run against it. Code: `bridgeforge/probe_scenario.py` (loader, staging, evaluation) and the probe's
`ScenarioRunner.java`. The loader refuses unknown keys and unknown steps at every level.

```json
{
  "schema": 1,
  "settings": {"data/config/tem_crusade_settings.json": {"debugStartInDays": 1}},
  "steps": [{"step": "advance_days", "days": 10}],
  "expect": [
    {"id": "launch", "line": "BF-TEMCRUSADE\\|launch\\|", "within_days": 4},
    {"id": "end", "line": "BF-TEMCRUSADE\\|end\\|", "within_days": 14, "count_min": 1, "after": "launch"}
  ],
  "pass_requires": ["launch", "end"]
}
```

## settings

`{mod-relative .json path: {top-level key: value}}`. Applied only to the staged rig copy (`<rig>/mods/<folder>`) before launch;
never to `working/`. The loader refuses a path with `..`, an absolute path, a non-`.json` file, a file missing from the rig copy,
and a rig copy that is or overlaps the working copy. The file is read leniently (comments allowed) and rewritten as strict JSON, so
comments are gone from the rig copy only. The install result lists each file with the before and after values.

**Provenance consequence:** the staged bytes then differ from the candidate, so the run manifest reports "staged files differ from the
candidate" and the member's provenance is not BOUND. A scenario with `settings` is evidence for its expectations, not for acceptance
of the shipped bytes; accept from a run without settings edits.

## steps (closed set, run by `ScenarioRunner`, public API only)

Each logs `BF-PROBE|<ver>|scenario|INFO|step=<name>|result=...` (`WARN` with `result=error` on a throw). javap-verified against RC8's
`starfarer.api.jar`, 2026-10-20:

| step | keys | API |
|---|---|---|
| `advance_days` | `days` | waits (the game's own time passes) using `CampaignClockAPI.getTimestamp()` / `getElapsedDaysSince(long)`; later steps run after |
| `damage_player_module` | `member_hull_id`, `module_index` (>= 1), `hull_fraction` (0..1) | player fleet `FleetDataAPI.getMembersListCopy()`, `FleetMemberAPI.getHullId()`, `getStatus()`, `FleetMemberStatusAPI.setHullFraction(int, float)` |
| `destroy_player_module` | `member_hull_id`, `module_index` (>= 1) | `setHullFraction(int, 0)`, `setDetached(int, Boolean)`, `setPermaDetached(int, Boolean)` |
| `log_player_modules` | optional `member_hull_id` | `getNumStatuses()`, `getHullFraction(int)`, `isDetached(int)`, `isPermaDetached(int)`, `getArmorDamageTaken()` |

Not included: `open_market_dialog` (`CampaignUIAPI.showInteractionDialog(SectorEntityToken)` exists, but the dialog pauses the campaign and
the public API has no call that closes it, so the rest of the run would stall); armor damage per module (the API only has
`repairArmorAllCells`, no setter). Status index 0 is the ship's own hull, modules start at 1; this is the assumed convention and needs
the live run to confirm (`log_player_modules` prints every index). After a save and reload the mutating steps are not repeated (a sector
memory flag records the first run); `log_player_modules` runs again so values can be compared.

The runner also logs `scenario|INFO|clock|day=N` once per elapsed in-game day since it started; `within_days` is measured on those lines.

## expect and pass_requires

`line` is a regex searched in each log line. Exactly one of `within_days` (in-game days since the scenario clock started, one-day
resolution) or `within_seconds` (log milliseconds since the clock line). `count_min` defaults to 1. `after` names an earlier expectation:
only lines after its satisfying line count. Only lines after the first scenario clock line count; with no clock line in the log (old probe, or
no scenario staged) every expectation is NOT_OBSERVED.

| status | meaning |
|---|---|
| PASS | `count_min` lines matched inside the window (the first one is recorded as evidence) |
| FAIL | the window is over without enough matches, or only late lines matched |
| NOT_OBSERVED | the log ended before the deadline, or an `after` expectation never passed |

`pass_requires` (default: all) lists the expectations that decide the member: any FAIL makes the member FAIL; any NOT_OBSERVED turns a
PASS member INCOMPLETE. The run record (`_live/<TESTID>.json`) gets a `scenario` block per mod id.

## Where it applies

- `probe-group install`: validates each member's scenario, stages its settings into that member's rig copy, writes `scenario_steps` and
  `scenario_clock` into the merged `bf_probe_config`, and lists staged files under `scenarios`.
- `probe-config <mod> --runtime <rig>`: same for a single mod (needs the mod already installed in `<rig>/mods` when `settings` is non-empty).
- `probe-group record`: evaluates the log, folds the verdict into the member's verdict and the run record.

Examples: `tests/fixtures/probe_scenarios/` (Templar Crusade, SEEKER SK-6c, All the Domain Drones). They are fixtures, not installed into
`In operation`. The stage names and the `fingerprint` / `content-parity` regexes follow what the other work currently logs and need a
check against the first live log.
