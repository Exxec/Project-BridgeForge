from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .baseline import load_baseline_keys, split_by_baseline
from .build_tag import DEFAULT_LABEL, BuildTagError, build_tag
from .copy_drift import _find_mod_root, compare_copies
from .fixers import SUPPORTED_FINDINGS
from .jar_audit import audit_jar
from .log_triage import triage_log
from .models import Finding, TargetProfile
from .scanner import (
    CAMPAIGN_SYSTEM_CREATION_PATTERN,
    FACTION_SPECIAL_ROLE_KEYS,
    _load_lenient_json_file,
    _read_csv_rows,
    _registered_csv_ids,
    _relative,
    _wing_ids_set,
    scan_mod,
)

DOSSIER_VERSION = 1
DEFAULT_MAX_KB = 40.0
DEFAULT_CONTEXT_LINES = 5
MAX_LIST_ITEMS = 50
MAX_LINE_CHARS = 200
MAX_EVIDENCE_ITEMS = 4
PROTECTED_OUTPUT_DIR_NAMES = {"in operation", "done"}

_CLASSIFICATION_RANK = {"MANUAL": 0, "REVIEW": 1, "UNKNOWN": 2, "SAFE": 3}
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_LINE_EVIDENCE_RE = re.compile(r"^line:(\d+)$")

# Findings that tell the reader to leave something unchanged, or that are purely informational,
# do not belong in open_questions -- they are not judgment calls for a triager to act on. Most of
# these are already excluded by the classification/severity rule below (SAFE or info-severity),
# but non-strict-json-trailing-comma is REVIEW/medium ("retain it unchanged") and needs an explicit
# id. Listed here anyway for documentation even where redundant with the general rule.
_OPEN_QUESTION_NOISE_IDS = {
    "non-strict-json-trailing-comma",
    "json-hash-comment",
    "json-slash-comment",
    "json-single-quoted-string",
    "json-unquoted-key",
    "json-bareword-value",
    "json-java-number-suffix",
}
# General rule: a SAFE-classified or info-severity finding is retain-as-is/informational by
# construction and is excluded from open_questions regardless of id.
_OPEN_QUESTION_NOISE_CLASSIFICATIONS = {"SAFE"}
_OPEN_QUESTION_NOISE_SEVERITIES = {"info"}
# When the same finding id appears in at least this many distinct files, collapse its
# open_questions lines into one summary line instead of one per file.
_OPEN_QUESTION_COLLAPSE_FILE_THRESHOLD = 3


class DossierError(ValueError):
    """Raised when a dossier cannot be built or its output would be unsafe to write."""


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def _current_build_tag(root: Path) -> dict[str, object] | None:
    """Read (never write) the current `[BF rN]` build tag by consulting build_tag's own bump logic.

    `build_tag()` never writes to disk; it always computes the *next* build number (current + 1
    when no --set is given). So the tag already on disk is simply one less than that, and "no tag
    yet" is the case where the computed build is 1 (i.e. current was 0).
    """
    try:
        computed = build_tag(root, label=DEFAULT_LABEL)
    except BuildTagError:
        return None
    build = computed.get("build")
    if not isinstance(build, int) or build <= 1:
        return None
    return {"label": DEFAULT_LABEL, "build": build - 1}


def _mod_info_sha256(mod_info_path: Path) -> str | None:
    if not mod_info_path.is_file():
        return None
    return hashlib.sha256(mod_info_path.read_bytes()).hexdigest()


def _build_identity(root: Path, metadata: dict[str, object]) -> dict[str, object]:
    mod_info_path = root / "mod_info.json"
    return {
        "mod_root": str(root),
        "id": metadata.get("id"),
        "name": metadata.get("name"),
        "version": metadata.get("version"),
        "build_tag": _current_build_tag(root),
        "game_version": metadata.get("gameVersion") or metadata.get("game_version"),
        "dependencies": metadata.get("dependencies") or [],
        "jars": metadata.get("jars") or [],
        "total_conversion": metadata.get("totalConversion") is True,
        "mod_info_sha256": _mod_info_sha256(mod_info_path),
    }


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


def _capped(ids: set[str] | list[str]) -> dict[str, object]:
    unique_sorted = sorted(set(ids))
    return {"count": len(unique_sorted), "ids": unique_sorted[:MAX_LIST_ITEMS]}


def _hull_inventory(root: Path) -> dict[str, object]:
    path = root / "data" / "hulls" / "ship_data.csv"
    entry = _capped(_registered_csv_ids(path) or set())
    with_modules = module_hint = fighter_hint = 0
    for row in _read_csv_rows(path) or []:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = (row.get("hints") or "").upper()
        if "SHIP_WITH_MODULES" in hints:
            with_modules += 1
        if "MODULE" in hints:
            module_hint += 1
        if "FIGHTER" in hints:
            fighter_hint += 1
    entry.update({"ship_with_modules_count": with_modules, "module_hint_count": module_hint, "fighter_hint_count": fighter_hint})
    return entry


def _faction_inventory(root: Path) -> dict[str, object]:
    faction_dir = root / "data" / "world" / "factions"
    entries: list[dict[str, object]] = []
    if faction_dir.is_dir():
        for path in sorted(faction_dir.glob("*.faction")):
            data = _load_lenient_json_file(path)
            if not isinstance(data, dict):
                continue
            faction_id = data.get("id")
            if not isinstance(faction_id, str) or not faction_id:
                continue
            ship_roles = data.get("shipRoles")
            role_variant_count = 0
            if isinstance(ship_roles, dict):
                for block in ship_roles.values():
                    if isinstance(block, dict):
                        role_variant_count += sum(1 for key in block if key not in FACTION_SPECIAL_ROLE_KEYS)

            def _known_count(key: str) -> int:
                value = data.get(key)
                return len(value) if isinstance(value, list) else 0

            entries.append(
                {
                    "id": faction_id,
                    "known_ships": _known_count("knownShips"),
                    "known_weapons": _known_count("knownWeapons"),
                    "known_fighters": _known_count("knownFighters"),
                    "ship_roles_variant_count": role_variant_count,
                }
            )
    entries.sort(key=lambda item: item["id"])
    result = _capped([entry["id"] for entry in entries])
    result["factions"] = entries[:MAX_LIST_ITEMS]
    return result


def _planet_star_inventory(root: Path) -> dict[str, object]:
    path = root / "data" / "config" / "planets.json"
    data = _load_lenient_json_file(path)
    planet_ids: list[str] = []
    star_ids: list[str] = []
    if isinstance(data, dict):
        for type_id, spec in data.items():
            if not isinstance(spec, dict) or not isinstance(type_id, str):
                continue
            (star_ids if spec.get("isStar") else planet_ids).append(type_id)
    return {"planet_types": _capped(planet_ids), "star_types": _capped(star_ids)}


def _star_systems_created(root: Path) -> dict[str, object]:
    """Source-level `createStarSystem("id")`/`addStarSystem("id")` literal hints.

    Bytecode-only mods (no shipped source) are not covered by this pass: correlating a
    compiled constant-pool string with a specific call site requires full method-body
    disassembly, which is out of scope here; source hints remain the strongest signal.
    """
    ids: set[str] = set()
    for source in sorted(root.rglob("*.java")):
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in CAMPAIGN_SYSTEM_CREATION_PATTERN.finditer(text):
            ids.add(match.group(1))
    return _capped(ids)


def _jar_class_inventory(compiled_class_names: set[str]) -> dict[str, object]:
    names = sorted(compiled_class_names)
    packages = {name.split(".", 1)[0] for name in names if "." in name}
    result = _capped(packages)
    result["class_count"] = len(names)
    result["top_level_packages"] = result.pop("ids")
    result["top_level_package_count"] = result.pop("count")
    return result


def _loose_script_count(root: Path) -> int:
    data_dir = root / "data"
    if not data_dir.is_dir():
        return 0
    return sum(1 for _ in data_dir.rglob("*.java"))


def _build_inventory(root: Path, compiled_class_names: set[str]) -> dict[str, object]:
    return {
        "hulls": _hull_inventory(root),
        "weapons": _capped(_registered_csv_ids(root / "data" / "weapons" / "weapon_data.csv") or set()),
        "wings": _capped(_wing_ids_set(root / "data" / "hulls" / "wing_data.csv")),
        "ship_systems": _capped(_registered_csv_ids(root / "data" / "shipsystems" / "ship_systems.csv") or set()),
        "hullmods": _capped(_registered_csv_ids(root / "data" / "hullmods" / "hull_mods.csv") or set()),
        "factions": _faction_inventory(root),
        "planet_star_types": _planet_star_inventory(root),
        "star_systems_created": _star_systems_created(root),
        "jars": _jar_class_inventory(compiled_class_names),
        "loose_script_count": _loose_script_count(root),
    }


# ---------------------------------------------------------------------------
# Findings -> entries (with context snippets), sorting, size-fitting, packing
# ---------------------------------------------------------------------------


def _extract_line(evidence: list[str]) -> int | None:
    for item in evidence:
        match = _LINE_EVIDENCE_RE.match(item)
        if match:
            return int(match.group(1))
    return None


def _extract_id_values(evidence: list[str]) -> list[str]:
    values = []
    for item in evidence:
        if ":" not in item or item.startswith("line:"):
            continue
        _key, _sep, value = item.partition(":")
        value = value.strip()
        if value:
            values.append(value)
    return values


def _truncate_line(text: str) -> str:
    return text if len(text) <= MAX_LINE_CHARS else text[:MAX_LINE_CHARS] + "…"


def _snippet_for_finding(root: Path, finding: Finding, line: int | None, context_lines: int) -> dict[str, object] | None:
    if not finding.file:
        return None
    path = root / finding.file
    if not path.is_file():
        return None
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if not raw_lines:
        return None
    if line is not None:
        start = max(1, line - context_lines)
        end = min(len(raw_lines), line + context_lines)
        lines = [{"line": n, "text": _truncate_line(raw_lines[n - 1])} for n in range(start, end + 1)]
        return {"start_line": start, "end_line": end, "matched_line": line, "match_kind": "line", "lines": lines}
    if path.suffix.lower() == ".csv":
        candidates = _extract_id_values(finding.evidence)
        for index, text in enumerate(raw_lines, start=1):
            if index == 1:
                continue  # header row
            if any(value and value in text for value in candidates):
                return {"start_line": index, "end_line": index, "matched_line": index, "match_kind": "csv-id", "lines": [{"line": index, "text": _truncate_line(text)}]}
    return None


def _build_finding_entries(root: Path, findings: list[Finding], context_lines: int) -> list[dict[str, object]]:
    entries = []
    for finding in findings:
        line = _extract_line(finding.evidence)
        entries.append(
            {
                "id": finding.id,
                "category": finding.category,
                "classification": finding.classification,
                "severity": finding.severity,
                "confidence": finding.confidence,
                "file": finding.file,
                "line": line,
                "explanation": finding.explanation,
                "evidence": list(finding.evidence[:MAX_EVIDENCE_ITEMS]),
                "fixer_available": finding.id in SUPPORTED_FINDINGS,
                "snippet": _snippet_for_finding(root, finding, line, context_lines),
            }
        )
    entries.sort(
        key=lambda e: (
            _CLASSIFICATION_RANK.get(e["classification"], 99),
            _SEVERITY_RANK.get(e["severity"], 99),
            e["file"] or "",
            e["line"] if e["line"] is not None else -1,
            e["id"],
        )
    )
    return entries


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _fit_entry(entry: dict[str, object], budget_bytes: int) -> dict[str, object]:
    """Shrink one finding entry in place until it fits `budget_bytes`, marking what was trimmed.

    Nothing is dropped outright: context lines are thinned (farthest from the flagged line first),
    then the remaining line's text, then evidence, then the explanation -- each a last resort after
    the previous one is exhausted. The original snippet span is preserved once trimming starts.
    """
    snippet = entry.get("snippet")
    original_start = snippet["start_line"] if snippet else None
    original_end = snippet["end_line"] if snippet else None
    trimmed = False
    guard = 0
    while len(_json_bytes(entry)) > budget_bytes and guard < 10_000:
        guard += 1
        if snippet and len(snippet["lines"]) > 1:
            anchor = snippet.get("matched_line", snippet["lines"][len(snippet["lines"]) // 2]["line"])
            drop_index = max(range(len(snippet["lines"])), key=lambda i: abs(snippet["lines"][i]["line"] - anchor))
            del snippet["lines"][drop_index]
            snippet["start_line"] = snippet["lines"][0]["line"]
            snippet["end_line"] = snippet["lines"][-1]["line"]
            trimmed = True
            continue
        if snippet and snippet["lines"] and len(snippet["lines"][0]["text"]) > 20:
            snippet["lines"][0]["text"] = snippet["lines"][0]["text"][:20] + "…"
            trimmed = True
            continue
        if len(entry["evidence"]) > 1:
            entry["evidence"] = entry["evidence"][:1]
            trimmed = True
            continue
        if len(entry["explanation"]) > 80:
            entry["explanation"] = entry["explanation"][:80] + "…"
            trimmed = True
            continue
        break
    if trimmed and snippet is not None:
        snippet["snippet_trimmed"] = True
        snippet["original_start_line"] = original_start
        snippet["original_end_line"] = original_end
    return entry


def _part_payload(mod_id: str | None, part_number: int, total_parts: int, entries: list[dict[str, object]]) -> dict[str, object]:
    return {"dossier_version": DOSSIER_VERSION, "mod_id": mod_id, "part": part_number, "total_parts": total_parts, "findings": entries}


def _pack_entries(mod_id: str | None, entries: list[dict[str, object]], max_kb: float) -> list[list[dict[str, object]]]:
    if not entries:
        return []
    max_bytes = int(max_kb * 1024)
    wrapper_bytes = len(_json_bytes(_part_payload(mod_id, 1, 1, [])))
    entry_budget = max(200, max_bytes - wrapper_bytes - 64)
    fitted = [_fit_entry(entry, entry_budget) for entry in entries]

    parts: list[list[dict[str, object]]] = []
    current: list[dict[str, object]] = []
    for entry in fitted:
        candidate = current + [entry]
        if current and len(_json_bytes(_part_payload(mod_id, 1, 1, candidate))) > max_bytes:
            parts.append(current)
            current = [entry]
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


# ---------------------------------------------------------------------------
# open_questions
# ---------------------------------------------------------------------------


def _short_explanation(explanation: object) -> str:
    short = str(explanation).strip().split(". ")[0]
    if len(short) > 160:
        short = short[:160] + "…"
    return short


def _is_open_question_noise(entry: dict[str, object]) -> bool:
    return (
        entry["id"] in _OPEN_QUESTION_NOISE_IDS
        or entry["classification"] in _OPEN_QUESTION_NOISE_CLASSIFICATIONS
        or entry["severity"] in _OPEN_QUESTION_NOISE_SEVERITIES
    )


def _open_questions(entries: list[dict[str, object]]) -> list[str]:
    """Build open_questions, collapsing an id repeated across many files into one summary line.

    Noise findings (see `_is_open_question_noise`) never appear here -- they stay in the parts.
    A finding id spread across >= `_OPEN_QUESTION_COLLAPSE_FILE_THRESHOLD` distinct files collapses
    to one line with a file count and a short "e.g." sample; otherwise each (id, file) gets its own
    line, same as before.
    """
    by_id: dict[str, list[dict[str, object]]] = {}
    id_order: list[str] = []
    for entry in entries:
        if entry["classification"] not in ("MANUAL", "REVIEW", "UNKNOWN") or entry["fixer_available"]:
            continue
        if _is_open_question_noise(entry):
            continue
        if entry["id"] not in by_id:
            by_id[entry["id"]] = []
            id_order.append(entry["id"])
        by_id[entry["id"]].append(entry)

    lines: list[str] = []
    for finding_id in id_order:
        group = by_id[finding_id]
        files_seen: list[str] = []
        for entry in group:
            if entry["file"] and entry["file"] not in files_seen:
                files_seen.append(entry["file"])

        if len(files_seen) >= _OPEN_QUESTION_COLLAPSE_FILE_THRESHOLD:
            short = _short_explanation(group[0]["explanation"])
            shown = files_seen[:3]
            remainder = len(files_seen) - len(shown)
            sample = ", ".join(shown)
            if remainder > 0:
                sample += f" +{remainder} more"
            lines.append(f"{finding_id} ×{len(files_seen)} files: {short} (e.g. {sample})")
            continue

        grouped: dict[str, dict[str, object]] = {}
        sub_order: list[str] = []
        for entry in group:
            key = entry["file"] or ""
            if key not in grouped:
                grouped[key] = {"file": entry["file"], "line": entry["line"], "explanation": entry["explanation"], "count": 0}
                sub_order.append(key)
            grouped[key]["count"] += 1
        for key in sub_order:
            item = grouped[key]
            location = f"{item['file']}:{item['line']}" if item["file"] and item["line"] is not None else (item["file"] or "unknown location")
            short = _short_explanation(item["explanation"])
            suffix = f" (x{item['count']})" if item["count"] > 1 else ""
            lines.append(f"{finding_id} at {location}: {short}{suffix}")
    return lines


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def _jar_audit_artifact(root: Path, jars: list[dict[str, object]], original_jar: Path | None) -> dict[str, object]:
    if original_jar is None:
        return {"not_supplied": True}
    original_path = Path(original_jar).expanduser().resolve()
    match = next((jar for jar in jars if Path(str(jar["path"])).name.lower() == original_path.name.lower()), None)
    if match is None and len(jars) == 1:
        match = jars[0]
    if match is None:
        return {"not_supplied": False, "error": f"No loaded mod jar matched '{original_path.name}' among {[jar['path'] for jar in jars]}."}
    try:
        result = audit_jar(root / str(match["path"]), original_path)
    except ValueError as exc:
        return {"not_supplied": False, "error": str(exc)}
    return {
        "not_supplied": False,
        "matched_jar": match["path"],
        "status": result["status"],
        "rebuilt_class_count": result["rebuilt_class_count"],
        "original_class_count": result["original_class_count"],
        "removed_class_count": len(result["removed_classes"]),
        "changed_class_count": result["changed_class_count"],
        "unchanged_class_count": result["unchanged_class_count"],
        "bundled_library_packages": [entry["package"] for entry in result["bundled_library_packages"]],
        "unexpected_new_packages": [entry["package"] for entry in result["unexpected_new_packages"]],
        "reflection_finding_count": len(result["reflection_findings"]),
        "reflection_classes": [entry["class"] for entry in result["reflection_findings"]][:10],
    }


def _copy_drift_artifact(root: Path, rig: Path | None) -> dict[str, object]:
    if rig is None:
        return {"not_supplied": True}
    try:
        result = compare_copies(root, rig)
    except ValueError as exc:
        return {"not_supplied": False, "error": str(exc)}
    return {
        "not_supplied": False,
        "status": result["status"],
        "drift_count": result["drift_count"],
        "missing_in_deployed": result["missing_in_deployed"][:MAX_LIST_ITEMS],
        "different": result["different"][:MAX_LIST_ITEMS],
        "extra_in_deployed": result["extra_in_deployed"][:MAX_LIST_ITEMS],
    }


def _runtime_footprint_artifact(root: Path, save: Path | None, vanilla_core: Path | None) -> dict[str, object]:
    """P3b-J: the mod's live footprint from a real rig save -- classes (save_compat, always
    available) plus objects/scripts/factions/markets (save_inspect, lazily imported since another
    agent may still be building it). Never raises; unavailability is reported, not silenced."""
    if save is None:
        return {"not_supplied": True}
    result: dict[str, object] = {"not_supplied": False}
    try:
        from .save_compat import check_save_compat

        compat = check_save_compat(save, root, vanilla_core=vanilla_core)
        result["classes"] = {
            "status": compat["status"],
            "referenced_class_count": compat["referenced"]["count"],
            "missing": compat["missing"],
            "ambiguous": compat["ambiguous"],
        }
    except Exception as exc:  # a save-tooling failure must never break the whole dossier
        result["classes"] = {"available": False, "reason": str(exc)}

    try:
        from . import save_inspect as _save_inspect  # lazy: another agent may still be building this
    except ImportError:
        result["objects"] = {"available": False, "reason": "bridgeforge.save_inspect is not available yet"}
    else:
        entry_fn = getattr(_save_inspect, "inspect_save", None) or getattr(_save_inspect, "inspect", None)
        if entry_fn is None:
            result["objects"] = {"available": False, "reason": "save_inspect has no inspect_save()/inspect() entry point"}
        else:
            call_attempts = (
                lambda: entry_fn(save, mod_dir=root, vanilla_core=vanilla_core),
                lambda: entry_fn(save, root),
                lambda: entry_fn(save),
            )
            last_error: Exception | None = None
            data = None
            succeeded = False
            for attempt in call_attempts:
                try:
                    data = attempt()
                    succeeded = True
                    break
                except TypeError as exc:
                    last_error = exc
                    continue
                except Exception as exc:  # a save_inspect bug must never break the whole dossier
                    result["objects"] = {"available": False, "reason": str(exc)}
                    succeeded = None
                    break
            if succeeded is True:
                result["objects"] = {"available": True, "data": data}
            elif succeeded is None:
                pass  # already set above
            else:
                result["objects"] = {"available": False, "reason": f"no known call form matched save_inspect's entry point ({last_error})"}
    return result


def _performance_artifact(perf: Path | None, log: Path | None, mod_prefixes: list[str] | None) -> dict[str, object]:
    """P6: an SPW `performance-report.json` summary plus log-spam counts. Lazy import of
    `spw_bridge` so a dossier build never fails when that module (or SPW's report) is absent."""
    if perf is None:
        return {"not_supplied": True}
    result: dict[str, object] = {"not_supplied": False}
    try:
        from .spw_bridge import SpwBridgeError, ingest_spw_report, log_spam
    except ImportError:
        return {"not_supplied": False, "available": False, "reason": "bridgeforge.spw_bridge is not available"}
    try:
        report = ingest_spw_report(perf)
        result["spw_report"] = {
            "source": report["source"],
            "per_mod": report["per_mod"],
            "startup": report["startup"],
            "limitations": report["limitations"],
        }
    except SpwBridgeError as exc:
        result["spw_report_error"] = str(exc)
    if log is not None:
        try:
            result["log_spam"] = log_spam(log, mod_prefixes or [])
        except SpwBridgeError as exc:
            result["log_spam_error"] = str(exc)
    return result


def _log_triage_artifact(log: Path | None) -> dict[str, object]:
    if log is None:
        return {"not_supplied": True}
    try:
        result = triage_log(log)
    except ValueError as exc:
        return {"not_supplied": False, "error": str(exc)}
    top_fatal = [{"line": e["line"], "matched_rule": e.get("matched_rule"), "message": _truncate_line(e["message"]), "top_mod_frame": e.get("top_mod_frame")} for e in result["fatal"][:5]]
    top_mod_error = [{"line": e["line"], "message": _truncate_line(e.get("top_mod_frame") or e["message"])} for e in result["mod_errors"][:5]]
    return {
        "not_supplied": False,
        "counts": result["counts"],
        "top_fatal": top_fatal,
        "top_mod_errors": top_mod_error,
        "milestones": result["milestones"],
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def _render_finding_line(entry: dict[str, object]) -> list[str]:
    loc = f"{entry['file']}:{entry['line']}" if entry["file"] and entry["line"] is not None else (entry["file"] or "(no file)")
    lines = [f"### {entry['id']} [{entry['classification']}/{entry['severity']}] - {loc}", "", entry["explanation"], "", f"- fixer available: {entry['fixer_available']}", f"- evidence: {', '.join(entry['evidence']) or '(none)'}"]
    snippet = entry.get("snippet")
    if snippet:
        lines.append("")
        if snippet.get("snippet_trimmed"):
            lines.append(f"(snippet trimmed to fit size cap; original span {snippet.get('original_start_line')}-{snippet.get('original_end_line')})")
        lines.append("```")
        for row in snippet["lines"]:
            lines.append(f"{row['line']}: {row['text']}")
        lines.append("```")
    lines.append("")
    return lines


def _render_part_markdown(mod_id: str | None, part_number: int, total_parts: int, entries: list[dict[str, object]]) -> str:
    lines = [f"# Dossier findings part {part_number}/{total_parts} - {mod_id or '(unknown mod)'}", ""]
    for entry in entries:
        lines.extend(_render_finding_line(entry))
    return "\n".join(lines) + "\n"


def _stringify_dependency(dep: object) -> str:
    if isinstance(dep, dict):
        label = dep.get("name") or dep.get("id") or "?"
        version = dep.get("version")
        return f"{label} {version}" if version else str(label)
    return str(dep)


def _format_build_tag(build_tag: object) -> str | None:
    if not isinstance(build_tag, dict):
        return None
    label = build_tag.get("label")
    build = build_tag.get("build")
    if label is None or build is None:
        return None
    return f"{label} r{build}"


def _format_kv(value: object) -> str:
    """Render a dict as `key=value, key2=value2` (never a Python repr), dropping bulky id lists."""
    if not isinstance(value, dict):
        return str(value)
    parts = []
    for key, val in value.items():
        if key in ("ids", "factions", "top_level_packages"):
            continue
        if isinstance(val, dict):
            val = f"({_format_kv(val)})"
        parts.append(f"{key}={val}")
    return ", ".join(parts) if parts else "(none)"


def _render_identity_markdown(identity: dict[str, object]) -> list[str]:
    name = identity.get("name") or identity.get("id") or "(unknown mod)"
    mod_id = identity.get("id") or "unknown"
    header = f"{name} ({mod_id})"
    build = _format_build_tag(identity.get("build_tag"))
    if build:
        header += f" — build {build}"
    dependencies = identity.get("dependencies") or []
    dependency_text = ", ".join(_stringify_dependency(d) for d in dependencies) if dependencies else "(none)"
    jars = identity.get("jars") or []
    jar_text = ", ".join(str(j) for j in jars) if jars else "(none)"
    return [
        f"- {header}",
        f"- mod_root: {identity.get('mod_root')}",
        f"- version: {identity.get('version')}",
        f"- game_version: {identity.get('game_version')}",
        f"- total_conversion: {identity.get('total_conversion')}",
        f"- mod_info_sha256: {identity.get('mod_info_sha256')}",
        f"- dependencies: {dependency_text}",
        f"- jars: {jar_text}",
    ]


def _render_inventory_markdown(inventory: dict[str, object]) -> list[str]:
    lines = []
    if inventory.get("detail_part"):
        lines.append(f"(full id lists moved to {inventory['detail_part']} to keep the index within --max-kb)")
    for key, value in inventory.items():
        if key == "detail_part":
            continue
        lines.append(f"- {key}: {_format_kv(value) if isinstance(value, dict) else value}")
    return lines


def _render_parts_table(parts: list[dict[str, object]]) -> list[str]:
    lines = ["| Part | Findings | Size | Classifications | Severities |", "| --- | --- | --- | --- | --- |"]
    for part in parts:
        size_kb = round(part["size_bytes"] / 1024, 1)
        classifications = ", ".join(part["classifications"]) or "(none)"
        severities = ", ".join(part["severities"]) or "(none)"
        lines.append(f"| {part['json_file']} / {part['markdown_file']} | {part['finding_count']} | {size_kb} KB | {classifications} | {severities} |")
    return lines


def _render_jar_audit_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "jar_audit: not supplied"
    if data.get("error"):
        return f"jar_audit: error - {data['error']}"
    return (
        f"jar_audit: {data.get('status')}, matched {data.get('matched_jar')} "
        f"({data.get('rebuilt_class_count')} rebuilt / {data.get('original_class_count')} original class(es); "
        f"{data.get('removed_class_count')} removed, {data.get('changed_class_count')} changed, "
        f"{data.get('unchanged_class_count')} unchanged; "
        f"{len(data.get('bundled_library_packages') or [])} bundled package(s), "
        f"{len(data.get('unexpected_new_packages') or [])} unexpected new package(s), "
        f"{data.get('reflection_finding_count')} reflection finding(s))"
    )


def _render_copy_drift_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "copy_drift: not supplied"
    if data.get("error"):
        return f"copy_drift: error - {data['error']}"
    return (
        f"copy_drift: {data.get('status')}, {data.get('drift_count')} drifted file(s) "
        f"({len(data.get('missing_in_deployed') or [])} missing, {len(data.get('different') or [])} different, "
        f"{len(data.get('extra_in_deployed') or [])} extra)"
    )


def _render_log_triage_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "log_triage: not supplied"
    if data.get("error"):
        return f"log_triage: error - {data['error']}"
    return (
        f"log_triage: {_format_kv(data.get('counts') or {})}; "
        f"{len(data.get('top_fatal') or [])} top fatal, {len(data.get('top_mod_errors') or [])} top mod error(s)"
    )


def _render_runtime_footprint_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "runtime_footprint: not supplied"
    classes = data.get("classes") or {}
    objects = data.get("objects") or {}
    class_part = f"classes: {classes.get('status', classes.get('reason', 'unavailable'))}"
    if "referenced_class_count" in classes:
        class_part += f" ({classes['referenced_class_count']} referenced)"
    objects_part = "objects: available" if objects.get("available") else f"objects: unavailable ({objects.get('reason', 'n/a')})"
    return f"runtime_footprint: {class_part}; {objects_part}"


def _render_performance_line(data: dict[str, object]) -> str:
    if data.get("not_supplied"):
        return "performance: not supplied"
    if not data.get("available", True):
        return f"performance: unavailable ({data.get('reason')})"
    report = data.get("spw_report")
    parts = []
    if report:
        parts.append(f"{len(report.get('per_mod') or [])} mod entrie(s), startup {report.get('startup', {}).get('total_ms')} ms")
    elif data.get("spw_report_error"):
        parts.append(f"spw_report error: {data['spw_report_error']}")
    log_spam = data.get("log_spam")
    if log_spam:
        parts.append(f"{log_spam.get('total_spam_lines', 0)} spam line(s)")
    return "performance: " + ("; ".join(parts) if parts else "(no data)")


def _render_index_markdown(index: dict[str, object]) -> str:
    identity = index["identity"]
    inventory = index["inventory"]
    lines = [f"# BridgeForge dossier - {identity.get('name') or identity.get('id') or '(unknown mod)'}", ""]
    lines.append(f"Generated: {index['generated_at']}")
    lines.append(f"Dossier version: {index['dossier_version']}")
    lines.append("")
    lines.append("## Identity")
    lines.extend(_render_identity_markdown(identity))
    lines.append("")
    lines.append("## Inventory")
    lines.extend(_render_inventory_markdown(inventory))
    lines.append("")
    lines.append("## Findings")
    lines.append(f"- new: {index['finding_counts']['new']}, baselined: {index['finding_counts']['baselined']}, resolved: {index['finding_counts']['resolved']}")
    lines.append("")
    lines.append("## Parts")
    lines.extend(_render_parts_table(index["parts"]))
    lines.append("")
    lines.append("## Artifacts")
    lines.append(f"- {_render_jar_audit_line(index['artifacts']['jar_audit'])}")
    lines.append(f"- {_render_copy_drift_line(index['artifacts']['copy_drift'])}")
    lines.append(f"- {_render_log_triage_line(index['artifacts']['log_triage'])}")
    lines.append(f"- {_render_runtime_footprint_line(index['artifacts']['runtime_footprint'])}")
    lines.append(f"- {_render_performance_line(index['artifacts']['performance'])}")
    lines.append("")
    lines.append("## Open questions")
    if index["open_questions"]:
        for question in index["open_questions"]:
            lines.append(f"- {question}")
    else:
        lines.append("(none)")
    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------


def build_dossier(
    mod_dir: Path,
    *,
    vanilla_core: Path | None = None,
    baseline: Path | None = None,
    original_jar: Path | None = None,
    rig: Path | None = None,
    log: Path | None = None,
    save: Path | None = None,
    perf: Path | None = None,
    perf_mod_prefixes: list[str] | None = None,
    max_kb: float = DEFAULT_MAX_KB,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> dict[str, object]:
    """Build a size-capped, deterministic triage dossier: an index dict plus a list of finding parts."""
    root = _find_mod_root(mod_dir)
    scan_result = scan_mod(root, TargetProfile(), vanilla_core)
    metadata = scan_result.metadata or {}

    if baseline is not None:
        baseline_keys = load_baseline_keys(baseline)
        new_findings, resolved_count = split_by_baseline(scan_result.findings, baseline_keys)
        baselined_count = len(scan_result.findings) - len(new_findings)
    else:
        new_findings = list(scan_result.findings)
        resolved_count = 0
        baselined_count = 0

    entries = _build_finding_entries(root, new_findings, context_lines)
    open_questions = _open_questions(entries)
    mod_id = metadata.get("id") if isinstance(metadata.get("id"), str) else None
    packed_parts = _pack_entries(mod_id, entries, max_kb)
    total_parts = len(packed_parts)

    part_payloads = []
    part_manifest = []
    for number, part_entries in enumerate(packed_parts, start=1):
        payload = _part_payload(mod_id, number, total_parts, part_entries)
        json_bytes = _json_bytes(payload)
        json_file = f"dossier.part-{number:02d}.json"
        markdown_file = f"dossier.part-{number:02d}.md"
        part_payloads.append(
            {
                "json_file": json_file,
                "markdown_file": markdown_file,
                "json_text": json_bytes.decode("utf-8"),
                "markdown_text": _render_part_markdown(mod_id, number, total_parts, part_entries),
                "size_bytes": len(json_bytes),
            }
        )
        part_manifest.append(
            {
                "json_file": json_file,
                "markdown_file": markdown_file,
                "size_bytes": len(json_bytes),
                "finding_count": len(part_entries),
                "classifications": sorted({e["classification"] for e in part_entries}),
                "severities": sorted({e["severity"] for e in part_entries}),
                "finding_ids": sorted({e["id"] for e in part_entries}),
                "files": sorted({e["file"] for e in part_entries if e["file"]}),
            }
        )

    inventory = _build_inventory(root, scan_result.compiled_class_names)
    identity = _build_identity(root, metadata)
    artifacts = {
        "jar_audit": _jar_audit_artifact(root, scan_result.jars, original_jar),
        "copy_drift": _copy_drift_artifact(root, rig),
        "log_triage": _log_triage_artifact(log),
        "runtime_footprint": _runtime_footprint_artifact(root, save, vanilla_core),
        "performance": _performance_artifact(perf, log, perf_mod_prefixes),
    }

    index: dict[str, object] = {
        "dossier_version": DOSSIER_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "identity": identity,
        "inventory": inventory,
        "finding_counts": {"new": len(new_findings), "baselined": baselined_count, "resolved": resolved_count},
        "parts": part_manifest,
        "artifacts": artifacts,
        "open_questions": open_questions,
    }

    # If the inventory's detail lists alone push the index over --max-kb, move them into a
    # dedicated part and leave only counts (plus a pointer) in the index.
    max_bytes = int(max_kb * 1024)
    if len(_json_bytes(index)) > max_bytes:
        detail = {"dossier_version": DOSSIER_VERSION, "mod_id": mod_id, "part": "inventory", "inventory": inventory}
        detail_json_file = "dossier.part-00-inventory.json"
        detail_markdown_file = "dossier.part-00-inventory.md"
        detail_json_bytes = _json_bytes(detail)
        detail_markdown = "\n".join([f"# Inventory detail - {mod_id or '(unknown mod)'}", "", "```json", json.dumps(inventory, indent=2, sort_keys=True), "```", ""])
        part_payloads.insert(
            0,
            {
                "json_file": detail_json_file,
                "markdown_file": detail_markdown_file,
                "json_text": detail_json_bytes.decode("utf-8"),
                "markdown_text": detail_markdown,
                "size_bytes": len(detail_json_bytes),
            },
        )
        slim_inventory = {}
        for key, value in inventory.items():
            if isinstance(value, dict):
                slim_inventory[key] = {k: v for k, v in value.items() if k not in ("ids", "factions", "top_level_packages")}
            else:
                slim_inventory[key] = value
        slim_inventory["detail_part"] = detail_json_file
        index["inventory"] = slim_inventory

    index_markdown = _render_index_markdown(index)

    return {
        "index": index,
        "index_markdown": index_markdown,
        "parts": part_payloads,
        "summary": {
            "new_finding_count": len(new_findings),
            "baselined_count": baselined_count,
            "resolved_count": resolved_count,
            "open_question_count": len(open_questions),
            "part_count": len(part_payloads),
            "part_sizes_kb": [round(part["size_bytes"] / 1024, 2) for part in part_payloads],
            "index_size_kb": round(len(_json_bytes(index)) / 1024, 2),
        },
    }


def _default_output_dir(mod_id: str | None, root: Path) -> Path:
    return Path.cwd() / "bridgeforge-dossier" / (mod_id or root.name)


def _refuse_protected_output(output_dir: Path) -> None:
    lowered = {part.strip().lower() for part in output_dir.parts}
    if lowered & PROTECTED_OUTPUT_DIR_NAMES:
        raise DossierError(f"Refusing to write a dossier under a protected directory (In operation/Done): {output_dir}")


def write_dossier(
    mod_dir: Path,
    output: Path | None = None,
    *,
    vanilla_core: Path | None = None,
    baseline: Path | None = None,
    original_jar: Path | None = None,
    rig: Path | None = None,
    log: Path | None = None,
    save: Path | None = None,
    perf: Path | None = None,
    perf_mod_prefixes: list[str] | None = None,
    max_kb: float = DEFAULT_MAX_KB,
    context_lines: int = DEFAULT_CONTEXT_LINES,
) -> dict[str, object]:
    """Build a dossier and write dossier.json/.md plus any dossier.part-*.json/.md to `output`."""
    root = _find_mod_root(mod_dir)
    result = build_dossier(
        root,
        vanilla_core=vanilla_core,
        baseline=baseline,
        original_jar=original_jar,
        rig=rig,
        log=log,
        save=save,
        perf=perf,
        perf_mod_prefixes=perf_mod_prefixes,
        max_kb=max_kb,
        context_lines=context_lines,
    )
    mod_id = result["index"]["identity"].get("id")
    output_dir = Path(output).expanduser().resolve() if output is not None else _default_output_dir(mod_id, root)
    _refuse_protected_output(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for stale in output_dir.glob("dossier.part-*"):
        if stale.is_file():
            stale.unlink()

    index_path = output_dir / "dossier.json"
    index_md_path = output_dir / "dossier.md"
    index_path.write_text(json.dumps(result["index"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
    index_md_path.write_text(result["index_markdown"], encoding="utf-8")

    written_parts = []
    for part in result["parts"]:
        json_path = output_dir / part["json_file"]
        md_path = output_dir / part["markdown_file"]
        json_path.write_text(part["json_text"] + "\n", encoding="utf-8")
        md_path.write_text(part["markdown_text"], encoding="utf-8")
        written_parts.append({"json": json_path, "markdown": md_path, "size_bytes": part["size_bytes"]})

    return {
        "output_dir": output_dir,
        "index_json": index_path,
        "index_markdown": index_md_path,
        "parts": written_parts,
        "summary": result["summary"],
    }
