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
