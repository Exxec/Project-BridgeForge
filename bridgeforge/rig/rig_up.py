"""`rig-up RIG --mods ID...`: bring a test rig to a known, recorded state in one command (ROADMAP item 73 G3).

Done by hand before every live test: sync the working copies into the rig, write `enabled_mods.json` (the mods, their dependencies,
SpeedUp), optionally the probe and its config, then run `rig-doctor`. `probe-group install` does this for a planned group; this
does it for any set of mod ids, a workspace's mod or a provider already in the rig. It records the state it left (enabled ids,
versions, file hashes of the synced copies) in `<rig>/rig_up_state.json`, which `probe-group record` copies into the run record.

Refuses, before changing anything, unless the rig's `starsector-core` is a junction or symlink (house rule), when a game is running
under the rig, when an id is unknown or ambiguous, or when a dependency is missing from the rig.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from bridgeforge.boot_test import _is_link, _running_java_under
from bridgeforge.run_manifest import RIG_STATE_FILE, ManifestError, record_candidates, refuse_if_owned
from bridgeforge.safeio import atomic_write_json, atomic_write_text


class RigUpError(ValueError):
    """The rig is not isolated or busy, an id cannot be resolved, or a dependency is missing."""


def _resolve_ids(queue: Path, mods_dir: Path, mod_ids: list[str]) -> tuple[dict[str, Path], list[str]]:
    """({mod id: workspace} for ids a queue workspace provides, [ids that are providers already in the rig])."""
    from bridgeforge.probe.probe_group import _workspaces_by_mod_id, rig_mod_ids

    owners = _workspaces_by_mod_id(queue, mods_dir) if Path(queue).is_dir() else {}
    installed = rig_mod_ids(mods_dir)
    members: dict[str, Path] = {}
    providers: list[str] = []
    problems: list[str] = []
    for mod_id in dict.fromkeys(mod_ids):
        if mod_id in owners and owners[mod_id] is None:
            problems.append(f"{mod_id}: two or more workspaces (or rig folders) share this id; remove one")
        elif owners.get(mod_id) is not None:
            members[mod_id] = owners[mod_id]
        elif mod_id in installed:
            providers.append(mod_id)
        else:
            problems.append(f"{mod_id}: no workspace in {queue} and no mod in the rig has this id")
    if problems:
        raise RigUpError("; ".join(problems))
    return members, providers


def _declared_dependencies(members: dict[str, Path]) -> list[str]:
    from bridgeforge.probe.probe_group import _mod_info

    found: list[str] = []
    for mod_id, workspace in members.items():
        for dep in _mod_info(workspace / "working").get("dependencies") or []:
            if isinstance(dep, dict) and isinstance(dep.get("id"), str) and dep["id"] != mod_id and dep["id"] not in found:
                found.append(dep["id"])
    return found


def rig_up(rig: Path, queue: Path, mod_ids: list[str], *, probe_config: bool = False, also_enable: list[str] | None = None,
           with_lunalib: bool = False, no_lunalib: bool = False, doctor=None, today: str | None = None) -> dict:
    from bridgeforge.live.live_trust import shipped_hash
    from bridgeforge.probe.probe_config import CONFIG_FILE, RIG_MARKER_FILE, _install_probe_mod, build_probe_config
    from bridgeforge.probe.probe_group import (LUNALIB_ID, PROBE_MOD_ID, SPEEDUP_MOD_ID, _mod_info, _move_aside_duplicate_ids, _refuse_running_game,
                              _reset_combat_round, dependency_closure, dependency_version_conflicts, expand_also_enable, lunalib_rule,
                              merge_configs, rig_mod_ids, sync_working_copy)

    rig, queue = Path(rig).expanduser().resolve(), Path(queue).expanduser().resolve()
    if not _is_link(rig / "starsector-core"):
        raise RigUpError(f"{rig / 'starsector-core'} is not a junction/symlink: rig-up refuses a non-isolated rig")
    if _running_java_under(rig):
        raise RigUpError(f"java is already running under {rig}; close the game first")
    _refuse_running_game(rig)
    try:
        refuse_if_owned(rig, "rig-up")  # R1: a prepared run owns the staged files until it is released
    except ManifestError as exc:
        raise RigUpError(str(exc)) from exc
    if not mod_ids:
        raise RigUpError("--mods needs at least one mod id")
    mods_dir = rig / "mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    members, providers = _resolve_ids(queue, mods_dir, mod_ids)
    if probe_config and not members:
        raise RigUpError("--probe-config needs at least one mod that comes from a workspace")
    missing = dependency_closure(mods_dir, _declared_dependencies(members), rig_mod_ids(mods_dir))[1]
    if missing:
        raise RigUpError("dependencies not in the rig: " + ", ".join(missing))

    synced = {mod_id: sync_working_copy(workspace / "working", mods_dir / workspace.name) for mod_id, workspace in members.items()}
    moved_aside = _move_aside_duplicate_ids(rig, {mod_id: mods_dir / ws.name for mod_id, ws in members.items()})
    installed = rig_mod_ids(mods_dir)
    probe_note = None
    if probe_config:
        config = merge_configs([build_probe_config(ws / "working") for ws in members.values()])
        common = rig / "saves" / "common"
        common.mkdir(parents=True, exist_ok=True)
        _reset_combat_round(common)
        atomic_write_text(common / CONFIG_FILE, json.dumps(config, indent=2, sort_keys=True))
        if not (common / RIG_MARKER_FILE).is_file():
            atomic_write_text(common / RIG_MARKER_FILE, "rig\n")
        _install_probe_mod(rig)
        installed = rig_mod_ids(mods_dir)
        probe_note = str(common / CONFIG_FILE)

    enabled: list[str] = []
    wanted = [*members, *providers, *expand_also_enable(also_enable or [], installed)]
    for mod_id in wanted:
        needed, gone = dependency_closure(mods_dir, [mod_id], installed)
        if gone:
            raise RigUpError(f"{mod_id}: dependencies not in the rig: {', '.join(gone)}")
        enabled.extend(m for m in needed if m not in enabled)
    add_lunalib, lunalib_why, advice = lunalib_rule(enabled, installed, mods_dir, with_lunalib=with_lunalib, no_lunalib=no_lunalib)
    if add_lunalib:
        enabled.append(LUNALIB_ID)
    if probe_config:
        enabled.append(PROBE_MOD_ID)
    if SPEEDUP_MOD_ID in installed and SPEEDUP_MOD_ID not in enabled:
        enabled.append(SPEEDUP_MOD_ID)
    enabled_path = mods_dir / "enabled_mods.json"
    backup = enabled_path.with_name("enabled_mods.json.pre-bftest.bak")
    if enabled_path.is_file() and not backup.exists():
        atomic_write_text(backup, enabled_path.read_text(encoding="utf-8"))
    atomic_write_text(enabled_path, json.dumps({"enabledMods": enabled}))

    state = {"schema_version": 1, "mode": "RIG_UP_STATE", "date": today or date.today().isoformat(), "rig": str(rig),
             "enabled": [{"id": mod_id, "version": str(_mod_info(mods_dir / installed[mod_id]).get("version") or ""), "folder": installed[mod_id],
                          "shipped_sha256": shipped_hash(mods_dir / installed[mod_id]) if mod_id in members else None} for mod_id in enabled if mod_id in installed],
             "probe_config": probe_note}
    atomic_write_json(rig / RIG_STATE_FILE, state)
    record_candidates(rig, {mod_id: ws / "working" for mod_id, ws in members.items()})  # the manifest binds these to the staged files
    working_copies = {mod_id: ws / "working" for mod_id, ws in members.items()}
    if doctor is None:
        from bridgeforge.rig.rig_doctor import rig_doctor as doctor
    report = doctor(rig, working_copies=working_copies, real_install=Path((rig / "starsector-core").resolve()).parent)
    return {"schema_version": 1, "mode": "RIG_UP", "rig": str(rig), "members": {m: w.name for m, w in members.items()}, "providers": providers,
            "synced": {m: a for m, a in synced.items() if a}, "moved_aside": moved_aside, "enabled_mods": enabled, "lunalib": lunalib_why,
            "lunalib_advice": advice, "dependency_version_conflicts": dependency_version_conflicts(mods_dir, enabled), "state": str(rig / RIG_STATE_FILE),
            "doctor": {"status": report["status"], "checks": [c for c in report["checks"] if c["status"] in ("FAIL", "WARN")]}}


def read_rig_state(rig: Path) -> dict | None:
    """The state `rig-up` last recorded for this rig, or None."""
    try:
        data = json.loads((Path(rig) / RIG_STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def add_parser(subcommands) -> None:
    up = subcommands.add_parser("rig-up", help="bring a test rig to a recorded state: sync the working copies of --mods into it, enable them with their dependencies (and SpeedUp), optionally install the probe and its config, run rig-doctor; refuses unless starsector-core is a junction/symlink")
    up.add_argument("rig", type=Path)
    up.add_argument("--mods", nargs="+", required=True, metavar="ID", help="mod ids: a queue workspace's mod is synced into the rig, a provider already in the rig is only enabled")
    up.add_argument("--queue", type=Path, help="default: <repo>/In operation")
    up.add_argument("--probe-config", action="store_true", help="also install the probe mod and write its config for the synced mods")
    up.add_argument("--also-enable", action="append", default=[], metavar="MOD_OR_SET", help="also enable this mod id or named set (aotd); repeatable")
    up.add_argument("--with-lunalib", action="store_true")
    up.add_argument("--no-lunalib", action="store_true")
    up.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    from bridgeforge.probe.probe_config import ProbeConfigError
    from bridgeforge.probe.probe_group import ProbeGroupError
    from bridgeforge.substitutes import REPO_ROOT

    queue = (args.queue or REPO_ROOT / "In operation").expanduser().resolve()
    try:
        result = rig_up(args.rig, queue, args.mods, probe_config=args.probe_config, also_enable=args.also_enable,
                        with_lunalib=args.with_lunalib, no_lunalib=args.no_lunalib)
    except (RigUpError, ProbeGroupError, ProbeConfigError, OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        for mod_id, action in result["synced"].items():
            print(f"  {mod_id}: {action}")
        print(f"Rig up: enabled {', '.join(result['enabled_mods'])}")
        for item in result["dependency_version_conflicts"]:
            print(f"  WARN {item['mod_id']} wants {item['dependency']} {item['wanted']}, rig has {item['installed']} (RC8-23)")
        print(f"Rig doctor: {result['doctor']['status']}; state recorded in {result['state']}")
        for check in result["doctor"]["checks"]:
            print(f"  {check['status']:<5} {check['name']}: {check['detail']}")
    return 1 if result["doctor"]["status"] == "FAIL" else 0
