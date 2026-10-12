"""Settings keys a mod reads that no settings.json defines (owner crash log 2026-10-04).

Exigency 0.8's Avesta black market read `Global.getSettings().getFloat("blackMarketMinSupplies")` (and ...MinFuel,
...MinMarines): vanilla dropped those keys in 0.9a (0.8.1a had 50, 50, 30), Exigency never defined them, and RC8 threw
`JSONException: JSONObject["blackMarketMinSupplies"] not found` when the market was opened. A settings read resolves
against the merged settings: vanilla's settings.json plus every enabled mod's (lists add; keys merge). So a literal key
is suspect when neither RC8's settings.json nor the mod's nor a declared dependency's defines it.

Reads are found in Java sources (`getSettings().getFloat("key")`) and, with a JDK, in jar classes via javap (`ldc
String key` followed by `SettingsAPI.getFloat/getInt/getBoolean/getString/getColor:(Ljava/lang/String;)`). `getSettingsJSON()`
reads with opt*/has guards are not flagged.
"""
from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

GETTERS = ("getFloat", "getInt", "getBoolean", "getString", "getColor", "getDouble", "getLong")
_SOURCE_READ = re.compile(r"getSettings\s*\(\s*\)\s*\.\s*(" + "|".join(GETTERS) + r")\s*\(\s*\"([^\"]+)\"\s*\)")
_LDC = re.compile(r"ldc(?:_w)?\s+#\d+\s+// String (.+)$")
_SETTINGS_CALL = re.compile(r"invokeinterface\s+#\d+,\s*\d+\s+// InterfaceMethod com/fs/starfarer/api/SettingsAPI\.(" + "|".join(GETTERS) + r"):\(Ljava/lang/String;\)")


def settings_keys(*settings_files: Path) -> set[str]:
    """Top-level keys of the given settings.json files (lenient: RC8 org.json rules)."""
    from .scanner import _load_lenient_json_file

    keys: set[str] = set()
    for path in settings_files:
        if path and Path(path).is_file():
            data = _load_lenient_json_file(Path(path))
            if isinstance(data, dict):
                keys |= set(data)
    return keys


_MOD_GUARD = re.compile(r"isModEnabled\s*\(\s*\"[^\"]+\"\s*\)\s*(?:&&|\?)")


def source_reads(text: str) -> list[tuple[int, str, str]]:
    """(line, getter, key) for literal settings reads in Java source (comments must be blanked).

    A read guarded earlier in the same statement by `isModEnabled("x") &&` (or `? ...`) is left out: the key is that
    other mod's setting, read only when it is enabled (Kadur Remnant reads IndEvo's PirateHaven/dryDock and Better
    Deserving S-Mods' BuiltInSMod that way, 2026-10-05)."""
    found = []
    for m in _SOURCE_READ.finditer(text):
        statement_start = max(text.rfind(";", 0, m.start()), text.rfind("{", 0, m.start()), text.rfind("}", 0, m.start()))
        if _MOD_GUARD.search(text[statement_start + 1:m.start()]):
            continue
        found.append((text.count("\n", 0, m.start()) + 1, m.group(1), m.group(2)))
    return found


def guarded_keys(text: str) -> set[str]:
    """Keys this source reads only behind an isModEnabled guard (see source_reads)."""
    guarded = set()
    for m in _SOURCE_READ.finditer(text):
        statement_start = max(text.rfind(";", 0, m.start()), text.rfind("{", 0, m.start()), text.rfind("}", 0, m.start()))
        if _MOD_GUARD.search(text[statement_start + 1:m.start()]):
            guarded.add(m.group(2))
    return guarded


def javap_reads(listing: str) -> list[tuple[str, str]]:
    """(getter, key) for `ldc String key; invokeinterface SettingsAPI.getX(String)` pairs in a javap -c listing."""
    found, previous = [], None
    for line in listing.splitlines():
        if not re.match(r"^\s*\d+:", line):
            continue  # not an instruction
        call = _SETTINGS_CALL.search(line)
        if call and previous is not None:
            found.append((call.group(1), previous))
        ldc = _LDC.search(line)
        previous = ldc.group(1).strip() if ldc else None  # only the instruction right before the call counts
    return found


def jar_reads(jar: Path, javap: Path) -> list[tuple[str, str, str]]:
    """(class, getter, key) for classes in a jar that call SettingsAPI getters."""
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.endswith(".class") and b"com/fs/starfarer/api/SettingsAPI" in archive.read(n)]
    except (OSError, zipfile.BadZipFile):
        return []
    found = []
    for name in names:
        out = subprocess.run([str(javap), "-c", "-p", "-constants", "-cp", str(jar), name[:-6].replace("/", ".")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
        found += [(name, getter, key) for getter, key in javap_reads(out)]
    return found
