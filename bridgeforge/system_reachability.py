"""Which `createStarSystem` calls a mod can actually reach (EPTA Alicerce, 2026-10-22).

EPTA Consortium 2.0.3 and 2.1.x still ship `sevencorpGenEpta` -> `sevencorp_alicerceGen`, which creates "Alicerce", but the
author commented out the only call (`sevencorp_ModPlugin.onNewGame`, line 62), so no campaign has the system. Counting
every `createStarSystem` in the jar made the probe's campaign-layout check expect it and FAIL on every run (EPTA213-20261013,
EPTA213BF2-20261022; reviewed in the workspace's reports/ASTRA_LIVE_REVIEW.md).

A jar class counts only when it is reachable from the mod's entry points, following the class constants (CONSTANT_Class)
and class-name strings (reflection) in each class's constant pool:
- the `modPlugin` named in mod_info.json;
- every jar class whose dotted name appears in the mod's data files (settings plugins, industries, hull mods, rules
  scripts, ...) or in a loose script the game can load.
When no entry point resolves to a jar class, every jar class counts (the old behaviour), so nothing is hidden by a missing
root. Bytecode stays authoritative: a source file that the game cannot load (its path does not match its package, e.g.
`src/...`) is ignored when the mod ships jars. Virtual dispatch through an interface the reachable code never names is not
followed; a class reached only that way is reported as unreached, never silently dropped.
"""
from __future__ import annotations

import re
import zipfile
from collections import deque
from pathlib import Path

from .scanner import _loaded_mod_jars

_DOTTED = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+")
_PACKAGE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.M)
_WILDCARD_IMPORT = re.compile(r"^\s*import\s+([\w.]+)\.\*\s*;", re.M)
_WORD = re.compile(r"[A-Za-z_$][\w$]*")
_DATA_SUFFIXES = {".json", ".csv", ".faction", ".skin", ".ship", ".variant", ".system", ".txt"}
_MAX_DATA_BYTES = 4 * 1024 * 1024
# Classes the game itself loads by name (RC8 starsector-core data/config/settings.json, read 2026-10-22). A mod that ships a
# class of the same name replaces the vanilla one: Ironclads' total conversion ships data.scripts.world.SectorGen, which
# creates Centronom, Lomonosov, Nexus and Shington.
_ENGINE_CLASSES = frozenset({
    "data.scripts.world.SectorGen", "com.fs.starfarer.api.impl.MusicPlayerPluginImpl",
    "com.fs.starfarer.api.impl.SimulatorPluginImpl", "com.fs.starfarer.api.impl.campaign.CoreLifecyclePluginImpl",
    "com.fs.starfarer.api.impl.campaign.FactionPersonalityPickerPluginImpl",
    "com.fs.starfarer.api.impl.campaign.NewGameDialogPluginImpl", "com.fs.starfarer.api.impl.campaign.OfficerLevelupPluginImpl",
    "com.fs.starfarer.api.impl.campaign.SurveyPluginImpl", "com.fs.starfarer.api.impl.campaign.procgen.SectorProcGen",
    "com.fs.starfarer.api.impl.campaign.skills.CommRelayScript",
    "com.fs.starfarer.api.impl.campaign.skills.CoordinatedManeuversScript",
    "com.fs.starfarer.api.impl.campaign.skills.ElectronicWarfareScript", "com.fs.starfarer.api.impl.campaign.skills.NeuralLinkScript",
    "com.fs.starfarer.api.impl.combat.CRPluginImpl", "com.fs.starfarer.api.impl.combat.GenericCombatPlugin",
})
# rules.csv names a command by its simple name; the game looks it up in these packages (same settings.json).
_RULE_COMMAND_PACKAGES = frozenset({
    "com/fs/starfarer/api/impl/campaign/rulecmd", "com/fs/starfarer/api/impl/campaign/rulecmd/academy",
    "com/fs/starfarer/api/impl/campaign/rulecmd/missions", "com/fs/starfarer/api/impl/campaign/rulecmd/newgame",
    "com/fs/starfarer/api/impl/campaign/rulecmd/salvage",
})


def _implicit_root(internal_name: str) -> bool:
    """Loaded by convention rather than by a name in the mod: rule commands and mission definitions."""
    package, _, simple = internal_name.rpartition("/")
    return package in _RULE_COMMAND_PACKAGES or (package.startswith("data/missions/") and simple == "MissionDefinition")


def loadable_source(root: Path, source: Path) -> bool:
    """True when the game's script loader can find this .java by class name: its path matches its package."""
    try:
        match = _PACKAGE.search(source.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False
    package = match.group(1).split(".") if match else []
    return list(source.relative_to(root).parts[:-1]) == package


def _source_class_names(text: str, known: set[str]) -> set[str]:
    """Known classes a loose script names through a wildcard import or its own package (Ironclads' SectorGen:
    `import data.scripts.world.RSF.*;` then `new Lomonosov()`)."""
    package = _PACKAGE.search(text)
    packages = set(_WILDCARD_IMPORT.findall(text)) | ({package.group(1)} if package else set())
    words = set(_WORD.findall(text))
    return {name for name in known if name.rpartition(".")[0] in packages and name.rpartition(".")[2] in words}


def entry_names(root: Path, mod_info: dict, known: set[str] = frozenset()) -> set[str]:
    """Dotted class names the mod's entry points name; `known` (dotted jar classes) resolves loose scripts' simple names."""
    names: set[str] = set(_ENGINE_CLASSES)
    plugin = mod_info.get("modPlugin")
    if isinstance(plugin, str):
        names.add(plugin.strip())
    data = root / "data"
    files = [p for p in data.rglob("*") if p.is_file() and p.suffix.lower() in _DATA_SUFFIXES] if data.is_dir() else []
    sources = [p for p in root.rglob("*.java") if loadable_source(root, p)]
    for path in files + sources:
        try:
            if path.stat().st_size > _MAX_DATA_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names.update(_DOTTED.findall(text))
        if path.suffix == ".java" and known:
            names.update(_source_class_names(text, set(known)))
    return names


def reachable_classes(classes: dict[str, tuple[set[str], set[str]]], entry_names: set[str]) -> set[str] | None:
    """Internal names reachable from the entry points; None when no entry point is a known class (count everything).

    `classes` maps an internal name to (referenced internal names, string constants)."""
    dotted = {name.replace("/", "."): name for name in classes}
    roots = {dotted[n] for n in entry_names if n in dotted} | {n for n in classes if _implicit_root(n)}
    if not roots:
        return None
    seen, queue = set(roots), deque(roots)
    while queue:
        refs, strings = classes[queue.popleft()]
        for target in refs | {dotted[s] for s in strings if s in dotted}:
            if target in classes and target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def jar_classes(root: Path) -> dict[str, tuple[bytes, set[str], set[str]]]:
    """Every class in the mod's loaded jars: internal name -> (bytes, class refs, string constants)."""
    from .campaign_layout import _constant_pool, _utf8
    root = Path(root)
    found: dict[str, tuple[bytes, set[str], set[str]]] = {}
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                for member in archive.namelist():
                    if not member.endswith(".class"):
                        continue
                    data = archive.read(member)
                    parsed = _constant_pool(data)
                    refs: set[str] = set()
                    strings: set[str] = set()
                    if parsed is not None:
                        pool, _ = parsed
                        for entry in pool.values():
                            if entry[0] == 7:
                                refs.add(_utf8(pool, entry[1]).lstrip("[").removeprefix("L").removesuffix(";"))
                            elif entry[0] == 8:
                                strings.add(_utf8(pool, entry[1]))
                    found.setdefault(member[:-len(".class")], (data, refs, strings))
        except (OSError, zipfile.BadZipFile):
            continue
    return found
