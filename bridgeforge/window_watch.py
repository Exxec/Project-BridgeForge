"""Watch the rig game's windows while it runs (the single launch path, launch.py, starts it for every caller).

Starsector shows a Java Fatal Error only as a modal dialog; it never reaches the redirected log. This records the text of every new
visible top-level window of the game's processes to `<rig>/logs/<TESTID>.windows.txt` in the format log-triage reads
(`HH:mm:ss window: '<title>'`, `HH:mm:ss dialog: '<title>' text: '<text>'`), takes a screenshot of a second or error-titled window
(`<TESTID>-window<N>.png`, at most 10) and one when java runs 180 s without the main menu (`<TESTID>-no-main-menu.png`).
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


def save_screenshot(path: Path) -> bool:
    """The whole virtual screen as a PNG (PowerShell + System.Drawing)."""
    import subprocess

    quoted = str(path).replace("'", "''")
    script = ("Add-Type -AssemblyName System.Windows.Forms, System.Drawing; $v=[System.Windows.Forms.SystemInformation]::VirtualScreen; "
              "$b=New-Object System.Drawing.Bitmap $v.Width,$v.Height; $g=[System.Drawing.Graphics]::FromImage($b); "
              f"$g.CopyFromScreen($v.Left,$v.Top,0,0,$b.Size); $b.Save('{quoted}', [System.Drawing.Imaging.ImageFormat]::Png)")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=60, check=True)
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
                self._screenshot(self.logs / f"{self.test_id}-window{self._shots}.png")
        if pids and not self._menu_reached and not self._suspect_shot and self._clock() - self._started > NO_MENU_SECONDS:
            self._suspect_shot = True
            self._screenshot(self.logs / f"{self.test_id}-no-main-menu.png")

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
