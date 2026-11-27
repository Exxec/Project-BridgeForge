"""A game window that vanishes mid-run (ROADMAP-3 93.50) or will not come to the front (98.12): the errors, and the verdict text.

SR7-LIVE-0985a-20261117 raised "the game window is gone" from New Game's click and gave no verdict. live_run.drive turns
this error into LIVE_STUCK at the stage in progress, with `detail(log_text)`, and so does save_reload_run.drive_reload
(88.19/88.22).

`game_click.bring_to_front` returns whether the game is in front, and `Hands.front()` dropped it, so a click or key after a
failed foreground landed in whatever window was in front (98.12). `checked_front` retries once and then raises GameNotInFront:
`live_run.drive` and `save_reload_run.drive_reload` end LIVE_STUCK with a screenshot, and `duel_run.run_duel` reports it as
the run's problem. The retry's `bring_to_front` taps Alt once more; nothing else is sent.
"""
from __future__ import annotations

from collections.abc import Callable

TAIL_LINES = 3  # log lines quoted when the window vanishes


class GameWindowGone(RuntimeError):
    """The game's window vanished mid-run (it closed or crashed). A RuntimeError still, so a handler that caught the old error
    behaves as before."""


class GameNotInFront(RuntimeError):
    """The game window did not come to the front, also on a second try: the next click or key would land in another window."""


def checked_front(front: Callable[[], bool | None], note: Callable[[str], None] | None = None) -> Callable[[], None]:
    """`front`, retried once when it reports False and then raising GameNotInFront. None (test fakes, which have no other window)
    counts as in front. `note` records each failure, as `live_run.recording` does in the actions log."""
    def call() -> None:
        if front() is not False:
            return
        if note is not None:
            note("front failed: the game window is not in front; trying again")
        if front() is False:
            if note is not None:
                note("front failed again; stopping")
            raise GameNotInFront("the game window did not come to the front, also on a second try, so nothing more was sent to it")
    return call


def detail(log_text: str) -> str:
    """The LIVE_STUCK detail for a vanished window: what happened and the log's last non-empty lines."""
    last = [line.strip()[:200] for line in log_text.splitlines() if line.strip()][-TAIL_LINES:]
    return "the game window is gone (the game closed or crashed); the log's last lines: " + (" | ".join(last) or "(the log is empty)")
