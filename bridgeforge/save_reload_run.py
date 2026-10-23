"""Second launch of a save-reload live run: load the save the first launch wrote and wait for the probe's fingerprint compare line.

The first launch (`probe-group live --save-reload`) ends with the probe's `fingerprint|save` line (a real `cmdSave()`, RC8-30) and the stored
`bf_probe_fingerprint` common file. This launch starts the rig game again, clicks the main menu's Continue (RC8-29: Continue loads the
save the game last wrote or loaded) and waits for `fingerprint|<status>|compare|equal=...`. `reload_after_save` is read from the log by
`run_manifest.evaluate_run` (field `milestones.reload_after_save`), never set here. If the screen click path fails, the manual fallback is:
start the rig game, choose Continue (or Load Game and pick the newest save), and read the log with `run-manifest evaluate`.
"""
from __future__ import annotations

import json
from pathlib import Path

from bridgeforge.live.live_run import (GameRefused, Hands, LaunchNoProcess, LiveResult, MENU_LOADED, _log_text, click_menu, running_game, wait_for)

RELOAD_EXPECTED = ("main_menu", "campaign_load", "reload_after_save")
COMPARE_MARKER = "|compare|equal="
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


def drive_reload(log: Path, hands: Hands, menu_timeout: float = 240, compare_timeout: float = 300) -> LiveResult:
    """Main menu, Continue, then wait for the compare line."""
    result = LiveResult("LIVE_STUCK", log=str(log))
    if not wait_for(log, MENU_LOADED, menu_timeout, hands):
        result.stage, result.detail = "main-menu", "the game never logged that the main menu was up"
        return result
    result.stages.append("main-menu")
    hands.sleep(20)
    if not click_menu(hands, "Continue", MAIN_MENU_CONTINUE):
        result.stage, result.detail = "continue", "the main menu is still up after clicking Continue (no save to continue, or the click missed)"
        return result
    result.stages.append("continue")
    if COMPARE_MARKER not in _log_text(log) and not wait_for(log, COMPARE_MARKER, compare_timeout, hands):
        result.stage, result.detail = "fingerprint-compare", "no 'fingerprint|compare' probe line after loading: the stored fingerprint did not match this save, or the probe is off"
        return result
    result.stages.append("fingerprint-compare")
    result.verdict = "LIVE_DONE"
    return result


def reload_run(rig: Path, test_id: str, bat_name: str = "run-j25-direct.bat", menu_timeout: float = 240) -> LiveResult:
    """Start the rig game again under its own manifest, load the last save and observe the compare line."""
    try:
        with running_game(rig, test_id, bat_name, expected=RELOAD_EXPECTED, scenario="probe-group live --save-reload (reload)") as (log, hands, _rows):
            return drive_reload(log, hands, menu_timeout=menu_timeout)
    except LaunchNoProcess as exc:
        return LiveResult("LIVE_STUCK", "LAUNCH_NO_PROCESS", str(exc))
    except GameRefused as exc:
        return LiveResult("LIVE_STUCK", "refused", str(exc))
