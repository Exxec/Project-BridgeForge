"""Click "Play Starsector" in the game launcher window for an unattended boot (ROADMAP 60f).

Evidence 2026-10-11: on the real rig the launcher window ('Starsector 0.98a-RC8') waits for a click and the log stops
after the launcher's fonts load; `tools/bf-test.ps1 launch` clicks by posting WM_LBUTTONDOWN/UP at (50%, 68%) of the
window to the child under that point, and the game then reached the main menu (CLICKTEST-20261011). This is the same
click from Python through ctypes. Windows only; elsewhere every function returns False and does nothing.
"""
from __future__ import annotations

import sys
import time

PLAY_X, PLAY_Y = 0.50, 0.68
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202


def _windows_for(pids: set[int]) -> list[tuple[int, str]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buffer, 256)
            if buffer.value:
                found.append((int(hwnd), buffer.value))
        return True

    user32.EnumWindows(visit, 0)
    return found


def click_window(handle: int, fx: float = PLAY_X, fy: float = PLAY_Y) -> str:
    """Post a click at fractions of the window rectangle to the child window under that point."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rect = wintypes.RECT()
    if not user32.GetWindowRect(handle, ctypes.byref(rect)):
        return "no window rectangle"
    sx = rect.left + int((rect.right - rect.left) * fx)
    sy = rect.top + int((rect.bottom - rect.top) * fy)
    point = wintypes.POINT(sx, sy)
    user32.ScreenToClient(handle, ctypes.byref(point))
    child = user32.ChildWindowFromPointEx(handle, point, 0)
    target = child or handle
    local = wintypes.POINT(sx, sy)
    user32.ScreenToClient(target, ctypes.byref(local))
    lparam = (local.y << 16) | (local.x & 0xFFFF)
    user32.PostMessageW(target, WM_MOUSEMOVE, 0, lparam)
    user32.PostMessageW(target, WM_LBUTTONDOWN, 1, lparam)
    user32.PostMessageW(target, WM_LBUTTONUP, 0, lparam)
    return f"posted click to {target} at {sx},{sy}"


def click_launcher_once(pids: set[int]) -> str | None:
    """Click the first visible Starsector window of these processes; the note, or None when there is none yet."""
    if sys.platform != "win32" or not pids:
        return None
    for handle, title in _windows_for(pids):
        if "Starsector" in title:
            time.sleep(1.5)  # let the launcher finish drawing before the click
            return click_window(handle)
    return None


def descendant_pids(root_pid: int) -> set[int]:
    """The process ids below `root_pid` (the cmd.exe that runs a launcher .bat), so a java.exe that lives outside the rig (the java-28
    JDK sits in the real install, not under _rig) is still found; matching the exe path under the rig missed it and the launcher
    waited for a click that never came (SMOKE-iron28-20261011)."""
    try:
        import psutil  # type: ignore

        return {child.pid for child in psutil.Process(root_pid).children(recursive=True)}
    except Exception:
        pass
    import json
    import subprocess

    script = ("$ids=@(" + str(int(root_pid)) + "); $all=Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId; "
              "do { $new=@($all | Where-Object { $ids -contains $_.ParentProcessId -and $ids -notcontains $_.ProcessId } | ForEach-Object { $_.ProcessId }); "
              "$ids+=$new } while ($new.Count -gt 0); $ids | ConvertTo-Json -Compress")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=30).stdout.strip()
        data = json.loads(out) if out else []
    except Exception:
        return set()
    data = data if isinstance(data, list) else [data]
    return {int(x) for x in data if int(x) != root_pid}
