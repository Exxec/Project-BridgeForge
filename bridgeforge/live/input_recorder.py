"""Who had the desktop during a live run: one sample about every second (ROADMAP-3 98.13).

For 98.4 (2026-11-26) a PowerShell recorder ran beside each live run on Test1 and wrote, once a second, the cursor position,
whether the foreground window belonged to the game, and the system's last-input tick. A `game` stretch broken by another
window while the game runs means a person took the desktop, or a dialog came up: the run's clicks then went elsewhere. This is
that recorder inside the harness, with the same columns, so every launch keeps the record.

It records no screenshot and no window title (owner rule: never capture the owner's desktop), only whether the foreground
window's process is one of the game's. The foreground column reads `game`, `other` (another window), `none` (no foreground
window, a locked screen for one) or `gone` (no game process: before it started or after it ended), and `error` when a sample
failed. Outside Windows, and in the test suite (BRIDGEFORGE_INPUT_RECORDER=off), it records nothing. Nothing about it can stop
or slow the run: a failed sample is a row, a file that cannot be written is no record.
"""
from __future__ import annotations

import os
import sys
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from itertools import groupby
from pathlib import Path

HEADER = "time,tick_ms,last_input_tick_ms,idle_ms,cursor_x,cursor_y,foreground"
KIND_COLUMN = 6
INTERVAL_SECONDS = 1.0
PIDS_EVERY = 5  # the game's process ids are re-read every fifth sample, as the PowerShell recorder did
TICK_WRAP = 2 ** 32
SWITCH_ENV = "BRIDGEFORGE_INPUT_RECORDER"  # "off": record nothing (tests/support.py sets it, so the suite never samples a desktop)
AWAY_KINDS = ("other", "none")  # the game not in front while it runs


class _User32:
    """The four user32 calls and GetTickCount, typed: a handle is pointer-sized on 64-bit Windows (review, 2026-11-27)."""

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class LastInput(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        self._ctypes, self._LastInput, self._wintypes = ctypes, LastInput, wintypes
        user32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetForegroundWindow.argtypes = []
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetLastInputInfo.restype = wintypes.BOOL
        user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LastInput)]
        user32.GetCursorPos.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        kernel32.GetTickCount.restype = wintypes.DWORD
        kernel32.GetTickCount.argtypes = []
        self._user32, self._kernel32 = user32, kernel32

    def tick(self) -> int:
        return int(self._kernel32.GetTickCount())

    def last_input(self) -> int | None:
        info = self._LastInput(self._ctypes.sizeof(self._LastInput), 0)
        return int(info.dwTime) if self._user32.GetLastInputInfo(self._ctypes.byref(info)) else None

    def cursor(self) -> tuple[int, int] | None:
        point = self._wintypes.POINT()
        return (point.x, point.y) if self._user32.GetCursorPos(self._ctypes.byref(point)) else None

    def foreground_owner(self) -> int | None:
        """The process id owning the foreground window, or None when there is none."""
        window = self._user32.GetForegroundWindow()
        if not window:
            return None
        owner = self._wintypes.DWORD(0)
        self._user32.GetWindowThreadProcessId(window, self._ctypes.byref(owner))
        return int(owner.value) or None


def sample(api, game_pids: set[int]) -> tuple[int, int | None, int | None, int | None, str]:
    """(tick, last input tick, cursor x, cursor y, foreground kind); a call that failed leaves its field empty."""
    last_input = api.last_input()  # read before the tick, so the input is never later than it
    tick = api.tick() & 0xFFFFFFFF
    cursor = api.cursor() or (None, None)
    owner = api.foreground_owner()
    if not game_pids:
        kind = "gone"
    elif owner is None:
        kind = "none"
    else:
        kind = "game" if owner in game_pids else "other"
    return tick, last_input, cursor[0], cursor[1], kind


def row(tick: int | None, last_input: int | None, x: int | None, y: int | None, kind: str, now: time.struct_time | None = None) -> str:
    """One CSV row; idle is the tick distance, across the 49.7-day wrap; an unknown field is empty."""
    idle = (tick - last_input) % TICK_WRAP if tick is not None and last_input is not None else None
    cells = [time.strftime("%H:%M:%S", now or time.localtime()), tick, last_input, idle, x, y, kind]
    return ",".join("" if cell is None else str(cell) for cell in cells)


def _append(path: Path, line: str) -> None:
    """One line, the file opened and closed for it: no handle is held, so the run's folder is never locked by the recorder."""
    with path.open("a", encoding="ascii", newline="\n") as out:
        out.write(line + "\n")


@contextmanager
def recording(path: Path, game_pids: Callable[[], set[int]], *, interval: float = INTERVAL_SECONDS,
              take: Callable[[set[int]], tuple] | None = None):
    """Write `path` (CSV, HEADER) about once each `interval` while the block runs, and stop with it. Yields the path, or None when
    nothing is recorded (outside Windows, switched off, or the file cannot be started)."""
    if take is None and (sys.platform != "win32" or os.environ.get(SWITCH_ENV, "").strip().lower() == "off"):
        yield None
        return
    path = Path(path)
    try:
        path.unlink(missing_ok=True)  # an earlier run with the same test id must not pass for this one
        _append(path, HEADER)
    except OSError:
        yield None
        return
    if take is None:
        api = _User32()

        def take(pids: set[int]) -> tuple:
            return sample(api, pids)

    stop = threading.Event()

    def run() -> None:
        pids: set[int] = set()
        started, count = time.monotonic(), 0
        while not stop.is_set():
            try:
                if count % PIDS_EVERY == 0:
                    pids = set(game_pids())
                if stop.is_set():  # a slow process lookup ended after the block: write nothing more
                    return
                line = row(*take(pids))
            except Exception:  # a failed sample is a row, never the end of the record (review, 2026-11-27)
                line = row(None, None, None, None, "error")
            try:
                _append(path, line)
            except OSError:
                return
            count += 1
            stop.wait(max(0.0, started + count * interval - time.monotonic()))  # about one row a second, whatever a row cost

    worker = threading.Thread(target=run, name="bf-input-recorder", daemon=True)
    worker.start()
    try:
        yield path
    finally:
        stop.set()
        worker.join(timeout=5)


def segments(text: str) -> list[tuple[str, int]]:
    """The foreground kinds in order, each with its run of rows (about a second each): [("game", 210), ("other", 61), ...]."""
    kinds = [line.split(",")[KIND_COLUMN].strip() for line in text.splitlines()[1:] if line.count(",") >= KIND_COLUMN]
    return [(kind, len(list(group))) for kind, group in groupby(kinds)]


def summary(path: Path) -> dict | None:
    """{"file", "samples", "segments", "away_seconds", "errors"}: away is the time the game, once it had first come to the front,
    was not in front while its process still ran (another window or none; `gone` after it exited is not away); None without
    a record."""
    try:
        text = Path(path).read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    found = segments(text)
    games = [index for index, (kind, _seconds) in enumerate(found) if kind == "game"]
    away = sum(seconds for kind, seconds in found[games[0]:] if kind in AWAY_KINDS) if games else 0
    return {"file": str(path), "samples": sum(seconds for _kind, seconds in found),
            "segments": " | ".join(f"{kind} {seconds}s" for kind, seconds in found), "away_seconds": away,
            "errors": sum(seconds for kind, seconds in found if kind == "error")}


def describe(found: dict | None) -> str | None:
    if not found:
        return None
    if not found["samples"]:
        return "desktop: no samples (the recorder wrote none)"
    if found["away_seconds"]:
        return (f"desktop: {found['segments']}: the game was not in front for {found['away_seconds']} s while it ran (another "
                "window or none: a person, or a dialog); read the run's clicks with that in mind")
    return f"desktop: {found['segments']}"
