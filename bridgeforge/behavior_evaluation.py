"""Judging a mod's behaviour against evidence (split from behavior_discovery.py, ROADMAP-3 96.5 A6).

behavior_discovery builds the static picture (archaeology, the behaviour model). This module works from it: probe and
save baselines, synthesized tests, expected changes, behaviour diffs, release evaluation, decisions and coverage.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from bridgeforge.save.save_inspect import inspect_save
from bridgeforge.scan.scanner import _load_lenient_json_file

from .safeio import atomic_write_text
from .behavior_discovery import SCHEMA_VERSION, DiscoveryError, _load_object, _resolved_directory, _stable_id, _write_json


def _normalized_observations(payload: object) -> list[dict[str, object]]:
    raw = payload.get("observations") if isinstance(payload, dict) else payload
    if not isinstance(raw, list):
        raise DiscoveryError("observation input must be a list or an object with an observations list")
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DiscoveryError(f"observation {index} must be an object")
        observation, subject = item.get("observation"), item.get("subject")
        if not isinstance(observation, str) or not observation or not isinstance(subject, str) or not subject:
            raise DiscoveryError(f"observation {index} requires non-empty observation and subject")
        fields = item.get("fields")
        if fields is None and "field" in item and "value" in item:
            fields = {str(item["field"]): item["value"]}
        if not isinstance(fields, dict) or not fields:
            raise DiscoveryError(f"observation {index} requires fields or field/value")
        normalized.append({
            "behavior_id": str(item["behavior_id"]) if item.get("behavior_id") else None,
            "observation": observation,
            "subject": subject,
            "fields": {str(key): fields[key] for key in sorted(fields, key=str)},
            "source": str(item.get("source", "captured")),
        })
    return sorted(normalized, key=lambda item: (str(item.get("behavior_id") or ""), str(item["observation"]), str(item["subject"]), json.dumps(item["fields"], sort_keys=True)))


def build_probe_baseline(observation_input: Path, *, build: str, scenario: str, reference_kind: str = "build") -> dict[str, object]:
    if not build.strip() or not scenario.strip():
        raise DiscoveryError("build and scenario must be non-empty")
    path = observation_input.expanduser().resolve()
    if not path.is_file():
        raise DiscoveryError(f"observation input does not exist: {path}")
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8-sig"))
    observations = _normalized_observations(payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "NO_VERDICT_BASELINE",
        "reference": {"kind": reference_kind, "id": build},
        "scenario": scenario,
        "input": {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()},
        "observations": observations,
        "observation_count": len(observations),
        "verdict": None,
    }


def write_probe_baseline(observation_input: Path, output: Path, *, build: str, scenario: str, reference_kind: str = "build") -> Path:
    result = build_probe_baseline(observation_input, build=build, scenario=scenario, reference_kind=reference_kind)
    path = output.expanduser().resolve()
    if path.exists() and path.is_dir():
        safe_build = re.sub(r"[^A-Za-z0-9._-]+", "-", build)
        safe_scenario = re.sub(r"[^A-Za-z0-9._-]+", "-", scenario)
        path = path / f"baseline-{safe_build}-{safe_scenario}.json"
    return _write_json(path, result)


def _save_made_with(save_dir: Path) -> dict | None:
    from bridgeforge.live.live_trust import save_made_with

    return save_made_with(save_dir)


def build_save_baseline(
    save: Path,
    *,
    build: str,
    scenario: str,
    track_classes: Iterable[str] = (),
    track_ids: Iterable[str] = (),
    mod_dir: Path | None = None,
) -> dict[str, object]:
    """Convert read-only historical-save evidence into the same no-verdict D2 contract."""
    if not build.strip() or not scenario.strip():
        raise DiscoveryError("build and scenario must be non-empty")
    inspected = inspect_save(
        save,
        track_classes=list(track_classes),
        track_ids=list(track_ids),
        mod_dir=mod_dir,
    )
    observations: list[dict[str, object]] = []
    for item in inspected["tracked_objects"]:
        observations.append({
            "behavior_id": None,
            "observation": "save.object",
            "subject": f"{item['class']}@{item['path']}",
            "fields": item["fields"],
            "source": "save-inspect",
        })
    # XStream writes each faction in full wherever it is first referenced (inside some fleet or
    # route), so a known list's path changes from save to save. List tag + owning faction is the
    # stable subject; the path (plus an occurrence number) is only a fallback for owner-less lists.
    # behavior-diff refuses duplicate subjects, and unstable ones read as missing/new behaviour.
    seen_subjects: Counter = Counter()
    for item in inspected["known_lists"]:
        subject = f"{item['tag']}[{item['owner']}]" if item.get("owner") else f"{item['tag']}@{item['path']}"
        seen_subjects[subject] += 1
        if seen_subjects[subject] > 1:
            subject += f"#{seen_subjects[subject]}"
        observations.append({
            "behavior_id": None,
            "observation": "save.known-list",
            "subject": subject,
            "fields": {"size": item["size"]},
            "source": "save-inspect-heuristic",
        })
    hits: dict[str, list[str]] = defaultdict(list)
    for item in inspected["tracked_id_hits"]:
        hits[str(item["id"])].append(str(item["path"]))
    for tracked_id, paths in sorted(hits.items()):
        observations.append({
            "behavior_id": None,
            "observation": "save.id",
            "subject": tracked_id,
            "fields": {"occurrences": len(paths), "paths": sorted(paths)},
            "source": "save-inspect",
        })
    counts = inspected.get("mod_object_counts")
    if isinstance(counts, dict):
        for namespace, count in sorted(counts.get("by_namespace", {}).items()):
            observations.append({
                "behavior_id": None,
                "observation": "save.mod-object-count",
                "subject": namespace,
                "fields": {"count": count},
                "source": "save-inspect",
            })
        observations.append({
            "behavior_id": None,
            "observation": "save.mod-object-count",
            "subject": "TOTAL",
            "fields": {"count": counts["total"]},
            "source": "save-inspect",
        })
    observations = _normalized_observations({"observations": observations})
    campaign = Path(str(inspected["save"]))
    raw = campaign.read_bytes()
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "NO_VERDICT_BASELINE",
        "reference": {"kind": "old-game-rig", "id": build},
        "scenario": scenario,
        "input": {"kind": "starsector-save", "path": str(campaign), "sha256": hashlib.sha256(raw).hexdigest()},
        # ROADMAP 36.5: the build and mods the save was made with, so a comparison can say it is not like-for-like.
        "made_with": _save_made_with(campaign.parent),
        "observations": observations,
        "observation_count": len(observations),
        "verdict": None,
    }


def write_save_baseline(save: Path, output: Path, **kwargs: Any) -> Path:
    result = build_save_baseline(save, **kwargs)
    return _write_json(Path(output).expanduser().resolve(), result)


def synthesize_tests(hypotheses_path: Path) -> dict[str, object]:
    payload = _load_object(hypotheses_path, "hypotheses")
    hypotheses = payload.get("hypotheses")
    if payload.get("schema_version") != SCHEMA_VERSION or not isinstance(hypotheses, list):
        raise DiscoveryError("hypotheses file has an unsupported schema or no hypotheses list")
    tests: list[dict[str, object]] = []
    for hypothesis in sorted(hypotheses, key=lambda item: str(item.get("id", ""))):
        hyp_id = str(hypothesis.get("id", ""))
        behavior_id = str(hypothesis.get("behavior_id", ""))
        for index, observation in enumerate(hypothesis.get("required_observations", []), start=1):
            tests.append({
                "id": _stable_id("TEST", hyp_id, index, observation),
                "hypothesis_id": hyp_id,
                "behavior_id": behavior_id,
                "kind": observation.get("kind", "observation") if isinstance(observation, dict) else "observation",
                "setup": "Reproduce the named scenario from an immutable build and capture the precondition.",
                "action": observation.get("when", "trigger behavior") if isinstance(observation, dict) else str(observation),
                "adversarial_variants": ["repeat the trigger", "save and reload between trigger and observation", "run with the declared compatibility set"],
                "acceptance": "The captured observation remains explainable and consistent with the approved behavior contract.",
                "stop_conditions": ["unexpected save mutation", "unattributed fatal error", "evidence input hash changed"],
                "status": "PROPOSED",
            })
    return {"schema_version": SCHEMA_VERSION, "source": str(hypotheses_path.expanduser().resolve()), "tests": tests}


def write_synthesized_tests(hypotheses_path: Path, output: Path) -> Path:
    return _write_json(output.expanduser().resolve(), synthesize_tests(hypotheses_path))


def _artifact_ids(paths: Iterable[Path]) -> set[str]:
    result: set[str] = set()
    for path in paths:
        payload = _load_object(path, "linked artifact")
        for key in ("risks", "hypotheses", "tests", "behaviors"):
            entries = payload.get(key)
            if isinstance(entries, list):
                result.update(str(item.get("id")) for item in entries if isinstance(item, dict) and item.get("id"))
    return result


def check_expected_changes(expected_path: Path, *, linked_artifacts: Iterable[Path] = (), known_builds: Iterable[str] = ()) -> dict[str, object]:
    path = expected_path.expanduser().resolve()
    payload = _load_lenient_json_file(path)
    if not isinstance(payload, dict):
        raise DiscoveryError("expected-changes file must contain a JSON object")
    errors: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append({"code": "unsupported-schema", "value": payload.get("schema_version")})
    changes = payload.get("changes")
    if not isinstance(changes, list):
        errors.append({"code": "changes-not-list"})
        changes = []
    linked_ids = _artifact_ids(linked_artifacts)
    build_set = set(map(str, known_builds))
    seen: set[str] = set()
    required = {"id", "build", "layer", "summary", "why", "match", "status"}
    for index, change in enumerate(changes):
        if not isinstance(change, dict):
            errors.append({"code": "change-not-object", "index": index})
            continue
        change_id = str(change.get("id", ""))
        missing = sorted(required - set(change))
        if missing:
            errors.append({"code": "missing-fields", "id": change_id, "fields": missing})
        if change_id in seen:
            errors.append({"code": "duplicate-id", "id": change_id})
        seen.add(change_id)
        if not re.fullmatch(r"EXP-[A-Za-z0-9]+-\d{3,}", change_id):
            errors.append({"code": "invalid-id", "id": change_id})
        if change.get("status") not in {"PROPOSED", "APPROVED", "RETIRED"}:
            errors.append({"code": "invalid-status", "id": change_id, "value": change.get("status")})
        elif change.get("status") == "APPROVED" and not all(change.get(key) for key in ("approved_by", "approved_on")):
            errors.append({"code": "approval-provenance-missing", "id": change_id})
        elif change.get("status") == "RETIRED" and not all(change.get(key) for key in ("retired_by", "retired_why")):
            errors.append({"code": "retirement-provenance-missing", "id": change_id})
        if change.get("layer") not in {"runtime", "save", "static"}:
            errors.append({"code": "invalid-layer", "id": change_id, "value": change.get("layer")})
        if build_set and str(change.get("build")) not in build_set:
            errors.append({"code": "unknown-build", "id": change_id, "build": change.get("build")})
        match = change.get("match")
        if not isinstance(match, dict) or match.get("change") not in {"from_to", "count", "added", "removed", "renamed", "any"}:
            errors.append({"code": "invalid-matcher", "id": change_id})
        elif match.get("change") == "any":
            warnings.append({"code": "broad-any-matcher", "id": change_id})
        links = change.get("links", {})
        if links and not isinstance(links, dict):
            errors.append({"code": "links-not-object", "id": change_id})
        elif isinstance(links, dict):
            if not any(links.get(kind) for kind in ("risk", "hyp", "test")):
                errors.append({"code": "missing-modernization-breadcrumb", "id": change_id})
            for kind in ("risk", "hyp", "test"):
                for linked in links.get(kind, []):
                    if linked_ids and str(linked) not in linked_ids:
                        errors.append({"code": "unknown-link", "id": change_id, "kind": kind, "target": linked})
    return {"schema_version": SCHEMA_VERSION, "file": str(path), "status": "PASS" if not errors else "FAIL", "change_count": len(changes), "errors": errors, "warnings": warnings, "changes": changes}


def _write_expected_decision(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        backup = path.with_suffix(path.suffix + ".before-last-edit")
        backup.write_bytes(path.read_bytes())
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")  # was a hand-made .tmp + replace (96.5 A6)


def add_expected_change(
    expected_path: Path,
    *,
    mod_id: str,
    change_id: str,
    build: str,
    layer: str,
    summary: str,
    why: str,
    match: dict[str, object],
    links: dict[str, list[str]] | None = None,
    proposed_by: str = "agent",
) -> dict[str, object]:
    if not re.fullmatch(r"EXP-[A-Za-z0-9]+-\d{3,}", change_id):
        raise DiscoveryError("expected-change id must match EXP-<MOD>-nnn")
    if layer not in {"runtime", "save", "static"}:
        raise DiscoveryError(f"invalid expected-change layer: {layer}")
    matcher_kind = match.get("change")
    if matcher_kind in {"from_to", "count"} and not {"from", "to"}.issubset(match):
        raise DiscoveryError(f"{matcher_kind} matcher requires --from and --to")
    if matcher_kind == "renamed" and not {"old", "new"}.issubset(match):
        raise DiscoveryError("renamed matcher requires --old and --new")
    if matcher_kind not in {"from_to", "count", "added", "removed", "renamed", "any"}:
        raise DiscoveryError(f"invalid expected-change matcher: {matcher_kind}")
    path = expected_path.expanduser().resolve()
    if path.exists():
        payload = _load_lenient_json_file(path)
        if not isinstance(payload, dict):
            raise DiscoveryError("expected-changes file must contain a JSON object")
    else:
        payload = {"schema_version": SCHEMA_VERSION, "mod_id": mod_id, "changes": []}
    if payload.get("mod_id") != mod_id:
        raise DiscoveryError(f"mod id mismatch: file has {payload.get('mod_id')!r}, command supplied {mod_id!r}")
    changes = payload.setdefault("changes", [])
    if not isinstance(changes, list):
        raise DiscoveryError("expected-changes changes must be a list")
    if any(isinstance(item, dict) and item.get("id") == change_id for item in changes):
        raise DiscoveryError(f"expected-change id already exists: {change_id}")
    entry = {"id": change_id, "build": build, "layer": layer, "summary": summary, "why": why, "links": links or {}, "match": match, "status": "PROPOSED", "proposed_by": proposed_by}
    changes.append(entry)
    changes.sort(key=lambda item: str(item.get("id", "")) if isinstance(item, dict) else "")
    _write_expected_decision(path, payload)
    return {"status": "UPDATED", "action": "add", "id": change_id, "file": str(path), "backup": str(path.with_suffix(path.suffix + ".before-last-edit")) if path.with_suffix(path.suffix + ".before-last-edit").exists() else None}


def update_expected_change_status(expected_path: Path, change_id: str, *, status: str, actor: str, on: str | None = None, why: str | None = None) -> dict[str, object]:
    if status not in {"APPROVED", "RETIRED"}:
        raise DiscoveryError(f"unsupported expected-change transition: {status}")
    path = expected_path.expanduser().resolve()
    payload = _load_lenient_json_file(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("changes"), list):
        raise DiscoveryError("expected-changes file must contain a changes list")
    matches = [item for item in payload["changes"] if isinstance(item, dict) and item.get("id") == change_id]
    if len(matches) != 1:
        raise DiscoveryError(f"expected exactly one entry for {change_id}; found {len(matches)}")
    entry = matches[0]
    if status == "APPROVED" and entry.get("status") != "PROPOSED":
        raise DiscoveryError(f"only a PROPOSED entry can be approved; {change_id} is {entry.get('status')}")
    if status == "APPROVED" and not on:
        raise DiscoveryError("approving an expected change requires an approval date")
    if status == "RETIRED" and not why:
        raise DiscoveryError("retiring an expected change requires --why")
    entry["status"] = status
    key = "approved" if status == "APPROVED" else "retired"
    entry[f"{key}_by"] = actor
    if on:
        entry[f"{key}_on"] = on
    if why:
        entry["retired_why"] = why
    _write_expected_decision(path, payload)
    return {"status": "UPDATED", "action": key, "id": change_id, "file": str(path), "backup": str(path.with_suffix(path.suffix + ".before-last-edit"))}


def _flat_observations(baseline: dict[str, object]) -> dict[tuple[str, str, str, str], object]:
    result: dict[tuple[str, str, str, str], object] = {}
    for item in baseline.get("observations", []):
        if not isinstance(item, dict) or not isinstance(item.get("fields"), dict):
            continue
        for field, value in item["fields"].items():
            key = (str(item.get("behavior_id") or ""), str(item.get("observation")), str(item.get("subject")), str(field))
            if key in result:
                raise DiscoveryError(f"duplicate observation field: {key}")
            result[key] = value
    return result


def _value_matches(pattern: object, value: object) -> bool:
    if pattern == "*":
        return True
    if isinstance(pattern, str):
        if re.fullmatch(r">-?\d+(?:\.\d+)?", pattern):
            return isinstance(value, (int, float)) and value > float(pattern[1:])
        if re.fullmatch(r"<-?\d+(?:\.\d+)?", pattern):
            return isinstance(value, (int, float)) and value < float(pattern[1:])
        range_match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\.\.(-?\d+(?:\.\d+)?)", pattern)
        if range_match:
            return isinstance(value, (int, float)) and float(range_match.group(1)) <= value <= float(range_match.group(2))
    return pattern == value


def _glob_matches(pattern: object, value: str) -> bool:
    regex = "^" + re.escape(str(pattern)).replace(r"\*", ".*") + "$"
    return bool(re.match(regex, value))


def _change_matches(change: dict[str, object], delta: dict[str, object]) -> bool:
    match = change.get("match")
    if not isinstance(match, dict):
        return False
    if change.get("layer") and change.get("layer") != delta.get("layer"):
        return False
    if delta.get("before") == delta.get("after"):
        return False
    for field in ("observation", "subject", "field"):
        if field in match and not _glob_matches(match[field], str(delta.get(field, ""))):
            return False
    kind = match.get("change")
    before, after = delta.get("before"), delta.get("after")
    if kind in {"from_to", "count"}:
        return _value_matches(match.get("from", "*"), before) and _value_matches(match.get("to", "*"), after)
    if kind == "added":
        return before is None and after is not None
    if kind == "removed":
        return before is not None and after is None
    if kind == "renamed":
        return before == match.get("old") and after == match.get("new")
    return kind == "any"


def _flat_static_map(payload: dict[str, object]) -> dict[tuple[str, str, str], object]:
    result: dict[tuple[str, str, str], object] = {}
    for node in payload.get("nodes", []):
        if isinstance(node, dict) and node.get("kind") in {"class", "data", "resource"}:
            subject = str(node.get("name") or node.get("path") or node.get("id"))
            result[(f"static.{node['kind']}", subject, "present")] = True
    lifecycle = payload.get("lifecycle", {})
    if isinstance(lifecycle, dict):
        for hook in lifecycle.get("hooks", []):
            if isinstance(hook, dict):
                result[("static.lifecycle", str(hook.get("class")), str(hook.get("hook")))] = True
        for registration in lifecycle.get("registrations", []):
            if isinstance(registration, dict):
                result[("static.registration", str(registration.get("owner")), f"{registration.get('call')}:{registration.get('target')}")] = True
    for field in payload.get("persistent_state", []):
        if isinstance(field, dict):
            result[("static.persistent-field", str(field.get("class")), str(field.get("field")))] = field.get("status")
    return result


def behavior_diff(before_path: Path, after_path: Path, *, expected_path: Path | None = None, before_map_path: Path | None = None, after_map_path: Path | None = None) -> dict[str, object]:
    before = _load_object(before_path, "before baseline")
    after = _load_object(after_path, "after baseline")
    for label, payload in (("before", before), ("after", after)):
        if payload.get("schema_version") != SCHEMA_VERSION or payload.get("mode") != "NO_VERDICT_BASELINE":
            raise DiscoveryError(f"{label} baseline has an unsupported schema or mode")
    before_flat, after_flat = _flat_observations(before), _flat_observations(after)
    expected = check_expected_changes(expected_path)["changes"] if expected_path else []
    deltas: list[dict[str, object]] = []
    matched_expected: set[str] = set()
    for key in sorted(set(before_flat) | set(after_flat)):
        behavior_id, observation, subject, field = key
        old, new = before_flat.get(key), after_flat.get(key)
        delta = {"layer": "runtime", "behavior_id": behavior_id or None, "observation": observation, "subject": subject, "field": field, "before": old, "after": new}
        if key in before_flat and key in after_flat and old == new:
            category = "UNCHANGED"
        elif key not in before_flat:
            category = "NEW_BEHAVIOR"
        elif key not in after_flat:
            category = "MISSING_OBSERVATION"
        else:
            category = "UNEXPLAINED_CHANGE"
        matches = [item for item in expected if isinstance(item, dict) and item.get("status") != "RETIRED" and _change_matches(item, delta)]
        approved = [item for item in matches if item.get("status") == "APPROVED"]
        proposed = [item for item in matches if item.get("status") == "PROPOSED"]
        if approved:
            category = "EXPECTED_CHANGE"
            matched_expected.update(str(item["id"]) for item in approved)
        elif proposed:
            category = "PENDING_APPROVAL"
            matched_expected.update(str(item["id"]) for item in proposed)
        delta["category"] = category
        delta["expected_change_ids"] = [str(item["id"]) for item in approved + proposed]
        deltas.append(delta)
    if (before_map_path is None) != (after_map_path is None):
        raise DiscoveryError("static map diff requires both before_map_path and after_map_path")
    if before_map_path is not None and after_map_path is not None:
        before_map_payload = _load_object(before_map_path, "before architecture map")
        after_map_payload = _load_object(after_map_path, "after architecture map")
        if before_map_payload.get("schema_version") != SCHEMA_VERSION or after_map_payload.get("schema_version") != SCHEMA_VERSION:
            raise DiscoveryError("architecture map has an unsupported schema_version")
        before_map = _flat_static_map(before_map_payload)
        after_map = _flat_static_map(after_map_payload)
        for key in sorted(set(before_map) | set(after_map)):
            observation, subject, field = key
            old, new = before_map.get(key), after_map.get(key)
            delta = {"layer": "static", "behavior_id": None, "observation": observation, "subject": subject, "field": field, "before": old, "after": new}
            if key in before_map and key in after_map and old == new:
                category = "UNCHANGED"
            elif key not in before_map:
                category = "NEW_BEHAVIOR"
            elif key not in after_map:
                category = "MISSING_OBSERVATION"
            else:
                category = "UNEXPLAINED_CHANGE"
            matches = [item for item in expected if isinstance(item, dict) and item.get("status") != "RETIRED" and _change_matches(item, delta)]
            approved = [item for item in matches if item.get("status") == "APPROVED"]
            proposed = [item for item in matches if item.get("status") == "PROPOSED"]
            if approved:
                category = "EXPECTED_CHANGE"
                matched_expected.update(str(item["id"]) for item in approved)
            elif proposed:
                category = "PENDING_APPROVAL"
                matched_expected.update(str(item["id"]) for item in proposed)
            delta["category"] = category
            delta["expected_change_ids"] = [str(item["id"]) for item in approved + proposed]
            deltas.append(delta)
    for change in expected:
        if isinstance(change, dict) and change.get("status") == "APPROVED" and str(change.get("id")) not in matched_expected:
            match = change.get("match", {})
            deltas.append({"layer": change.get("layer"), "behavior_id": None, "observation": match.get("observation"), "subject": match.get("subject"), "field": match.get("field"), "before": None, "after": None, "category": "EXPECTED_BUT_ABSENT", "expected_change_ids": [str(change["id"])]})
    deltas.sort(key=lambda item: (str(item.get("layer")), str(item.get("behavior_id") or ""), str(item.get("observation")), str(item.get("subject")), str(item.get("field")), str(item.get("category"))))
    counts = Counter(str(item["category"]) for item in deltas)
    blocking = sum(counts[name] for name in ("UNEXPLAINED_CHANGE", "PENDING_APPROVAL", "EXPECTED_BUT_ABSENT", "MISSING_OBSERVATION", "NEW_BEHAVIOR"))
    return {"schema_version": SCHEMA_VERSION, "before": str(before_path.expanduser().resolve()), "after": str(after_path.expanduser().resolve()), "before_map": str(before_map_path.expanduser().resolve()) if before_map_path else None, "after_map": str(after_map_path.expanduser().resolve()) if after_map_path else None, "expected_changes": str(expected_path.expanduser().resolve()) if expected_path else None, "status": "PASS" if blocking == 0 else "REVIEW_REQUIRED", "counts": dict(sorted(counts.items())), "blocking_count": blocking, "deltas": deltas}


def evaluate_behavior_release(diff_path: Path, *, risks_path: Path | None = None, unknowns_path: Path | None = None) -> dict[str, object]:
    diff = _load_object(diff_path, "behavior diff")
    if diff.get("schema_version") != SCHEMA_VERSION:
        raise DiscoveryError("behavior diff has an unsupported schema_version")
    blocking_reasons = []
    if diff.get("status") != "PASS":
        blocking_reasons.append("behavior-diff-has-unresolved-deltas")
    high_open: list[str] = []
    if risks_path:
        risk_payload = _load_object(risks_path, "risks")
        if risk_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(risk_payload.get("risks"), list):
            raise DiscoveryError("risks file has an unsupported schema or no risks list")
        risks = risk_payload["risks"]
        high_open = [str(item.get("id")) for item in risks if isinstance(item, dict) and item.get("level") == "HIGH" and item.get("status") in {"OPEN", "UNKNOWN", "PRESERVE UNTIL EXPLAINED"}]
    preserved_unknowns: list[str] = []
    if unknowns_path:
        unknown_payload = _load_object(unknowns_path, "unknowns")
        if unknown_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(unknown_payload.get("unknowns"), list):
            raise DiscoveryError("unknowns file has an unsupported schema or no unknowns list")
        unknowns = unknown_payload["unknowns"]
        preserved_unknowns = [str(item.get("id")) for item in unknowns if isinstance(item, dict) and item.get("status") in {"UNKNOWN", "PRESERVE UNTIL EXPLAINED"}]
    if high_open:
        blocking_reasons.append("high-risk-behavior-remains-open")
    if preserved_unknowns:
        blocking_reasons.append("unknown-behavior-lacks-written-decision")
    return {"schema_version": SCHEMA_VERSION, "status": "PASS" if not blocking_reasons else "FAIL", "blocking_reasons": blocking_reasons, "high_risks_open": high_open, "unknowns_open": preserved_unknowns, "diff_status": diff.get("status")}


DECIDED_UNKNOWN_STATUSES = frozenset({"EXPLAINED", "LIKELY INTENTIONAL", "LIKELY DEFECT"})


DECIDED_RISK_STATUSES = frozenset({"MITIGATED", "ACCEPTED", "EXPLAINED"})


_DECISION_SELECTORS = frozenset({"ids", "lifecycle", "subsystem", "entry_point_prefix"})


def _decision_selects(select: dict, item: dict, behavior: dict) -> bool:
    ids = set(select.get("ids") or [])
    if "ids" in select and item.get("id") not in ids and item.get("behavior_id") not in ids:
        return False
    if "lifecycle" in select and behavior.get("lifecycle") != select["lifecycle"]:
        return False
    if "subsystem" in select and behavior.get("subsystem") != select["subsystem"]:
        return False
    if "entry_point_prefix" in select and not str(behavior.get("entry_point", "")).startswith(str(select["entry_point_prefix"])):
        return False
    return True


def apply_behavior_decisions(discovery_dir: Path, decisions_path: Path) -> dict[str, object]:
    """Apply written decisions to a D1 model's risks and unknowns, leaving the generated files untouched.

    Each decision selects items (by risk/unknown/behavior id, lifecycle, subsystem or entry-point
    prefix) and must carry a status, why, by and on (YYYY-MM-DD). A decision that selects nothing is
    refused as stale, so regenerated maps can't silently drop a decision.
    """
    base = _resolved_directory(discovery_dir, "discovery directory")
    behavior = _load_object(base / "behavior.json", "behavior map")
    risks = _load_object(base / "risks.json", "risks")
    unknowns = _load_object(base / "unknowns.json", "unknowns")
    decisions_file = Path(decisions_path).expanduser().resolve()
    decisions = _load_object(decisions_file, "decisions")
    if decisions.get("schema_version") != SCHEMA_VERSION or not isinstance(decisions.get("decisions"), list):
        raise DiscoveryError("decisions file needs schema_version 1 and a decisions list")
    by_behavior = {b["id"]: b for b in behavior.get("behaviors", []) if isinstance(b, dict)}
    items = {"risks": risks.get("risks", []), "unknowns": unknowns.get("unknowns", [])}
    applied: Counter = Counter()
    for index, decision in enumerate(decisions["decisions"], start=1):
        where = f"decision {index}"
        for field in ("status", "why", "by", "on"):
            if not str(decision.get(field) or "").strip():
                raise DiscoveryError(f"{where}: missing {field}")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(decision["on"])):
            raise DiscoveryError(f"{where}: 'on' must be YYYY-MM-DD")
        select = decision.get("select") or {}
        if not select or set(select) - _DECISION_SELECTORS:
            raise DiscoveryError(f"{where}: select needs only keys from {sorted(_DECISION_SELECTORS)}")
        matched = 0
        for kind in decision.get("applies_to") or ["unknowns", "risks"]:
            if kind not in items:
                raise DiscoveryError(f"{where}: applies_to must be unknowns and/or risks")
            allowed = DECIDED_UNKNOWN_STATUSES if kind == "unknowns" else DECIDED_RISK_STATUSES
            if decision["status"] not in allowed:
                raise DiscoveryError(f"{where}: status {decision['status']!r} is not valid for {kind} ({sorted(allowed)})")
            for item in items[kind]:
                if isinstance(item, dict) and _decision_selects(select, item, by_behavior.get(item.get("behavior_id"), {})):
                    item["status"] = decision["status"]
                    item["decision"] = {
                        "why": decision["why"],
                        "evidence": list(decision.get("evidence") or []),
                        "by": decision["by"],
                        "on": decision["on"],
                        "source": f"{decisions_file.name}#{index}",
                    }
                    matched += 1
                    applied[kind] += 1
        if not matched:
            raise DiscoveryError(f"{where}: selects nothing (stale after regenerating the maps?)")
    open_unknowns = [u["id"] for u in items["unknowns"] if isinstance(u, dict) and u.get("status") not in DECIDED_UNKNOWN_STATUSES]
    open_high = [r["id"] for r in items["risks"] if isinstance(r, dict) and r.get("level") == "HIGH" and r.get("status") in {"OPEN", "UNKNOWN", "PRESERVE UNTIL EXPLAINED"}]
    return {
        "risks": risks,
        "unknowns": unknowns,
        "summary": {"decisions": len(decisions["decisions"]), "applied": dict(applied), "unknowns_open": open_unknowns, "high_risks_open": open_high},
    }


def write_behavior_decisions(discovery_dir: Path, decisions_path: Path, output: Path | None = None) -> dict[str, object]:
    """Write risks.decided.json / unknowns.decided.json for the release gate."""
    result = apply_behavior_decisions(discovery_dir, decisions_path)
    out = Path(output or discovery_dir).expanduser().resolve()
    risks_path = _write_json(out / "risks.decided.json", result["risks"])
    unknowns_path = _write_json(out / "unknowns.decided.json", result["unknowns"])
    return {"schema_version": SCHEMA_VERSION, "risks": str(risks_path), "unknowns": str(unknowns_path), **result["summary"]}


def build_coverage(behavior_path: Path, *, baselines: Iterable[Path] = (), diff_path: Path | None = None, tests_path: Path | None = None, unknowns_path: Path | None = None) -> dict[str, object]:
    behavior_payload = _load_object(behavior_path, "behavior map")
    if behavior_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(behavior_payload.get("behaviors"), list):
        raise DiscoveryError("behavior map has an unsupported schema or no behaviors list")
    behaviors = behavior_payload["behaviors"]
    runtime_ids: set[str] = set()
    save_ids: set[str] = set()
    compat_ids: set[str] = set()
    for path in baselines:
        baseline = _load_object(path, "baseline")
        if baseline.get("schema_version") != SCHEMA_VERSION or baseline.get("mode") != "NO_VERDICT_BASELINE":
            raise DiscoveryError("baseline has an unsupported schema or mode")
        scenario = str(baseline.get("scenario", "")).lower()
        for item in baseline.get("observations", []):
            if isinstance(item, dict) and item.get("behavior_id"):
                behavior_id = str(item["behavior_id"])
                runtime_ids.add(behavior_id)
                if "save" in scenario or "load" in scenario:
                    save_ids.add(behavior_id)
                if "compat" in scenario:
                    compat_ids.add(behavior_id)
    diff_ids: set[str] = set()
    if diff_path:
        diff = _load_object(diff_path, "behavior diff")
        if diff.get("schema_version") != SCHEMA_VERSION:
            raise DiscoveryError("behavior diff has an unsupported schema_version")
        diff_ids = {str(item["behavior_id"]) for item in diff.get("deltas", []) if isinstance(item, dict) and item.get("behavior_id") and item.get("category") in {"UNCHANGED", "EXPECTED_CHANGE"}}
    tested_ids: set[str] = set()
    if tests_path:
        test_payload = _load_object(tests_path, "tests")
        if test_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(test_payload.get("tests"), list):
            raise DiscoveryError("tests file has an unsupported schema or no tests list")
        tests = test_payload["tests"]
        tested_ids = {str(item["behavior_id"]) for item in tests if isinstance(item, dict) and item.get("behavior_id") and item.get("status") in {"PASS", "COVERED"}}
    rows = []
    for behavior in sorted((item for item in behaviors if isinstance(item, dict)), key=lambda item: str(item.get("id", ""))):
        behavior_id = str(behavior.get("id"))
        runtime = behavior_id in runtime_ids
        differential = behavior_id in diff_ids
        save_load = behavior_id in save_ids
        compat = behavior_id in compat_ids
        human = behavior_id in tested_ids
        covered = runtime and differential and (not behavior.get("persistent_state") or save_load) and (not behavior.get("other_mods") or compat)
        rows.append({"behavior_id": behavior_id, "static": True, "runtime": runtime, "differential": differential, "save_load": save_load, "compat": compat, "human": human, "status": "COVERED" if covered else "OPEN"})
    unknown_open = 0
    if unknowns_path:
        unknown_payload = _load_object(unknowns_path, "unknowns")
        if unknown_payload.get("schema_version") != SCHEMA_VERSION or not isinstance(unknown_payload.get("unknowns"), list):
            raise DiscoveryError("unknowns file has an unsupported schema or no unknowns list")
        unknowns = unknown_payload["unknowns"]
        unknown_open = sum(1 for item in unknowns if isinstance(item, dict) and item.get("status") not in {"EXPLAINED", "LIKELY INTENTIONAL", "LIKELY DEFECT"})
    counts = Counter(row["status"] for row in rows)
    need_runtime = sum(1 for row in rows if not row["runtime"])
    need_human = sum(1 for row in rows if row["runtime"] and not row["human"])
    residual = []
    for row in rows:
        if row["status"] == "COVERED":
            continue
        reasons = []
        if not row["runtime"]:
            reasons.append("runtime evidence missing or unresolved")
        elif not row["differential"]:
            reasons.append("D5 differential evidence missing or unresolved")
        if not row["save_load"]:
            reasons.append("save/load evidence not supplied")
        if not row["compat"]:
            reasons.append("compat-set evidence not supplied")
        if not row["human"]:
            reasons.append("human/adversarial test not recorded as passed")
        residual.append({"behavior_id": row["behavior_id"], "reasons": reasons, "action": "Run only the missing evidence rows; do not repeat covered checks."})
    return {"schema_version": SCHEMA_VERSION, "coverage": rows, "residual_human_tests": residual, "counts": {"known_behaviors": len(rows), "covered": counts["COVERED"], "open": counts["OPEN"], "need_runtime_evidence": need_runtime, "need_human_judgment": need_human, "unknowns_open": unknown_open}, "percentage": None, "status": "PASS" if counts["OPEN"] == 0 and unknown_open == 0 else "OPEN"}


def write_coverage(behavior_path: Path, output: Path, **kwargs: object) -> Path:
    return _write_json(output.expanduser().resolve(), build_coverage(behavior_path, **kwargs))
