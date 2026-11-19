"""Start the rig's game directly, without its launcher, and place its window (ROADMAP-3 95.4, from 93.21).

Until 95.4 every Test1 run went through `bridgeforge-state/live-wrappers/live_direct.py` and `smoke_direct.py`, which patched
BridgeForge at run time. This is that wrapper's behaviour, built in:
- the game skips its launcher when started with `-DlaunchDirect=true -DstartRes=WxH -DstartFS=false -DstartSound=true` in
  JAVA_TOOL_OPTIONS. It does so only when a licence key is stored for the Windows user (93.20, 93.21). The options go to the
  game process alone (`launch.start_game(env=...)`), not to this process;
- with no launcher to click, the click step moves the game window once instead, so that the client area's top edge sits at
  screen y `client_top`. live_run's click fractions are for a 1920x1440 client at UI scale 1; on a 1080-pixel screen,
  client_top -200 puts every measured point (24-76% of the height) at y 146-894, above the taskbar (Test1, 2026-11-17);
- the launcher's resolution preference is pinned to the same size for the run, and the owner's value is restored after it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

RESOLUTION = re.compile(r"^(\d{3,5})x(\d{3,5})$")
DEFAULT_RESOLUTION = "1920x1440"


@dataclass(frozen=True)
class DirectStart:
    resolution: str = DEFAULT_RESOLUTION
    client_top: int | None = None

    def __post_init__(self) -> None:
        if not RESOLUTION.match(self.resolution):
            raise ValueError(f"resolution is WIDTHxHEIGHT, e.g. 1920x1440; got {self.resolution!r}")

    def java_options(self) -> str:
        return f"-DlaunchDirect=true -DstartRes={self.resolution} -DstartFS=false -DstartSound=true"

    def env(self, base: dict[str, str] | None = None) -> dict[str, str]:
        """The game process's environment: `base` (this process's by default) with the direct-start options added to any
        JAVA_TOOL_OPTIONS already there."""
        env = dict(os.environ if base is None else base)
        existing = env.get("JAVA_TOOL_OPTIONS", "").strip()
        env["JAVA_TOOL_OPTIONS"] = f"{existing} {self.java_options()}".strip()
        return env

    def pinned_prefs(self, live_pinned: dict[str, str]) -> dict[str, str]:
        return {**live_pinned, "resolution": self.resolution}


def place_window(rig: Path, process, client_top: int | None) -> str | None:
    """Stands in for the launcher click: nothing to press. With `client_top`, move the game window once it exists (None until
    then, so the caller asks again). Windows only; elsewhere, and without `client_top`, nothing is moved."""
    if client_top is None:
        return "direct start: no launcher to click"
    import sys

    if sys.platform != "win32":
        return "direct start: window placement is Windows only"
    import ctypes
    from ctypes import wintypes

    from bridgeforge import game_click
    from bridgeforge.boot_test import _running_java_under
    from bridgeforge.launcher_click import descendant_pids

    pids = {j["pid"] for j in _running_java_under(rig) if isinstance(j.get("pid"), int)} | descendant_pids(process.pid)
    found = game_click.game_window(pids)
    if found is None:
        return None
    hwnd, left, top, _, _ = found
    user32 = ctypes.windll.user32
    frame = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(frame))
    # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE; the window keeps its frame's offset from the client area.
    user32.SetWindowPos(hwnd, 0, 0 - (left - frame.left), client_top - (top - frame.top), 0, 0, 0x0001 | 0x0004 | 0x0010)
    after = game_click.game_window(pids)
    return f"direct start: client {after[3]}x{after[4]} at {after[1]},{after[2]}" if after else "direct start: window moved"
