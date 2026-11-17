"""The game version a starsector-core belongs to, read from its own jar (ROADMAP-3 item 89, 2026-11-15).

`revive --target` defaulted to "0.98a-RC8", so reviving against 0.98.5a-RC3's core would still have written RC8 into
every `mod_info.json`. The version string is compiled into `starfarer_obf.jar` (found 2026-11-15: "0.98.5a-RC3" in
0.98.5a's, "0.98a-RC8" in RC8's; both also carry "0.9.1a-RC8", a legacy constant), so the newest version-shaped
string in that jar is the core's version.
"""
from __future__ import annotations

import re
import zipfile
from functools import lru_cache
from pathlib import Path

from .zipsafe import MAX_CLASS_BYTES, read_limited

_VERSION = re.compile(rb"\b(0\.\d+(?:\.\d+)*a)-RC(\d+)\b")


def _key(text: str) -> tuple:
    base, rc = text.rsplit("-RC", 1)
    return tuple(int(part) for part in base[:-1].split(".")), int(rc)  # 0.98.5a-RC3 > 0.98a-RC10


@lru_cache(maxsize=8)
def _from_jar(jar: str, _mtime: int) -> str | None:
    found: set[str] = set()
    with zipfile.ZipFile(jar) as archive:
        for info in archive.infolist():
            if info.filename.endswith(".class") and info.file_size <= MAX_CLASS_BYTES:
                found |= {f"{a.decode()}-RC{b.decode()}" for a, b in _VERSION.findall(read_limited(archive, info, MAX_CLASS_BYTES))}
    return max(found, key=_key) if found else None


def core_game_version(vanilla_core: Path | None) -> str | None:
    """"0.98.5a-RC3" for that core; None when the folder has no readable starfarer_obf.jar."""
    if vanilla_core is None:
        return None
    jar = Path(vanilla_core) / "starfarer_obf.jar"
    try:
        return _from_jar(str(jar.resolve()), jar.stat().st_mtime_ns)
    except (OSError, zipfile.BadZipFile):
        return None


def base_version(version: str) -> str:
    """'0.98a-RC8' -> '0.98a'; '0.98' -> '0.98a'; '0.98.5a-RC7' -> '0.98.5a'. The launcher matches on the base version."""
    base = re.sub(r"-RC\d+$", "", (version or "").strip(), flags=re.I).lower()
    return base if not base or base.endswith("a") else base + "a"


def reference_core_for(declared: str | None, search_roots: list[Path], *, exclude: Path | None = None) -> Path | None:
    """The installed starsector-core a mod was made for: the newest core under `search_roots` (each a core, an install
    holding `starsector-core/`, or a folder of installs) whose own version has the mod's declared base version.

    ROADMAP-3 item 92.17 (2026-11-16): `revive` passed no reference core to the `variant-op-over-budget` fixer, so the
    owner ruling of 2026-09-27 (option 2, RC8-06: trim only what the new build's costs pushed over) did not apply and the
    six-mod batch had 42 authored over-budget variants trimmed (all were over budget on their own RC8 core too)."""
    want = base_version(declared or "")
    if not want:
        return None
    skip = Path(exclude).resolve() if exclude else None
    found: list[tuple[str, Path]] = []
    for root in search_roots:
        root = Path(root)
        candidates = [root, root / "starsector-core"]
        if root.is_dir():
            candidates += [child / "starsector-core" for child in sorted(root.iterdir()) if child.is_dir()]
        for core in candidates:
            if not (core / "starfarer_obf.jar").is_file() or (skip and core.resolve() == skip):
                continue
            version = core_game_version(core)
            if version and base_version(version) == want and (version, core) not in found:
                found.append((version, core))
    return max(found, key=lambda item: _key(item[0]))[1] if found else None


_BUILD = re.compile(r"\d+\.\d+(?:\.\d+)*a(?:-RC\d+)?", re.I)


def revival_build(working: Path) -> str | None:
    """The game build a revived copy is for, as records name it (ROADMAP-3 96.5 A1: archives and live records said "RC8" for
    mods revived against 0.98.5a-RC7). That is the working copy's mod_info.json gameVersion, which revive's fixer and
    `retarget` set to the target core's own build; else the target its last `revive` recorded (reports/revive/REVIVE.json).
    None when neither names a build: an author's "0.98" is not one."""
    import json

    from .scan.scan_json import _load_lenient_json_file

    working = Path(working)
    info = _load_lenient_json_file(working / "mod_info.json") if (working / "mod_info.json").is_file() else None
    declared = str(info.get("gameVersion") or "").strip() if isinstance(info, dict) else ""
    if _BUILD.fullmatch(declared):
        return declared
    try:
        recorded = json.loads((working.parent / "reports" / "revive" / "REVIVE.json").read_text(encoding="utf-8")).get("target")
    except (OSError, ValueError, AttributeError):
        return None
    return recorded.strip() if isinstance(recorded, str) and _BUILD.fullmatch(recorded.strip()) else None


def rig_label(rig: Path | None) -> str:
    """How a record names the rig a run used: "0.98.5a-RC7 rig", the build its starsector-core reports; "rig (build not read)"
    when there is no rig or its core cannot be read. Records called every rig "RC8 rig" (96.5 A1)."""
    build = core_game_version(Path(rig) / "starsector-core") if rig else None
    return f"{build} rig" if build else "rig (build not read)"
