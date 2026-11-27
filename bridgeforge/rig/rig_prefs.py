"""Pin the launcher's resolution for an unattended rig run, and give the owner's own setting back afterwards (ROADMAP 65m).

Starsector's launcher keeps resolution and fullscreen in Java preferences under HKCU\\Software\\JavaSoft\\Prefs\\com\\fs\\starfarer,
one store for every install on the machine: the rig and the owner's real game share it. The owner's real game had set 2048x1152,
so the next rig session drew its menus at another size and the fixed click positions measured at 1280x960 missed (2026-10-11).
Windows only; elsewhere nothing is changed.
"""
from __future__ import annotations

import contextlib
import contextvars
import sys

PREFS_KEY = r"Software\JavaSoft\Prefs\com\fs\starfarer"
ERROR_NO_MORE_ITEMS = 259  # RegEnumValueW past the last value; any other non-zero code is an error, not the end of the list
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


def pref_names(key_path: str = PREFS_KEY) -> list[str] | None:
    """The value names under the key, listed without any value's data (`RegEnumValueW` with no data buffer): the licence key
    shares this key and is never read (owner rule 2026-11-17); `winreg.EnumValue` would return its data. None off Windows,
    [] without the key. `key_path` (under HKEY_CURRENT_USER) is for tests.

    A listing error raises OSError: a short list taken as complete would make the restore delete every owner value it missed
    (review of #269)."""
    if sys.platform != "win32":
        return None
    import ctypes
    import winreg

    enum = ctypes.windll.advapi32.RegEnumValueW
    enum.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong), ctypes.c_void_p,
                     ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
    enum.restype = ctypes.c_long
    names: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            while True:
                buffer, size = ctypes.create_unicode_buffer(16384), ctypes.c_ulong(16384)  # a value name has at most 16383 characters
                code = enum(key.handle, len(names), buffer, ctypes.byref(size), None, None, None, None)
                if code == ERROR_NO_MORE_ITEMS:
                    break
                if code != 0:
                    raise OSError(f"listing the preference names failed (RegEnumValueW {code}) after {len(names)} name(s)")
                names.append(buffer.value)
    except FileNotFoundError:
        return []
    return names


def owner_prefs() -> dict[str, str | None]:
    """Every value of the shared preferences except the licence key, each read by name (ROADMAP-3 98.23 a)."""
    return read_prefs(tuple(name for name in pref_names() or [] if name.lower() != LICENCE_KEY.lower()))


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


# Set while owner_prefs_kept holds the owner's values for several launches: each launch then gives back only what it pinned.
_KEPT: contextvars.ContextVar[bool] = contextvars.ContextVar("owner_prefs_kept", default=False)


def _give_back(others: dict[str, str | None], wanted: dict[str, str]) -> None:
    """Write back every value of `others` (the owner's, taken before) that now differs, is new or is gone, except the pinned
    names (`wanted`, restored apart) and the licence key, which is never read, compared or written."""
    after = owner_prefs()
    changed = {name: others.get(name) for name in sorted(set(others) | set(after))
               if name not in wanted and name.lower() != LICENCE_KEY.lower() and others.get(name) != after.get(name)}
    if changed:
        write_prefs(changed)


@contextlib.contextmanager
def owner_prefs_kept():
    """Take the owner's values once for several launches and give them back after the last, even on error.

    A save-reload run starts the game twice: the first launch saves, which moves `continue` to the rig's save, and the reload
    clicks Continue, which loads the last save the game wrote (RC8-29), the one `continue` records. Given back between the two,
    `continue` names the owner's save, which the rig does not have (review of #269; the in-game link is inferred, and a
    save-reload run proves it). Inside, each pinned_launcher_prefs restores only its pinned values. Nested, the outermost one
    gives back."""
    if _KEPT.get():
        yield
        return
    others = owner_prefs()
    token = _KEPT.set(True)
    try:
        yield
    finally:
        _KEPT.reset(token)
        _give_back(others, {})


@contextlib.contextmanager
def pinned_launcher_prefs(values: dict[str, str] | None = None):
    """Set the rig's launcher values for the run and restore the owner's exactly (including absent ones), even on error.

    The game also writes other values into this store, which every install on the machine shares: on White_Legion, the owner's
    own desktop, each run moved `continue` (the owner's last save) to the rig's save (2026-11-27, ROADMAP-3 98.23 a). So every
    other value is taken before the run and any the run changed, added or removed is given back, unless owner_prefs_kept
    holds them for a later launch. The licence key is never read, compared or written."""
    wanted = dict(values or PINNED)
    before = read_prefs(tuple(wanted))
    others = None if _KEPT.get() else owner_prefs()
    write_prefs(wanted)
    try:
        yield before
    finally:
        write_prefs(before)
        if others is not None:
            _give_back(others, wanted)
