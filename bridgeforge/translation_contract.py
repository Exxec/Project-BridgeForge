"""Source-bound schema-v1 extension checks; imported roles never grant approval."""

from __future__ import annotations

import copy
import hashlib
import os
import tempfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

KINDS = {"csv", "json", "json-key", "java", "jar", "text-line", "class"}
ROLES = {"TEXT", "IDENTIFIER", "LINKED", "UNKNOWN"}


def _contained(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or relative.is_absolute() or ".." in relative.parts or relative.as_posix() != name:
        raise ValueError(f"Unsafe relative source path: {name}")
    path = root / name
    if root not in path.resolve().parents:
        raise ValueError(f"Source path escapes root: {name}")
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError(f"Linked source path: {name}")
        cursor = cursor.parent
    return path


def prepare_document(root: Path, document: dict, current: dict) -> tuple[dict, list[str], bool]:
    """Check identities against rediscovery and propagate only complete, consistent declared groups."""
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("Expected translation schema_version 1")
    entries = document.get("entries")
    hashes = document.get("file_hashes")
    glossary = document.get("glossary", {})
    if not isinstance(entries, list) or not isinstance(hashes, dict) or not isinstance(glossary, dict):
        raise ValueError("Invalid translation collections")
    if document.get("mod_id") != current.get("mod_id"):
        raise ValueError("Translation mod_id differs from selected source")
    for name, digest in hashes.items():
        if not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Invalid source hash")
        path = _contained(root, name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest().lower() != digest.lower():
            raise ValueError(f"source files changed since export: {name}")
    if any(not isinstance(value, str) for value in glossary.values()):
        raise ValueError("Glossary values must be text")
    if "roles_version" in document and not isinstance(document["roles_version"], str):
        raise ValueError("roles_version must be text")
    actual = {entry["id"]: entry for entry in current["entries"]}
    prepared = copy.deepcopy(document)
    prepared["file_hashes"] = {name: digest.lower() for name, digest in hashes.items()}
    groups = defaultdict(list)
    seen = set()
    protected = []
    for entry in prepared["entries"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or entry["id"] in seen:
            raise ValueError("Invalid or duplicate translation identity")
        seen.add(entry["id"])
        source_entry = actual.get(entry["id"])
        if source_entry is None or any(entry.get(field) != source_entry[field] for field in ("file", "kind", "source", "context")):
            raise ValueError(f"Protected entry field differs: {entry['id']}")
        if entry["kind"] not in KINDS or entry["file"] not in hashes or not isinstance(entry.get("translation"), str):
            raise ValueError(f"Invalid translation entry: {entry['id']}")
        role = entry.get("role", "TEXT")
        if not isinstance(role, str) or role not in ROLES or ("role_rule" in entry and not isinstance(entry["role_rule"], str)):
            raise ValueError(f"Invalid role metadata: {entry['id']}")
        if role == "LINKED":
            if not isinstance(entry.get("group"), str) or not entry["group"]:
                raise ValueError("LINKED unit requires a group")
            groups[entry["group"]].append(entry)
        elif "group" in entry:
            raise ValueError("Only LINKED units may carry a group")
        if role == "IDENTIFIER":
            if entry["translation"] or glossary.get(entry["source"]):
                protected.append(f"{entry['id']}: protected identifier is not translated")
            entry["translation"] = ""
            prepared.get("glossary", {}).pop(entry["source"], None)
    targets = {}
    translated_groups = False
    for group, members in groups.items():
        sources = {entry["source"] for entry in members}
        if len(sources) != 1 or len(members) < 2:
            raise ValueError(f"Invalid linked group: {group}")
        source = next(iter(sources))
        supplied = {entry["translation"] or prepared.get("glossary", {}).get(source, "") for entry in members} - {""}
        if len(supplied) > 1:
            raise ValueError(f"Linked group translated inconsistently: {group}")
        target = next(iter(supplied), source)
        if target in targets and targets[target] != group:
            raise ValueError("Linked groups would share one translation")
        targets[target] = group
        if supplied:
            complete = {entry["id"] for entry in current["entries"] if entry["source"] == source}
            if complete != {entry["id"] for entry in members}:
                raise ValueError(f"Linked group omits same-source references: {group}")
            translated_groups = True
            for entry in members:
                entry["translation"] = target
    # Removing protected units also prevents glossary fallback inside the legacy resolver.
    prepared["entries"] = [entry for entry in prepared["entries"] if entry.get("role") != "IDENTIFIER"]
    return prepared, protected, translated_groups


def apply_with_contract(root: Path, document: dict, out_dir: Path | None, in_place: bool, exporter, apply):
    """A LINKED publication is staged and refused in full if any member fails the existing format checks."""
    root = Path(root).expanduser().resolve()
    if (out_dir is None) == (not in_place):
        raise ValueError("give exactly one of out_dir or in_place=True")
    prepared, protected, linked = prepare_document(root, document, exporter(root))
    if not linked:
        result = apply(root, prepared, out_dir=out_dir, in_place=in_place)
    else:
        if in_place:
            raise ValueError("LINKED interchange requires a new --out copy; in-place linked application is not supported")
        target = Path(out_dir).expanduser().resolve()
        if target.exists() or target == root or root in target.parents or target in root.parents:
            raise ValueError("Linked output must be a new directory outside the source")
        with tempfile.TemporaryDirectory(prefix=".bf-linked-", dir=target.parent) as directory:
            staged = Path(directory) / "candidate"
            result = apply(root, prepared, out_dir=staged, in_place=False)
            if result["problems"]:
                raise ValueError("Linked translation rejected: " + "; ".join(result["problems"]))
            for name, digest in document["file_hashes"].items():
                if hashlib.sha256(_contained(root, name).read_bytes()).hexdigest().lower() != digest.lower():
                    raise ValueError("Source changed during linked translation preflight")
            if target.exists():
                raise ValueError("Output appeared during linked translation preflight")
            os.replace(staged, target)
            result["target"] = str(target)
    result["entries"] = len(document["entries"])
    result["problems"].extend(protected)
    if protected:
        result["status"] = "PARTIAL" if sum(result["applied"].values()) else "FAIL"
    if prepared.get("_reindexed"):
        document["_reindexed"] = prepared["_reindexed"]
    return result
