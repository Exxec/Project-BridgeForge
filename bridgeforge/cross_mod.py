from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .models import TargetProfile
from .scanner import scan_mod


def _normalize(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _dependency_ids(metadata: dict) -> list[str]:
    raw = metadata.get("dependencies") or metadata.get("requiredDependencies") or []
    values: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            values.extend(str(item[key]).strip() for key in ("id", "name") if item.get(key))
        elif str(item).strip():
            values.append(str(item).strip())
    return sorted(dict.fromkeys(values), key=str.casefold)


def analyze_mod_set(mod_directories: list[Path], target: TargetProfile, aliases: dict[str, str] | None = None) -> dict:
    """Create a deterministic, read-only ownership/dependency graph.

    Only the explicitly provided mods participate. Absence from this graph is
    reported as unknown, never as evidence that a dependency is not installed.
    """
    requested = [path.expanduser().resolve() for path in mod_directories]
    directories = sorted(dict.fromkeys(requested), key=lambda path: path.name.casefold())
    if not directories or any(not path.is_dir() for path in directories):
        raise ValueError("Cross-mod analysis requires one or more existing mod directories.")
    aliases = aliases or {}
    unknown_aliases = sorted(set(aliases) - {directory.name for directory in directories}, key=str.casefold)
    if unknown_aliases:
        raise ValueError(f"Cross-mod aliases do not match selected directory names: {', '.join(unknown_aliases)}")
    scans = [(directory, scan_mod(directory, target)) for directory in directories]
    nodes: list[dict[str, object]] = []
    id_owners: dict[str, list[str]] = defaultdict(list)
    class_owners: dict[str, list[str]] = defaultdict(list)
    identifier_owners: dict[tuple[str, str], list[str]] = defaultdict(list)
    node_details: dict[str, dict[str, object]] = {}
    for directory, result in scans:
        metadata_mod_id = str(result.metadata.get("id") or "").strip() or None
        mod_id = aliases.get(directory.name) or metadata_mod_id
        identity_source = "EXPLICIT_ALIAS" if directory.name in aliases else "METADATA" if metadata_mod_id else "UNAVAILABLE"
        name = directory.name
        key = name
        dependencies = _dependency_ids(result.metadata)
        direct_apis = result.migration_context.get("dependency_compatibility", {}).get("direct_api_dependencies", [])
        node = {
            "mod": name,
            "mod_id": mod_id,
            "identity_source": identity_source,
            "declared_dependencies": dependencies,
            "direct_api_dependencies": direct_apis,
            "packaged_class_count": len(result.compiled_class_names),
            "source_class_count": len(result.migration_context.get("configured_class_integrity", {}).get("source_class_names", [])),
        }
        nodes.append(node)
        node_details[key] = {"result": result, "dependencies": dependencies}
        if mod_id:
            id_owners[_normalize(mod_id)].append(key)
        for class_name in result.compiled_class_names:
            class_owners[class_name].append(key)
        for class_name in result.migration_context.get("configured_class_integrity", {}).get("source_class_names", []):
            class_owners[class_name].append(key)
        campaign = result.migration_context.get("campaign_identifier_context", {})
        for identifier in campaign.get("defined_system_ids", []):
            identifier_owners[("system", identifier)].append(key)
        for identifier in campaign.get("defined_entity_ids", []):
            identifier_owners[("entity", identifier)].append(key)

    edges: list[dict[str, object]] = []
    for node in nodes:
        for dependency in node["declared_dependencies"]:
            owners = id_owners.get(_normalize(dependency), [])
            edges.append({
                "from": node["mod"],
                "dependency": dependency,
                "status": "RESOLVED_IN_SELECTED_SET" if len(owners) == 1 else "AMBIGUOUS_IN_SELECTED_SET" if len(owners) > 1 else "NOT_IN_SELECTED_SET",
                "candidates": sorted(owners, key=str.casefold),
            })

    lookups: list[dict[str, object]] = []
    for node in nodes:
        result = node_details[node["mod"]]["result"]
        campaign = result.migration_context.get("campaign_identifier_context", {})
        for lookup in campaign.get("lookups", []):
            owners = identifier_owners.get((lookup["kind"], lookup["id"]), [])
            external = [owner for owner in owners if owner != node["mod"]]
            status = "DEFINED_BY_THIS_MOD" if lookup["ownership"] == "defined-locally" else "RESOLVED_BY_SELECTED_MOD" if len(external) == 1 else "AMBIGUOUS_SELECTED_MOD_OWNER" if len(external) > 1 else "NOT_IN_SELECTED_SET"
            lookups.append({"from": node["mod"], "kind": lookup["kind"], "id": lookup["id"], "scanner_ownership": lookup["ownership"], "status": status, "candidates": sorted(external, key=str.casefold)})

    duplicate_classes = [
        {"class": class_name, "owners": sorted(set(owners), key=str.casefold)}
        for class_name, owners in sorted(class_owners.items()) if len(set(owners)) > 1
    ]
    duplicate_identifiers = [
        {"kind": kind, "id": identifier, "owners": sorted(set(owners), key=str.casefold)}
        for (kind, identifier), owners in sorted(identifier_owners.items()) if len(set(owners)) > 1
    ]
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_CROSS_MOD_ANALYSIS",
        "mod_count": len(nodes),
        "duplicate_input_count": len(requested) - len(directories),
        "explicit_aliases": dict(sorted(aliases.items(), key=lambda item: item[0].casefold())),
        "mods": nodes,
        "dependency_edges": edges,
        "duplicate_class_ownership": duplicate_classes,
        "duplicate_campaign_identifier_ownership": duplicate_identifiers,
        "campaign_lookup_resolution": lookups,
        "limitations": [
            "Only explicitly supplied mods are graph members; NOT_IN_SELECTED_SET does not mean unavailable in the game.",
            "Class and campaign-ID ownership are static evidence only and do not prove load order or runtime behavior.",
        ],
    }
