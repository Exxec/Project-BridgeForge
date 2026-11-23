"""Second launch of a save-reload live run: load the save the first launch wrote and wait for the probe's fingerprint compare line.

The first launch (`probe-group live --save-reload`) ends with the probe's `fingerprint|save` line (a real `cmdSave()`, RC8-30) and the stored
`bf_probe_fingerprint` common file. This launch starts the rig game again, clicks the main menu's Continue (RC8-29: Continue loads the
save the game last wrote or loaded) and waits for `fingerprint|<status>|compare|equal=...`. `reload_after_save` is read from the log by
`run_manifest.evaluate_run` (field `milestones.reload_after_save`), never set here. If the screen click path fails, the manual fallback is:
start the rig game, choose Continue (or Load Game and pick the newest save), and read the log with `run-manifest check`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from bridgeforge.live.live_run import (GameRefused, Hands, LaunchNoProcess, LiveResult, MENU_LOADED, _log_text, click_menu, running_game,
                                       wait_for)
from bridgeforge.live.window_gone import GameWindowGone, detail as window_gone_detail

RELOAD_EXPECTED = ("main_menu", "campaign_load", "reload_after_save")
COMPARE_MARKER = "|compare|equal="
# 88.22: the game's own load line (log_triage.CAMPAIGN_LOAD_RE; "Reading save data from" is not one, the menu logs it for every
# save). ICBF2C-J28's Continue started a New Game instead, and the run only ended at "no compare line".
LOAD_LINE = re.compile(r"CampaignGameManager\s+-\s+Loading .*saves[\\/]")
LOAD_START_TIMEOUT = 120  # seconds from Continue to the load line
# 88.19: ICBF2-J28FR's Fatal came 243 ms after the compare line and the run was called LIVE_DONE. Stay up this long after it.
RELOAD_SETTLE_SECONDS = 20
FATAL_LINE = re.compile(r"\bFatal:|\sFATAL\s")
MAIN_MENU_CONTINUE = (0.7195, 0.3)  # blind fallback only; the real position is read from the screen
FINGERPRINT_FILE = Path("saves") / "common" / "bf_probe_fingerprint.data"
CONFIG_FILE = Path("saves") / "common" / "bf_probe_config.data"


def save_reload_configured(rig: Path) -> int:
    """The rig probe config's save_reload.after_days (0 when absent or unreadable)."""
    try:
        config = json.loads((Path(rig) / CONFIG_FILE).read_text(encoding="utf-8"))
        return int((config.get("save_reload") or {}).get("after_days") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def clear_stale_fingerprint(rig: Path) -> bool:
    """Remove a fingerprint file left by an earlier run, so the compare line can only come from this run's own save."""
    target = Path(rig) / FINGERPRINT_FILE
    existed = target.is_file()
    target.unlink(missing_ok=True)
    return existed


def _dialogs(log: Path) -> list[str]:
    """The dialog lines the window watcher wrote for this run (<TESTID>.windows.txt beside <TESTID>.stdout.log)."""
    name = log.name[: -len(".stdout.log")] if log.name.endswith(".stdout.log") else log.stem
    try:
        lines = (log.with_name(name + ".windows.txt")).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [line for line in lines if " dialog: " in line]


def drive_reload(log: Path, hands: Hands, menu_timeout: float = 240, compare_timeout: float = 300,
                 load_timeout: float = LOAD_START_TIMEOUT, settle_seconds: int = RELOAD_SETTLE_SECONDS) -> LiveResult:
    """Main menu, Continue, the game's own load line (88.22), the compare line, then `settle_seconds` with the game up, no new
    dialog and no Fatal (88.19). A vanished window ends it LIVE_STUCK at the stage in progress (93.50)."""
    result = LiveResult("LIVE_STUCK", log=str(log))
    at = ["main-menu"]

    def stuck(detail: str) -> LiveResult:
        result.stage, result.detail = at[0], detail
        return result

    try:
        if not wait_for(log, MENU_LOADED, menu_timeout, hands):
            return stuck("the game never logged that the main menu was up")
        result.stages.append("main-menu")
        at[0] = "continue"
        hands.sleep(20)
        offset = len(_log_text(log))
        if not click_menu(hands, "Continue", MAIN_MENU_CONTINUE):
            return stuck("the main menu is still up after clicking Continue (no save to continue, or the click missed)")
        if not wait_for(log, LOAD_LINE, load_timeout, hands, since=offset):
            return stuck("Continue loaded no save: no 'CampaignGameManager - Loading ..saves/..' line after the click. The click may have "
                         "started a New Game instead (88.22: ICBF2C-J28), or missed")
        result.stages.append("continue")
        at[0] = "fingerprint-compare"
        if not wait_for(log, COMPARE_MARKER, compare_timeout, hands, since=offset):
            return stuck("no 'fingerprint|compare' probe line after loading: the stored fingerprint did not match this save, or the probe is off")
        result.stages.append("fingerprint-compare")
        at[0] = "after-compare"
        compared, dialogs = len(_log_text(log)), len(_dialogs(log))
        for _ in range(max(settle_seconds, 1)):
            new = _dialogs(log)[dialogs:]
            if new:
                return stuck(f"a dialog appeared after the compare line (88.19): {new[0].strip()[:300]}")
            fatal = next((line for line in _log_text(log)[compared:].splitlines() if FATAL_LINE.search(line)), None)
            if fatal:
                return stuck(f"a Fatal came after the compare line (88.19): {fatal.strip()[:300]}")
            if not hands.alive():
                return stuck("the game exited within the settle period after the compare line (88.19)")
            hands.sleep(1)
        result.stages.append("settled")
        result.verdict = "LIVE_DONE"
        return result
    except GameWindowGone:
        return stuck(window_gone_detail(_log_text(log)))


def reload_run(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", menu_timeout: float = 240, direct=None) -> LiveResult:
    """Start the rig game again under its own manifest, load the last save and observe the compare line. `direct` starts it
    without the launcher, as the first run did (ROADMAP-3 95.4)."""
    try:
        with running_game(rig, test_id, bat_name, expected=RELOAD_EXPECTED, scenario="probe-group live --save-reload (reload)",
                          direct=direct) as (log, hands, _rows):
            return drive_reload(log, hands, menu_timeout=menu_timeout)
    except LaunchNoProcess as exc:
        return LiveResult("LIVE_STUCK", "LAUNCH_NO_PROCESS", str(exc))
    except GameRefused as exc:
        return LiveResult("LIVE_STUCK", "refused", str(exc))
