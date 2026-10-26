"""Declarative per-mod probe scenarios (`working/reports/PROBE_SCENARIO.json`, schema 1; docs/PROBE_SCENARIOS.md).

A scenario says what to change in the staged rig copy (`settings`), what the probe should do in game (`steps`, a closed set run
by the probe's ScenarioRunner through the public API), what the game log must show (`expect`) and which expectations decide the
member's verdict (`pass_requires`). The loader refuses unknown keys and unknown steps at every level, so a typo is an error, not
a silently ignored line.
"""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from bridgeforge.safeio import atomic_write_text

SCENARIO_FILE = Path("reports") / "PROBE_SCENARIO.json"
SCHEMA = 1
SCENARIO_CHECK = "scenario"
MAX_DAYS = 3650
MAX_SECONDS = 86400 * 10
MAX_REGEX = 500
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_HULL_ID = re.compile(r"^[A-Za-z0-9_\-]{1,80}$")

# step name -> (required keys, optional keys). The set is closed; each is verified against RC8's starfarer.api.jar with javap
# (docs/PROBE_SCENARIOS.md). `open_market_dialog` is deliberately absent: showInteractionDialog exists, but a dialog pauses the campaign
# and nothing in the public API closes it again, so the probe would stall the rest of the run.
STEPS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "advance_days": (frozenset({"days"}), frozenset()),
    "damage_player_module": (frozenset({"member_hull_id", "module_index", "hull_fraction"}), frozenset()),
    "destroy_player_module": (frozenset({"member_hull_id", "module_index"}), frozenset()),
    "log_player_modules": (frozenset(), frozenset({"member_hull_id"})),
}
_TOP_KEYS = frozenset({"schema", "settings", "steps", "expect", "pass_requires"})
_EXPECT_KEYS = frozenset({"id", "line", "within_days", "within_seconds", "count_min", "after"})


class ScenarioError(ValueError):
    """Raised when a scenario file or a staging request is invalid or unsafe."""


def _number(value: object, what: str, low: float, high: float, *, inclusive_low: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ScenarioError(f"{what} must be a number, got {value!r}.")
    if value < low or value > high or (not inclusive_low and value == low):
        raise ScenarioError(f"{what} must be between {low} and {high}, got {value!r}.")
    return float(value)


def _int(value: object, what: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low or value > high:
        raise ScenarioError(f"{what} must be an integer from {low} to {high}, got {value!r}.")
    return value


def _check_relative_path(raw: object) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ScenarioError(f"settings key {raw!r} must be a mod-relative file path.")
    path = PurePosixPath(raw.replace("\\", "/"))
    if path.is_absolute() or re.match(r"^[A-Za-z]:", raw) or ".." in path.parts:
        raise ScenarioError(f"settings path {raw!r} must be relative to the mod folder, with no '..'.")
    if path.suffix.lower() != ".json":
        raise ScenarioError(f"settings path {raw!r}: only .json files can be edited.")
    return path.as_posix()


def _validate_settings(raw: object) -> dict[str, dict[str, object]]:
    if not isinstance(raw, dict):
        raise ScenarioError("'settings' must be an object {relative json path: {key: value}}.")
    settings: dict[str, dict[str, object]] = {}
    for path, edits in raw.items():
        key = _check_relative_path(path)
        if not isinstance(edits, dict) or not edits:
            raise ScenarioError(f"settings[{path!r}] must be a non-empty object of top-level key edits.")
        settings[key] = dict(edits)
    return settings


def _validate_step(index: int, raw: object) -> dict[str, object]:
    where = f"steps[{index}]"
    if not isinstance(raw, dict) or not isinstance(raw.get("step"), str):
        raise ScenarioError(f"{where} must be an object with a string 'step'.")
    name = raw["step"]
    if name not in STEPS:
        raise ScenarioError(f"{where}: unknown step {name!r}; supported: {', '.join(sorted(STEPS))}.")
    required, optional = STEPS[name]
    keys = set(raw) - {"step"}
    if keys - required - optional:
        raise ScenarioError(f"{where} ({name}): unknown key(s) {sorted(keys - required - optional)}.")
    if required - keys:
        raise ScenarioError(f"{where} ({name}): missing key(s) {sorted(required - keys)}.")
    step: dict[str, object] = {"step": name}
    if "days" in raw:
        step["days"] = _number(raw["days"], f"{where}.days", 0, MAX_DAYS, inclusive_low=False)
    for key in ("member_hull_id",):
        if key in raw:
            if not isinstance(raw[key], str) or not _HULL_ID.match(raw[key]):
                raise ScenarioError(f"{where}.{key} must be a hull id (letters, digits, _ and -).")
            step[key] = raw[key]
    if "module_index" in raw:
        # FleetMemberStatusAPI index 0 is the ship's own hull; modules start at 1.
        step["module_index"] = _int(raw["module_index"], f"{where}.module_index", 1, 64)
    if "hull_fraction" in raw:
        step["hull_fraction"] = _number(raw["hull_fraction"], f"{where}.hull_fraction", 0, 1)
    return step


def _validate_expect(index: int, raw: object, seen: set[str]) -> dict[str, object]:
    where = f"expect[{index}]"
    if not isinstance(raw, dict):
        raise ScenarioError(f"{where} must be an object.")
    if set(raw) - _EXPECT_KEYS:
        raise ScenarioError(f"{where}: unknown key(s) {sorted(set(raw) - _EXPECT_KEYS)}.")
    ident = raw.get("id")
    if not isinstance(ident, str) or not _ID.match(ident):
        raise ScenarioError(f"{where}.id must be a short id (letters, digits, _ and -).")
    if ident in seen:
        raise ScenarioError(f"{where}: duplicate id {ident!r}.")
    pattern = raw.get("line")
    if not isinstance(pattern, str) or not pattern or len(pattern) > MAX_REGEX:
        raise ScenarioError(f"{where}.line must be a regex string of 1 to {MAX_REGEX} characters.")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ScenarioError(f"{where}.line is not a valid regex: {exc}") from exc
    if ("within_days" in raw) == ("within_seconds" in raw):
        raise ScenarioError(f"{where}: give exactly one of within_days or within_seconds.")
    expectation: dict[str, object] = {"id": ident, "line": pattern, "count_min": _int(raw.get("count_min", 1), f"{where}.count_min", 1, 100000)}
    if "within_days" in raw:
        expectation["within_days"] = _number(raw["within_days"], f"{where}.within_days", 0, MAX_DAYS)
    else:
        expectation["within_seconds"] = _number(raw["within_seconds"], f"{where}.within_seconds", 0, MAX_SECONDS)
    if "after" in raw:
        after = raw["after"]
        if after not in seen:  # only an earlier expectation: this also rules out cycles
            raise ScenarioError(f"{where}.after {after!r} must name an expectation defined earlier in 'expect'.")
        expectation["after"] = after
    return expectation


def validate_scenario(raw: object) -> dict[str, object]:
    """Return the normalized scenario (schema 1) or raise ScenarioError. Never mutates `raw`."""
    if not isinstance(raw, dict):
        raise ScenarioError("a scenario must be a JSON object.")
    if set(raw) - _TOP_KEYS:
        raise ScenarioError(f"unknown key(s) {sorted(set(raw) - _TOP_KEYS)}; allowed: {sorted(_TOP_KEYS)}.")
    if raw.get("schema") != SCHEMA:
        raise ScenarioError(f"'schema' must be {SCHEMA}, got {raw.get('schema')!r}.")
    settings = _validate_settings(raw.get("settings", {}))
    steps_raw = raw.get("steps", [])
    expect_raw = raw.get("expect", [])
    if not isinstance(steps_raw, list) or not isinstance(expect_raw, list):
        raise ScenarioError("'steps' and 'expect' must be lists.")
    steps = [_validate_step(i, s) for i, s in enumerate(steps_raw)]
    expect: list[dict[str, object]] = []
    seen: set[str] = set()
    for i, item in enumerate(expect_raw):
        expectation = _validate_expect(i, item, seen)
        seen.add(str(expectation["id"]))
        expect.append(expectation)
    required = raw.get("pass_requires", sorted(seen))
    if not isinstance(required, list) or any(not isinstance(r, str) for r in required) or len(set(required)) != len(required):
        raise ScenarioError("'pass_requires' must be a list of distinct expectation ids.")
    unknown = [r for r in required if r not in seen]
    if unknown:
        raise ScenarioError(f"'pass_requires' names unknown expectation id(s): {unknown}.")
    return {"schema": SCHEMA, "settings": settings, "steps": steps, "expect": expect, "pass_requires": list(required)}


def load_scenario(path: Path | str) -> dict[str, object]:
    """Read and validate one scenario file; ScenarioError carries the file name."""
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ScenarioError(f"{path}: cannot read: {exc}") from exc
    except ValueError as exc:
        raise ScenarioError(f"{path}: not valid JSON: {exc}") from exc
    try:
        return validate_scenario(raw)
    except ScenarioError as exc:
        raise ScenarioError(f"{path}: {exc}") from exc


def scenario_path(working: Path | str) -> Path:
    return Path(working) / SCENARIO_FILE


def load_for_working(working: Path | str) -> dict[str, object] | None:
    """The working copy's scenario, or None when it has none."""
    path = scenario_path(working)
    return load_scenario(path) if path.is_file() else None


# ---- staging: edits go to the rig copy only ----------------------------------------------------------------------

def stage_settings(scenario: dict[str, object], rig_copy: Path | str, working: Path | str) -> list[dict[str, object]]:
    """Apply `settings` to files of the staged rig copy. Refuses a rig copy that is (or is inside) the working copy, a target that
    escapes the rig copy, and a target file that does not exist there (a scenario edits settings, it does not create files).
    Each file is read leniently (RC8 settings may carry comments) and rewritten as strict JSON; only the named top-level keys change.
    Returns one record per file: path, keys, before/after values of the changed keys."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    rig_copy, working = Path(rig_copy).resolve(), Path(working).resolve()
    if rig_copy == working or working in rig_copy.parents or rig_copy in working.parents:
        raise ScenarioError(f"refusing to stage settings: {rig_copy} is the working copy or overlaps it ({working}).")
    staged = []
    for relative, edits in scenario["settings"].items():  # type: ignore[union-attr]
        target = (rig_copy / relative).resolve()
        if rig_copy not in target.parents:
            raise ScenarioError(f"settings path {relative!r} escapes the rig copy {rig_copy}.")
        if not target.is_file():
            raise ScenarioError(f"settings file {relative!r} is not in the rig copy {rig_copy}; a scenario edits existing files only.")
        data = _load_lenient_json_file(target)
        if not isinstance(data, dict):
            raise ScenarioError(f"settings file {relative!r} is not a JSON object.")
        updated = {**data, **edits}
        atomic_write_text(target, json.dumps(updated, indent=2, ensure_ascii=False) + "\n")
        staged.append({"path": relative, "keys": sorted(edits), "before": {k: data.get(k) for k in edits}, "after": dict(edits)})
    return staged


def probe_config_keys(scenarios: list[dict[str, object]]) -> dict[str, object]:
    """The keys the Java ScenarioRunner reads from bf_probe_config: the steps of every scenario, in order, and the clock flag."""
    return {"scenario_steps": [step for s in scenarios for step in s["steps"]],  # type: ignore[union-attr]
            "scenario_clock": bool(scenarios)}


# ---- evaluation --------------------------------------------------------------------------------------------------

_CLOCK = re.compile(r"BF-PROBE\|[^|]*\|scenario\|[^|]*\|clock\|day=(?P<day>\d+)")
_MILLIS = re.compile(r"^\s*(?P<ms>\d+)\s")
PASS, FAIL, NOT_OBSERVED = "PASS", "FAIL", "NOT_OBSERVED"


def _timeline(lines: list[str]) -> tuple[list[tuple[int, int | None, int | None]], int | None, bool, int | None]:
    """(index, in-scenario day, ms since scenario start) per line after the scenario's first clock line; the start index;
    whether the clock was seen; the last clock day."""
    start_index, start_ms, day, last_day = None, None, 0, None
    rows: list[tuple[int, int | None, int | None]] = []
    for index, line in enumerate(lines):
        clock = _CLOCK.search(line)
        ms_match = _MILLIS.match(line)
        ms = int(ms_match["ms"]) if ms_match else None
        if clock:
            day = int(clock["day"])
            last_day = day
            if start_index is None:
                start_index, start_ms = index, ms
        if start_index is None:
            continue
        rows.append((index, day, (ms - start_ms) if ms is not None and start_ms is not None else None))
    return rows, start_index, start_index is not None, last_day


def evaluate_expectations(log_text: str, scenario: dict[str, object]) -> dict[str, object]:
    """Judge each expectation against the game log. Statuses: PASS (count_min matching lines inside the window, after any `after`
    expectation's satisfying line), FAIL (the window is over, or only late lines matched), NOT_OBSERVED (the log ended before the
    deadline, or the scenario clock never appeared so no window can be measured). Only lines after the probe's first scenario clock
    line count. Returns the `scenario` block: per-expectation results, the required ids and a verdict PASS/FAIL/INCOMPLETE."""
    lines = log_text.splitlines()
    rows, _start, clock_seen, last_day = _timeline(lines)
    last_ms = next((ms for _i, _d, ms in reversed(rows) if ms is not None), None)
    results: dict[str, dict[str, object]] = {}
    satisfied_at: dict[str, int] = {}
    for expectation in scenario["expect"]:  # type: ignore[union-attr]
        ident = str(expectation["id"])
        regex = re.compile(str(expectation["line"]))
        by_days = "within_days" in expectation
        limit = float(expectation["within_days" if by_days else "within_seconds"])
        result: dict[str, object] = {"status": NOT_OBSERVED, "line": expectation["line"], "count_min": expectation["count_min"],
                                     ("within_days" if by_days else "within_seconds"): limit, "matched": 0, "evidence": None}
        results[ident] = result
        after = expectation.get("after")
        if after is not None:
            result["after"] = after
        if not clock_seen:
            result["reason"] = "no scenario clock line in the log (probe without ScenarioRunner, or the scenario was not staged)"
            continue
        floor = -1
        if after is not None:
            if after not in satisfied_at:
                result["reason"] = f"'after' expectation {after!r} was not satisfied"
                continue
            floor = satisfied_at[str(after)]
        inside, late = [], []
        for index, day, ms in rows:
            if index <= floor or not regex.search(lines[index]):
                continue
            moment = day if by_days else (ms / 1000 if ms is not None else None)
            if moment is None:
                continue
            (inside if moment <= limit else late).append(index)
        result["matched"] = len(inside)
        if len(inside) >= int(expectation["count_min"]):
            hit = inside[int(expectation["count_min"]) - 1]
            satisfied_at[ident] = hit
            result.update(status=PASS, evidence=lines[hit].strip()[:300])
            continue
        reached = (last_day is not None and last_day > limit) if by_days else (last_ms is not None and last_ms > limit * 1000)
        if reached or late:
            result.update(status=FAIL, reason=("deadline passed" if reached else "only late matches"),
                          evidence=lines[late[0]].strip()[:300] if late else None)
        else:
            result["reason"] = "the log ended before the deadline"
    required = list(scenario["pass_requires"])  # type: ignore[arg-type]
    bad = [r for r in required if results[r]["status"] == FAIL]
    open_ = [r for r in required if results[r]["status"] == NOT_OBSERVED]
    verdict = FAIL if bad else ("INCOMPLETE" if open_ else PASS)
    return {"verdict": verdict, "required": required, "failed": bad, "not_observed": open_, "expectations": results,
            "clock_seen": clock_seen, "last_clock_day": last_day}


def apply_to_verdicts(members: dict[str, dict], blocks: dict[str, dict[str, object]]) -> None:
    """Fold scenario verdicts into group_report's per-member verdicts (mutates the report's own dicts, which are fresh per call):
    a failed required expectation makes the member FAIL; a required one still NOT_OBSERVED makes a PASS member INCOMPLETE."""
    for mod_id, block in blocks.items():
        member = members.get(mod_id)
        if member is None or not block.get("required"):
            continue
        if block["verdict"] == FAIL:
            member.setdefault("failures", []).append("scenario|" + ",".join(block["failed"]) + "|required expectation failed")  # type: ignore[arg-type]
            member["verdict"] = "FAIL"
        elif block["verdict"] == "INCOMPLETE" and member.get("verdict") == "PASS":
            member["verdict"] = "INCOMPLETE"
