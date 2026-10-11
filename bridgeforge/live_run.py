"""`probe-group live`: play a probe group's live run without a person (ROADMAP 60f(2)).

Drives the real game with real mouse clicks (game_click): launcher Play, New Game with the default chip and the first
choice on every screen, the campaign probe's one in-game day (it runs and ends by itself), then the probe combat mission
once per round. Every stage is confirmed from the game's own log, never from the screen: a stage whose log line does not
come in time ends the run as LIVE_STUCK naming it, and the rig game is stopped. Screen positions were measured on
2026-10-11 from the unmodified RC8 flow (client-area fractions, see game_click); a mod that adds its own New Game screen
or reorders the mission list will stop the run at the stage where the log stays silent, which is the intended failure.
The owner must leave the mouse and keyboard alone while it runs (about three minutes after loading).
"""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# Client-area fractions of the game window (1280x960 view), measured 2026-10-11.
MAIN_MENU_NEW_GAME = (0.7195, 0.4625)
MAIN_MENU_MISSIONS = (0.719, 0.4385)
NEW_CHIP_GENERATE_NAME = (0.645, 0.371)
NEW_CHIP_CONTINUE = (0.286, 0.618)
FIRST_CHOICE = (0.40, 0.618)  # occupation and the extra fleet member: row 1 each time (wide text)
DIFFICULTY_NORMAL = (0.30, 0.618)  # "Normal" is short text: a click at x 0.40 misses it (LIVETEST-20261011 then took Easy)
SKIP_TUTORIAL = (0.30, 0.6375)
START_GAME = (0.293, 0.459)
ESCAPE_KEY, SPACE_KEY = 0x1B, 0x20
GAME_MENU_EXIT = (0.602, 0.580)
GAME_MENU_EXIT_OK = (0.498, 0.549)
MISSION_LIST_SCROLL_POINT = (0.31, 0.60)
PROBE_MISSION = (0.336, 0.729)  # the probe's mission is the last entry in the list
PLAY_MISSION = (0.6875, 0.752)
DEPLOY_ALL = (0.577, 0.635)
DEPLOY = (0.526, 0.635)
COMBAT_CONTINUE = (0.50, 0.745)

MENU_LOADED = "Reading save data from"
CAMPAIGN_END = "probe|INFO|campaign|END"
COMBAT_END = "probe|INFO|combat|END"
ROUND_LINE = re.compile(r"combat-round\|INFO\|round (\d+) of (\d+)")


@dataclass
class Hands:
    """What the run does to the game; the real one is built from game_click, tests pass fakes."""

    click: Callable[[float, float], None]
    key: Callable[[int], None]
    scroll: Callable[[float, float, int], None]
    sleep: Callable[[float], None] = time.sleep
    alive: Callable[[], bool] = lambda: True
    front: Callable[[], None] = lambda: None


@dataclass
class LiveResult:
    verdict: str  # LIVE_DONE | LIVE_STUCK
    stage: str | None = None
    detail: str | None = None
    rounds: int = 0
    log: str | None = None
    stages: list[str] = field(default_factory=list)


def _log_text(log: Path) -> str:
    try:
        return log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def wait_for(log: Path, marker: str, timeout: float, hands: Hands, since: int = 0, poll: float = 1.0) -> bool:
    """True once `marker` is in the log after offset `since`; False on timeout or when the game has exited."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker in _log_text(log)[since:]:
            return True
        if not hands.alive():
            return False
        hands.sleep(poll)
    return marker in _log_text(log)[since:]


def new_game(hands: Hands) -> None:
    """Main menu to the campaign map's first frame: default chip, first choice everywhere, Normal, skip the tutorial."""
    for point, pause in ((MAIN_MENU_NEW_GAME, 3), (NEW_CHIP_GENERATE_NAME, 1.5), (NEW_CHIP_CONTINUE, 4),
                         (FIRST_CHOICE, 4), (FIRST_CHOICE, 4), (DIFFICULTY_NORMAL, 4), (SKIP_TUTORIAL, 12), (START_GAME, 1)):
        hands.front()
        hands.click(*point)
        hands.sleep(pause)


def to_mission_list(hands: Hands) -> None:
    """From the campaign map (or the combat result) to the main menu's mission list."""
    hands.front()
    hands.key(ESCAPE_KEY)
    hands.sleep(1.5)
    hands.click(*GAME_MENU_EXIT)
    hands.sleep(2)
    hands.click(*GAME_MENU_EXIT_OK)
    hands.sleep(8)
    hands.click(*MAIN_MENU_MISSIONS)
    hands.sleep(3)


def play_probe_combat(hands: Hands) -> None:
    hands.front()
    hands.scroll(*MISSION_LIST_SCROLL_POINT, -30)
    hands.sleep(1)
    hands.click(*PROBE_MISSION)
    hands.sleep(1.5)
    hands.click(*PLAY_MISSION)
    hands.sleep(6)
    hands.click(*DEPLOY_ALL)
    hands.sleep(1)
    hands.click(*DEPLOY)
    hands.sleep(2)
    hands.key(SPACE_KEY)


def drive(log: Path, hands: Hands, menu_timeout: float = 240, campaign_timeout: float = 600, combat_timeout: float = 240) -> LiveResult:
    """Run the whole live sequence against a started game whose stdout is `log`."""
    result = LiveResult("LIVE_STUCK", log=str(log))

    def stuck(stage: str, detail: str) -> LiveResult:
        result.stage, result.detail = stage, detail
        return result

    if not wait_for(log, MENU_LOADED, menu_timeout, hands):
        return stuck("main-menu", "the game never logged that the main menu was up")
    result.stages.append("main-menu")
    hands.sleep(20)  # the menu is drawn some seconds after its log line
    new_game(hands)
    if not wait_for(log, CAMPAIGN_END, campaign_timeout, hands):
        return stuck("new-game", "no 'campaign END' probe line: a screen did not take the click, generation failed, or the probe is not enabled")
    result.stages.append("campaign")
    to_mission_list(hands)
    rounds_total, round_no = 1, 0
    while round_no < rounds_total:
        offset = len(_log_text(log))
        play_probe_combat(hands)
        if not wait_for(log, COMBAT_END, combat_timeout, hands, since=offset):
            return stuck(f"combat-round-{round_no + 1}", "no 'combat END' probe line after starting the probe mission")
        round_no += 1
        result.rounds = round_no
        found = ROUND_LINE.findall(_log_text(log)[offset:])
        if found:
            rounds_total = max(rounds_total, int(found[-1][1]))
        result.stages.append(f"combat-{round_no}")
        if round_no < rounds_total:
            hands.front()
            hands.click(*COMBAT_CONTINUE)
            hands.sleep(4)
    result.verdict = "LIVE_DONE"
    return result


def real_hands(rig: Path) -> Hands:
    """Hands on the game under `rig`: foreground and click through game_click, aliveness from the rig's java processes."""
    from . import game_click
    from .boot_test import _running_java_under

    def pids() -> set[int]:
        return {item["pid"] for item in _running_java_under(rig) if isinstance(item.get("pid"), int)}

    def geometry():
        found = game_click.game_window(pids())
        if found is None:
            raise RuntimeError("the game window is gone")
        return found

    def front() -> None:
        game_click.bring_to_front(geometry()[0])

    return Hands(click=lambda fx, fy: game_click.click_fraction(geometry(), fx, fy),
                 key=game_click.press_key,
                 scroll=lambda fx, fy, n: game_click.scroll(geometry(), fx, fy, n),
                 alive=lambda: bool(pids()), front=front)


def live_run(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", menu_timeout: float = 240) -> LiveResult:
    """Start the rig game, click through the launcher, drive the run, then stop the rig's java. Refuses like boot_test."""
    from .boot_test import _is_link, _running_java_under, _terminate_tree
    from .launcher_click import click_launcher_once

    rig = Path(rig).expanduser().resolve()
    if not _is_link(rig / "starsector-core"):
        return LiveResult("LIVE_STUCK", "refused", f"{rig / 'starsector-core'} is not a junction/symlink; refusing to run in a shared install")
    if _running_java_under(rig):
        return LiveResult("LIVE_STUCK", "refused", "java is already running under the rig; close it first")
    bat = rig / bat_name
    if not bat.is_file():
        return LiveResult("LIVE_STUCK", "refused", f"launcher not found: {bat}")
    logs = rig / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log, err = logs / f"{test_id}.stdout.log", logs / f"{test_id}.stderr.log"
    process = subprocess.Popen(f'cmd.exe /c ""{bat}" > "{log}" 2> "{err}""', cwd=str(rig))
    hands = real_hands(rig)
    base_alive = hands.alive
    clicked = {"done": False}

    def alive_and_click() -> bool:
        # The launcher window waits for Play before the game logs anything (owner, 2026-10-11).
        if not clicked["done"]:
            pids = {item["pid"] for item in _running_java_under(rig) if isinstance(item.get("pid"), int)}
            if click_launcher_once(pids):
                clicked["done"] = True
        return base_alive() or process.poll() is None

    hands.alive = alive_and_click
    try:
        return drive(log, hands, menu_timeout=menu_timeout)
    finally:
        for java in _running_java_under(rig):
            if isinstance(java.get("pid"), int):
                _terminate_tree(java["pid"])
        if process.poll() is None:
            _terminate_tree(process.pid)
