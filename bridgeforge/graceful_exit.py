"""Close the game gracefully when the probe says its run is done (ROADMAP item 75 R1, exit evidence).

The probe writes `<rig>/saves/common/bf_probe_done.data` (JSON with the manifest id) when the campaign checks and the last combat round
have ended. The harness waits for that file, checks its manifest id is this run's, posts WM_CLOSE to the game window, and waits for
the process to leave by itself: NATURAL with its return code, or KILLED when the marker never came, named another run, the window was
not found or the game was still up at the bound (the caller then kills the tree, as before). A code is never inferred.
"""
from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from pathlib import Path

DONE_FILE = "bf_probe_done.data"  # SettingsAPI appends ".data" to the name the probe writes ("bf_probe_done")
WM_CLOSE = 0x0010
DONE_WAIT_SECONDS = 20.0
CLOSE_WAIT_SECONDS = 60.0
DONE_POLL_SECONDS = 1.0


def done_path(rig: Path) -> Path:
    return Path(rig) / "saves" / "common" / DONE_FILE


def clear_done(rig: Path) -> None:
    """Remove a marker an earlier run left, so only this run's can be seen."""
    try:
        done_path(rig).unlink()
    except OSError:
        pass


def read_done(rig: Path) -> dict | None:
    try:
        data = json.loads(done_path(rig).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def wait_for_done(rig: Path, manifest_id: str, timeout: float = DONE_WAIT_SECONDS, *, sleep: Callable[[float], None] = time.sleep,
                  clock: Callable[[], float] = time.monotonic) -> bool:
    """True once the marker exists and carries this run's manifest id; a marker naming another id is never accepted."""
    deadline = clock() + timeout
    while True:
        marker = read_done(rig)
        if marker is not None and marker.get("manifest_id") == manifest_id:
            return True
        if clock() >= deadline:
            return False
        sleep(DONE_POLL_SECONDS)


def post_close(pids: set[int]) -> bool:
    """Post WM_CLOSE to the game's window (what the title bar's close button does). False when no window was found."""
    if sys.platform != "win32":
        return False
    from . import game_click

    found = game_click.game_window(pids)
    if found is None:
        return False
    game_click._user32().PostMessageW(found[0], WM_CLOSE, 0, 0)
    return True


def graceful_close(rig: Path, manifest_id: str, process, *, settle: Callable[..., tuple[str, int | None]], pids: Callable[[], set[int]],
                   java_left: Callable[[], bool], close: Callable[[set[int]], bool] | None = None, done_wait: float | None = None,
                   close_wait: float | None = None, sleep: Callable[[float], None] = time.sleep,
                   clock: Callable[[], float] = time.monotonic) -> tuple[str, int | None]:
    """(observed, code) after asking the finished game to close: KILLED with no code unless it left by itself within `close_wait`."""
    from .exit_observation import KILLED

    if not wait_for_done(rig, manifest_id, DONE_WAIT_SECONDS if done_wait is None else done_wait, sleep=sleep, clock=clock):
        return KILLED, None
    if not (close or post_close)(pids()):
        return KILLED, None
    return settle(process, CLOSE_WAIT_SECONDS if close_wait is None else close_wait, sleep=sleep, clock=clock, java_left=java_left)
