"""Watch the rig game's windows while it runs (the single launch path, launch.py, starts it for every caller).

Starsector shows a Java Fatal Error only as a modal dialog; it never reaches the redirected log. This records the text of every new
visible top-level window of the game's processes to `<rig>/logs/<TESTID>.windows.txt` in the format log-triage reads
(`HH:mm:ss window: '<title>'`, `HH:mm:ss dialog: '<title>' text: '<text>'`), takes a screenshot of a second or error-titled window
(`<TESTID>-window<N>.png`, at most 10) and one of the game's window when java runs 180 s without the main menu
(`<TESTID>-no-main-menu.png`). Each capture is that window's rectangle only, never the whole screen (ROADMAP-3 93.24).
The window enumeration, child-text read, screenshot and clock are injectable for tests.
"""
from __future__ import annotations

import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

POLL_SECONDS = 2.0
NO_MENU_SECONDS = 180.0
MAX_WINDOW_SHOTS = 10
ERROR_TITLE = re.compile(r"error|fatal|exception", re.IGNORECASE)


def enumerate_windows(pids: set[int]) -> list[tuple[int, str]]:
    from .launcher_click import _windows_for

    return _windows_for(pids)


def child_text(handle: int) -> str:
    """The text of a message box's child controls (Starsector's "Fatal: ..." dialog is one), without the OK button."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    parts: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(child, _lparam):
        buffer = ctypes.create_unicode_buffer(2048)
        user32.GetWindowTextW(child, buffer, 2048)
        value = buffer.value.strip()
        if value and value != "OK":
            parts.append(value)
        return True

    user32.EnumChildWindows(handle, visit, 0)
    return " ".join(parts).replace("\r", " ").replace("\n", " ")


def save_screenshot(path: Path, handle: int | None = None) -> bool:
    """One of the game's windows as a PNG, drawn by the window itself (`PrintWindow` with `PW_RENDERFULLCONTENT`), so whatever
    covers it on screen is not in the picture; never the whole screen. Without a window nothing is captured. Owner 2026-11-27:
    live tests run on White_Legion, the owner's own desktop, which is never captured (ROADMAP-3 93.24); the earlier capture took
    the whole virtual screen, and copying the window's rectangle from the screen would still show a window in front of it.

    The path and the window go to PowerShell in environment variables, never inside the script: a single-quoted string also ends
    at U+2018-U+201B, and the mass test's paths carried a mod's id (ROADMAP-3 93.47)."""
    import os
    import subprocess

    if not handle:
        return False
    script = ("Add-Type -AssemblyName System.Drawing; Add-Type 'using System; using System.Runtime.InteropServices; public class BfWindow { "
              "[DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware(); "
              "[StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left; public int Top; public int Right; public int Bottom; } "
              "[DllImport(\"user32.dll\")] public static extern bool GetWindowRect(IntPtr window, out Rect rect); "
              "[DllImport(\"user32.dll\")] public static extern bool PrintWindow(IntPtr window, IntPtr dc, uint flags); }'; "
              "[BfWindow]::SetProcessDPIAware() | Out-Null; $r=New-Object BfWindow+Rect; $win=[IntPtr][long]$env:BF_WINDOW; "
              "if (-not [BfWindow]::GetWindowRect($win, [ref]$r)) { exit 3 }; "
              "$w=$r.Right-$r.Left; $h=$r.Bottom-$r.Top; if ($w -le 0 -or $h -le 0) { exit 3 }; "
              "$b=New-Object System.Drawing.Bitmap $w,$h; $g=[System.Drawing.Graphics]::FromImage($b); $dc=$g.GetHdc(); "
              "$ok=[BfWindow]::PrintWindow($win, $dc, 2); $g.ReleaseHdc($dc); if (-not $ok) { exit 4 }; "
              "$b.Save($env:BF_IMAGE_PATH, [System.Drawing.Imaging.ImageFormat]::Png)")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=60, check=True,
                       env={**os.environ, "BF_IMAGE_PATH": str(path), "BF_WINDOW": str(int(handle))})
    except Exception:
        return False
    return Path(path).is_file()


class WindowWatcher:
    def __init__(self, rig: Path, test_id: str, pids: Callable[[], set[int]], *, enumerate_fn=enumerate_windows,
                 child_text_fn=child_text, screenshot=save_screenshot, clock: Callable[[], float] = time.monotonic,
                 now: Callable[[], datetime] = datetime.now, sleep: Callable[[float], None] = time.sleep) -> None:
        from .boot_test import MAIN_MENU_MARKER

        self.logs = Path(rig) / "logs"
        self.test_id = test_id
        self.log = self.logs / f"{test_id}.stdout.log"
        self.windows_log = self.logs / f"{test_id}.windows.txt"
        self._pids, self._enumerate, self._child_text, self._screenshot = pids, enumerate_fn, child_text_fn, screenshot
        self._clock, self._now, self._sleep = clock, now, sleep
        self._marker = MAIN_MENU_MARKER
        self._seen: set[tuple[int, str]] = set()
        self._shots = 0
        self._menu_reached = False
        self._suspect_shot = False
        self._started = clock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.logs.mkdir(parents=True, exist_ok=True)
        if self.windows_log.exists():  # a reused test id must not carry an earlier attempt's dialogs into this run's triage
            self.windows_log.replace(self.logs / f"{test_id}.windows.{self._now():%Y%m%d-%H%M%S}.prev.txt")

    def note(self, text: str) -> None:
        with self.windows_log.open("a", encoding="utf-8") as handle:
            handle.write(f"{self._now():%H:%M:%S} {text}\n")

    def _menu_in_log(self) -> bool:
        try:
            return self._marker in self.log.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False

    def poll_once(self) -> None:
        pids = self._pids()
        if not self._menu_reached and self._menu_in_log():
            self._menu_reached = True
        for handle, title in self._enumerate(pids) if pids else []:
            if (handle, title) in self._seen:
                continue
            self._seen.add((handle, title))
            self.note(f"window: '{title}'")
            text = self._child_text(handle)
            if text:
                self.note(f"dialog: '{title}' text: '{text}'")
            if (len(self._seen) > 1 or ERROR_TITLE.search(title)) and self._shots < MAX_WINDOW_SHOTS:
                self._sleep(0.8)
                self._shots += 1
                self._screenshot(self.logs / f"{self.test_id}-window{self._shots}.png", handle)  # that window only
        if pids and not self._menu_reached and not self._suspect_shot and self._clock() - self._started > NO_MENU_SECONDS:
            self._suspect_shot = True
            window = self._game_window_now(pids)
            if window is not None:  # with no game window there is nothing to show, and the screen is never captured
                if not self._screenshot(self.logs / f"{self.test_id}-no-main-menu.png", window):
                    self.note("shot: the no-main-menu screenshot of the game's window failed")

    def _game_window_now(self, pids: set[int]) -> int | None:
        """The game's window as it is now, not the first one seen: the launcher's window is destroyed before the game's own
        window opens (RC9 `GLLauncher$2` calls `Display.destroy()` before Play's `actionPerformed`; review of 93.24). A window
        titled Starsector that is not an error comes first, else any window of the game's processes."""
        windows = list(self._enumerate(pids))
        named = [handle for handle, title in windows if "Starsector" in title and not ERROR_TITLE.search(title)]
        return (named or [handle for handle, _ in windows] or [None])[0]

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # a watcher failure must never stop the run it watches
                pass
            self._stop.wait(POLL_SECONDS)

    def start(self) -> "WindowWatcher":
        if sys.platform == "win32":
            self._thread = threading.Thread(target=self._run, name="window-watch", daemon=True)
            self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
