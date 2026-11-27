"""Live testing paused, enforced in code (ROADMAP-3 98.16).

The owner paused live testing at about 20:05 on 2026-11-26, but an idle gate already running in the background kept polling
Test1 and launched RC9NC-LIVE4 at 22:03, once the desktop went idle. A pause that lives only in a session's notes cannot stop
a loop that is already running. So `bridgeforge live pause` writes a flag on the machine, and every place that starts a game
refuses while it is set: `live_run.running_game` (the live, save-reload and duel runs, and the gene boots, which run as
`probe-group live`), `boot_test.run_boot_test` (smoke runs and java-matrix) and `runtime-smoke --execute`. `live resume`
removes it. `live-queue` stops at a refused group, and java-matrix keeps a refused variant out of its ledger.

The flag belongs to the machine that runs the game (Test1): pause there. It sits in the user's local application data
(`%LOCALAPPDATA%\\BridgeForge` on Windows), not in a checkout or data root: the first version kept it in `state_dir()`, so a
worktree or a run with another `BRIDGEFORGE_DATA_ROOT` read a different flag and started the game (review, 2026-11-27). A flag
that cannot be read still counts as paused.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from bridgeforge.safeio import atomic_write_json

PAUSE_FILE_NAME = "live-paused.json"
# The test suite points this at a temporary path (tests/support.py), so a paused machine's real flag cannot fail the tests
# that start a fake game.
PAUSE_FILE_ENV = "BRIDGEFORGE_LIVE_PAUSE_FILE"


def machine_dir() -> Path:
    """The user's BridgeForge folder outside every checkout: %LOCALAPPDATA%\\BridgeForge, else $XDG_STATE_HOME/bridgeforge or
    ~/.local/state/bridgeforge. The game, the desktop tasks and SSH all run as the same user, so they all read one flag."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "BridgeForge"
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(xdg) if xdg else Path.home() / ".local" / "state") / "bridgeforge"


def pause_file(state: Path | None = None) -> Path:
    if state is not None:
        return Path(state) / PAUSE_FILE_NAME
    override = os.environ.get(PAUSE_FILE_ENV, "").strip()
    return Path(override) if override else machine_dir() / PAUSE_FILE_NAME


def pause(reason: str, *, state: Path | None = None, now: datetime | None = None) -> dict:
    """Set the flag; a second pause replaces the reason."""
    record = {"paused_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), "reason": reason.strip() or "(no reason given)"}
    path = pause_file(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, record, indent=2)
    return record


def resume(*, state: Path | None = None) -> bool:
    """Clear the flag; whether one was set."""
    path = pause_file(state)
    if not path.exists():
        return False
    path.unlink()
    return True


def paused(*, state: Path | None = None) -> dict | None:
    """The pause record, or None when live testing is not paused. An unreadable flag still pauses."""
    path = pause_file(state)
    try:
        path.stat()  # not exists(): that reads a denied or failing check as "no flag" (review)
    except FileNotFoundError:
        return None
    except OSError:
        return {"paused_at": None, "reason": f"{path.name} cannot be checked"}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"paused_at": None, "reason": f"{path.name} exists but cannot be read"}
    return record if isinstance(record, dict) else {"paused_at": None, "reason": f"{path.name} holds no record"}


def refusal(*, state: Path | None = None) -> str | None:
    """The refusal text for a game start while paused, else None."""
    record = paused(state=state)
    if record is None:
        return None
    since = f" since {record.get('paused_at')}" if record.get("paused_at") else ""
    return (f"live testing is paused{since}: {record.get('reason')}. Nothing was started; "
            "`bridgeforge live resume` lifts it, on the owner's word.")


def add_parser(subcommands) -> None:
    live = subcommands.add_parser("live", help="pause or resume live testing on this machine: while paused, no live, save-reload, "
                                               "duel, smoke, gene boot or java-matrix run starts (ROADMAP-3 98.16)")
    actions = live.add_subparsers(dest="live_action", required=True)
    stop = actions.add_parser("pause", help="set the pause flag in the user's local application data (every checkout reads it)")
    stop.add_argument("--reason", default="", help="why, in the owner's words")
    actions.add_parser("resume", help="clear the pause flag")
    actions.add_parser("status", help="say whether live testing is paused")


def run_cli(args: argparse.Namespace) -> int:
    if args.live_action == "pause":
        record = pause(args.reason)
        print(f"Live testing paused at {record['paused_at']}: {record['reason']}")
    elif args.live_action == "resume":
        print("Live testing resumed." if resume() else "Live testing was not paused.")
    else:
        record = paused()
        # `is not None`: a flag holding `{}` still pauses (refusal() refuses it), so status must say so too (review)
        print(f"PAUSED since {record.get('paused_at')}: {record.get('reason')}" if record is not None else "not paused")
    return 0
