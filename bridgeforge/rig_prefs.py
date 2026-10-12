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
