"""Keep the display (and the machine) awake while a live run drives the game (ROADMAP-3 93.58).

Test1 turns its display off after 180 s without input (power plan, VIDEOIDLE 0xb4). Live runs started after an idle spell
reached the campaign, then the harness's Escape and menu clicks never reached the game (P962KR, P962KR2: LIVE_STUCK at the
first combat round, the log silent after the probe's checks); the same group passed when a background process held the
display on (P962KR3). Windows' SetThreadExecutionState with ES_DISPLAY_REQUIRED does this for the calling thread until it
is reset; elsewhere this is a no-op.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Iterator

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _set_state(flags: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))


@contextmanager
def display_kept_on() -> Iterator[bool]:
    """Hold the display and system on inside the block; yields whether Windows accepted the request."""
    held = _set_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    try:
        yield held
    finally:
        if held:
            _set_state(ES_CONTINUOUS)  # back to the power plan's own timeouts
