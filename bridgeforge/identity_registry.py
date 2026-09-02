from __future__ import annotations

import json
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod


def build_campaign_identity_inventory(mod_directories: list[Path], target: TargetProfile) -> dict:
    """Inventory locally defined campaign IDs from explicitly selected mod roots."""
    directories = sorted(dict.fromkeys(path.expanduser().resolve() for path in mod_directories), key=lambda path: path.name.casefold())
    if not directories or any(not path.is_dir() for path in directories):
        raise ValueError("Campaign identity inventory requires one or more existing mod directories.")
    entries: list[dict[str, str]] = []
    for directory in directories:
        result = scan_mod(directory, target)
        source = str(result.metadata.get("id") or "").strip() or directory.name
        context = result.migration_context.get("campaign_identifier_context", {})
        entries.extend({"kind": "system", "id": identifier, "source": source} for identifier in context.get("defined_system_ids", []))
        entries.extend({"kind": "entity", "id": identifier, "source": source} for identifier in context.get("defined_entity_ids", []))
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_CAMPAIGN_IDENTITY_INVENTORY",
        "entries": sorted(entries, key=lambda item: (item["kind"], item["id"], item["source"].casefold())),
        "limitations": [
            "Only source-defined IDs in explicitly selected mod directories are inventoried.",
            "An absent ID may be vanilla, generated dynamically, or supplied by an unselected mod.",
        ],
    }


def load_campaign_identity_inventory(path: Path) -> dict:
    try:
        inventory = json.loads(path.expanduser().resolve().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid campaign identity inventory: {path}") from exc
    entries = inventory.get("entries")
    if inventory.get("schema_version") != 1 or inventory.get("mode") != "READ_ONLY_CAMPAIGN_IDENTITY_INVENTORY" or not isinstance(entries, list):
        raise ValueError("Unsupported campaign identity inventory schema.")
    if not all(isinstance(item, dict) and item.get("kind") in {"system", "entity"} and isinstance(item.get("id"), str) and isinstance(item.get("source"), str) for item in entries):
        raise ValueError("Campaign identity inventory contains invalid entries.")
    return inventory


def check_campaign_identity_references(mod_directory: Path, inventory: dict, target: TargetProfile) -> dict:
    """Resolve literal campaign lookups using an explicit, read-only inventory."""
    result = scan_mod(mod_directory, target)
    owners: dict[tuple[str, str], list[str]] = {}
    for item in inventory["entries"]:
        owners.setdefault((item["kind"], item["id"]), []).append(item["source"])
    checks: list[dict[str, object]] = []
    lookups = result.migration_context.get("campaign_identifier_context", {}).get("lookups", [])
    for lookup in lookups:
        key = (lookup["kind"], lookup["id"])
        candidates = sorted(set(owners.get(key, [])), key=str.casefold)
        status = "DEFINED_BY_THIS_MOD" if lookup["ownership"] == "defined-locally" else "RESOLVED_EXPLICIT_REGISTRY" if len(candidates) == 1 else "AMBIGUOUS_EXPLICIT_REGISTRY" if len(candidates) > 1 else "NOT_IN_EXPLICIT_REGISTRY"
        checks.append({"kind": lookup["kind"], "id": lookup["id"], "scanner_ownership": lookup["ownership"], "status": status, "candidates": candidates})
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_CAMPAIGN_IDENTITY_CHECK",
        "mod": mod_directory.expanduser().resolve().name,
        "checks": checks,
        "limitations": [
            "Only the supplied inventory is consulted; NOT_IN_EXPLICIT_REGISTRY is not proof an ID is unavailable in the game.",
            "Registry resolution does not establish creation order, load order, or null-safe runtime behavior.",
        ],
    }
