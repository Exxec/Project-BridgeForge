"""Who had the desktop during a live run: one sample a second (ROADMAP-3 98.13).

For 98.4 (2026-11-26) a PowerShell recorder ran beside each live run on Test1 and wrote, once a second, the cursor position,
whether the foreground window belonged to the game, and the system's last-input tick. A `game` stretch broken by `other`
while the game runs means a person took the desktop, or a dialog came up: the run's clicks then went elsewhere. This is that
recorder inside the harness, with the same columns, so every run keeps the record.

It records no screenshot and no window title (owner rule: never capture the owner's desktop), only whether the foreground
window's process is one of the game's. Outside Windows it records nothing.
"""
from __future__ import annotations

import ctypes
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


class _LastInput(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _windows_sample(game_pids: set[int]) -> tuple[int, int, int, int, str]:
    """(tick, last input tick, cursor x, cursor y, foreground kind) from user32 and kernel32."""
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    info = _LastInput(ctypes.sizeof(_LastInput), 0)
    user32.GetLastInputInfo(ctypes.byref(info))
    point = _Point()
    user32.GetCursorPos(ctypes.byref(point))
    window = user32.GetForegroundWindow()
    owner = ctypes.c_ulong(0)
    if window:
        user32.GetWindowThreadProcessId(window, ctypes.byref(owner))
    kind = "none" if not window else ("game" if owner.value in game_pids else "other")
    return kernel32.GetTickCount() & 0xFFFFFFFF, info.dwTime, point.x, point.y, kind


def row(tick: int, last_input: int, x: int, y: int, kind: str, now: time.struct_time | None = None) -> str:
    """One CSV row; idle is the tick distance, across the 49.7-day wrap."""
    idle = (tick - last_input) % TICK_WRAP
    return f"{time.strftime('%H:%M:%S', now or time.localtime())},{tick},{last_input},{idle},{x},{y},{kind}"


@contextmanager
def recording(path: Path, game_pids: Callable[[], set[int]], *, interval: float = INTERVAL_SECONDS,
              sample: Callable[[set[int]], tuple[int, int, int, int, str]] | None = None):
    """Write `path` (CSV, HEADER) once each `interval` while the block runs. Outside Windows, and when the file cannot be
    written, nothing is recorded and the run goes on: the record is evidence, never a reason to stop."""
    if sample is None and sys.platform != "win32":
        yield None
        return
    take = sample or _windows_sample
    stop = threading.Event()

    def run() -> None:
        pids: set[int] = set()
        try:
            with Path(path).open("w", encoding="ascii", newline="\n") as out:
                out.write(HEADER + "\n")
                count = 0
                while not stop.is_set():
                    if count % PIDS_EVERY == 0:
                        pids = set(game_pids())
                    out.write(row(*take(pids)) + "\n")
                    out.flush()
                    count += 1
                    stop.wait(interval)
        except Exception:  # evidence only (OSError writing, a failed user32 call): the run never stops for it
            return

    worker = threading.Thread(target=run, name="bf-input-recorder", daemon=True)
    worker.start()
    try:
        yield Path(path)
    finally:
        stop.set()
        worker.join(timeout=5)


def segments(text: str) -> list[tuple[str, int]]:
    """The foreground kinds in order, each with its run of seconds: [("game", 210), ("other", 61), ...]."""
    kinds = [line.split(",")[KIND_COLUMN] for line in text.splitlines()[1:] if line.count(",") >= KIND_COLUMN]
    return [(kind, len(list(group))) for kind, group in groupby(kinds)]


def summary(path: Path) -> dict | None:
    """{"file", "samples", "segments", "away_seconds"}: away is the time the desktop was not the game's after the game first came
    to the front and before it was last there; None when there is no record."""
    try:
        text = Path(path).read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    found = segments(text)
    games = [index for index, (kind, _seconds) in enumerate(found) if kind == "game"]
    away = sum(seconds for kind, seconds in found[games[0]:games[-1]] if kind != "game") if games else 0
    return {"file": str(path), "samples": sum(seconds for _kind, seconds in found),
            "segments": " | ".join(f"{kind} {seconds}s" for kind, seconds in found), "away_seconds": away}


def describe(found: dict | None) -> str | None:
    if not found:
        return None
    if found["away_seconds"]:
        return (f"desktop: {found['segments']}: another window had the desktop for {found['away_seconds']} s while the game ran "
                "(a person, or a dialog); read the run's clicks with that in mind")
    return f"desktop: {found['segments']}"
