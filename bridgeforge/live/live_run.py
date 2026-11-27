"""`probe-group live`: play a probe group's live run without a person (ROADMAP 60f(2)).

Drives the real game with real mouse clicks (game_click): launcher Play, New Game with the default chip and the first
choice on every screen, the campaign probe's one in-game day (it runs and ends by itself), then the probe combat mission
once per round. Every stage is confirmed from the game's own log, never from the screen: a stage whose log line does not
come in time ends the run as LIVE_STUCK naming it, and the rig game is stopped. Screen positions were measured on
2026-10-11 from the unmodified RC8 flow (client-area fractions, see game_click); a mod that adds its own New Game screen
or reorders the mission list will stop the run at the stage where the log stays silent, which is the intended failure.
A fixed New Game flow that stops on a mod's own page is continued by the generic screen-reading flow (new_game_generic, item 73 G1) after NEW_GAME_GRACE seconds.
The owner must leave the mouse and keyboard alone while it runs (about three minutes after loading).
"""
from __future__ import annotations

import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from bridgeforge.log_triage import MAIN_MENU_RE
from bridgeforge.launch import EXIT_POLL_SECONDS, GameRefused, LaunchNoProcess, settle_exit  # noqa: F401  (re-exported: callers and tests import them from here)
from bridgeforge.live.window_gone import (GameNotInFront, GameWindowGone, checked_front,  # noqa: F401  (re-exported: 93.50, 98.12)
                                          detail as window_gone_detail)
from bridgeforge.live.main_menu import (MENU_CHECK_READS, MenuMisread, _main_menu_shown, _menu_buttons,  # noqa: F401
                                      click_menu, menu_point)  # (re-exported: save_reload_run, duel_run and tests import them from here)

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
MISSION_ROW_STEP = 0.0594  # list entries are 57 px apart in the 960 px view (measured 2026-10-11)
MAX_ROWS_REACHABLE = 7  # entries above the last one that show without scrolling back up
VISIBLE_MISSION_ROWS = 9
FIRST_MISSION_ROW_Y = 0.248  # centre of the top slot (238 px of 960)
VANILLA_MISSION_ROWS = 14  # RC8's own mission_list.csv; live_run reads the real count from the rig's core

NEW_GAME_GRACE = 150.0  # seconds a fixed New Game flow gets to reach the campaign before the generic flow continues
MENU_LOADED = "Reading save data from"
# Fresh rigs have no save descriptors to enumerate; actual playback also confirms the menu.
MENU_READY = re.compile(re.escape(MENU_LOADED) + "|" + MAIN_MENU_RE.pattern)
CAMPAIGN_END = "probe|INFO|campaign|END"
COMBAT_START = "probe|INFO|combat|START"
COMBAT_END = "probe|INFO|combat|END"
# The probe logs 'combat START' about 2.5 s after the game defines the mission for a battle (G2B-LIVE-0985a-20261117), well inside
# play_probe_combat's clicks. A restart whose clicks start nothing logs nothing: UAF-LIVE-0985a-20261117 and SR3-LIVE-0985a-20261117
# waited out the whole combat timeout in round 2 (93.37). The start is confirmed after the clicks, with a screenshot and one retry.
COMBAT_START_TIMEOUT = 45.0
# The game defines the probe mission again 1.8 to 2.4 s after each battle ends (the 2026-11-17 runs); Continue is clicked after
# that line, not into the transition.
POST_BATTLE_SETTLE = 15.0
FINGERPRINT_SAVED = "fingerprint|INFO|save|cmdSave returned true"  # save_reload stage (next probe version)
# 93.59: with save_after_checks the probe saves right after its first 'campaign END'. Keys and clicks sent during the save are lost:
# P962BS4 (27.8 s from END to 'cmdSave returned') and P962YC2 (20.3 s) stayed on the campaign map, P962KR3 (2.3 s) passed. The run
# leaves the campaign once the probe has logged the save's result (INFO or FAIL).
PROBE_SAVED = re.compile(r"BF-PROBE\|[^|\r\n]+\|save\|(?:INFO|FAIL)\|campaign\|cmdSave returned")
PROBE_SAVE_TIMEOUT = 180.0
PROBE_SAVE_SETTLE = 3.0  # the save's own overlay closes after the line
ROUND_LINE = re.compile(r"combat-round\|INFO\|round (\d+) of (\d+)")


@dataclass
class Hands:
    """What the run does to the game; the real one is built from game_click, tests pass fakes."""

    click: Callable[[float, float], None]
    key: Callable[[int], None]
    scroll: Callable[[float, float, int], None]
    sleep: Callable[[float], None] = time.sleep
    alive: Callable[[], bool] = lambda: True
    front: Callable[[], bool | None] = lambda: None  # False: the game did not come to the front (98.12, `checked_front`)
    geometry: Callable[[], tuple] | None = None
    capture: Callable[[Path], bool] | None = None  # a screenshot of the game window to this path; True once written


@dataclass
class LiveResult:
    verdict: str  # LIVE_DONE | LIVE_STUCK
    stage: str | None = None
    detail: str | None = None
    rounds: int = 0
    log: str | None = None
    stages: list[str] = field(default_factory=list)
    # 96.9: every key, click and scroll with the run log's size and the seconds since the run began, so a stall can be read
    # against the game's own lines (93.59 took a manual comparison of two logs).
    actions: list[dict] = field(default_factory=list)


def recording(hands: Hands, log: Path, actions: list[dict]) -> Hands:
    """`hands`, with each key, click and scroll appended to `actions` as {"t", "action", "log_bytes"}, and a front() that retries
    once and then stops the run, noting each failure (98.12, `checked_front`)."""
    start = time.monotonic()

    def note(text: str) -> None:
        try:
            size = log.stat().st_size
        except OSError:
            size = None
        actions.append({"t": round(time.monotonic() - start, 1), "action": text, "log_bytes": size})

    def click(fx: float, fy: float) -> None:
        note(f"click {fx:.4f},{fy:.4f}")
        hands.click(fx, fy)

    def key(vk: int) -> None:
        note(f"key 0x{vk:02X}")
        hands.key(vk)

    def scroll(*args) -> None:
        note("scroll " + ",".join(str(a) for a in args))
        hands.scroll(*args)

    return Hands(click=click, key=key, scroll=scroll, sleep=hands.sleep, alive=hands.alive, front=checked_front(hands.front, note),
                 geometry=hands.geometry, capture=hands.capture)


def _log_text(log: Path) -> str:
    try:
        return log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def wait_for(log: Path, marker: str | re.Pattern[str], timeout: float, hands: Hands, since: int = 0, poll: float = 1.0) -> bool:
    """True once `marker` is in the log after offset `since`; False on timeout or when the game has exited."""
    def observed() -> bool:
        text = _log_text(log)[since:]
        return bool(marker.search(text)) if isinstance(marker, re.Pattern) else marker in text
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if observed():
            return True
        if not hands.alive():
            return False
        hands.sleep(poll)
    return observed()


# Ironclads (a total conversion with its own New Game rules.csv rows) asks occupation, territory, a recent event and how the skills
# were learned, then goes straight to generation: no fleet, difficulty or tutorial screens. Measured on GRP10Y2-20261011 (java 28, FR).
IRONCLADS_OCCUPATION = (0.30, 0.618)
IRONCLADS_TERRITORY = (0.40, 0.618)
IRONCLADS_RECENT = (0.40, 0.618)
IRONCLADS_SKILLS_AUTOMATIC = (0.50, 0.618)
IRONCLADS_CONTINUE = (0.30, 0.618)

# Nexerelin (0.12.2c) replaces New Game with its own dialog, which takes number keys: Next, Next, Start playing, Proceed (sector
# settings as they are), the faction letter range, the first faction. That faction's page only offers "Go back" as option 1; the
# starting fleet's Select button on the right moves on. Then Ensign, Done (background) and Start game [G] on the skill screen.
# Seen on screen at 1920x1440 windowed (GRP-EXI-AVESTA-OLD, EXPLORE-NEWGAME-20261011); Select measured at 803,311 of 1280x960.
KEY_1 = 0x31
KEY_G = 0x47
NEX_FLEET_SELECT = (803 / 1280, 311 / 960)

NEW_GAME_FLOWS: dict[str, tuple[tuple, ...]] = {
    "nexerelin": ((MAIN_MENU_NEW_GAME, 3), (NEW_CHIP_GENERATE_NAME, 1.5), (NEW_CHIP_CONTINUE, 5),
                  *((("key", KEY_1), 3),) * 6, (NEX_FLEET_SELECT, 4), (("key", KEY_1), 3), (("key", KEY_1), 3), (("key", KEY_G), 1)),
    "default": ((MAIN_MENU_NEW_GAME, 3), (NEW_CHIP_GENERATE_NAME, 1.5), (NEW_CHIP_CONTINUE, 4), (FIRST_CHOICE, 4), (FIRST_CHOICE, 4),
                (DIFFICULTY_NORMAL, 4), (SKIP_TUTORIAL, 12), (START_GAME, 1)),
    "ironclads": ((MAIN_MENU_NEW_GAME, 3), (NEW_CHIP_GENERATE_NAME, 1.5), (NEW_CHIP_CONTINUE, 4), (IRONCLADS_OCCUPATION, 4),
                  (IRONCLADS_TERRITORY, 4), (IRONCLADS_RECENT, 4), (IRONCLADS_SKILLS_AUTOMATIC, 4), (IRONCLADS_CONTINUE, 1)),
}


def new_game_flow_for(log_text: str) -> str:
    """The New Game flow the group needs: a mod with its own screens is named in the log's mod list, else the default."""
    block = _MOD_LINE.search(log_text)
    ids = {m.group("id") for m in _MOD_ENTRY.finditer(block.group("body"))} if block else set()
    if "ironclads" in ids:
        return "ironclads"
    return "nexerelin" if "nexerelin" in ids else "default"


def _screen(hands: Hands):
    """The game window as a Bitmap, or None when it cannot be read."""
    if not hands.geometry:
        return None
    try:
        import tempfile

        from bridgeforge import game_click
        from bridgeforge.screen_read import Bitmap

        with tempfile.TemporaryDirectory() as directory:
            shot = Path(directory) / "screen.bmp"
            if not game_click.capture_client(hands.geometry(), shot):
                return None
            return Bitmap.load(shot)
    except Exception:
        return None


def nexerelin_new_game(hands: Hands, max_pages: int = 12) -> None:
    """Nexerelin's New Game: press 1 one page at a time until the faction page's fleet Select button is on screen, click it, then
    Ensign, Done and Start game [G]. The number of pages before the faction page varies between runs (DEBUG-NEXSELECT-20261011:
    six presses overshot by one, and every later 1 toggled 'Go back' / the faction, the loop the owner saw)."""
    from bridgeforge.screen_read import nexerelin_fleet_select

    for point, pause in NEW_GAME_FLOWS["nexerelin"][:3]:
        hands.front()
        if point == MAIN_MENU_NEW_GAME:
            click_menu(hands, "New Game", MAIN_MENU_NEW_GAME)
            hands.sleep(max(0.0, pause - 2.5))
        else:
            hands.click(*point)
            hands.sleep(pause)
    select = None
    for _ in range(max_pages):
        hands.front()
        bitmap = _screen(hands)
        select = nexerelin_fleet_select(bitmap) if bitmap is not None else None
        if select:
            break
        hands.key(KEY_1)
        hands.sleep(3)
    hands.click(*(select or NEX_FLEET_SELECT))
    hands.sleep(4)
    for key in (KEY_1, KEY_1, KEY_G):
        hands.front()
        hands.key(key)
        hands.sleep(3)


def new_game(hands: Hands, flow: str = "default") -> None:
    """Main menu to the campaign map's first frame: default chip, first choice everywhere, Normal, skip the tutorial."""
    if flow == "nexerelin" and hands.geometry:
        nexerelin_new_game(hands)
        return
    for point, pause in NEW_GAME_FLOWS[flow]:
        hands.front()
        if point == MAIN_MENU_NEW_GAME:
            click_menu(hands, "New Game", MAIN_MENU_NEW_GAME)
            hands.sleep(max(0.0, pause - 2.5))
            continue
        if point[0] == "key":
            hands.key(point[1])
            hands.sleep(pause)
            continue
        hands.click(*point)
        hands.sleep(pause)


def generic_new_game(hands: Hands, done: Callable[[], bool], shots_dir: Path | None = None, max_pages: int = 12) -> list:
    """The generic fallback (ROADMAP item 73 G1): continue from the New Game page that is up, reading the screen page by page
    (new_game_generic.run_pages). One screenshot per page goes to `shots_dir`. Returns the page steps, empty when the screen cannot
    be read. Used after a fixed flow did not reach the campaign; the default, Ironclads and Nexerelin flows stay first."""
    from bridgeforge.new_game_generic import run_pages

    if not hands.geometry:
        return []

    def capture():
        return _screen(hands)

    hands.front()
    return run_pages(lambda fx, fy: (hands.front(), hands.click(fx, fy)), hands.sleep, capture, done, max_pages, shots_dir=shots_dir)


def _leave_campaign(hands: Hands) -> None:
    hands.front()
    hands.key(ESCAPE_KEY)
    hands.sleep(1.5)
    hands.click(*GAME_MENU_EXIT)
    hands.sleep(2)
    hands.click(*GAME_MENU_EXIT_OK)
    hands.sleep(8)


def to_mission_list(hands: Hands, shot: Path | None = None) -> bool | None:
    """From the campaign map (or the combat result) to the main menu's mission list. 96.9: when the screen can be read and shows no
    main menu after leaving, a screenshot is taken (`shot`.png) and the Escape, Exit and OK are sent once more; False when the
    menu is still not there (nothing more is clicked), True when it was, None when the screen could not be read (the blind
    clicks stand, as before)."""
    _leave_campaign(hands)
    shown = _main_menu_shown(hands)
    if shown is False:
        if shot is not None and hands.capture:
            hands.capture(Path(f"{shot}.png"))
        _leave_campaign(hands)
        shown = _main_menu_shown(hands)
        if shown is False:
            return False
    click_menu(hands, "Missions", MAIN_MENU_MISSIONS)
    hands.sleep(3)
    return shown


def _write_actions(log: Path, actions: list[dict]) -> None:
    """`<log>.actions.json`: the run's keys and clicks against the log's size, for a stuck run's triage (96.9)."""
    from bridgeforge.safeio import atomic_write_json

    try:
        atomic_write_json(Path(f"{log}.actions.json"), actions, indent=1)
    except OSError:
        pass  # the stuck verdict stands without it


_MOD_LINE = re.compile(r"Running with the following mods[^\n]*\n(?P<body>(?:[^\n]*StarfarerLauncher\s+-\s{4}[^\n]+\n)+)")
_MOD_ENTRY = re.compile(r"StarfarerLauncher\s+-\s{4}(?P<name>.+?) \[id: (?P<id>[^\]]+)\].*?\(from (?P<path>[^)]+)\)")


def _mission_ids(mod_path: str) -> list[str]:
    csv_path = Path(mod_path) / "data" / "missions" / "mission_list.csv"
    try:
        lines = csv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [row.split(",", 1)[0].strip() for row in lines[1:] if row.strip(" ,\t")]


def _mission_rows(mod_path: str) -> int:
    return len(_mission_ids(mod_path))


def _replaces_mission_list(mod_path: str) -> bool:
    from bridgeforge.scan.scanner import _load_lenient_json_file

    info = _load_lenient_json_file(Path(mod_path) / "mod_info.json")
    replace = info.get("replace") if isinstance(info, dict) else None
    return isinstance(replace, list) and any(str(item).replace("\\", "/").lower() == "data/missions/mission_list.csv" for item in replace)


def mission_list_layout(log_text: str, vanilla_rows: int = 0, probe_id: str = "bridgeforge_probe") -> tuple[int, int] | None:
    """(rows below the probe's mission, rows in the whole list) as the in-game mission list will show them, from the log's mod list.

    The list shows mods in the launcher's priority order, so a mod listed after the probe puts its missions below it: Neutrino's
    five pushed the probe up and the fixed click started a Neutrino mission (GRP1B-20261011). A mod whose mod_info `replace`s
    mission_list.csv drops the vanilla missions and every mod before it, and `install` adds the probe mission to that mod's own list,
    so the probe is that list's last row: Ironclads' list is its eight missions and nothing else (GRP10Y2-20261011).
    None: the log has no mod list or no probe in it."""
    block = _MOD_LINE.search(log_text)
    if not block:
        return None
    entries = [m.groupdict() for m in _MOD_ENTRY.finditer(block.group("body"))]
    ids = [e["id"] for e in entries]
    if probe_id not in ids:
        return None
    probe_at = ids.index(probe_id)
    replacer = next((i for i, e in enumerate(entries) if _replaces_mission_list(e["path"])), None)
    if replacer is None:
        total = vanilla_rows + sum(_mission_rows(e["path"]) for e in entries)
        below = sum(_mission_rows(e["path"]) for e in entries[probe_at + 1:])
        return below, total
    shown = entries[replacer:]
    # The game loads a mission id once: when `install` put the probe mission into the replacer's own list and the probe mod, listed
    # after it, lists the same row, that row is one row, not two (REG2-20261012: the click landed one row low and started an Ironclads
    # mission, "stuck at combat-round-1").
    seen: set[str] = set()
    total = 0
    for entry in shown:
        for mission_id in _mission_ids(entry["path"]):
            if mission_id not in seen:
                seen.add(mission_id)
                total += 1
    anchor = max(probe_at, replacer)  # the probe sits in the replacer's own list when it is listed before it
    below = sum(_mission_rows(e["path"]) for e in entries[anchor + 1:])
    return below, total


def missions_below_probe(log_text: str, probe_id: str = "bridgeforge_probe") -> int | None:
    """The first half of `mission_list_layout`, with no vanilla missions counted."""
    layout = mission_list_layout(log_text, 0, probe_id)
    return None if layout is None else layout[0]


def probe_mission_y(rows_below: int, total: int | None = None) -> float:
    """Where the probe's row is in the mission list. A list longer than the view is scrolled to its bottom, so the last row is at the
    bottom slot; a short one starts at the top slot and the last row is where its count puts it."""
    if total is not None and total <= VISIBLE_MISSION_ROWS:
        return FIRST_MISSION_ROW_Y + (total - 1 - rows_below) * MISSION_ROW_STEP
    return PROBE_MISSION[1] - rows_below * MISSION_ROW_STEP


def play_probe_combat(hands: Hands, rows_below: int = 0, total: int | None = None) -> None:
    hands.front()
    # 40 ticks reached the bottom of lists up to about 50 rows; REG-20261012 group 10 (58 missions loaded, 48 counted) stopped short and
    # started another mission, so scroll two ticks per counted row, never fewer than 40.
    hands.scroll(*MISSION_LIST_SCROLL_POINT, -max(40, 2 * (total or 0)))
    hands.sleep(1)
    hands.click(PROBE_MISSION[0], probe_mission_y(rows_below, total))
    hands.sleep(1.5)
    hands.click(*PLAY_MISSION)
    hands.sleep(6)
    hands.click(*DEPLOY_ALL)
    hands.sleep(1)
    hands.click(*DEPLOY)
    hands.sleep(2)
    hands.key(SPACE_KEY)


# The probe's combat round runs about 60 s once unpaused (3,596 frames, EXO-RC3-LIVE-20261026). The single SPACE press 2 s
# after deploying could land before the mission took input and leave it paused: EXO-RC4B-LIVE-20261026 stopped logging right
# after deployment, and the owner (2026-10-26) had been unpausing combat by hand. Between slices of this length with no
# 'combat END', SPACE is pressed again: a second press un-pauses a wrongly paused mission; a running one would have ended.
COMBAT_UNPAUSE_RETRY = 90.0
# The combat wait must hold the last retry plus a whole round (93.62). It was a flat 240 s: SA-SR2-20261119 lost the press
# after deploying and the 90 s retry, the 180 s retry started the round, and its about 62 s of running ended 2 s past the
# wait (combat START at 329 s, the harness gave up near 569 s). The press after deploying and two retries, then a round.
COMBAT_ROUND_SECONDS = 75.0  # about 60 s once unpaused (3,596 frames at 17 ms), plus margin
COMBAT_UNPAUSE_TRIES = 3


def combat_wait() -> float:
    """How long to wait for 'combat END': the last unpause retry plus a whole round."""
    return (COMBAT_UNPAUSE_TRIES - 1) * COMBAT_UNPAUSE_RETRY + COMBAT_ROUND_SECONDS


def wait_for_combat_end(log: Path, hands: Hands, timeout: float, since: int) -> bool:
    """True once the probe's 'combat END' is logged; presses SPACE again after each silent COMBAT_UNPAUSE_RETRY."""
    remaining = timeout
    while True:
        step = min(COMBAT_UNPAUSE_RETRY, remaining)
        if wait_for(log, COMBAT_END, step, hands, since=since):
            return True
        remaining -= step
        if remaining <= 0 or not hands.alive():
            return False
        hands.front()
        hands.key(SPACE_KEY)


def _capture(hands: Hands, log: Path, tag: str) -> str | None:
    """A screenshot of the game window beside the log (<TESTID>.<tag>.png) when the hands can take one: its path, else None."""
    if hands.capture is None:
        return None
    path = log.with_name(f"{log.name.split('.stdout.log')[0]}.{tag}.png")
    try:
        return str(path) if hands.capture(path) else None
    except Exception:  # evidence only: a failed screenshot never ends the run
        return None


def start_probe_combat(log: Path, hands: Hands, layout: tuple[int, int | None], round_no: int, timeout: float, since: int,
                       stages: list[str]) -> tuple[bool, str | None]:
    """Play the probe mission and confirm its battle started ('combat START' after `since`). If it did not, take a screenshot and
    retry once (95.12(a)); a later round first clicks Continue again, in case the last battle's results are still up. Returns
    (started, the screenshot's path or None)."""
    play_probe_combat(hands, *layout)
    if wait_for(log, COMBAT_START, timeout, hands, since=since):
        return True, None
    if not hands.alive():  # the game exited: nothing to photograph or click (the clicks would raise on a closed window)
        return False, None
    shot = _capture(hands, log, f"round{round_no}-no-start")
    stages.append(f"combat-{round_no}-retry")
    if round_no > 1:
        hands.front()
        hands.click(*COMBAT_CONTINUE)
        hands.sleep(4)
    play_probe_combat(hands, *layout)
    return wait_for(log, COMBAT_START, timeout, hands, since=since), shot


def continue_after_battle(log: Path, hands: Hands, round_from: int, timeout: float) -> None:
    """Leave a battle's results for the mission list: wait for the game's own re-definition of the mission (its combat-round line
    after the battle's END), then click Continue."""
    text = _log_text(log)
    end_at = text.find(COMBAT_END, round_from)
    if wait_for(log, ROUND_LINE, timeout, hands, since=end_at + len(COMBAT_END) if end_at >= 0 else len(text)):
        hands.sleep(2)
    hands.front()
    hands.click(*COMBAT_CONTINUE)
    hands.sleep(4)


def drive(log: Path, hands: Hands, menu_timeout: float = 240, campaign_timeout: float = 600, combat_timeout: float | None = None,
          generic_fallback: bool = True, new_game_grace: float = NEW_GAME_GRACE,
          vanilla_rows: int = VANILLA_MISSION_ROWS, save_reload: bool = False, probe_saves: bool = False) -> LiveResult:
    """Run the whole live sequence against a started game whose stdout is `log`. `combat_timeout` defaults to combat_wait().

    A game window that vanishes mid-run ends it as LIVE_STUCK at the stage in progress, with the log's last lines (93.50:
    SR7-LIVE-0985a-20261117 raised "the game window is gone" from New Game's click and gave no verdict)."""
    if combat_timeout is None:
        combat_timeout = combat_wait()  # read at call time, so the retry and round constants decide it (93.62)
    result = LiveResult("LIVE_STUCK", log=str(log))
    hands = recording(hands, log, result.actions)
    at = ["main-menu"]  # the stage in progress, for a vanished window
    try:
        return _drive(log, hands, result, at, menu_timeout, campaign_timeout, combat_timeout, generic_fallback,
                      new_game_grace, vanilla_rows, save_reload, probe_saves)
    except GameWindowGone:
        result.stage, result.detail = at[0], window_gone_detail(_log_text(log))
        _write_actions(log, result.actions)
        return result
    except (MenuMisread, GameNotInFront) as exc:
        # Nothing was clicked: on a misread menu, which is still up (98.11), or after a window that would not come to the front,
        # whose screenshot shows what covers it (98.12).
        shot = _capture(hands, log, f"{at[0]}-{'menu' if isinstance(exc, MenuMisread) else 'front'}")
        result.stage, result.detail = at[0], f"{exc}" + (f"; screenshot {shot}" if shot else "")
        _write_actions(log, result.actions)
        return result


def _drive(log: Path, hands: Hands, result: LiveResult, at: list[str], menu_timeout: float, campaign_timeout: float,
           combat_timeout: float, generic_fallback: bool, new_game_grace: float, vanilla_rows: int, save_reload: bool,
           probe_saves: bool) -> LiveResult:
    """drive's sequence; `at[0]` names the stage in progress (set where a click can find the window gone)."""
    def stuck(stage: str, detail: str) -> LiveResult:
        result.stage, result.detail = stage, detail
        _write_actions(log, result.actions)
        return result

    if not wait_for(log, MENU_READY, menu_timeout, hands):
        return stuck("main-menu", "the game never logged that the main menu was up")
    result.stages.append("main-menu")
    at[0] = "new-game"
    hands.sleep(20)  # the menu is drawn some seconds after its log line
    flow = new_game_flow_for(_log_text(log))
    new_game(hands, flow)
    # A fixed flow that stops on a page of a mod's own is given NEW_GAME_GRACE seconds, then the generic screen-reading flow continues
    # from that page (G1). Nexerelin's flow already reads the screen, and a run without a readable screen has nothing to fall back on.
    grace = min(new_game_grace, campaign_timeout) if (generic_fallback and hands.geometry and flow != "nexerelin") else campaign_timeout
    reached = wait_for(log, CAMPAIGN_END, grace, hands)
    fallback_ran = False
    if not reached and grace < campaign_timeout:
        fallback_ran = True
        steps = generic_new_game(hands, lambda: CAMPAIGN_END in _log_text(log), Path(f"{log}.newgame"))
        result.stages.append(f"new-game-generic({len(steps)} pages)")
        reached = wait_for(log, CAMPAIGN_END, campaign_timeout - grace, hands)
    if not reached:
        tail = "; the generic New Game flow was tried and did not reach the campaign" if fallback_ran else ""
        return stuck("new-game", "no 'campaign END' probe line: a screen did not take the click, generation failed, or the probe is not enabled" + tail)
    result.stages.append("campaign")
    if save_reload:  # the probe fingerprints and saves at day N; the reload is a second launch (save_reload_run)
        if not wait_for(log, FINGERPRINT_SAVED, campaign_timeout, hands):
            return stuck("fingerprint-save", "no 'fingerprint|save|cmdSave returned true' probe line: save_reload.after_days not reached or cmdSave failed")
        result.stages.append("fingerprint-saved")
    if probe_saves:
        if not wait_for(log, PROBE_SAVED, PROBE_SAVE_TIMEOUT, hands):
            return stuck("probe-save", "the probe config asks for a save after the checks, and no 'save|campaign|cmdSave returned' "
                                       "probe line came: leaving the campaign during a save loses the keys and clicks (93.59)")
        result.stages.append("probe-saved")
        hands.sleep(PROBE_SAVE_SETTLE)
    at[0] = "leave-campaign"
    left = to_mission_list(hands, Path(f"{log}.leave-campaign"))
    if left is False:
        return stuck("leave-campaign", "no main menu on screen after Escape, Exit and OK, also after one retry: the keys did not reach "
                                       f"the game or a dialog is open; screenshot {log}.leave-campaign.png")
    rounds_total, round_no = 1, 0
    layout = mission_list_layout(_log_text(log), vanilla_rows)
    rows_below, list_total = layout if layout else (0, None)
    if rows_below > MAX_ROWS_REACHABLE:
        return stuck("mission-list", f"{rows_below} mission rows sit below the probe's; only {MAX_ROWS_REACHABLE} are reachable without scrolling back")
    start_timeout, settle_timeout = min(COMBAT_START_TIMEOUT, combat_timeout), min(POST_BATTLE_SETTLE, combat_timeout)
    while round_no < rounds_total:
        at[0] = f"combat-round-{round_no + 1}"
        offset = len(_log_text(log))
        started, shot = start_probe_combat(log, hands, (rows_below, list_total), round_no + 1, start_timeout, offset, result.stages)
        if not started:
            if not hands.alive():
                return stuck(f"combat-round-{round_no + 1}", "the game exited before the probe mission's battle started")
            return stuck(f"combat-round-{round_no + 1}", "the probe mission did not start (no 'combat START' probe line), also after one retry"
                         + (f"; screenshot {shot}" if shot else ""))
        if not wait_for_combat_end(log, hands, combat_timeout, offset):
            if not hands.alive():
                return stuck(f"combat-round-{round_no + 1}", "the game exited during the probe mission's battle")
            # SR4-LIVE-0985a-20261117: the battle started and the log went silent with no ship logged. A screenshot tells a
            # deployment dialog left open from a frozen frame (93.40).
            shot = _capture(hands, log, f"round{round_no + 1}-no-end")
            return stuck(f"combat-round-{round_no + 1}", "no 'combat END' probe line after the probe mission started"
                         + (f"; screenshot {shot}" if shot else ""))
        round_no += 1
        result.rounds = round_no
        found = ROUND_LINE.findall(_log_text(log)[offset:])
        if found:
            rounds_total = max(rounds_total, int(found[-1][1]))
        result.stages.append(f"combat-{round_no}")
        if round_no < rounds_total:
            continue_after_battle(log, hands, offset, settle_timeout)
    result.verdict = "LIVE_DONE"
    return result


def real_hands(rig: Path, launcher_pid: int | None = None) -> Hands:
    """Hands on the game under `rig`: foreground and click through game_click, aliveness from the rig's java processes and, when the
    launcher's process id is given, everything it started (the java-28 JDK sits outside the rig)."""
    from bridgeforge import game_click
    from bridgeforge.boot_test import _running_java_under
    from bridgeforge.launcher_click import descendant_pids

    def pids() -> set[int]:
        found = {item["pid"] for item in _running_java_under(rig) if isinstance(item.get("pid"), int)}
        return found | (descendant_pids(launcher_pid) if launcher_pid else set())

    def geometry():
        found = game_click.game_window(pids())
        if found is None:
            raise GameWindowGone("the game window is gone")
        return found

    def front() -> bool:
        return game_click.bring_to_front(geometry()[0])  # whether it came to the front; checked_front acts on it (98.12)

    return Hands(click=lambda fx, fy: game_click.click_fraction(geometry(), fx, fy),
                 key=game_click.press_key,
                 scroll=lambda fx, fy, n: game_click.scroll(geometry(), fx, fy, n),
                 alive=lambda: bool(pids()), front=front, geometry=geometry,
                 capture=lambda path: game_click.capture_client(geometry(), path))


# What a unattended live run must show in its log to count (ROADMAP item 75 R1); `drive` ends LIVE_DONE after a combat round.
LIVE_EXPECTED_MILESTONES = ("main_menu", "campaign_checks", "content_ids", "combat")


@contextlib.contextmanager
def running_game(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", natural_exit: bool = False, exit_wait: float = 180,
                 outcome: dict | None = None, expected: tuple[str, ...] | None = None, scenario: str = "probe-group live",
                 graceful_exit: bool = True, pin_prefs: bool = True, direct=None):
    """Start the rig game, click through the launcher, yield (log, hands, vanilla mission rows), then stop the rig's java and the
    launcher's whole tree. Refuses like boot_test: GameRefused with the reason.

    With `natural_exit`, the body sets `outcome["await_exit"] = True` once the run is done; the game is then given `exit_wait`
    seconds to be quit by the operator and its return code is written to <rig>/logs/<TESTID>.exit.json (NATURAL), else KILLED.
    Without it, `graceful_exit` (the default) closes a finished game by itself once the probe has written its done marker for this
    manifest (see graceful_exit.py) and records NATURAL with the code, or KILLED when it had to be stopped."""
    from bridgeforge import launch
    from bridgeforge.boot_test import LAUNCH_WATCHDOG_SECONDS, _is_link, _running_java_under, watchdog_message
    from bridgeforge.run_manifest import ManifestError, read_staging_state

    rig = Path(rig).expanduser().resolve()
    if not _is_link(rig / "starsector-core"):
        raise GameRefused(f"{rig / 'starsector-core'} is not a junction/symlink; refusing to run in a shared install")
    if _running_java_under(rig):
        raise GameRefused("java is already running under the rig; close it first")
    bat = rig / bat_name
    if not bat.is_file():
        raise GameRefused(f"launcher not found: {bat}")
    logs = rig / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    log, err = logs / f"{test_id}.stdout.log", logs / f"{test_id}.stderr.log"
    # R1: record what is staged before anything starts; the rig belongs to this run until it is released below.
    try:
        manifest = launch.prepare_manifest(rig, test_id, "live", targets=sorted(read_staging_state(rig).get("candidates") or {}),
                                           expected=list(expected or LIVE_EXPECTED_MILESTONES), scenario=scenario, bat=bat)
    except ManifestError as exc:
        raise GameRefused(f"no pre-launch manifest: {exc}") from exc
    from bridgeforge.graceful_exit import clear_done

    clear_done(rig)
    from bridgeforge.rig.rig_prefs import LIVE_PINNED, pinned_launcher_prefs

    # The window the click fractions were measured in, and canSkipTutorial for New Game's "Skip it" (ROADMAP-3 93.28); the
    # owner's own values come back afterwards.
    # 95.4: a direct start pins its own resolution, skips the launcher and places the window instead of clicking Play.
    pinned = direct.pinned_prefs(LIVE_PINNED) if direct is not None else LIVE_PINNED
    prefs = pinned_launcher_prefs(pinned) if pin_prefs else contextlib.nullcontext()
    prefs.__enter__()
    try:
        process = launch.start_game(rig, bat, log, err, env=direct.env() if direct is not None else None)
    except Exception:
        prefs.__exit__(None, None, None)
        launch.release_manifest(rig, test_id, bat)
        raise
    watcher = launch.watch_windows(rig, test_id, process)
    hands = real_hands(rig, process.pid)
    if direct is not None:
        from .direct_start import place_window

        def start_step(rig_path, proc):
            return place_window(rig_path, proc, direct.client_top)
    else:
        start_step = launch.click_launcher
    base_alive = hands.alive
    clicked = {"done": False}
    launched_at = time.monotonic()
    java_seen: dict = {}

    def alive_and_click() -> bool:
        if launch.watchdog_tripped(rig, process, launched_at, java_seen, test_id):
            raise LaunchNoProcess(watchdog_message(rig, LAUNCH_WATCHDOG_SECONDS))
        if not clicked["done"] and start_step(rig, process):
            clicked["done"] = True
        return base_alive() or process.poll() is None

    hands.alive = alive_and_click
    try:
        core_list = rig / "starsector-core" / "data" / "missions" / "mission_list.csv"
        yield log, hands, (_mission_rows(str(core_list.parent.parent.parent)) or VANILLA_MISSION_ROWS)
    finally:
        try:
            launch.stop_game(rig, test_id, process, record_exit=natural_exit, await_exit=bool((outcome or {}).get("await_exit")),
                             exit_wait=exit_wait, graceful=graceful_exit, manifest_id=manifest["manifest_id"], watcher=watcher)
        finally:
            prefs.__exit__(None, None, None)
            launch.release_manifest(rig, test_id, bat)


def probe_saves_after_checks(rig: Path) -> bool:
    """Whether the rig's installed probe config asks the probe to save after its first checks (`--save-after-checks`)."""
    from bridgeforge.run_manifest import CONFIG_RELATIVE

    try:
        config = json.loads((Path(rig) / CONFIG_RELATIVE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(config, dict) and config.get("save_after_checks") is True


def live_run(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", menu_timeout: float = 240,
             natural_exit: bool = False, exit_wait: float = 180, save_reload: bool = False,
             graceful_exit: bool = True, interactive: bool = False, scenario: str = "probe-group live", direct=None) -> LiveResult:
    """Play a group's live run (see drive) on a freshly started rig game, then stop it. With `natural_exit`, a finished run
    (LIVE_DONE) first waits for the game to be quit from its menu and records the observed exit (see running_game)."""
    from .display_awake import display_kept_on

    outcome: dict = {}
    try:
        # The display stays on for the whole run: keys and clicks sent to a game whose display went dark were lost (93.58).
        with display_kept_on(), \
                running_game(rig, test_id, bat_name, natural_exit=natural_exit or interactive, exit_wait=exit_wait, outcome=outcome,
                             graceful_exit=graceful_exit, pin_prefs=not interactive, scenario=scenario,
                             direct=direct) as (log, hands, vanilla_rows):
            if interactive:  # the operator plays and closes the game; nothing is clicked or typed (launch.py records NATURAL + code)
                while hands.alive():
                    hands.sleep(EXIT_POLL_SECONDS)
                outcome["await_exit"] = True
                return LiveResult("LIVE_DONE", stages=["interactive"], log=str(log))
            result = drive(log, hands, menu_timeout=menu_timeout, vanilla_rows=vanilla_rows, save_reload=save_reload,
                           probe_saves=probe_saves_after_checks(rig))
            outcome["await_exit"] = result.verdict == "LIVE_DONE"
            return result
    except LaunchNoProcess as exc:
        return LiveResult("LIVE_STUCK", "LAUNCH_NO_PROCESS", str(exc))
    except GameRefused as exc:
        return LiveResult("LIVE_STUCK", "refused", str(exc))
