from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LibraryRegistryEntry:
    library_id: str
    path: str
    note: str = ""


def load_library_registry(path: Path) -> dict[str, LibraryRegistryEntry]:
    """Load a local, user-maintained map of dependency id -> local library jar path.

    Bridgeforge never bundles, fetches, or assumes the presence of
    third-party library jars. This file is the user's own record of which
    real library jars exist on this machine (e.g. a real LazyLib install),
    kept wherever they choose -- never inside a Bridgeforge-managed
    workspace or the Bridgeforge repository itself. It only lets a mod's
    own declared dependency id resolve to an explicit local jar path
    automatically, instead of retyping --dependency-jar by hand every run.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid library registry {path}: {exc}") from exc
    if raw.get("schema_version") != 1 or not isinstance(raw.get("libraries"), dict):
        raise ValueError(f"Unsupported library registry schema: {path}")
    entries: dict[str, LibraryRegistryEntry] = {}
    for library_id, entry in raw["libraries"].items():
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"].strip():
            raise ValueError(f"Library registry entry for {library_id!r} is missing a path: {path}")
        entries[library_id] = LibraryRegistryEntry(library_id=library_id, path=entry["path"], note=entry.get("note", ""))
    return entries
