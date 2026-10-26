"""`mission-map-reference-missing` (item 73 F5): a mission map that names a background image or planet type that does not exist.

`MissionDefinition.java` builds the battle map: `api.setBackgroundSpriteName("graphics/...png")` loads an image and
`api.addPlanet(x, y, radius, "<type>", ...)` builds a planet from a `planets.json` type. A missing image or type fails when the
mission starts, not at New Game (compare `mission-local-fleet-reference-missing`). `addNebula(x, y, radius)` takes numbers only
and has no id to resolve, so it is not read (the plan listed it; the API has nothing to check).

Needs `--vanilla-core`: without RC8's files nothing is claimed. Images and types are looked up in the mod, RC8 and the declared
dependencies' folders (`migration_context["dependency_roots"]`); only string-literal arguments are read, a constant is not guessed.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..models import ScanResult
from .scan_common import _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _load_lenient_json_file

_BACKGROUND = re.compile(r'\bsetBackgroundSpriteName\s*\(\s*"([^"]+)"\s*\)')
_PLANET = re.compile(r'\baddPlanet\s*\(\s*[^,()]+,\s*[^,()]+,\s*[^,()]+,\s*"([^"]+)"')


def mission_map_references(text: str) -> list[tuple[str, str]]:
    """[(kind, id)] with kind 'background' or 'planet-type', from comment-blanked MissionDefinition source."""
    return [("background", m) for m in _BACKGROUND.findall(text)] + [("planet-type", m) for m in _PLANET.findall(text)]


def _planet_types(folders: list[Path]) -> set[str]:
    types: set[str] = set()
    for folder in folders:
        data = _load_lenient_json_file(folder / "data" / "config" / "planets.json")
        if isinstance(data, dict):
            types.update(data)
    return types


def scan_mission_map_references(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    if vanilla_core is None:
        return
    folders = [root, vanilla_core, *[Path(p) for p in result.migration_context.get("dependency_roots") or []]]
    types = _planet_types(folders)
    sources = sorted({*(root / "src").glob("data/missions/*/MissionDefinition.java"), *(root / "data").glob("missions/*/MissionDefinition.java")})
    for source in sources:
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        # Comment-blanking keeps string contents, so the literals below are real arguments.
        for kind, name in mission_map_references(text):
            if kind == "background":
                found = any((folder / name.lstrip("/\\")).is_file() for folder in folders)
            else:
                found = not types or name in types
            if found:
                continue
            result.add(
                id="mission-map-reference-missing", category="missions", severity="high", classification="REVIEW", confidence="DETERMINISTIC",
                explanation=(f"This mission's map names {kind} '{name}', which exists in neither this mod, RC8 nor a declared dependency. "
                             "The mission fails when it is started (the picker may still list it)."),
                file=_relative(root, source), evidence=[f"{kind}:{name}", "resolution: missing"])
