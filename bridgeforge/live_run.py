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
MISSION_ROW_STEP = 0.0594  # list entries are 57 px apart in the 960 px view (measured 2026-10-11)
MAX_ROWS_REACHABLE = 7  # entries above the last one that show without scrolling back up
VISIBLE_MISSION_ROWS = 9
FIRST_MISSION_ROW_Y = 0.248  # centre of the top slot (238 px of 960)
VANILLA_MISSION_ROWS = 14  # RC8's own mission_list.csv; live_run reads the real count from the rig's core

NEW_GAME_GRACE = 150.0  # seconds a fixed New Game flow gets to reach the campaign before the generic flow continues
MENU_LOADED = "Reading save data from"
CAMPAIGN_END = "probe|INFO|campaign|END"
COMBAT_END = "probe|INFO|combat|END"
FINGERPRINT_SAVED = "fingerprint|INFO|save|cmdSave returned true"  # save_reload stage (next probe version)
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
    geometry: Callable[[], tuple] | None = None


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


def _menu_buttons(hands: Hands) -> list[tuple[float, float]] | None:
    """The main menu buttons on screen now, or None when the screen cannot be read."""
    if not hands.geometry:
        return None
    try:
        import tempfile

        from . import game_click
        from .screen_read import Bitmap, main_menu_buttons

        with tempfile.TemporaryDirectory() as directory:
            shot = Path(directory) / "menu.bmp"
            if not game_click.capture_client(hands.geometry(), shot):
                return None
            return main_menu_buttons(Bitmap.load(shot))
    except Exception:
        return None


def menu_point(hands: Hands, name: str, fallback: tuple[float, float]) -> tuple[float, float]:
    """Where the main menu's `name` button is, read from the screen once the menu has stopped moving (it slides in after a return
    from the campaign, and a reading taken mid-slide sent a click to the wrong row, GRP-CMU3-20261011); the measured fraction when
    the screen cannot be read."""
    from .screen_read import main_menu_target

    previous = None
    for _ in range(10):
        buttons = _menu_buttons(hands)
        if buttons is None:
            return fallback
        if buttons and buttons == previous and main_menu_target(buttons, name):
            return main_menu_target(buttons, name)
        previous = buttons
        hands.sleep(1.0)
    return (main_menu_target(previous, name) if previous else None) or fallback


def click_menu(hands: Hands, name: str, fallback: tuple[float, float], attempts: int = 3) -> bool:
    """Click a main menu button and check the menu went away; try again if it is still there. True once it has gone (or when the
    screen cannot be read, so the old blind click stands)."""
    from .screen_read import main_menu_target

    for _ in range(attempts):
        hands.front()
        hands.click(*menu_point(hands, name, fallback))
        hands.sleep(2.5)
        after = _menu_buttons(hands)
        if after is None or not main_menu_target(after, name):
            return True
    return False


def _screen(hands: Hands):
    """The game window as a Bitmap, or None when it cannot be read."""
    if not hands.geometry:
        return None
    try:
        import tempfile

        from . import game_click
        from .screen_read import Bitmap

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
    from .screen_read import nexerelin_fleet_select

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
    from .new_game_generic import run_pages

    if not hands.geometry:
        return []

    def capture():
        return _screen(hands)

    hands.front()
    return run_pages(lambda fx, fy: (hands.front(), hands.click(fx, fy)), hands.sleep, capture, done, max_pages, shots_dir=shots_dir)


def to_mission_list(hands: Hands) -> None:
    """From the campaign map (or the combat result) to the main menu's mission list."""
    hands.front()
    hands.key(ESCAPE_KEY)
    hands.sleep(1.5)
    hands.click(*GAME_MENU_EXIT)
    hands.sleep(2)
    hands.click(*GAME_MENU_EXIT_OK)
    hands.sleep(8)
    click_menu(hands, "Missions", MAIN_MENU_MISSIONS)
    hands.sleep(3)


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
    from .scanner import _load_lenient_json_file

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


def drive(log: Path, hands: Hands, menu_timeout: float = 240, campaign_timeout: float = 600, combat_timeout: float = 240,
          generic_fallback: bool = True, new_game_grace: float = NEW_GAME_GRACE,
          vanilla_rows: int = VANILLA_MISSION_ROWS, save_reload: bool = False) -> LiveResult:
    """Run the whole live sequence against a started game whose stdout is `log`."""
    result = LiveResult("LIVE_STUCK", log=str(log))

    def stuck(stage: str, detail: str) -> LiveResult:
        result.stage, result.detail = stage, detail
        return result

    if not wait_for(log, MENU_LOADED, menu_timeout, hands):
        return stuck("main-menu", "the game never logged that the main menu was up")
    result.stages.append("main-menu")
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
    to_mission_list(hands)
    rounds_total, round_no = 1, 0
    layout = mission_list_layout(_log_text(log), vanilla_rows)
    rows_below, list_total = layout if layout else (0, None)
    if rows_below > MAX_ROWS_REACHABLE:
        return stuck("mission-list", f"{rows_below} mission rows sit below the probe's; only {MAX_ROWS_REACHABLE} are reachable without scrolling back")
    while round_no < rounds_total:
        offset = len(_log_text(log))
        play_probe_combat(hands, rows_below, list_total)
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


def real_hands(rig: Path, launcher_pid: int | None = None) -> Hands:
    """Hands on the game under `rig`: foreground and click through game_click, aliveness from the rig's java processes and, when the
    launcher's process id is given, everything it started (the java-28 JDK sits outside the rig)."""
    from . import game_click
    from .boot_test import _running_java_under
    from .launcher_click import descendant_pids

    def pids() -> set[int]:
        found = {item["pid"] for item in _running_java_under(rig) if isinstance(item.get("pid"), int)}
        return found | (descendant_pids(launcher_pid) if launcher_pid else set())

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
                 alive=lambda: bool(pids()), front=front, geometry=geometry)


class GameRefused(RuntimeError):
    """The rig is not safe or ready to run a game (shared install, a game already running, no launcher)."""


# What a unattended live run must show in its log to count (ROADMAP item 75 R1); `drive` ends LIVE_DONE after a combat round.
LIVE_EXPECTED_MILESTONES = ("main_menu", "campaign_load", "content_ids", "combat")


def _release(rig: Path, test_id: str, bat: Path) -> None:
    """The run ended: re-hash the staged files and give the rig back. A failure here is left visible (no completion record means the
    evaluator refuses the run), never swallowed into a pass."""
    from .run_manifest import ManifestError, release_run

    try:
        release_run(rig, test_id, bat)
    except (ManifestError, OSError):
        pass


class LaunchNoProcess(GameRefused):
    """The launch watchdog fired: no java process appeared (ROADMAP item 73 G4). The live result stage is LAUNCH_NO_PROCESS."""


EXIT_POLL_SECONDS = 2.0


def settle_exit(process, wait: float, *, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
                java_left: Callable[[], bool] = lambda: False) -> tuple[str, int | None]:
    """Wait up to `wait` seconds for the launched process to exit by itself: (NATURAL, its integer return code), or (KILLED, None)
    when it is still running at the bound or left a java process behind. Never returns a code for a process that was not seen to exit."""
    from .exit_observation import KILLED, observed_exit

    deadline = clock() + wait
    while process.poll() is None:
        if clock() >= deadline:
            return KILLED, None
        sleep(EXIT_POLL_SECONDS)
    return observed_exit(process.poll(), java_left())


@contextlib.contextmanager
def running_game(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", natural_exit: bool = False, exit_wait: float = 180,
                 outcome: dict | None = None, expected: tuple[str, ...] | None = None, scenario: str = "probe-group live"):
    """Start the rig game, click through the launcher, yield (log, hands, vanilla mission rows), then stop the rig's java and the
    launcher's whole tree. Refuses like boot_test: GameRefused with the reason.

    With `natural_exit`, the body sets `outcome["await_exit"] = True` once the run is done; the game is then given `exit_wait`
    seconds to be quit by the operator and its return code is written to <rig>/logs/<TESTID>.exit.json (NATURAL), else KILLED."""
    from .boot_test import LAUNCH_WATCHDOG_SECONDS, _is_link, _running_java_under, _terminate_tree, java_started, watchdog_message
    from .launcher_click import click_launcher_once, descendant_pids

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
    from .run_manifest import ManifestError, prepare_run, read_staging_state

    # R1: record what is staged before anything starts; the rig belongs to this run until it is released below.
    try:
        prepare_run(rig, test_id, "live", targets=sorted(read_staging_state(rig).get("candidates") or {}), launcher=bat,
                    expected=list(expected or LIVE_EXPECTED_MILESTONES), scenario=scenario)
    except ManifestError as exc:
        raise GameRefused(f"no pre-launch manifest: {exc}") from exc
    from .rig_prefs import pinned_launcher_prefs

    prefs = pinned_launcher_prefs()  # the click fractions were measured at 1280x960; the owner's own setting comes back afterwards
    prefs.__enter__()
    try:
        process = subprocess.Popen(f'cmd.exe /c ""{bat}" > "{log}" 2> "{err}""', cwd=str(rig))
    except Exception:
        prefs.__exit__(None, None, None)
        _release(rig, test_id, bat)
        raise
    hands = real_hands(rig, process.pid)
    base_alive = hands.alive
    clicked = {"done": False}
    launched_at = time.monotonic()
    java_seen = {"seen": False}

    def alive_and_click() -> bool:
        # Launch watchdog (ROADMAP 60f): no java process 60 s after launch means the bat never started the game; say so and stop.
        if not java_seen["seen"]:
            java_seen["seen"] = java_started(rig, process.pid)
            if not java_seen["seen"] and time.monotonic() - launched_at >= LAUNCH_WATCHDOG_SECONDS:
                raise LaunchNoProcess(watchdog_message(rig, LAUNCH_WATCHDOG_SECONDS))
        # The launcher window waits for Play before the game logs anything (owner, 2026-10-11).
        if not clicked["done"]:
            pids = {item["pid"] for item in _running_java_under(rig) if isinstance(item.get("pid"), int)} | descendant_pids(process.pid)
            if click_launcher_once(pids):
                clicked["done"] = True
        return base_alive() or process.poll() is None

    hands.alive = alive_and_click
    try:
        core_list = rig / "starsector-core" / "data" / "missions" / "mission_list.csv"
        yield log, hands, (_mission_rows(str(core_list.parent.parent.parent)) or VANILLA_MISSION_ROWS)
    finally:
        if natural_exit:
            from .exit_observation import KILLED, write_exit_observation

            observed, code = KILLED, None
            if (outcome or {}).get("await_exit"):
                observed, code = settle_exit(process, exit_wait, java_left=lambda: bool(_running_java_under(rig)))
            write_exit_observation(rig, test_id, observed, code)
        for java in _running_java_under(rig):
            if isinstance(java.get("pid"), int):
                _terminate_tree(java["pid"])
        if process.poll() is None:
            _terminate_tree(process.pid)
        prefs.__exit__(None, None, None)
        _release(rig, test_id, bat)


def live_run(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", menu_timeout: float = 240,
             natural_exit: bool = False, exit_wait: float = 180, save_reload: bool = False) -> LiveResult:
    """Play a group's live run (see drive) on a freshly started rig game, then stop it. With `natural_exit`, a finished run
    (LIVE_DONE) first waits for the game to be quit from its menu and records the observed exit (see running_game)."""
    outcome: dict = {}
    try:
        with running_game(rig, test_id, bat_name, natural_exit=natural_exit, exit_wait=exit_wait, outcome=outcome) as (log, hands, vanilla_rows):
            result = drive(log, hands, menu_timeout=menu_timeout, vanilla_rows=vanilla_rows, save_reload=save_reload)
            outcome["await_exit"] = result.verdict == "LIVE_DONE"
            return result
    except LaunchNoProcess as exc:
        return LiveResult("LIVE_STUCK", "LAUNCH_NO_PROCESS", str(exc))
    except GameRefused as exc:
        return LiveResult("LIVE_STUCK", "refused", str(exc))
