"""Check bf-test.ps1 presets against the rig's installed mods (2026-09-14).

Flu-X r3 and Zorg18 r2 dropped LazyLib/MagicLib, yet their presets still enabled them; nothing noticed
until a person read the file. For each preset this reports:
- ERROR: the preset's folder has no mod_info.json; its own mod isn't enabled; a dependency its mod
  declares isn't enabled; an enabled id no installed rig mod has.
- WARNING: an enabled library that no enabled mod declares (a leftover, or an optional library worth a
  comment in the script).
Read-only: it never edits the script or the rig.
"""

from __future__ import annotations

import re
from pathlib import Path

from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1
# Library id -> package paths its users reference (slash form, as in class files).
LIBRARY_PACKAGES = {
    "lw_lazylib": ("org/lazywizard/",),
    "MagicLib": ("org/magiclib/", "data/scripts/util/Magic"),
    "shaderLib": ("org/dark/shaders/",),
    "lunalib": ("lunalib/",),
}
LIBRARY_IDS = frozenset(LIBRARY_PACKAGES)
_PRESET_LINE = re.compile(r'^\s*"(?P<name>[^"]+)"\s*=\s*@\{\s*Folder\s*=\s*"(?P<folder>[^"]+)"\s*;\s*Mods\s*=\s*@\((?P<mods>[^)]*)\)', re.M)


def parse_presets(script_text: str) -> dict[str, dict[str, object]]:
    presets = {}
    for match in _PRESET_LINE.finditer(script_text):
        presets[match.group("name")] = {"folder": match.group("folder"), "mods": re.findall(r'"([^"]+)"', match.group("mods"))}
    return presets


def _dependency_ids(mod_info: dict) -> list[str]:
    deps = mod_info.get("dependencies") or mod_info.get("requiredDependencies") or []
    return [str(item.get("id")) for item in deps if isinstance(item, dict) and item.get("id")]


def _referenced_libraries(folder: Path) -> set[str]:
    """Libraries a mod's code references (Java sources and jar class files), declared or not.

    LunaLib is often an undeclared, optional settings library; a mod that references it needs it enabled.
    """
    import zipfile

    found: set[str] = set()
    needles = {library: [prefix.encode() for prefix in prefixes] + [prefix.replace("/", ".").encode() for prefix in prefixes] for library, prefixes in LIBRARY_PACKAGES.items()}
    blobs = []
    for source in folder.rglob("*.java"):
        try:
            blobs.append(source.read_bytes())
        except OSError:
            continue
    for jar in folder.rglob("*.jar"):
        try:
            with zipfile.ZipFile(jar) as archive:
                blobs.extend(archive.read(item) for item in archive.infolist() if item.filename.endswith(".class"))
        except (OSError, zipfile.BadZipFile, NotImplementedError):
            continue
    for library, patterns in needles.items():
        if any(pattern in blob for blob in blobs for pattern in patterns):
            found.add(library)
    return found


def installed_mods(rig_mods: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """({mod id: declared dependency ids}, {folder name: mod id}) for every rig mod with a readable mod_info."""
    by_id: dict[str, list[str]] = {}
    by_folder: dict[str, str] = {}
    for folder in sorted(path for path in rig_mods.iterdir() if path.is_dir()) if rig_mods.is_dir() else []:
        info = _load_lenient_json_file(folder / "mod_info.json") if (folder / "mod_info.json").is_file() else None
        if isinstance(info, dict) and info.get("id"):
            by_id[str(info["id"])] = _dependency_ids(info)
            by_folder[folder.name] = str(info["id"])
    return by_id, by_folder


def check_presets(script: Path, rig_mods: Path | None = None) -> dict[str, object]:
    script = Path(script).expanduser().resolve()
    rig_mods = Path(rig_mods).expanduser().resolve() if rig_mods else script.parent / "_rig" / "mods"
    presets = parse_presets(script.read_text(encoding="utf-8-sig", errors="replace"))
    by_id, by_folder = installed_mods(rig_mods)
    folder_of = {mod_id: folder for folder, mod_id in by_folder.items()}
    references: dict[str, set[str]] = {}

    def referenced(mod_id: str) -> set[str]:
        if mod_id not in references:
            references[mod_id] = _referenced_libraries(rig_mods / folder_of[mod_id]) if mod_id in folder_of else set()
        return references[mod_id]

    results = []
    for name, preset in sorted(presets.items()):
        mods: list[str] = preset["mods"]  # type: ignore[assignment]
        errors: list[str] = []
        warnings: list[str] = []
        own = by_folder.get(str(preset["folder"]))
        if own is None:
            errors.append(f"folder {preset['folder']!r} has no readable mod_info.json in {rig_mods}")
        elif own not in mods:
            errors.append(f"the preset's own mod {own!r} is not enabled")
        for mod_id in mods:
            if mod_id not in by_id:
                errors.append(f"{mod_id!r} is enabled but no rig mod has that id")
        for dep in by_id.get(own, []) if own else []:
            if dep not in mods:
                errors.append(f"{own!r} declares dependency {dep!r}, which is not enabled")
        # A library is needed when reached from a non-library enabled mod through declared dependencies,
        # or referenced by one's code. Libraries only other leftover libraries need are leftovers too
        # (Flu-X r3: MagicLib declares LazyLib, but nothing needs MagicLib).
        roots = [mod_id for mod_id in mods if mod_id not in LIBRARY_IDS]
        needed: set[str] = set()
        pending = list(roots)
        while pending:
            for dep in by_id.get(pending.pop(), []):
                if dep not in needed:
                    needed.add(dep)
                    pending.append(dep)
        used = set().union(*(referenced(mod_id) for mod_id in roots)) if roots else set()
        for mod_id in mods:
            if mod_id in LIBRARY_IDS and mod_id not in needed and mod_id not in used:
                warnings.append(f"library {mod_id!r} is enabled, but no enabled mod declares it (even indirectly) or references it in code")
        results.append({"preset": name, "folder": preset["folder"], "mod_id": own, "status": "FAIL" if errors else "REVIEW" if warnings else "PASS", "errors": errors, "warnings": warnings})
    status = "FAIL" if any(r["status"] == "FAIL" for r in results) else "REVIEW" if any(r["status"] == "REVIEW" for r in results) else "PASS"
    return {"schema_version": SCHEMA_VERSION, "mode": "PRESET_CHECK", "status": status, "script": str(script), "rig_mods": str(rig_mods), "presets": results}
