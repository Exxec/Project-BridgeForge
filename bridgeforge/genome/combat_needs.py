"""What a gene's ships need once they are built for combat: engine styles and sounds (94.G2 slice 22; RC8_BEHAVIOUR RC8-52,
RC8-53).

Both live in shared donor files (`data/config/engine_styles.json`, `data/config/sounds.json`). Under the owner's ruling of
2026-11-23 ("Separate, needed") each entry the gene uses is a need: the carrier gets a copy and the subtraction keeps it. The
subtraction scan cannot see a sound id used from code, so a removed sound would break the donor at run time (advisor
2026-11-23). What gets carried is broad: every mod sound id the gene's specs, styles or code name. What fails the carrier
check is narrow, only what a run showed to be Fatal:
- an engine style a hull's engine slot names that nothing defines (DIAG-P3-S21);
- a `*Set` sound id of a hull style the carrier's hulls use that nothing defines (DIAG-P4-S21);
- a sound id that carried code passes to `SoundPlayerAPI.playSound`, `playUISound`, `playLoop` or `playUILoop`, which
  nothing defines (DIAG-P4-S22A).

The engine-slot rule comes from javap of RC7's `ShipHullSpecLoader`, 2026-11-23:
- A slot's `style` is read as the engine enum.
- A value outside the enum is taken as the `styleId` of a CUSTOM style.
- A CUSTOM slot names its style by `styleId`, or carries an inline `styleSpec`, which needs nothing.
- An enum name takes the core's `engine_styles.json` entry of that name when there is one.
- A `styleId` nothing defines leaves the slot without a style. The hull loads, and the ship is Fatal when it is built for
  combat.
"""
from __future__ import annotations

import re
from pathlib import Path

ENGINE_STYLES = "data/config/engine_styles.json"
SOUNDS = "data/config/sounds.json"
# RC7 `com.fs.starfarer.loading.specs.E$o` (javap 2026-11-23).
ENGINE_ENUM = frozenset({"LOW_TECH", "MIDLINE", "HIGH_TECH", "COBRA_BOMBER", "ATTACK_SWARM", "THREAT", "ONSLAUGHT_MKI",
                         "MISSILE_LOW_TECH", "MISSILE_MIDLINE", "MISSILE_HIGH_TECH", "LOW_TECH_FIGHTER", "TORPEDO",
                         "TORPEDO_ATROPOS", "ROCKET_LOW_TECH", "OMEGA", "DWELLER", "CUSTOM"})
# RC7 `starfarer.api.jar` SoundPlayerAPI: the methods whose first argument is a sounds.json id (javap 2026-11-23).
SOUND_SINKS = frozenset(f"com/fs/starfarer/api/SoundPlayerAPI.{m}#0" for m in ("playSound", "playUISound", "playLoop", "playUILoop"))
_JAVA_PLAY = re.compile(r'\.play(?:Sound|UISound|Loop|UILoop)\s*\(\s*"([^"\\]+)"')
_SPEC_SUFFIXES = (".ship", ".skin", ".wpn", ".proj", ".system", ".variant", ".wing")
_SOUND_FILES = (".ogg", ".wav")


def _json_object(path: Path) -> dict:
    from bridgeforge.scan.scanner import _load_lenient_json_file

    data = _load_lenient_json_file(path) if path.is_file() else None
    return data if isinstance(data, dict) else {}


def strings(value: object) -> list[str]:
    """Every string in a parsed JSON value."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def engine_style_ids(spec: object) -> list[str]:
    """The engine style ids a `.ship`'s engine slots, or a `.skin`'s `engineSlotChanges`, name (RC8-52)."""
    if not isinstance(spec, dict):
        return []
    slots = list(spec.get("engineSlots") or []) if isinstance(spec.get("engineSlots"), list) else []
    changes = spec.get("engineSlotChanges")
    slots += list(changes.values()) if isinstance(changes, dict) else []
    found = set()
    for slot in slots:
        style = slot.get("style") if isinstance(slot, dict) else None
        if not isinstance(style, str) or not style:
            continue
        if style == "CUSTOM":
            ident = slot.get("styleId")
            found |= {ident} if isinstance(ident, str) and ident else set()
        elif style not in ENGINE_ENUM:
            found.add(style)
    return sorted(found)


def style_sound_ids(style: object) -> list[str]:
    """The sound ids a hull style's `*Set` keys name (`engineLoopSet`, `shieldRaiseSet`, ...)."""
    return sorted({v for k, v in style.items() if k.endswith("Set") and isinstance(v, str) and v}) if isinstance(style, dict) else []


def _files(entry: object, root: Path, core: Path | None, suffixes: tuple[str, ...]) -> set[str]:
    from bridgeforge.genome.evidence import path_problem

    found = set()
    for value in strings(entry):
        relative = value.replace("\\", "/").lstrip("/")
        if (relative.lower().endswith(suffixes) and not path_problem(relative) and (root / relative).is_file()
                and not (core and (core / relative).is_file())):
            found.add(relative)
    return found


def donor_needs(root: Path, members: list[dict], vanilla_core: Path | None) -> dict[str, list[str]]:
    """{"donor": member paths, "missing": [...]}: the engine styles and sounds the gene uses that the mod defines (and the
    files those entries name that the mod has and the core lacks), and the keyed ones nothing defines. Without the core only
    the mod's own entries are judged."""
    from bridgeforge.genome.carrier_load import _styles
    from bridgeforge.genome.closure import code_literals, pointer

    root = Path(root)
    core = Path(vanilla_core) if vanilla_core else None
    files = [m["path"] for m in members if m["what"] == "file"]
    specs = {path: _json_object(root / path) for path in files if path.lower().endswith(_SPEC_SUFFIXES)}
    hulls = {p: s for p, s in specs.items() if p.startswith("data/hulls/") and p.endswith((".ship", ".skin"))}
    core_engines, mod_engines = _json_object(core / ENGINE_STYLES) if core else {}, _json_object(root / ENGINE_STYLES)
    core_sounds, mod_sounds = set(_json_object(core / SOUNDS)) if core else set(), _json_object(root / SOUNDS)
    donor: set[str] = set()
    missing: list[str] = []
    named = {s for spec in specs.values() for s in strings(spec)} | code_literals(root, members)
    for ident in sorted({i for spec in hulls.values() for i in engine_style_ids(spec)}):
        if ident in core_engines:
            continue
        if ident in mod_engines:
            donor.add(f"{ENGINE_STYLES}#{pointer(ident)}")
            donor |= _files(mod_engines[ident], root, core, (".png", ".jpg", ".jpeg"))
            named |= set(strings(mod_engines[ident]))
        elif core is not None:
            missing.append(f"engine style {ident}: no engine_styles.json defines it (RC8-52)")
    styles = {**_styles(core), **_styles(root)} if core else _styles(root)
    used = {spec.get("style") for spec in hulls.values() if isinstance(spec.get("style"), str)}
    for name in sorted(used & set(styles)):
        for ident in style_sound_ids(styles[name]):
            named.add(ident)
            if core is not None and ident not in core_sounds and ident not in mod_sounds:
                missing.append(f"sound {ident} (hull style {name}): no sounds.json defines it (RC8-53)")
    for ident in sorted(named & (set(mod_sounds) - core_sounds)):
        donor.add(f"{SOUNDS}#{pointer(ident)}")
        donor |= _files(mod_sounds[ident], root, core, _SOUND_FILES)
    return {"donor": sorted(donor), "missing": missing}


def combat_gaps(carrier: Path, others: list[Path], *, code: bool = True) -> list[dict]:
    """The carrier check's part for combat (RC8-52, RC8-53): `engine-style-undefined`, `hull-style-sound-undefined` and,
    with `code`, `sound-play-undefined`. `others` are the declared dependencies' folders and the core."""
    from bridgeforge.genome.carrier_load import _styles

    carrier = Path(carrier)
    roots = [carrier, *others]
    engines = {k for root in roots for k in _json_object(root / ENGINE_STYLES)}
    sounds = {k for root in roots for k in _json_object(root / SOUNDS)}
    styles: dict = {}
    for root in roots:
        styles.update({k: v for k, v in _styles(root).items() if k not in styles})
    gaps: list[dict] = []
    hulls = carrier / "data" / "hulls"
    used: dict[str, str] = {}
    for path in sorted([*hulls.rglob("*.ship"), *hulls.rglob("*.skin")]) if hulls.is_dir() else []:
        spec = _json_object(path)
        relative = path.relative_to(carrier).as_posix()
        for ident in engine_style_ids(spec):
            if ident not in engines:
                gaps.append({"finding": "engine-style-undefined", "file": relative, "style": ident})
        if isinstance(spec.get("style"), str):
            used.setdefault(spec["style"], relative)
    for name, relative in sorted(used.items()):
        for ident in style_sound_ids(styles.get(name)):
            if ident not in sounds:
                gaps.append({"finding": "hull-style-sound-undefined", "file": relative, "style": name, "sound": ident})
    if code:
        for ident, where in sorted(_played_ids(carrier).items()):
            if ident not in sounds:
                gaps.append({"finding": "sound-play-undefined", "file": where, "sound": ident})
    return gaps


def _played_ids(carrier: Path) -> dict[str, str]:
    """{sound id: where} for each literal the carrier's code passes to a SoundPlayerAPI play method: loose scripts by
    text, loaded jar classes by their literals' sinks (genome/literal_sinks.py)."""
    from bridgeforge.genome.literal_sinks import class_literal_sinks
    from bridgeforge.scan.scan_classfile import _loaded_mod_jars, _parse_class_file, iter_class_files_in_jars

    found: dict[str, str] = {}
    for source in sorted(Path(carrier).rglob("*.java")):
        for ident in _JAVA_PLAY.findall(source.read_text(encoding="utf-8-sig", errors="replace")):
            found.setdefault(ident, source.relative_to(carrier).as_posix())
    for jar, member, data in iter_class_files_in_jars(_loaded_mod_jars(Path(carrier))):
        info = _parse_class_file(data)
        for ident, sinks in class_literal_sinks(data, info.string_constants if info else []).items():
            if sinks & SOUND_SINKS:
                found.setdefault(ident, f"{Path(jar).relative_to(carrier).as_posix()}!{member}")
    return found


__all__ = ["ENGINE_ENUM", "ENGINE_STYLES", "SOUNDS", "SOUND_SINKS", "combat_gaps", "donor_needs", "engine_style_ids",
           "style_sound_ids", "strings"]
