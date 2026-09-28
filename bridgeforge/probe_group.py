"""`bridgeforge probe-group`: probe several finished mods in one live session (ROADMAP P15 item 24).

The probe (0.2.5) reads one config of lists and maps, and never uses the target mod id for a check, so a
group is probed by merging each member's `build_probe_config` output. 66 mods reached UNATTENDED_DONE on
2026-09-27 and each still needs a probe run; one mod per session is the bottleneck.

- `plan`: workspaces whose revival report ends `READY_FOR_LIVE_TEST`, grouped so no two members share a mod
  id or a content id (hull, variant, wing, special item) and every member's declared dependencies are in the
  rig. Total conversions always go alone. Anything unplaceable is listed with its reason.
- `install_group`: copies or syncs each member into the rig (shipped files only), writes the merged config
  and rig marker, installs the probe, and sets enabled_mods.json (members, their dependencies, the probe).
- `group_report`: after a run, attributes each probe FAIL line to the member whose content id it names, and
  each crash to the member whose jar threw (log-triage attribution), giving one verdict per member.
Refuses to write anywhere but an isolated rig (starsector-core a junction/symlink), like probe-config.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .copy_drift import _collect, compare_copies
from .probe_config import CONFIG_FILE, RIG_MARKER_FILE, _install_probe_mod, _refuse_non_rig, build_probe_config
from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1
PROBE_MOD_ID = "bridgeforge_probe"
READY_STATUS = "READY_FOR_LIVE_TEST"
_STATUS_LINE = re.compile(r"^[A-Z][A-Z_]+$")


class ProbeGroupError(ValueError):
    """Raised for a missing queue/rig, an unknown group, or an unreadable plan."""


def _report_status(workspace: Path) -> str | None:
    report = workspace / "working" / "reports" / "REVIVAL_REPORT.md"
    if not report.is_file():
        return None
    # Older hand-written reports bold the status line (**READY_FOR_LIVE_TEST**, RogueSynth and Xenoargh AI
    # Overhaul, 2026-09-28); project_board reads that form too.
    lines = [line.strip().strip("*").strip() for line in report.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    statuses = [line for line in lines if _STATUS_LINE.match(line)]
    return statuses[-1] if statuses else None


def _latest_revive_status(workspace: Path) -> str | None:
    result = workspace / "reports" / "revive" / "REVIVE.json"
    if not result.is_file():
        return None
    try:
        return json.loads(result.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return None


def ready_workspaces(queue: Path) -> list[Path]:
    """Workspaces whose revival report's last status line is READY_FOR_LIVE_TEST and, when `revive` has run,
    whose latest revive result is UNATTENDED_DONE: a report status can be stale (GRP-2, 2026-09-27:
    Covert-Cargoliners' report said READY_FOR_LIVE_TEST from an earlier pass while revive said ESCALATED)."""
    queue = Path(queue).expanduser().resolve()
    if not queue.is_dir():
        raise ProbeGroupError(f"{queue} is not a directory.")
    return [ws for ws in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_"))
            if (ws / "working" / "mod_info.json").is_file() and _report_status(ws) == READY_STATUS
            and _latest_revive_status(ws) in (None, "UNATTENDED_DONE")]


def _mod_info(root: Path) -> dict:
    info = _load_lenient_json_file(root / "mod_info.json")
    return info if isinstance(info, dict) else {}


def rig_mod_ids(rig_mods: Path) -> dict[str, str]:
    """{mod id: folder name} for every mod installed in the rig."""
    found = {}
    for child in sorted(p for p in Path(rig_mods).iterdir() if p.is_dir()):
        mod_id = _mod_info(child).get("id")
        if isinstance(mod_id, str) and mod_id:
            found[mod_id] = child.name
    return found


def dependency_closure(rig_mods: Path, dependencies: list[str], installed: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """(every mod id needed, dependencies first; ids missing from the rig), following dependencies of dependencies.

    GRP-SPARKLE (2026-09-27): SPARKLE needs Secrets of the Frontier, which needs LazyLib, GraphicsLib, LunaLib
    and MagicLib; enabling only direct dependencies would have left the launcher reporting unmet requirements.
    """
    installed = rig_mod_ids(rig_mods) if installed is None else installed
    ordered: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()

    def visit(mod_id: str) -> None:
        if mod_id in seen:
            return
        seen.add(mod_id)
        folder = installed.get(mod_id)
        if folder is None:
            missing.append(mod_id)
            return
        info = _mod_info(Path(rig_mods) / folder)
        for dep in info.get("dependencies") or []:
            if isinstance(dep, dict) and isinstance(dep.get("id"), str) and dep["id"]:
                visit(dep["id"])
        ordered.append(mod_id)

    for mod_id in dependencies:
        visit(mod_id)
    return ordered, missing


def _member(workspace: Path) -> dict:
    working = workspace / "working"
    info = _mod_info(working)
    config = build_probe_config(working)
    deps = [d.get("id") for d in info.get("dependencies") or [] if isinstance(d, dict) and d.get("id")]
    content = set(config["hulls"]) | set(config["content_variants"]["ship"]) | set(config["content_variants"]["other"]) \
        | set(config["content_wings"]) | set(config["content_special_items"])
    return {"workspace": workspace.name, "mod_id": config["target_mod_id"], "dependencies": sorted(set(deps)),
            "total_conversion": str(info.get("totalConversion", "")).lower() == "true", "content": sorted(content),
            "config": config}


def plan_groups(queue: Path, rig: Path, size: int = 8, workspaces: list[Path] | None = None) -> dict:
    """Greedy grouping: each member joins the first group it shares no mod or content id with."""
    rig = Path(rig).expanduser().resolve()
    installed = rig_mod_ids(rig / "mods")
    members, unplaced = [], []
    for workspace in workspaces if workspaces is not None else ready_workspaces(queue):
        try:
            member = _member(workspace)
        except Exception as exc:  # an unreadable mod is reported, never fatal to the plan
            unplaced.append({"workspace": workspace.name, "reason": f"probe config failed: {exc}"})
            continue
        game_version = str(_mod_info(workspace / "working").get("gameVersion") or "")
        if not game_version.startswith("0.98"):
            # The launcher treats any other gameVersion as an unmet requirement and refuses to start (GRP-2,
            # 2026-09-27: Covert-Cargoliners still said 0.95.1a-RC6 under a stale READY_FOR_LIVE_TEST report).
            unplaced.append({"workspace": workspace.name, "reason": f"gameVersion {game_version or 'missing'} is not 0.98a: the launcher would refuse it (revive it first)"})
            continue
        _, missing = dependency_closure(rig / "mods", [dep for dep in member["dependencies"] if dep != member["mod_id"]], installed)
        if missing:
            unplaced.append({"workspace": workspace.name, "reason": f"dependencies not in the rig: {', '.join(missing)}"})
            continue
        members.append(member)
    groups: list[list[dict]] = []
    for member in members:
        if member["total_conversion"]:
            groups.append([member])
            continue
        ids = {member["mod_id"], *member["content"]}
        for group in groups:
            if len(group) >= size or group[0]["total_conversion"]:
                continue
            if all(not ids & {other["mod_id"], *other["content"]} for other in group):
                group.append(member)
                break
        else:
            groups.append([member])
    return {
        "schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_PLAN", "rig": str(rig), "size": size,
        "groups": [{"group": index, "members": [{k: v for k, v in m.items() if k != "config"} for m in group]}
                   for index, group in enumerate(groups, 1)],
        "unplaced": unplaced,
    }


def merge_configs(configs: list[dict]) -> dict:
    """One probe config for a group: lists united, maps merged, per-member ids kept for the report."""
    merged: dict = {
        "schema_version": 1, "target_mod_id": "group:" + ",".join(c["target_mod_id"] for c in configs),
        "hulls": [], "variants": {}, "track_entities": [], "factions": [], "content_variants": {"ship": [], "other": []},
        "content_ship_hulls": {}, "content_special_items": [], "content_wings": [], "hulls_skipped_no_variant": [],
        "setups": [], "apply": configs[0].get("apply", "once-per-save") if configs else "once-per-save",
        "campaign_interval_days": min((c["campaign_interval_days"] for c in configs), default=5.0),
        "combat_seconds": max((c["combat_seconds"] for c in configs), default=60.0),
        "combat_cap_per_side": max((c["combat_cap_per_side"] for c in configs), default=12),
        "group_members": {}, "mod_systems": [], "mod_body_types": {},
    }
    for c in configs:
        for key in ("hulls", "track_entities", "factions", "content_special_items", "content_wings", "hulls_skipped_no_variant"):
            merged[key] = sorted(set(merged[key]) | set(c.get(key) or []))
        for kind in ("ship", "other"):
            merged["content_variants"][kind] = sorted(set(merged["content_variants"][kind]) | set(c["content_variants"][kind]))
        merged["variants"].update(c.get("variants") or {})
        merged["content_ship_hulls"].update(c.get("content_ship_hulls") or {})
        merged["mod_systems"] = sorted(set(merged["mod_systems"]) | set(c.get("mod_systems") or []))
        merged["mod_body_types"].update(c.get("mod_body_types") or {})
        merged["group_members"][c["target_mod_id"]] = {
            "hulls": sorted(c["hulls"]), "variants": sorted(set(c["content_variants"]["ship"]) | set(c["content_variants"]["other"])),
            "wings": sorted(c["content_wings"]), "items": sorted(c["content_special_items"]), "factions": sorted(c["factions"])}
    return merged


def install_group(plan: dict, group_number: int, queue: Path, rig: Path, install_probe: bool = True) -> dict:
    """Copy/sync members into the rig, write the merged config, set enabled_mods.json."""
    rig = Path(rig).expanduser().resolve()
    queue = Path(queue).expanduser().resolve()
    _refuse_non_rig(rig)
    group = next((g for g in plan.get("groups", []) if g["group"] == group_number), None)
    if group is None:
        raise ProbeGroupError(f"no group {group_number} in the plan (it has {len(plan.get('groups', []))}).")
    mods_dir = rig / "mods"
    installed = rig_mod_ids(mods_dir)
    configs, copied = [], []
    for member in group["members"]:
        working = queue / member["workspace"] / "working"
        target = mods_dir / member["workspace"]
        if not target.exists():
            for relative, source in _collect(working).items():
                (target / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target / relative)
            copied.append({"workspace": member["workspace"], "action": "copied"})
        else:
            drift = compare_copies(working, target)
            if drift["drift_count"]:
                for relative in [*drift["missing_in_deployed"], *(d["path"] for d in drift["different"])]:
                    (target / relative).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(working / relative, target / relative)
                copied.append({"workspace": member["workspace"], "action": f"synced {drift['drift_count']} file(s)"})
        configs.append(build_probe_config(working))
        installed[member["mod_id"]] = member["workspace"]
    config = merge_configs(configs)
    common = rig / "saves" / "common"
    common.mkdir(parents=True, exist_ok=True)
    (common / CONFIG_FILE).write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
    if not (common / RIG_MARKER_FILE).is_file():
        (common / RIG_MARKER_FILE).write_text("rig\n", encoding="utf-8")
    if install_probe:
        _install_probe_mod(rig)
    enabled = []
    for member in group["members"]:
        needed, _ = dependency_closure(mods_dir, [dep for dep in member["dependencies"] if dep != member["mod_id"]])
        for mod_id in [*needed, member["mod_id"]]:
            if mod_id not in enabled:
                enabled.append(mod_id)
    enabled.append(PROBE_MOD_ID)
    enabled_path = mods_dir / "enabled_mods.json"
    backup = enabled_path.with_name("enabled_mods.json.pre-bftest.bak")
    if enabled_path.is_file() and not backup.exists():
        shutil.copy2(enabled_path, backup)
    enabled_path.write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
    return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_INSTALL", "group": group_number,
            "members": [m["workspace"] for m in group["members"]], "copied": copied, "enabled_mods": enabled,
            "config_path": str(common / CONFIG_FILE), "checked_ids": len(config["content_variants"]["ship"]) + len(config["content_variants"]["other"])
            + len(config["content_wings"]) + len(config["content_special_items"])}


_PROBE_LINE = re.compile(r"BF-PROBE\|(?P<version>[^|]*)\|(?P<check>[^|]*)\|(?P<status>[^|]*)\|(?P<subject>[^|]*)\|(?P<detail>.*)$")


def group_report(log: Path, config: dict, mods_dir: Path | None = None) -> dict:
    """One verdict per member: probe FAIL lines matched by the content id or faction they name, and crashes
    by the mod whose jar threw (log-triage attribution). Unmatched FAILs are reported for the group."""
    from .log_triage import triage_log

    members = config.get("group_members") or {}
    owner: dict[str, str] = {}
    for mod_id, ids in members.items():
        for kind in ("hulls", "variants", "wings", "items", "factions"):
            for item in ids.get(kind, []):
                owner.setdefault(item, mod_id)
    verdicts = {mod_id: {"failures": [], "crashes": []} for mod_id in members}
    unattributed, seen_content = [], False
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        match = _PROBE_LINE.search(line)
        if not match:
            continue
        if match["check"] == "content-ids" and match["subject"] == "all-content":
            seen_content = True
        if match["status"] != "FAIL":
            continue
        subject = match["subject"].split(":", 1)[-1].split("/", 1)[0]
        mod_id = owner.get(subject)
        entry = f"{match['check']}|{match['subject']}|{match['detail'].strip()[:200]}"
        (verdicts[mod_id]["failures"] if mod_id else unattributed).append(entry)
    triage = triage_log(log, mods_dir=mods_dir) if mods_dir is not None else triage_log(log)
    for event in triage["fatal"] + triage["mod_errors"]:
        suspect = event.get("suspect")
        text = f"{event.get('matched_rule') or event.get('level')}: {str(event.get('message'))[:160]}"
        (verdicts[suspect]["crashes"] if suspect in verdicts else unattributed).append(text)
    group_crash = any(not item.startswith(("content-ids", "faction", "planet", "rings", "submarket", "fleet", "setup", "combat"))
                      for item in unattributed) or (triage["counts"]["FATAL"] and not any(v["crashes"] for v in verdicts.values()))
    for mod_id, verdict in verdicts.items():
        if verdict["failures"] or verdict["crashes"]:
            verdict["verdict"] = "FAIL"
        elif group_crash:
            verdict["verdict"] = "UNCLEAR"  # a crash no member's jar owns: rerun the member alone to clear it
        else:
            verdict["verdict"] = "PASS" if seen_content else "INCOMPLETE"
    return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_REPORT", "log": str(log),
            "content_ids_ran": seen_content, "fatal": triage["counts"]["FATAL"], "mod_errors": triage["counts"]["MOD-ERROR"],
            "members": verdicts, "unattributed": unattributed,
            "note": "INCOMPLETE means the probe's content-ids check never ran (start a New Game and wait one in-game day)."}
