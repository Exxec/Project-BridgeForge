"""The dossier's inventory and artifact sections (split from dossier.py, ROADMAP-3 96.5 A6).

`_build_inventory` lists what a mod defines (hulls, factions, planets and stars, systems it creates, jar classes, loose
scripts); the `_*_artifact` functions summarise jar-audit, copy-drift, runtime-footprint, performance and log-triage
results for the dossier. dossier.py assembles them.
"""
from __future__ import annotations

from pathlib import Path

from bridgeforge.bytecode.jar_audit import audit_jar
from bridgeforge.scan.scanner import (
    CAMPAIGN_SYSTEM_CREATION_PATTERN,
    FACTION_SPECIAL_ROLE_KEYS,
    _load_lenient_json_file,
    _read_csv_rows,
    _registered_csv_ids,
    _wing_ids_set,
)

from .copy_drift import compare_copies
from .log_triage import triage_log

MAX_LIST_ITEMS = 50
MAX_LINE_CHARS = 200


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
# Artifacts
# ---------------------------------------------------------------------------

def _truncate_line(text: str) -> str:
    return text if len(text) <= MAX_LINE_CHARS else text[:MAX_LINE_CHARS] + "…"


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
        from bridgeforge.save.save_compat import check_save_compat

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
        from bridgeforge.save import save_inspect as _save_inspect  # lazy: another agent may still be building this
    except ImportError:
        result["objects"] = {"available": False, "reason": "bridgeforge.save.save_inspect is not available yet"}
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
