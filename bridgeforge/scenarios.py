from __future__ import annotations

import json
import re
from pathlib import Path

from .log_triage import PROBE_LINE_RE
from .probe_config import build_probe_config

"""Roadmap P3b-K: named, versioned scenario fixtures (`docs/P3B_SAVE_TOOLING_RECOMMENDATIONS.md`).

A scenario bundles: which mods to enable (optionally plus a named compat set from `compat_sets.py`),
`probe-config --setup` specs to apply once in-game, an optional `save-snapshot` tag, and expected
results -- probe-log assertions (check/status/subject-pattern counts against `log-triage`'s own
BF-PROBE line grammar) plus optional save-inspect assertions.

`scenario_plan` is pure and read-only: it never writes into a rig, a save, or a mod directory. It
only computes what a human/CI run *would* do (the exact `probe-config` argv, the resolved mod list,
and a config preview built from the target mod's own inventory), so it is always safe to call against
a real rig. `scenario_check` is likewise read-only: it re-parses an already-produced log (and,
optionally, an already-produced save) and never launches anything.
"""

SCENARIOS_DIR = Path(__file__).with_name("scenarios")


class ScenarioError(ValueError):
    """Raised when a named scenario cannot be loaded, planned, or checked."""


def list_scenarios() -> list[str]:
    if not SCENARIOS_DIR.is_dir():
        return []
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.json"))


def load_scenario(name: str) -> dict[str, object]:
    path = SCENARIOS_DIR / f"{name}.json"
    if not path.is_file():
        raise ScenarioError(f"Unknown scenario {name!r}; known scenarios: {list_scenarios()}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ScenarioError(f"{path} is not a recognized scenario file (schema_version 1).")
    return data


def _resolve_mods(scenario: dict[str, object]) -> tuple[list[str], str | None]:
    """(sorted mod ids to enable, a note if the compat set couldn't be resolved)."""
    mods = set(scenario.get("mods", []) or [])
    mods |= set(scenario.get("extra_mods", []) or [])
    compat_set = scenario.get("compat_set")
    note: str | None = None
    if compat_set:
        from .compat_sets import CompatSetError, load_compat_sets, set_mod_ids  # local: only needed when a scenario actually uses a pack

        try:
            mods |= set(set_mod_ids(load_compat_sets(), compat_set))
        except CompatSetError as exc:
            note = f"compat set '{compat_set}' could not be resolved: {exc}"
    return sorted(mods), note


def scenario_plan(name: str, runtime_dir: Path, mod_dirs: dict[str, Path]) -> dict[str, object]:
    """Compute the dry-run plan for a named scenario: resolved mods, the probe-config command line
    that would apply its setups/tracking, a preview of the probe config the target mod's own
    inventory would produce, and its snapshot tag (if any).

    `mod_dirs` maps a mod id used by the scenario (its "subject_mod") to that mod's source directory
    on disk. Never writes anything; a missing mod_dirs entry for the subject just leaves the
    probe-config preview absent, with a note explaining why, rather than raising.
    """
    scenario = load_scenario(name)
    runtime_dir = Path(runtime_dir).expanduser().resolve()

    all_mods, compat_set_note = _resolve_mods(scenario)
    subject_mod_id = scenario.get("subject_mod")
    subject_dir = mod_dirs.get(subject_mod_id) if isinstance(subject_mod_id, str) else None

    track_entities = list(scenario.get("track_entities", []) or [])
    probe_setups = list(scenario.get("probe_setups", []) or [])

    argv: list[str] = ["probe-config"]
    if subject_dir is not None:
        argv.append(str(subject_dir))
    argv += ["--runtime", str(runtime_dir)]
    for entity in track_entities:
        argv += ["--track", entity]
    for setup in probe_setups:
        argv += ["--setup", setup]
    argv.append("--dry-run")

    config_preview: dict[str, object] | None = None
    config_preview_error: str | None = None
    if subject_dir is not None:
        try:
            config_preview = build_probe_config(subject_dir, track_entities=track_entities, setups=probe_setups)
        except Exception as exc:  # defensive: a plan must never crash on a malformed mod directory
            config_preview_error = str(exc)
    else:
        config_preview_error = (
            f"No mod_dirs entry for subject_mod {subject_mod_id!r}; pass its source directory to "
            "preview the actual probe-config payload."
        )

    return {
        "schema_version": 1,
        "mode": "SCENARIO_PLAN",
        "scenario": name,
        "subject_mod": subject_mod_id,
        "mods": all_mods,
        "compat_set": scenario.get("compat_set"),
        "compat_set_note": compat_set_note,
        "probe_setups": probe_setups,
        "track_entities": track_entities,
        "snapshot_tag": scenario.get("snapshot_tag"),
        "probe_config_argv": argv,
        "probe_config_preview": config_preview,
        "probe_config_preview_error": config_preview_error,
        "expect": scenario.get("expect", {}),
    }


# ---- checking a scenario's expectations against a produced log/save ------------------------------


def _read_probe_entries(log_path: Path) -> list[dict[str, str]]:
    """Every BF-PROBE|... payload found anywhere on a line of a starsector.log-shaped file.

    Deliberately re-derives entries straight from PROBE_LINE_RE rather than depending on
    log_triage.triage_log()'s summarized `probe` section, since that summary only keeps counts plus
    the FAIL/WARN subset -- scenario assertions need OK/INFO entries too (e.g. "submarket-stock OK for
    subject~avesta"). Tolerant of the log4j "millis [thread] LEVEL logger - " prefix by searching for
    "BF-PROBE|" rather than anchoring at column 0.
    """
    path = Path(log_path).expanduser().resolve()
    if not path.is_file():
        raise ScenarioError(f"{path} is not an existing log file.")
    entries: list[dict[str, str]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        idx = raw.find("BF-PROBE|")
        if idx < 0:
            continue
        match = PROBE_LINE_RE.match(raw[idx:])
        if not match:
            continue
        entries.append(
            {
                "version": match.group("version"),
                "check": match.group("check"),
                "status": match.group("status"),
                "subject": match.group("subject"),
                "detail": match.group("detail"),
            }
        )
    return entries


def _field_matches(pattern: str, value: str) -> bool:
    if pattern == "*":
        return True
    return re.search(pattern, value, re.IGNORECASE) is not None


def _evaluate_probe_assertion(assertion: dict[str, object], entries: list[dict[str, str]]) -> dict[str, object]:
    check_pattern = str(assertion.get("check", "*"))
    status_pattern = str(assertion.get("status", "*"))
    subject_pattern = str(assertion.get("subject_pattern", "*"))

    matches = [
        entry
        for entry in entries
        if _field_matches(check_pattern, entry["check"])
        and (status_pattern == "*" or entry["status"] == status_pattern)
        and _field_matches(subject_pattern, entry["subject"])
    ]
    count = len(matches)
    min_count = assertion.get("min_count")
    max_count = assertion.get("max_count")
    if min_count is None and max_count is None:
        min_count = 1

    reasons: list[str] = []
    if isinstance(min_count, (int, float)) and count < min_count:
        reasons.append(f"expected at least {min_count} matching probe entries, found {count}")
    if isinstance(max_count, (int, float)) and count > max_count:
        reasons.append(f"expected at most {max_count} matching probe entries, found {count}")

    return {
        "assertion": assertion,
        "matched_count": count,
        "status": "FAIL" if reasons else "PASS",
        "reasons": reasons,
        "sample": matches[:5],
    }


def _condition_holds(value: object, condition: object) -> bool:
    if isinstance(condition, dict):
        if "equals" in condition and value != condition["equals"]:
            return False
        if "min" in condition and (value is None or value < condition["min"]):
            return False
        if "max" in condition and (value is None or value > condition["max"]):
            return False
        return True
    return value == condition


def _evaluate_save_assertion(assertion: dict[str, object], inspection: dict[str, object]) -> dict[str, object]:
    """Best-effort evaluation of a {class, field, condition} assertion against save-inspect's output.

    save-inspect's exact return shape is owned by another in-flight roadmap slice
    (bridgeforge.save_inspect.inspect_save, P3b-A); this only assumes the inspection dict has a
    top-level section per class name, holding a {field: value} mapping. Anything that doesn't match
    that shape (a missing section/field, or an inspection dict shaped differently than expected) is
    reported as FAIL with a stated reason rather than raising, since the module this leans on may
    still be evolving.
    """
    try:
        class_name = assertion.get("class")
        field = assertion.get("field")
        condition = assertion.get("condition")
        bucket = inspection.get(class_name) if isinstance(inspection, dict) else None
        if not isinstance(bucket, dict):
            return {"assertion": assertion, "status": "FAIL", "reason": f"No '{class_name}' section in save-inspect output"}
        value = bucket.get(field)
        ok = _condition_holds(value, condition)
        return {"assertion": assertion, "status": "PASS" if ok else "FAIL", "value": value}
    except Exception as exc:  # defensive: an assertion evaluation must never crash scenario_check
        return {"assertion": assertion, "status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"}


def scenario_check(name: str, log_path: Path, save_path: Path | None = None) -> dict[str, object]:
    """Evaluate a named scenario's expected results against a produced probe log (and, optionally, a
    produced save). Read-only: never launches anything and never modifies the log or the save.
    """
    scenario = load_scenario(name)
    expect = scenario.get("expect", {}) if isinstance(scenario.get("expect"), dict) else {}

    entries = _read_probe_entries(Path(log_path))
    probe_results = [_evaluate_probe_assertion(assertion, entries) for assertion in expect.get("probe", []) or []]

    save_assertions = expect.get("save", []) or []
    save_results: list[dict[str, object]] = []
    save_note: str | None = None
    if save_assertions:
        try:
            from .save_inspect import inspect_save  # lazy: bridgeforge.save_inspect is owned/written by another in-flight agent
        except ImportError:
            save_note = "save assertions skipped: module unavailable"
        else:
            if save_path is None:
                save_note = "save assertions skipped: no save_path given"
            else:
                inspection = inspect_save(Path(save_path))
                save_results = [_evaluate_save_assertion(assertion, inspection) for assertion in save_assertions]

    all_results = probe_results + save_results
    overall = "PASS" if all(result["status"] == "PASS" for result in all_results) else "FAIL"

    return {
        "schema_version": 1,
        "mode": "SCENARIO_CHECK",
        "scenario": name,
        "log": str(Path(log_path)),
        "save": str(save_path) if save_path is not None else None,
        "probe_assertions": probe_results,
        "save_assertions": save_results,
        "save_note": save_note,
        "status": overall,
    }
