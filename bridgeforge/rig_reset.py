"""`rig-reset`: put a test rig back to a clean state between runs (ROADMAP 70 H1.7).

Runs left state behind: an enabled-mods list edited by hand, probe round counters, and a pile of saves (121 accumulated by 2026-10-11)
among which the main menu's Continue picks the last one used. Dry run by default; `--apply` acts. Saves are moved into
`saves/_archived-<date>/`, never deleted; the enabled-mods list is restored from `mods/enabled_mods.json.pre-bftest.bak`, the copy
`probe-group install` makes before its first change.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date
from pathlib import Path

from .boot_test import _is_link
from .safeio import atomic_write_text, safe_unlink

BACKUP_NAME = "enabled_mods.json.pre-bftest.bak"
DEFAULT_KEEP_DAYS = 7


def plan_reset(rig: Path, keep_days: float = DEFAULT_KEEP_DAYS, now: float | None = None) -> dict:
    rig = Path(rig).expanduser().resolve()
    if not _is_link(rig / "starsector-core"):
        raise ValueError(f"{rig / 'starsector-core'} is not a junction/symlink: rig-reset refuses a non-isolated rig")
    now = now or time.time()
    mods, saves, common = rig / "mods", rig / "saves", rig / "saves" / "common"
    enabled = mods / "enabled_mods.json"
    backup = mods / BACKUP_NAME
    actions: list[dict] = []
    if backup.is_file() and (not enabled.is_file() or enabled.read_bytes() != backup.read_bytes()):
        actions.append({"action": "restore-enabled-mods", "from": backup.name, "to": enabled.name})
    for stale in sorted(common.glob("bf_probe_combat_round*")) if common.is_dir() else []:
        actions.append({"action": "remove-probe-state", "path": stale.name})
    if saves.is_dir():
        for folder in sorted(p for p in saves.iterdir() if p.is_dir() and p.name.startswith("save_")):
            age = (now - folder.stat().st_mtime) / 86400.0
            if age > keep_days:
                actions.append({"action": "archive-save", "path": folder.name, "age_days": round(age, 1)})
    return {"rig": str(rig), "keep_days": keep_days, "actions": actions}


def apply_reset(rig: Path, plan: dict) -> list[str]:
    rig = Path(rig).expanduser().resolve()
    mods, saves, common = rig / "mods", rig / "saves", rig / "saves" / "common"
    done: list[str] = []
    destination = saves / f"_archived-{date.today().isoformat()}"
    for step in plan["actions"]:
        if step["action"] == "restore-enabled-mods":
            atomic_write_text(mods / "enabled_mods.json", (mods / BACKUP_NAME).read_text(encoding="utf-8"), newline="")
        elif step["action"] == "remove-probe-state":
            safe_unlink(common / step["path"], [common])
        elif step["action"] == "archive-save":
            destination.mkdir(parents=True, exist_ok=True)
            shutil.move(str(saves / step["path"]), str(destination / step["path"]))
        done.append(f"{step['action']} {step.get('path') or step.get('to')}")
    return done


def add_parser(subcommands) -> None:
    reset = subcommands.add_parser("rig-reset", help="clean a test rig between runs: restore the original enabled mods, clear probe round state, move saves older than N days into saves/_archived-<date>/ (dry run unless --apply)")
    reset.add_argument("rig", type=Path)
    reset.add_argument("--keep-days", type=float, default=DEFAULT_KEEP_DAYS, help=f"keep saves newer than this many days (default {DEFAULT_KEEP_DAYS})")
    reset.add_argument("--apply", action="store_true")
    reset.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        plan = plan_reset(args.rig, args.keep_days)
        done = apply_reset(args.rig, plan) if args.apply else []
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({**plan, "applied": bool(args.apply), "done": done}, indent=2))
    else:
        counts: dict[str, int] = {}
        for step in plan["actions"]:
            counts[step["action"]] = counts.get(step["action"], 0) + 1
        print(("Applied: " if args.apply else "Would do (add --apply): ") + (", ".join(f"{n} x {a}" for a, n in counts.items()) or "nothing, the rig is clean"))
    return 0
