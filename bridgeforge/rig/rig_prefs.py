"""Pin the launcher's resolution for an unattended rig run, and give the owner's own setting back afterwards (ROADMAP 65m).

Starsector's launcher keeps resolution and fullscreen in Java preferences under HKCU\\Software\\JavaSoft\\Prefs\\com\\fs\\starfarer,
one store for every install on the machine: the rig and the owner's real game share it. The owner's real game had set 2048x1152,
so the next rig session drew its menus at another size and the fixed click positions measured at 1280x960 missed (2026-10-11).
Windows only; elsewhere nothing is changed.
"""
from __future__ import annotations

import contextlib
import sys

PREFS_KEY = r"Software\JavaSoft\Prefs\com\fs\starfarer"
RIG_RESOLUTION = "1920x1440"  # the window every click fraction in live_run was measured in (1920x1440 physical, 2026-10-11)
PINNED = {"resolution": RIG_RESOLUTION, "fullscreen": "false"}
# Java's Windows preferences store each capital as "/" plus the letter, so canSkipTutorial is the registry value
# can/Skip/Tutorial and controlsVersion is controls/Version (both machines' registries, 2026-11-17).
CAN_SKIP_TUTORIAL = "can/Skip/Tutorial"
CONTROLS_VERSION = "controls/Version"
LICENCE_KEY = "serial"
# A live run's New Game clicks "Skip it" (tutorial). rules.csv `ngcSkipTutorialNoSkip` disables it until the Windows user has
# started a game with the tutorial (`NGCCanSkipTutorial` is `!isNewPlayer()`, backed by canSkipTutorial): Test1 could not skip
# it (G1-LIVE2-0985a-20261117). The live run pins it with the resolution and gives the owner's state back (ROADMAP-3 93.28).
LIVE_PINNED = {**PINNED, CAN_SKIP_TUTORIAL: "true"}


def has_pref(name: str, key_path: str = PREFS_KEY) -> bool | None:
    """Whether the preference value exists, asked without reading it: the registry returns only its size (no data buffer), so
    the licence key is checked this way and never read out (owner rule 2026-11-17). None off Windows. `key_path` (under
    HKEY_CURRENT_USER) is for tests."""
    if sys.platform != "win32":
        return None
    import ctypes
    import winreg

    query = ctypes.windll.advapi32.RegQueryValueExW
    query.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    query.restype = ctypes.c_long
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            size = ctypes.c_ulong(0)
            return query(key.handle, name, None, None, None, ctypes.byref(size)) == 0
    except FileNotFoundError:
        return False


def read_prefs(names=tuple(PINNED)) -> dict[str, str | None]:
    if sys.platform != "win32":
        return {}
    import winreg

    found: dict[str, str | None] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PREFS_KEY) as key:
            for name in names:
                try:
                    found[name] = winreg.QueryValueEx(key, name)[0]
                except FileNotFoundError:
                    found[name] = None
    except FileNotFoundError:
        return {name: None for name in names}
    return found


def write_prefs(values: dict[str, str | None]) -> None:
    if sys.platform != "win32":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PREFS_KEY) as key:
        for name, value in values.items():
            if value is None:
                try:
                    winreg.DeleteValue(key, name)
                except FileNotFoundError:
                    pass
            else:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)


@contextlib.contextmanager
def pinned_launcher_prefs(values: dict[str, str] | None = None):
    """Set the rig's launcher values for the run and restore the owner's exactly (including absent ones), even on error."""
    wanted = dict(values or PINNED)
    before = read_prefs(tuple(wanted))
    write_prefs(wanted)
    try:
        yield before
    finally:
        write_prefs(before)
