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


class ProbeGroupError(ValueError):
    """Raised for a missing queue/rig, an unknown group, or an unreadable plan."""


def _report_status(workspace: Path) -> str | None:
    from .report_status import report_status

    return report_status(workspace / "working" / "reports" / "REVIVAL_REPORT.md")


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


# A campaign mod this large runs alone by default (ROADMAP P15 31.3): it creates star systems and ships this many
# content ids. Exigency, Broken Star, FlowerGod, Omega Trauma and SEEKER were planned into groups by hand, 2026-09-28.
SOLO_CONTENT_THRESHOLD = 60


def _is_large_campaign_mod(member: dict) -> bool:
    config = member.get("config") or {}
    return bool(config.get("mod_systems")) and len(member.get("content") or ()) >= SOLO_CONTENT_THRESHOLD


PROVIDER_READY = ("UNATTENDED_DONE",)


def _providers_for(queue: Path, missing: list[str]) -> tuple[list[dict], list[str]]:
    """Ready workspaces in the queue that provide each missing dependency id (ROADMAP 36.1, 2026-10-04: SCY Nation
    Utility, Yunru's Glinthawk/Old School and MUDA waited on SCY, YunruCore and ORA). A provider must declare the id
    in working/mod_info.json and its latest revive must be UNATTENDED_DONE; none or two is a problem, never a guess.
    Dependencies of a provider that are themselves missing are looked up the same way."""
    found: list[dict] = []
    problems: list[str] = []
    pending = list(missing)
    seen: set[str] = set()
    by_id: dict[str, list[Path]] = {}
    for workspace in sorted(p for p in Path(queue).iterdir() if p.is_dir() and not p.name.startswith("_")):
        mod_id = _mod_info(workspace / "working").get("id") if (workspace / "working" / "mod_info.json").is_file() else None
        if isinstance(mod_id, str) and mod_id:
            by_id.setdefault(mod_id, []).append(workspace)
    while pending:
        mod_id = pending.pop(0)
        if mod_id in seen:
            continue
        seen.add(mod_id)
        candidates = by_id.get(mod_id, [])
        ready = [w for w in candidates if _latest_revive_status(w) in PROVIDER_READY]
        if len(ready) != 1:
            states = ", ".join(f"{w.name}={_latest_revive_status(w)}" for w in candidates) or "no workspace declares it"
            problems.append(f"{mod_id}: {'two or more ready providers' if len(ready) > 1 else 'no ready provider'} ({states})")
            continue
        info = _mod_info(ready[0] / "working")
        found.append({"mod_id": mod_id, "workspace": ready[0].name, "version": str(info.get("version") or "")})
        for dep in info.get("dependencies") or []:
            if isinstance(dep, dict) and isinstance(dep.get("id"), str) and dep["id"] not in seen:
                pending.append(dep["id"])
    return found, problems


def stage_providers(group: dict, queue: Path, rig: Path) -> list[dict]:
    """Copy each provider a group's members need into the rig (shipped files only) and verify its identity: the
    rig folder's id and version equal the workspace's and copy_drift reports no drift. A rig folder already holding
    that id, edited in the rig, is refused rather than overwritten (ROADMAP 36.1)."""
    rig = Path(rig).expanduser().resolve()
    _refuse_non_rig(rig)
    mods_dir = rig / "mods"
    installed = rig_mod_ids(mods_dir)
    staged = []
    for provider in [p for m in group["members"] for p in m.get("stage_providers") or []]:
        if any(s["mod_id"] == provider["mod_id"] for s in staged):
            continue
        working = Path(queue) / provider["workspace"] / "working"
        if provider["mod_id"] in installed:
            target = mods_dir / installed[provider["mod_id"]]
            drift = compare_copies(working, target)
            if drift["drift_count"]:
                raise ProbeGroupError(f"{target.name} already holds {provider['mod_id']} but differs from {provider['workspace']} "
                                      f"({drift['drift_count']} file(s)); sync or remove it by hand, BridgeForge will not overwrite it.")
            staged.append({**provider, "action": "already staged"})
            continue
        target = mods_dir / provider["workspace"]
        for relative, source in _collect(working).items():
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / relative)
        info = _mod_info(target)
        if info.get("id") != provider["mod_id"] or str(info.get("version") or "") != provider["version"] or compare_copies(working, target)["drift_count"]:
            raise ProbeGroupError(f"staged {provider['workspace']} does not match its workspace (id, version or files); remove {target} and retry.")
        installed[provider["mod_id"]] = target.name
        staged.append({**provider, "action": "copied"})
    return staged


def plan_groups(queue: Path, rig: Path, size: int = 8, workspaces: list[Path] | None = None,
                exclude: set[str] | None = None, solo: set[str] | None = None, auto_solo: bool = True) -> dict:
    """Greedy grouping: each member joins the first group it shares no mod or content id with. `exclude` leaves
    workspaces out, `solo` gives each its own group, and large campaign mods run solo unless `auto_solo` is off."""
    exclude, solo = set(exclude or ()), set(solo or ())
    rig = Path(rig).expanduser().resolve()
    installed = rig_mod_ids(rig / "mods")
    members, unplaced = [], []
    for workspace in workspaces if workspaces is not None else ready_workspaces(queue):
        if workspace.name in exclude:
            continue
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
            found, problems = _providers_for(queue, missing)
            if problems:
                unplaced.append({"workspace": workspace.name, "reason": f"dependencies not in the rig: {', '.join(missing)}",
                                 "providers": problems})
                continue
            member["stage_providers"] = found
        members.append(member)
    groups: list[list[dict]] = []
    solo_groups: list[list[dict]] = []
    for member in members:
        if member["total_conversion"] or member["workspace"] in solo or (auto_solo and _is_large_campaign_mod(member)):
            solo_groups.append([member])
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
    groups += solo_groups
    return {
        "schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_PLAN", "rig": str(rig), "size": size,
        "groups": [{"group": index, "members": [{k: v for k, v in m.items() if k != "config"} for m in group]}
                   for index, group in enumerate(groups, 1)],
        "unplaced": unplaced,
    }


def bisect_group(plan: dict, group_number: int) -> dict:
    """Split a failed group into two new groups at the end of the plan (ROADMAP 36.8): the first half and the rest
    of its members, in plan order. Each member keeps its own dependencies and providers, which install resolves,
    so both halves stay dependency-closed. The original group stays in the plan, marked `bisected_into`."""
    group = next((g for g in plan.get("groups", []) if g["group"] == group_number), None)
    if group is None:
        raise ProbeGroupError(f"no group {group_number} in the plan.")
    members = group["members"]
    if len(members) < 2:
        raise ProbeGroupError(f"group {group_number} has one member; run it alone to read its result.")
    half = (len(members) + 1) // 2
    last = max(g["group"] for g in plan["groups"])
    new = [{"group": last + 1, "members": members[:half], "bisected_from": group_number},
           {"group": last + 2, "members": members[half:], "bisected_from": group_number}]
    group["bisected_into"] = [last + 1, last + 2]
    plan["groups"].extend(new)
    return plan


def merge_configs(configs: list[dict]) -> dict:
    """One probe config for a group: lists united, maps merged, per-member ids kept for the report."""
    merged: dict = {
        "schema_version": 1, "target_mod_id": "group:" + ",".join(c["target_mod_id"] for c in configs),
        "hulls": [], "variants": {}, "track_entities": [], "factions": [], "patched_factions": [], "content_variants": {"ship": [], "other": []},
        "content_ship_hulls": {}, "content_special_items": [], "content_wings": [], "hulls_skipped_no_variant": [],
        "setups": [], "apply": configs[0].get("apply", "once-per-save") if configs else "once-per-save",
        "campaign_interval_days": min((c["campaign_interval_days"] for c in configs), default=5.0),
        "combat_seconds": max((c["combat_seconds"] for c in configs), default=60.0),
        "combat_cap_per_side": max((c["combat_cap_per_side"] for c in configs), default=12),
        "group_members": {}, "mod_systems": [], "mod_body_types": {},
    }
    for c in configs:
        for key in ("hulls", "track_entities", "factions", "patched_factions", "content_special_items", "content_wings", "hulls_skipped_no_variant"):
            merged[key] = sorted(set(merged[key]) | set(c.get(key) or []))
        for kind in ("ship", "other"):
            merged["content_variants"][kind] = sorted(set(merged["content_variants"][kind]) | set(c["content_variants"][kind]))
        merged["variants"].update(c.get("variants") or {})
        merged["content_ship_hulls"].update(c.get("content_ship_hulls") or {})
        merged["mod_systems"] = sorted(set(merged["mod_systems"]) | set(c.get("mod_systems") or []))
        merged["mod_body_types"].update(c.get("mod_body_types") or {})
        merged["group_members"][c["target_mod_id"]] = {
            "hulls": sorted(c["hulls"]), "variants": sorted(set(c["content_variants"]["ship"]) | set(c["content_variants"]["other"])),
            "wings": sorted(c["content_wings"]), "items": sorted(c["content_special_items"]), "factions": sorted(set(c["factions"]) | set(c.get("patched_factions") or []))}
    return merged


def _refuse_running_game(rig: Path) -> None:
    """The rig's game holds the probe jar open, so an install fails midway with WinError 32 (2026-09-28). Try to
    move the jar aside and back first; if that fails, say so before anything is copied (ROADMAP P15 31.9)."""
    jar = Path(rig) / "mods" / "bridgeforge-probe" / "jars" / "bridgeforge-probe.jar"
    if not jar.is_file():
        return
    probe = jar.with_name(jar.name + ".lockcheck")
    try:
        jar.replace(probe)
    except OSError as exc:
        raise ProbeGroupError(f"the rig's game appears to be running ({jar.name} is in use: {exc}); close Starsector, then install again.") from exc
    probe.replace(jar)


def install_group(plan: dict, group_number: int, queue: Path, rig: Path, install_probe: bool = True,
                  stage: bool = False) -> dict:
    """Copy/sync members into the rig, write the merged config, set enabled_mods.json. A group whose members
    need providers from the queue installs only with `stage` (`--stage-providers`), which copies and verifies them."""
    rig = Path(rig).expanduser().resolve()
    queue = Path(queue).expanduser().resolve()
    _refuse_non_rig(rig)
    _refuse_running_game(rig)
    group = next((g for g in plan.get("groups", []) if g["group"] == group_number), None)
    if group is None:
        raise ProbeGroupError(f"no group {group_number} in the plan (it has {len(plan.get('groups', []))}).")
    needed = [p for m in group["members"] for p in m.get("stage_providers") or []]
    if needed and not stage:
        names = ", ".join(sorted({f"{p['mod_id']} ({p['workspace']})" for p in needed}))
        raise ProbeGroupError(f"group {group_number} needs providers staged into the rig: {names}. Rerun with --stage-providers.")
    staged = stage_providers(group, queue, rig) if needed else []
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
            "members": [m["workspace"] for m in group["members"]], "copied": copied, "staged_providers": staged, "enabled_mods": enabled,
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
    unattributed, seen_content, filler_sides = [], False, []
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        match = _PROBE_LINE.search(line)
        if not match:
            continue
        if match["check"] == "content-ids" and match["subject"] == "all-content":
            seen_content = True
        if match["check"] == "combat-filler" and match["status"] == "INFO":
            if match["subject"] not in filler_sides:
                filler_sides.append(match["subject"])  # ROADMAP P15 31.13: vanilla ships stood in for a side
        if match["status"] != "FAIL":
            continue
        subject = match["subject"].split(":", 1)[-1].split("/", 1)[0]
        mod_id = owner.get(subject)
        entry = f"{match['check']}|{match['subject']}|{match['detail'].strip()[:200]}"
        (verdicts[mod_id]["failures"] if mod_id else unattributed).append(entry)
    triage = triage_log(log, mods_dir=mods_dir) if mods_dir is not None else triage_log(log)
    for event in triage["fatal"] + triage["mod_errors"]:
        # A JVM crash names the mod owning its nearest Java frame (ROADMAP 36.4); a log exception its suspect.
        suspect = event.get("suspect") or event.get("top_mod")
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
            "members": verdicts, "unattributed": unattributed, "combat_filler_sides": filler_sides,
            "note": "INCOMPLETE means the probe's content-ids check never ran (start a New Game and wait one in-game day)."}


# The owner's standing reason for local-only revivals (owner decision 2026-09-27), used by `record --archive`.
OWNER_STANDING_REASON = "revived for the owner's local archive (live-validated {date}); not published without the author's permission (owner decision 2026-09-27)"


def _workspaces_by_mod_id(queue: Path, mods_dir: Path | None = None) -> dict[str, Path | None]:
    """{mod id: the workspace that was tested}. `install` copies a member to <rig>/mods/<workspace name>, so a rig
    folder with that id and a same-named workspace decides. Otherwise one workspace per id; two or more is None
    (ambiguous). SEEKER-SOLO2-20260928 recorded and archived the old `SEEKER` workspace, not the tested SEEKER-0.6,
    because the first workspace by name won."""
    candidates: dict[str, list[Path]] = {}
    for workspace in sorted(p for p in Path(queue).iterdir() if p.is_dir() and not p.name.startswith("_")):
        mod_id = _mod_info(workspace / "working").get("id")
        if isinstance(mod_id, str) and mod_id:
            candidates.setdefault(mod_id, []).append(workspace)
    in_rig: dict[str, set[str]] = {}
    if mods_dir is not None and Path(mods_dir).is_dir():
        for folder in Path(mods_dir).iterdir():
            mod_id = _mod_info(folder).get("id") if folder.is_dir() else None
            if isinstance(mod_id, str):
                in_rig.setdefault(mod_id, set()).add(folder.name)
    found: dict[str, Path | None] = {}
    for mod_id, workspaces in candidates.items():
        tested = [w for w in workspaces if w.name in in_rig.get(mod_id, set())]
        found[mod_id] = tested[0] if len(tested) == 1 else workspaces[0] if len(workspaces) == 1 else None
    return found


def _newest_save_made_with(rig: Path, reader) -> dict | None:
    saves = sorted((p for p in (rig / "saves").glob("save_*") if p.is_dir()), key=lambda p: p.stat().st_mtime) if (rig / "saves").is_dir() else []
    return reader(saves[-1]) if saves else None


def record_group(log: Path, config: dict, queue: Path, rig: Path, *, test_id: str, archive: bool = False,
                 done_dir: Path | None = None, policy_path: Path | None = None, today: str | None = None) -> dict:
    """After a group run: mark every PASS member LIVE_VALIDATED in its report; with `archive`, record the owner's
    standing local-only licence where none exists, archive it into Done/ and copy its zip to Done/'s top level
    (ROADMAP P15 item 31.1; replaces the session's record_group.py and shell loop)."""
    import re
    import shutil
    from datetime import date

    from .archive import ArchiveError, archive_mod
    from .release import record_policy_decision
    from .substitutes import revival_licence

    today = today or date.today().isoformat()
    report = group_report(log, config, mods_dir=Path(rig) / "mods")
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    version = (re.search(r"BF-PROBE\|(\d+\.\d+\.\d+)\|", text) or [None, "?"])[1]
    workspaces = _workspaces_by_mod_id(queue, Path(rig) / "mods")
    # ROADMAP 36.6: one run record joining inputs and outputs, written before any archive so the gate (36.11)
    # sees this run's shipped hashes.
    from .live_trust import archive_gate, save_made_with, write_run_record
    from .log_triage import triage_log
    from .rig_doctor import DEFAULT_CORE_BASELINE_RELATIVE, _repo_root

    tested = [workspaces[m] for m in sorted(report["members"]) if workspaces.get(m) is not None]
    run_record = write_run_record(queue, test_id, tested, triage=triage_log(log, mods_dir=Path(rig) / "mods"),
                                  verdicts={m: v["verdict"] for m, v in report["members"].items()}, probe_config=config,
                                  core_baseline=_repo_root() / DEFAULT_CORE_BASELINE_RELATIVE, today=today,
                                  save_made_with=_newest_save_made_with(Path(rig), save_made_with))
    recorded, skipped, archived = [], [], []
    for mod_id, verdict in sorted(report["members"].items()):
        workspace = workspaces.get(mod_id)
        if verdict["verdict"] != "PASS" or workspace is None:
            skipped.append({"mod_id": mod_id, "verdict": verdict["verdict"], "workspace": workspace.name if workspace else None})
            continue
        path = workspace / "working" / "reports" / "REVIVAL_REPORT.md"
        body = path.read_text(encoding="utf-8").rstrip() if path.is_file() else f"# Revival report: {workspace.name}"
        if f"## Live probe run {test_id}" not in body:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body + f"\n\n## Live probe run {test_id} (group run, RC8 rig)\n\n`bridgeforge probe-group report`: **PASS** "
                            f"(probe {version}: content-ids ran, no FAIL line for this mod; group triage FATAL={report['fatal']}, "
                            f"MOD-ERROR={report['mod_errors']}). Owner ran New Game, one in-game day and the probe combat mission.\n\nLIVE_VALIDATED\n",
                            encoding="utf-8")
        recorded.append(workspace.name)
        if not archive:
            continue
        if revival_licence(mod_id, _mod_info(workspace / "working").get("name"), policy_path).get("decision") not in ("LOCAL_ONLY", "RELEASABLE"):
            record_policy_decision(mod_id, local_only=True, reason=OWNER_STANDING_REASON.format(date=today), policy_path=policy_path)
        done = Path(done_dir or Path(queue).parent / "Done")
        gate = archive_gate(workspace)
        if not gate["allowed"]:
            skipped.append({"mod_id": mod_id, "verdict": "PASS", "workspace": workspace.name, "archive": "; ".join(gate["problems"])})
            continue
        try:
            result = archive_mod(workspace, done, policy_path=policy_path, today=today)
        except ArchiveError as exc:
            skipped.append({"mod_id": mod_id, "verdict": "PASS", "workspace": workspace.name, "archive": str(exc)})
            continue
        shutil.copy2(result["zip"], done / Path(result["zip"]).name)
        archived.append(workspace.name)
    return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_RECORD", "test_id": test_id, "probe_version": version,
            "recorded": recorded, "archived": archived, "skipped": skipped,
            "run_record": str(Path(queue) / "_live" / f"{test_id}.json"), "known_noise": run_record["known_noise"]}
