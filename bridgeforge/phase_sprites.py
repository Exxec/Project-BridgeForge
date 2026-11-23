"""Phase sprites: image files the game derives from a hull's sprite name, which no file names whole (RC8_BEHAVIOUR RC8-51).

RC7's `SpecStore` (javap 2026-11-23) takes every ship system whose `.system` sets both `phaseHighlight` and `phaseDiffuse`
(vanilla `phasecloak.system`: "_glow1" and "_glow2"). For every phase hull, it queues `sprite[:-4] + suffix + ".png"` for
each suffix that is not empty. That covers hulls whose ship system is that system, and hulls whose shield type is `PHASE`.
A queued image the game cannot find is Fatal at load (P4B-CAR-20261123: "Image with filename
[graphics/ships/ork_murtach_glow1.png] not found").

A hull is a phase hull (`O00o.isPhase`) when its hints hold `PHASE`, or its shield type is `PHASE` and its defense id is
`phasecloak`.

Vanilla follows this: `graphics/ships/phase/` and the skin folders ship `<sprite>_glow1.png` and `_glow2.png` beside every
phase sprite.

The functions take any index with `rows["hull"]` ({id: ship_data.csv row}) and `ship`, `skin` and `system`, each
{id: spec path}. vendor-plan's `_Index` is one; `light_index` builds one without reading code.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

PHASE_KEYS = ("phaseHighlight", "phaseDiffuse")


def light_index(root: Path | None) -> SimpleNamespace:
    """The hull rows and the `.ship`, `.skin` and `.system` specs of one folder, without vendor-plan's class walk."""
    from bridgeforge.vendor_plan import _rows, _specs

    present = root is not None and Path(root).is_dir()
    return SimpleNamespace(
        rows={"hull": _rows(Path(root), "data/hulls/ship_data.csv") if present else {}},
        ship=_specs(Path(root), "data/hulls", "*.ship", "hullId") if present else {},
        skin=_specs(Path(root), "data/hulls", "*.skin", "skinHullId") if present else {},
        system=_specs(Path(root), "data/shipsystems", "*.system", "id") if present else {})


def phase_systems(indexes: list) -> dict[str, tuple[str, str]]:
    """{system id: (highlight suffix, diffuse suffix)} for the systems whose spec sets both keys. The first index that
    defines an id wins, so list a mod before the core."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    found: dict[str, tuple[str, str]] = {}
    seen: set[str] = set()
    for index in indexes:
        for ident, path in sorted(index.system.items()):
            if ident in seen:
                continue
            seen.add(ident)
            spec = _load_lenient_json_file(path)
            if isinstance(spec, dict) and all(isinstance(spec.get(key), str) for key in PHASE_KEYS):
                found[ident] = (spec[PHASE_KEYS[0]], spec[PHASE_KEYS[1]])
    return found


def _hints(value: object) -> set[str]:
    return {h.strip().upper() for h in str(value or "").replace(",", " ").split() if h.strip()}


def hull_facts(ident: str, indexes: list, _depth: int = 0) -> dict | None:
    """The effective sprite, ship system, defense id, shield type and hints of hull `ident`. A skin takes its base hull's
    facts and its own `spriteName`, `systemId`, `addHints` and `removeHints`. None when no index defines the hull."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    for index in indexes:
        if ident in index.ship:
            spec = _load_lenient_json_file(index.ship[ident])
            row = next((i.rows["hull"][ident] for i in indexes if ident in i.rows["hull"]), None) or {}
            sprite = spec.get("spriteName") if isinstance(spec, dict) else None
            return {"sprite": sprite if isinstance(sprite, str) else "", "system": (row.get("system id") or "").strip(),
                    "defense": (row.get("defense id") or "").strip(), "shield": (row.get("shield type") or "").strip().upper(),
                    "hints": _hints(row.get("hints"))}
        if ident in index.skin:
            spec = _load_lenient_json_file(index.skin[ident])
            if not isinstance(spec, dict) or _depth > 4:
                return None
            base = hull_facts(str(spec.get("baseHullId") or ""), indexes, _depth + 1)
            if base is None:
                return None
            hints = (base["hints"] | _hints(" ".join(map(str, spec.get("addHints") or [])))) - _hints(
                " ".join(map(str, spec.get("removeHints") or [])))
            sprite = spec.get("spriteName")
            system = spec.get("systemId")
            return {**base, "sprite": sprite if isinstance(sprite, str) and sprite else base["sprite"],
                    "system": system.strip() if isinstance(system, str) and system.strip() else base["system"], "hints": hints}
    return None


def is_phase(facts: dict) -> bool:
    """`O00o.isPhase`: a PHASE hint, or a PHASE shield whose defense id is `phasecloak`."""
    return "PHASE" in facts["hints"] or (facts["shield"] == "PHASE" and facts["defense"] == "phasecloak")


def phase_sprite_paths(ident: str, indexes: list, systems: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    """[(image path, why)] the game queues for hull `ident`, deduplicated."""
    facts = hull_facts(ident, indexes)
    if facts is None or not facts["sprite"] or not is_phase(facts):
        return []
    stem = facts["sprite"].replace("\\", "/").lstrip("/")[:-4]
    found: dict[str, str] = {}
    for system, suffixes in sorted(systems.items()):
        if facts["system"] != system and facts["shield"] != "PHASE":
            continue
        for key, suffix in zip(PHASE_KEYS, suffixes):
            if suffix:
                found.setdefault(f"{stem}{suffix}.png", f"{key} {suffix!r} of ship system {system}")
    return sorted(found.items())


__all__ = ["PHASE_KEYS", "hull_facts", "is_phase", "light_index", "phase_sprite_paths", "phase_systems"]
