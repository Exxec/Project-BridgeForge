"""Real mouse clicks into the running game window, for an unattended New Game (ROADMAP 60f(2)).

The in-game screens are drawn with OpenGL, so posted window messages are unverifiable; this moves the real cursor, so the
owner must leave the machine alone while it runs. Everything is in client-area fractions of the game window, because the
window is 1280x960 logical and 1920x1440 physical at the owner's 150% scaling (measured 2026-10-11): the process must be
DPI aware or every coordinate is off by that scale. Windows only; elsewhere the functions return None/False.
"""
from __future__ import annotations

import sys
from pathlib import Path
import time

# Client-area fractions measured on the RC8 main menu (1280x960 view of the 1920x1440 client, 2026-10-11).
MAIN_MENU_NEW_GAME = (0.7195, 0.4625)


def _user32():
    import ctypes

    user32 = ctypes.windll.user32
    try:
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass
    return user32


def game_window(pids: set[int]) -> tuple[int, int, int, int, int] | None:
    """(hwnd, client left, client top, client width, client height) in physical pixels of the first 'Starsector' window."""
    if sys.platform != "win32" or not pids:
        return None
    import ctypes
    from ctypes import wintypes

    from .launcher_click import _windows_for

    user32 = _user32()
    for hwnd, title in _windows_for(pids):
        if "Starsector" not in title:
            continue
        client = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        user32.GetClientRect(hwnd, ctypes.byref(client))
        user32.ClientToScreen(hwnd, ctypes.byref(origin))
        if client.right > 0 and client.bottom > 0:
            return hwnd, origin.x, origin.y, client.right, client.bottom
    return None


def bring_to_front(hwnd: int) -> bool:
    """Foreground the window. A tap of Alt first lets SetForegroundWindow through when nothing else is being typed."""
    if sys.platform != "win32":
        return False
    user32 = _user32()
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return user32.GetForegroundWindow() == hwnd


def click_fraction(geometry: tuple[int, int, int, int, int], fx: float, fy: float, settle: float = 0.4) -> tuple[int, int]:
    """Move the cursor to a client-area fraction of the game window and left-click; returns the physical point."""
    _hwnd, left, top, width, height = geometry
    x, y = left + int(width * fx), top + int(height * fy)
    user32 = _user32()
    user32.SetCursorPos(x, y)
    time.sleep(settle)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.06)
    user32.mouse_event(0x0004, 0, 0, 0, 0)
    return x, y


def press_key(virtual_key: int, hold: float = 0.06) -> None:
    """Press and release one key (the game window must be in front; see bring_to_front). 0x20 is Space."""
    user32 = _user32()
    user32.keybd_event(virtual_key, 0, 0, 0)
    time.sleep(hold)
    user32.keybd_event(virtual_key, 0, 2, 0)


def scroll(geometry: tuple[int, int, int, int, int], fx: float, fy: float, notches: int) -> None:
    """Move the cursor over a point and turn the wheel; negative notches scroll down."""
    _hwnd, left, top, width, height = geometry
    user32 = _user32()
    user32.SetCursorPos(left + int(width * fx), top + int(height * fy))
    time.sleep(0.3)
    for _ in range(abs(notches)):
        user32.mouse_event(0x0800, 0, 0, (-120 if notches < 0 else 120) & 0xFFFFFFFF, 0)
        time.sleep(0.12)


def capture_client(geometry: tuple[int, int, int, int, int], path: Path) -> bool:
    """Save the game window's client area (PowerShell + System.Drawing, DPI-aware, only that rectangle): a .bmp at full size for
    screen_read, anything else as a 1280x960 PNG to look at."""
    import subprocess

    _hwnd, left, top, width, height = geometry
    quoted = str(path).replace("'", "''")
    save = (f"$b.Save('{quoted}', [System.Drawing.Imaging.ImageFormat]::Bmp)" if str(path).lower().endswith(".bmp")
            else f"$s=New-Object System.Drawing.Bitmap $b,1280,960; $s.Save('{quoted}')")
    script = ("Add-Type -AssemblyName System.Drawing; Add-Type 'using System.Runtime.InteropServices; public class D { [DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware(); }'; "
              "[D]::SetProcessDPIAware() | Out-Null; $b=New-Object System.Drawing.Bitmap " + str(width) + "," + str(height) + "; "
              "$g=[System.Drawing.Graphics]::FromImage($b); $g.CopyFromScreen(" + str(left) + "," + str(top) + ",0,0,(New-Object System.Drawing.Size " + str(width) + "," + str(height) + ")); "
              + save)
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=60, check=True)
    except Exception:
        return False
    return Path(path).is_file()
