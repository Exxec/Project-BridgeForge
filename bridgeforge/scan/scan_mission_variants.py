"""`mission-variant-not-defined` (item 73 F4): a mission names a ship variant or wing that no visible mod defines.

RC8 raises a Fatal when such a mission is started, not at New Game (found 2026-10-12 in Aivon Republic, Sylphon RnD and Silent Armada;
the probe logs `content-ids|mission-variant:<id>`). `mission-local-fleet-reference-missing` already covers ids with the mod's own
prefix; this check covers every other id the mission names. An id is defined when the mod, RC8 or a declared dependency has a
`.variant` file with it (subfolders included), a `wing_data.csv` row, or, for `<hull>_Hull`, the hull or skin. A name that appears only
inside an `if (...isModEnabled...)` block is guarded (`_blank_mod_guarded_blocks`) and not reported. When an id is missing, the
finding names the mods in the provider roots that do define it (the Vayra's Ship Pack `ii_*` and Kadur Remnant SWP/SEEKER cases,
LOCAL_HANDOFF section 0): a mod to add to the dependencies, or to guard on. The provider lookup reads only the file names of the
variants of each root's mods, and only runs when something is missing.
"""
from __future__ import annotations

from pathlib import Path

from ..models import ScanResult
from ..provider_renamed_ids import ids_in_csv
from .scan_campaign import _declared_spec_ids
from .scan_common import MISSION_FLEET_REFERENCE_PATTERN, _relative
from .scan_javatext import _blank_java_comments, _blank_mod_guarded_blocks
from .scan_json import _load_lenient_json_file

_CORE_CACHE: dict[str, tuple[set[str], set[str], set[str]]] = {}
_PROVIDER_CACHE: dict[tuple[str, int], tuple[set[str], set[str], set[str]]] = {}


def _folder_content(folder: Path) -> tuple[set[str], set[str], set[str]]:
    """(variant ids, wing ids, hull and skin ids) a mod folder defines."""
    data = folder / "data"
    variants = set(_declared_spec_ids(data / "variants", "*.variant", "variantId"))
    wings = ids_in_csv(data / "hulls" / "wing_data.csv")
    hulls = ids_in_csv(data / "hulls" / "ship_data.csv") | set(_declared_spec_ids(data / "hulls", "*.skin", "skinHullId"))
    return variants, wings, hulls


def _core_content(core: Path) -> tuple[set[str], set[str], set[str]]:
    key = str(core)
    if key not in _CORE_CACHE:
        _CORE_CACHE[key] = _folder_content(core)
    return _CORE_CACHE[key]


def _mod_folders(provider_roots: list[Path], exclude: Path) -> list[tuple[str, Path]]:
    """(mod id, folder) for the mods directly under each provider root (a mods folder, or an In operation tree with working/)."""
    found: list[tuple[str, Path]] = []
    for base in provider_roots:
        base = Path(base)
        if not base.is_dir():
            continue
        candidates = [base] if (base / "mod_info.json").is_file() else [p for p in base.iterdir() if p.is_dir()]
        for candidate in candidates:
            folder = candidate / "working" if (candidate / "working" / "mod_info.json").is_file() else candidate
            info = _load_lenient_json_file(folder / "mod_info.json")
            if isinstance(info, dict) and info.get("id") and folder.resolve() != exclude.resolve():
                found.append((str(info["id"]), folder))
    return found


def providers_of(missing: set[str], provider_roots: list[Path], exclude: Path) -> dict[str, list[str]]:
    """{missing id: ['<mod id> (<folder name>)', ...]} for mods under the provider roots whose variants or wings include the id."""
    named: dict[str, list[str]] = {}
    for mod_id, folder in _mod_folders(provider_roots, exclude):
        # Cached per folder and variants-folder mtime: a queue scan asks for the same few hundred folders once per mod.
        try:
            stamp = (str(folder), (folder / "data" / "variants").stat().st_mtime_ns)
        except OSError:
            stamp = (str(folder), 0)
        if stamp not in _PROVIDER_CACHE:
            _PROVIDER_CACHE[stamp] = _folder_content(folder)
        variants, wings, _ = _PROVIDER_CACHE[stamp]
        for name in missing & (variants | wings):
            named.setdefault(name, []).append(f"{mod_id} ({folder.parent.name if folder.name == 'working' else folder.name})")
    return named


def mission_fleet_references(root: Path) -> dict[str, dict]:
    """{id: {'type': 'SHIP'|'FIGHTER_WING', 'files': [...], 'guarded': bool}} over the mod's MissionDefinition sources."""
    found: dict[str, dict] = {}
    sources = sorted({*(root / "src").glob("data/missions/*/MissionDefinition.java"), *(root / "data").glob("missions/*/MissionDefinition.java")})
    for source in sources:
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        everything = set(MISSION_FLEET_REFERENCE_PATTERN.findall(text))
        unguarded = set(MISSION_FLEET_REFERENCE_PATTERN.findall(_blank_mod_guarded_blocks(text)))
        for name, member_type in everything:
            entry = found.setdefault(name, {"type": member_type, "files": [], "guarded": True, "tests_mods": False})
            entry["tests_mods"] = entry["tests_mods"] or "isModEnabled" in text
            entry["files"].append(_relative(root, source))
            if (name, member_type) in unguarded:
                entry["guarded"] = False
    return found


def _defined(name: str, member_type: str, contents: list[tuple[set[str], set[str], set[str]]]) -> bool:
    if member_type == "FIGHTER_WING":
        return any(name in wings for _, wings, _ in contents)
    if any(name in variants for variants, _, _ in contents):
        return True
    return name.endswith("_Hull") and any(name[:-5] in hulls for _, _, hulls in contents)


def scan_mission_variants_not_defined(root: Path, result: ScanResult, vanilla_core: Path | None, provider_roots: list[Path] | None = None) -> None:
    if vanilla_core is None:
        return
    mod_id = str(result.metadata.get("id") or "").strip()
    prefix = f"{mod_id}_" if mod_id else None
    references = mission_fleet_references(root)
    if not references:
        return
    folders = [root, vanilla_core, *[Path(p) for p in result.migration_context.get("dependency_roots") or []]]
    contents = [_core_content(vanilla_core) if folder == vanilla_core else _folder_content(folder) for folder in folders]
    missing = {n: r for n, r in references.items() if not (prefix and n.startswith(prefix)) and not _defined(n, r["type"], contents)}
    if not missing:
        return
    named = providers_of(set(missing), [Path(p) for p in provider_roots or []], root)
    for name, ref in sorted(missing.items()):
        providers = named.get(name, [])
        guard = "not inside an isModEnabled block" + ("; the mission tests isModEnabled elsewhere (a faction or case branch may guard it at run time)" if ref["tests_mods"] else "")
        who = f"defined by {', '.join(providers)}" if providers else "no mod under the provider roots defines it"
        if ref["guarded"]:
            result.migration_context.setdefault("mission_guarded_missing", []).append(name)
            continue
        result.add(
            id="mission-variant-not-defined", category="missions", severity="high", classification="REVIEW", confidence="LOW" if ref["tests_mods"] else ("HIGH" if providers else "MEDIUM"),
            explanation=(f"A mission names {'wing' if ref['type'] == 'FIGHTER_WING' else 'variant'} '{name}', which this mod, RC8 and the declared "
                         f"dependencies do not define; {who}. RC8 stops with a Fatal when the mission is started. Add the defining mod as a "
                         "dependency, guard the line with an isModEnabled test, or drop the entry."),
            file=ref["files"][0], evidence=[f"{ref['type']}:{name}", who, guard, *[f"mission:{f}" for f in sorted(set(ref["files"]))[:3]]])
