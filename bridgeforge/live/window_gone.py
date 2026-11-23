"""A game window that vanishes mid-run (ROADMAP-3 93.50): the error real hands raise, and the verdict text quoting the log.

SR7-LIVE-0985a-20261117 raised "the game window is gone" from New Game's click and gave no verdict. live_run.drive and
save_reload_run.drive_reload turn this error into LIVE_STUCK at the stage in progress, with `detail(log_text)`.
"""
from __future__ import annotations

TAIL_LINES = 3  # log lines quoted when the window vanishes


class GameWindowGone(RuntimeError):
    """The game's window vanished mid-run (it closed or crashed). A RuntimeError still, so a handler that caught the old error
    behaves as before."""


def detail(log_text: str) -> str:
    """The LIVE_STUCK detail for a vanished window: what happened and the log's last non-empty lines."""
    last = [line.strip()[:200] for line in log_text.splitlines() if line.strip()][-TAIL_LINES:]
    return "the game window is gone (the game closed or crashed); the log's last lines: " + (" | ".join(last) or "(the log is empty)")
