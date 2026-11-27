"""Reading and clicking Starsector's main menu for the live harness (split out of live_run.py for 98.11).

The menu's buttons are read from a screenshot (`screen_read.main_menu_buttons`) and named by position
(`screen_read.main_menu_target`). A steady reading that looks like a menu (eight bands or more) but cannot name the wanted
button raises MenuMisread rather than clicking a guess: in RC9NC-LIVE3-0985a-20261126 two extra bands shifted "Missions" onto
"Load Game", and the harness's next clicks loaded a save. A reading that does not look like a menu (fewer than eight bands, a
menu still sliding in, another screen) keeps the older behaviour: read again, then click the measured fraction. So does a
screen that cannot be read at all.

Left open (98.11): eight buttons plus one extra band read like nine with Continue, and a nine-button menu that loses a band
reads like eight; band spacing, or whether a save exists, could tell them apart.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # live_run imports this module, so Hands is only named for the type checker
    from bridgeforge.live.live_run import Hands

MENU_CHECK_READS = 6  # screen reads, a second apart, for the main menu to appear after leaving the campaign
STEADY_READS = 10  # readings, a second apart, for the menu to stop moving before a click


class MenuMisread(RuntimeError):
    """The main menu is on screen and stopped moving, but its reading cannot name the button: nothing was clicked (98.11).
    live_run.drive and save_reload_run.drive_reload end the run LIVE_STUCK at the stage in progress with a screenshot;
    duel_run.run_duel reports it as the run's problem."""


def _menu_buttons(hands: Hands) -> list[tuple[float, float]] | None:
    """The main menu buttons on screen now, or None when the screen cannot be read."""
    if not hands.geometry:
        return None
    try:
        import tempfile

        from bridgeforge import game_click
        from bridgeforge.screen_read import Bitmap, main_menu_buttons

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
    the screen cannot be read, or never reads as a menu. A steady menu-like reading that cannot name the button raises
    MenuMisread (see the module docstring)."""
    from bridgeforge.screen_read import main_menu_present, main_menu_target

    previous = None
    for _ in range(STEADY_READS):
        buttons = _menu_buttons(hands)
        if buttons is None:
            return fallback
        if buttons and buttons == previous:
            target = main_menu_target(buttons, name)
            if target is not None:
                return target
            if main_menu_present(buttons):
                if len(buttons) in (8, 9):  # a well-read menu without this button: Continue needs a save (RC8-29)
                    raise MenuMisread(f"the main menu has {len(buttons)} buttons and no '{name}', so nothing was clicked")
                raise MenuMisread(f"the main menu read as {len(buttons)} buttons, not 8 or 9, so '{name}' was not clicked")
        previous = buttons
        hands.sleep(1.0)
    return (main_menu_target(previous, name) if previous else None) or fallback


def click_menu(hands: Hands, name: str, fallback: tuple[float, float], attempts: int = 3) -> bool:
    """Click a main menu button and check the menu went away; try again if it is still there (any menu-like reading, misread or
    not: review of 98.11). True once it has gone, or when the screen cannot be read, so the old blind click stands."""
    from bridgeforge.screen_read import main_menu_present

    for _ in range(attempts):
        hands.front()
        hands.click(*menu_point(hands, name, fallback))
        hands.sleep(2.5)
        after = _menu_buttons(hands)
        if after is None or not main_menu_present(after):
            return True
    return False


def _main_menu_shown(hands: Hands) -> bool | None:
    """Whether the main menu is on screen (eight bands or more: a menu misread as too many is still up, and its click is refused
    later by menu_point, 98.11), waiting up to MENU_CHECK_READS reads; None when the screen cannot be read."""
    from bridgeforge.screen_read import main_menu_present

    for _ in range(MENU_CHECK_READS):
        buttons = _menu_buttons(hands)
        if buttons is None:
            return None
        if main_menu_present(buttons):
            return True
        hands.sleep(1.0)
    return False
