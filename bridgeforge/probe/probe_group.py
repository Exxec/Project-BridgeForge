"""`bridgeforge probe-group`: probe several finished mods in one live session (ROADMAP P15 item 24).

The probe (0.2.5) reads one config of lists and maps, and never uses the target mod id for a check, so a
group is probed by merging each member's `build_probe_config` output. 66 mods reached UNATTENDED_DONE on
2026-09-27 and each still needs a probe run; one mod per session is the bottleneck.

- `plan`: workspaces whose revival report ends `READY_FOR_LIVE_TEST`, grouped so no two members share a mod
  id or a content id (hull, variant, wing, special item) and every member's declared dependencies are in the
  rig. Total conversions always go alone. Anything unplaceable is listed with its reason.
- `install_group`: copies or syncs each member into the rig (shipped files only), writes the merged config
  and rig marker, installs the probe, and sets enabled_mods.json (members, their dependencies, the probe, SpeedUp when the rig has it).
After a run, probe_record.py reports one verdict per member (`group_report`), records them (`record_group`) and runs the
startup smoke (`smoke_group`); 96.5 A6.
Refuses to write anywhere but an isolated rig (starsector-core a junction/symlink), like probe-config.
"""
from __future__ import annotations

from bridgeforge.safeio import atomic_write_text, safe_rmtree

import json
import shutil
from pathlib import Path

from bridgeforge.copy_drift import _collect, compare_copies
from bridgeforge.live.live_content_parity import merge_parity
from bridgeforge.probe.probe_config import CONFIG_FILE, RIG_MARKER_FILE, _install_probe_mod, _refuse_non_rig, build_probe_config

SCHEMA_VERSION = 1
PROBE_MOD_ID = "bridgeforge_probe"
# Utility mod for live tests (owner request 2026-10-06): hold caps lock or the middle mouse button to speed the game up.
# Enabled in every rig that has it installed; it changes nothing unless the key is held.
SPEEDUP_MOD_ID = "speedUp"
READY_STATUS = "READY_FOR_LIVE_TEST"


class ProbeGroupError(ValueError):
    """Raised for a missing queue/rig, an unknown group, or an unreadable plan."""


def _report_status(workspace: Path) -> str | None:
    from bridgeforge.report_status import report_status

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
    from bridgeforge.mod_files import read_mod_info

    return read_mod_info(root) or {}


def rig_mod_ids(rig_mods: Path) -> dict[str, str]:
    """{mod id: folder name} for every mod installed in the rig."""
    found = {}
    for child in sorted(p for p in Path(rig_mods).iterdir() if p.is_dir()):
        mod_id = _mod_info(child).get("id")
        if isinstance(mod_id, str) and mod_id:
            found[mod_id] = child.name
    return found


def _version_major(version) -> str:
    if isinstance(version, dict):
        return str(version.get("major", "")).strip()
    return str(version or "").strip().split(".")[0]


def dependency_version_conflicts(rig_mods: Path, enabled: list[str]) -> list[dict]:
    """Enabled mods whose declared dependency version has another major than the installed provider. RC8's
    launcher drops such a mod from enabled_mods.json with no log line (RC8-23; zzz Bingus Sustem wanted IndEvo
    3.0.c and US 0.43 against 4.1.b and 3.0.3, GRP2C-20261005)."""
    folders = rig_mod_ids(rig_mods)
    infos = {mod_id: _mod_info(Path(rig_mods) / folder) for mod_id, folder in folders.items()}
    conflicts = []
    for mod_id in enabled:
        for dep in infos.get(mod_id, {}).get("dependencies") or []:
            if not isinstance(dep, dict) or dep.get("id") not in infos:
                continue
            wanted, installed = dep.get("version"), infos[dep["id"]].get("version")
            if _version_major(wanted) and _version_major(installed) and _version_major(wanted) != _version_major(installed):
                conflicts.append({"mod_id": mod_id, "dependency": dep["id"], "wanted": wanted, "installed": installed})
    return conflicts


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
# Where `probe-group plan` looks for providers the queue lacks (read and copied from, never written): the real
# install's mods/ and the owner's 0.98 modpack (2026-10-04). Only the CLI uses these defaults.
DEFAULT_PROVIDER_SOURCES = (
    Path(r"C:\Program Files (x86)\Fractal Softworks\Starsector\mods"),
    Path.home() / "Downloads" / "Starsector 0.98 Modpack V6.2" / "Starsector 0.98 Modpack V6.2" / "mods",
    # The owner's backlog: mostly 0.95a, so only its 0.98 copies are ever offered (see _providers_for).
    Path.home() / "Downloads" / "Ironclads mega archive",
)


def _source_index(sources: list[Path]) -> list[dict[str, list[Path]]]:
    """Per extra source folder (a mods/ directory), {mod id: [mod folders]}."""
    indexes = []
    for source in sources:
        by_id: dict[str, list[Path]] = {}
        for folder in sorted(p for p in Path(source).iterdir() if p.is_dir()) if Path(source).is_dir() else []:
            mod_id = _mod_info(folder).get("id") if (folder / "mod_info.json").is_file() else None
            if isinstance(mod_id, str) and mod_id:
                by_id.setdefault(mod_id, []).append(folder)
        indexes.append(by_id)
    return indexes


def _providers_for(queue: Path, missing: list[str], extra_sources: list[Path] | tuple = ()) -> tuple[list[dict], list[str]]:
    """Ready workspaces in the queue that provide each missing dependency id (ROADMAP 36.1, 2026-10-04: SCY Nation
    Utility, Yunru's Glinthawk/Old School and MUDA waited on SCY, YunruCore and ORA). A provider must declare the id
    in working/mod_info.json and its latest revive must be UNATTENDED_DONE; none or two is a problem, never a guess.
    With none in the queue, `extra_sources` (mods/ folders, e.g. the real install's or a modpack's; copied from,
    never edited) are tried in order, and the first holding exactly one folder with that id provides it (2026-10-04:
    16 blocked addons were fully provided by installed mods). Dependencies of a provider are looked up the same way."""
    found: list[dict] = []
    problems: list[str] = []
    pending = list(missing)
    seen: set[str] = set()
    by_id: dict[str, list[Path]] = {}
    for workspace in sorted(p for p in Path(queue).iterdir() if p.is_dir() and not p.name.startswith("_")):
        mod_id = _mod_info(workspace / "working").get("id") if (workspace / "working" / "mod_info.json").is_file() else None
        if isinstance(mod_id, str) and mod_id:
            by_id.setdefault(mod_id, []).append(workspace)
    extra = _source_index(list(extra_sources))
    while pending:
        mod_id = pending.pop(0)
        if mod_id in seen:
            continue
        seen.add(mod_id)
        candidates = by_id.get(mod_id, [])
        ready = [w for w in candidates if _latest_revive_status(w) in PROVIDER_READY]
        if not ready and not candidates:
            # Every source holding exactly one copy offers it; the newest version wins (Roider Union: 2.3.1 installed,
            # 2.6 in the archive, and Roider Armatura needs 2.6's items, 2026-10-04).
            from bridgeforge.archive import _version_text
            from bridgeforge.supersession import version_key

            # Only a copy built for 0.98 can run in the RC8 rig (the archive's Roider Union is 1.4.5 for 0.95.1a).
            offers = [(source, folders) for source, index in zip(extra_sources, extra) if len(folders := index.get(mod_id) or []) == 1
                      and str(_mod_info(folders[0]).get("gameVersion") or "").startswith("0.98")]
            duplicated = [(source, folders) for source, index in zip(extra_sources, extra) if len(index.get(mod_id) or []) > 1]
            outside = max(offers, key=lambda o: version_key(_version_text(_mod_info(o[1][0]).get("version"))), default=None) or \
                (duplicated[0] if duplicated else None)
            if outside and len(outside[1]) == 1:
                info = _mod_info(outside[1][0])
                found.append({"mod_id": mod_id, "workspace": outside[1][0].name, "version": str(info.get("version") or ""),
                              "source": str(outside[1][0]), "origin": str(outside[0])})
                for dep in info.get("dependencies") or []:
                    if isinstance(dep, dict) and isinstance(dep.get("id"), str) and dep["id"] not in seen:
                        pending.append(dep["id"])
                continue
            if outside:
                problems.append(f"{mod_id}: two or more copies in {outside[0]}")
                continue
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
        working = Path(provider["source"]) if provider.get("source") else Path(queue) / provider["workspace"] / "working"
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
                exclude: set[str] | None = None, solo: set[str] | None = None, auto_solo: bool = True,
                extra_sources: list[Path] | tuple = ()) -> dict:
    """Greedy grouping: each member joins the first group it shares no mod or content id with. `exclude` leaves
    workspaces out, `solo` gives each its own group, and large campaign mods run solo unless `auto_solo` is off."""
    from bridgeforge.intake import unprocessed_raw_folders

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
            found, problems = _providers_for(queue, missing, extra_sources)
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
        # Mods dropped in the queue unpacked and never taken in (ROADMAP 65): listed so they are not forgotten.
        "raw_folders": unprocessed_raw_folders(queue),
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
        "group_members": {}, "mod_systems": [], "mod_systems_unreached": [], "bounty_checks": {}, "entity_checks": [], "mod_body_types": {},
        # 2026-10-11: class_sweep and mission_fleets were dropped here, so group runs never swept classes or mission fleets.
        "class_sweep": [], "mission_fleets": {"ship": [], "wing": []}, "mod_commodities": [], "expect_supply": [],
        "content_parity": merge_parity(configs),
    }
    if any("campaign_perf_p95_ms" in c for c in configs):
        merged["campaign_perf_p95_ms"] = max(c.get("campaign_perf_p95_ms", 0.0) for c in configs)
    for c in configs:
        for key in ("hulls", "track_entities", "factions", "patched_factions", "content_special_items", "content_wings", "hulls_skipped_no_variant",
                    "class_sweep", "mod_commodities", "expect_supply"):
            merged[key] = sorted(set(merged[key]) | set(c.get(key) or []))
        for kind in ("ship", "wing"):
            merged["mission_fleets"][kind] = sorted(set(merged["mission_fleets"][kind]) | set((c.get("mission_fleets") or {}).get(kind) or []))
        for kind in ("ship", "other"):
            merged["content_variants"][kind] = sorted(set(merged["content_variants"][kind]) | set(c["content_variants"][kind]))
        merged["variants"].update(c.get("variants") or {})
        merged["content_ship_hulls"].update(c.get("content_ship_hulls") or {})
        merged["mod_systems"] = sorted(set(merged["mod_systems"]) | set(c.get("mod_systems") or []))
        merged["mod_systems_unreached"] = sorted(set(merged["mod_systems_unreached"]) | set(c.get("mod_systems_unreached") or []))
        merged["bounty_checks"].update(c.get("bounty_checks") or {})
        merged["entity_checks"] += [check for check in c.get("entity_checks") or [] if check not in merged["entity_checks"]]
        merged["mod_body_types"].update(c.get("mod_body_types") or {})
        merged["group_members"][c["target_mod_id"]] = {
            "hulls": sorted(c["hulls"]), "variants": sorted(set(c["content_variants"]["ship"]) | set(c["content_variants"]["other"])),
            "wings": sorted(c["content_wings"]), "items": sorted(c["content_special_items"]), "factions": sorted(set(c["factions"]) | set(c.get("patched_factions") or [])),
            "commodities": sorted(c.get("mod_commodities") or []),
            # Mission fleet members and jar classes: their FAIL lines name them (mission-variant:<id>, class-sweep|<class>); without
            # these the group report could not attribute them and every member of the group read UNCLEAR (REG-20261012-G1, Aivon-Republic).
            "missions": sorted(set((c.get("mission_fleets") or {}).get("ship") or []) | set((c.get("mission_fleets") or {}).get("wing") or [])),
            "classes": sorted(c.get("class_sweep") or [])}
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


def _rig_folders_by_id(mods_dir: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for child in sorted(q for q in Path(mods_dir).iterdir() if q.is_dir()):
        mod_id = _mod_info(child).get("id")
        if isinstance(mod_id, str) and mod_id:
            found.setdefault(mod_id, []).append(child)
    return found


SAVES_ASIDE_DIR = "_saves-moved"


def move_aside_saves(rig: Path, stamp: str | None = None) -> dict:
    """Move the rig's game saves (`saves/save_*` folders) into `<rig>/_saves-moved/<stamp>/`, never deleting one, so every run
    starts the same way (93.50: SR7-LIVE-0985a-20261117's New Game read a save SR6 had left, then the window vanished).
    `saves/common` (the probe's config and marker) stays. A `saves` folder that is a junction or link is the owner's, not the
    rig's: it is left alone and reported."""
    from datetime import datetime, timezone

    from bridgeforge.boot_test import _is_link

    saves = Path(rig) / "saves"
    if not saves.exists():
        return {"moved": [], "to": None}
    if _is_link(saves):
        return {"moved": [], "to": None, "left": f"{saves} is a junction or link, so its saves are not the rig's; left alone"}
    found = sorted(p for p in saves.iterdir() if p.name.startswith("save_") and p.is_dir() and not _is_link(p))
    if not found:
        return {"moved": [], "to": None}
    base = Path(rig) / SAVES_ASIDE_DIR / (stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    target, n = base, 2
    while target.exists():  # two installs in one second, or a stamp reused: never mix two batches
        target, n = base.with_name(f"{base.name}-{n}"), n + 1
    target.mkdir(parents=True)
    for folder in found:
        shutil.move(str(folder), str(target / folder.name))
    return {"moved": [p.name for p in found], "to": str(target)}


def _move_aside_duplicate_ids(rig: Path, members: dict[str, Path]) -> list[dict]:
    """Move a second rig folder with a member's mod id to <rig>/mods-disabled-providers. SEEKER-0.6 beside SEEKER and
    Legacy-of-Arkgneisis-0.98a beside Arkgneisis (2026-10-05): the game loads one, record_group could not tell which
    was tested."""
    mods_dir = rig / "mods"
    aside = rig / "mods-disabled-providers"
    moved = []
    for mod_id, keep in members.items():
        for folder in _rig_folders_by_id(mods_dir).get(mod_id, []):
            if folder.resolve() != keep.resolve():
                aside.mkdir(exist_ok=True)
                target = aside / folder.name
                if target.exists():
                    safe_rmtree(target, [aside])
                shutil.move(str(folder), str(target))
                moved.append({"mod_id": mod_id, "folder": folder.name, "kept": keep.name})
    return moved


_PROVIDER_COPY_IGNORED = {"src", ".git", ".github", "changelog", "changelog.txt", "license.txt", "desktop.ini"}


def incomplete_provider_copies(rig: Path, enabled: list[str]) -> list[dict]:
    """Enabled mods whose rig folder lacks a top-level entry the real install's copy of the same folder has (read
    only). Industrial Evolution in the rig had no IndEvo/ folder, so the first Group 2 launch ended on a missing
    sound (2026-10-05). The real mods folder is the one beside the rig's starsector-core junction target."""
    core = Path(rig) / "starsector-core"
    try:
        real_mods = core.resolve().parent / "mods"
    except OSError:
        return []
    if not real_mods.is_dir() or real_mods.resolve() == (Path(rig) / "mods").resolve():
        return []
    problems = []
    for mod_id in enabled:
        for folder in _rig_folders_by_id(Path(rig) / "mods").get(mod_id, []):
            real = real_mods / folder.name
            if not real.is_dir():
                continue
            have = {c.name.lower() for c in folder.iterdir()}
            missing = sorted(c.name for c in real.iterdir() if c.name.lower() not in have and c.name.lower() not in _PROVIDER_COPY_IGNORED)
            if missing:
                problems.append({"mod_id": mod_id, "folder": folder.name, "missing": missing})
    return problems


def _reset_combat_round(common: Path) -> None:
    for stale in Path(common).glob("bf_probe_combat_round*"):
        stale.unlink()


def _add_probe_mission_to_replacing_members(rig: Path, members: dict[str, Path]) -> list[str]:
    """A total conversion that lists data/missions/mission_list.csv in mod_info `replace` wipes every earlier mod's missions,
    and the probe loads before it (Ironclads GRP10N-20261005: the owner could not reach the probe mission). Append the probe's row
    to that member's rig copy, which `install` rewrites on every sync. Returns the folders changed."""
    from bridgeforge.conversion_checks import replace_list

    probe_list = Path(rig) / "mods" / "bridgeforge-probe" / "data" / "missions" / "mission_list.csv"
    if not probe_list.is_file():
        return []
    rows = [line.strip() for line in probe_list.read_text(encoding="utf-8-sig").splitlines()[1:] if line.strip().strip(",")]
    changed = []
    for folder in members.values():
        if "data/missions/mission_list.csv" not in replace_list(folder):
            continue
        target = folder / "data" / "missions" / "mission_list.csv"
        if not target.is_file():
            continue
        raw = target.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        have = {line.split(",")[0].strip() for line in text.splitlines()}
        missing = [row for row in rows if row.split(",")[0].strip() not in have]
        if not missing:
            continue
        newline = "\r\n" if "\r\n" in text else "\n"
        target.write_bytes((raw if raw.endswith((b"\n", b"\r")) else raw + newline.encode("utf-8"))
                           + (newline.join(missing) + newline).encode("utf-8"))
        changed.append(folder.name)
    return changed


def lunalib_advice(enabled: list[str], installed: dict[str, str]) -> str | None:
    """GraphicsLib 1.12.1 enabled without LunaLib while the rig has LunaLib: RC8-25 says a mod that calls ShaderLib.init then
    dies with NoClassDefFoundError lunalib/... under Fast Rendering. Advice only: adding an undeclared library to a group would
    hide a real dependency gap, so the owner decides (`--with-lunalib`)."""
    if "shaderLib" in enabled and "lunalib" not in enabled and "lunalib" in installed:
        return ("GraphicsLib is enabled without LunaLib. Under Fast Rendering a member that calls ShaderLib.init fails with "
                "NoClassDefFoundError lunalib/... (RC8-25). Re-run install with --with-lunalib to enable it for this run.")
    return None


LUNALIB_ID = "lunalib"
GRAPHICSLIB_ID = "shaderLib"
LUNALIB_RULE_VERSION = "1.12.1"


def lunalib_rule(enabled: list[str], installed: dict[str, str], mods_dir: Path, *, with_lunalib: bool = False,
                 no_lunalib: bool = False) -> tuple[bool, str | None, str | None]:
    """(enable LunaLib?, why, advice). Install rule RC8-25 (ROADMAP 60f): GraphicsLib 1.12.1's ShaderLib.init references LunaLib
    classes and the unattended runs use Fast Rendering, so when GraphicsLib 1.12.1 is enabled and the rig has LunaLib, LunaLib is
    enabled automatically ("auto"). `--with-lunalib` keeps its meaning (enable it whenever GraphicsLib is on without it, any
    version: "forced"); `--no-lunalib` opts out, for a run meant to show the dependency gap. Otherwise only the advice remains."""
    if with_lunalib and no_lunalib:
        raise ProbeGroupError("--with-lunalib and --no-lunalib contradict each other.")
    advice = lunalib_advice(enabled, installed)
    if advice is None:
        return False, None, None
    if no_lunalib:
        return False, "skipped (--no-lunalib)", advice
    if with_lunalib:
        return True, "forced (--with-lunalib)", None
    from bridgeforge.archive import _version_text

    version = _version_text(_mod_info(Path(mods_dir) / installed[GRAPHICSLIB_ID]).get("version"))
    if version.startswith(LUNALIB_RULE_VERSION):
        return True, f"auto: GraphicsLib {version} needs LunaLib under Fast Rendering (RC8-25)", None
    return False, None, advice


ENABLE_SETS = {
    # Named sets for `install --also-enable`, replacing hand edits of enabled_mods.json before AoTD runs (ROADMAP 70 H1.7). The Toolbox
    # fork needs the Prepatcher javaagent: run those groups with a `-prep` launcher (java-matrix setup --prepatcher).
    "aotd": ["aotd_vok", "aotd_theory_of_toolbox", "starsector_prepatcher", "bmo", "ashlib"],
}


def expand_also_enable(requested: list[str], installed: dict[str, str]) -> list[str]:
    """Mod ids for `--also-enable` values: a named set (`aotd`) expands to its ids, anything else is a mod id. Every id must be installed
    in the rig; the ones that are not are named together, never skipped silently."""
    ids: list[str] = []
    for item in requested:
        for mod_id in ENABLE_SETS.get(item.lower(), [item]):
            if mod_id not in ids:
                ids.append(mod_id)
    missing = [i for i in ids if i not in installed]
    if missing:
        raise ProbeGroupError(f"--also-enable names mods that are not in the rig: {', '.join(missing)} (sets: {', '.join(sorted(ENABLE_SETS))}).")
    return ids


STALE_STAGED_DIR = "_stale-staged"


def _stale_holding(target: Path) -> Path:
    """`<rig>/_stale-staged/<UTC time>/<target folder>` for a rig mod folder `<rig>/mods/<name>`; a new folder per sync."""
    from datetime import datetime, timezone

    base = target.parent.parent / STALE_STAGED_DIR / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    holding, n = base, 2
    while (holding / target.name).exists():  # two syncs in one second: never mix them
        holding, n = base.with_name(f"{base.name}-{n}"), n + 1
    return holding / target.name


def sync_working_copy(working: Path, target: Path) -> str | None:
    """Copy a working copy's shipped files into the rig folder `target` (a new folder: all of them; an existing one: the missing and
    different ones). A rig file the working copy no longer ships is moved into `<rig>/_stale-staged/<UTC time>/<name>/`, never
    deleted (96.12: Broken Star's bf.4 moved two .wpn files, the rig kept the old ones, and record refused a passing run as
    "staged files differ from the candidate working copy"). "copied", "synced N file(s)" (and what was moved aside), or None
    when the rig copy already matches."""
    if not target.exists():
        for relative, source in _collect(working).items():
            (target / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target / relative)
        return "copied"
    drift = compare_copies(working, target)
    if not drift["drift_count"]:
        return None
    for relative in [*drift["missing_in_deployed"], *(d["path"] for d in drift["different"])]:
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(working / relative, target / relative)
    # A path that differs from a shipped one only in case is that same file on Windows (`Data/x.csv` against `data/x.csv`):
    # moving it would take away the file just copied, and the rig would lose and regain it on alternate syncs (review of #214).
    shipped = {name.lower() for name in _collect(working)}
    stale = [relative for relative in drift["extra_in_deployed"] if relative.lower() not in shipped]
    if not stale:
        return f"synced {drift['drift_count']} file(s)"
    deployed_root, holding = Path(drift["deployed_root"]), _stale_holding(target)
    for relative in stale:
        (holding / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(deployed_root / relative), str(holding / relative))
    return f"synced {drift['drift_count']} file(s); moved {len(stale)} the working copy no longer has to {holding}"


def _stage_member_scenario(working: Path, rig_copy: Path, workspace: str) -> dict | None:
    """A member's PROBE_SCENARIO.json: validate it and apply its `settings` to the rig copy only (never to `working`)."""
    from bridgeforge.probe.probe_scenario import ScenarioError, load_for_working, stage_settings

    try:
        scenario = load_for_working(working)
        if scenario is None:
            return None
        staged = stage_settings(scenario, rig_copy, working) if scenario["settings"] else []
    except ScenarioError as exc:
        raise ProbeGroupError(f"{workspace}: {exc}") from exc
    return {"workspace": workspace, "settings_staged": staged, "steps": len(scenario["steps"]),
            "expectations": len(scenario["expect"]), "scenario": scenario}


def install_group(plan: dict, group_number: int, queue: Path, rig: Path, install_probe: bool = True,
                  stage: bool = False, with_lunalib: bool = False, setups: list[str] | None = None,
                  expect_supply: list[str] | None = None, save_after_checks: bool = False, no_lunalib: bool = False,
                  also_enable: list[str] | None = None, save_reload_after_days: int = 0, save_reload_note: str = "",
                  keep_saves: bool = False) -> dict:
    """Copy/sync members into the rig, write the merged config, set enabled_mods.json. A group whose members
    need providers from the queue installs only with `stage` (`--stage-providers`), which copies and verifies them.
    `setups` (probe setup specs) and `expect_supply` ("commodity@industry") go into the merged config (probe 0.2.25).
    The rig's earlier game saves are moved aside first (`move_aside_saves`, 93.50) unless `keep_saves`."""
    from bridgeforge.probe.probe_config import parse_expect_supply, parse_setups

    setups = parse_setups(setups)
    expect_supply = parse_expect_supply(expect_supply)
    rig = Path(rig).expanduser().resolve()
    queue = Path(queue).expanduser().resolve()
    _refuse_non_rig(rig)
    _refuse_running_game(rig)
    from bridgeforge.run_manifest import ManifestError, refuse_if_owned

    try:
        refuse_if_owned(rig, "install")  # R1: a prepared run owns the staged files until it is released
    except ManifestError as exc:
        raise ProbeGroupError(str(exc)) from exc
    group = next((g for g in plan.get("groups", []) if g["group"] == group_number), None)
    if group is None:
        raise ProbeGroupError(f"no group {group_number} in the plan (it has {len(plan.get('groups', []))}).")
    needed = [p for m in group["members"] for p in m.get("stage_providers") or []]
    if needed and not stage:
        names = ", ".join(sorted({f"{p['mod_id']} ({p['workspace']})" for p in needed}))
        raise ProbeGroupError(f"group {group_number} needs providers staged into the rig: {names}. Rerun with --stage-providers.")
    saves_aside = {"moved": [], "to": None, "kept": True} if keep_saves else move_aside_saves(rig)
    staged = stage_providers(group, queue, rig) if needed else []
    mods_dir = rig / "mods"
    installed = rig_mod_ids(mods_dir)
    configs, copied, scenarios = [], [], []
    for member in group["members"]:
        working = queue / member["workspace"] / "working"
        action = sync_working_copy(working, mods_dir / member["workspace"])
        if action:
            copied.append({"workspace": member["workspace"], "action": action})
        configs.append(build_probe_config(working))
        installed[member["mod_id"]] = member["workspace"]
        scenario = _stage_member_scenario(working, mods_dir / member["workspace"], member["workspace"])
        if scenario:
            scenarios.append(scenario)
    from bridgeforge.run_manifest import record_candidates

    record_candidates(rig, {m["mod_id"]: queue / m["workspace"] / "working" for m in group["members"]})  # R1: what the next manifest binds
    moved_aside = _move_aside_duplicate_ids(rig, {m["mod_id"]: mods_dir / m["workspace"] for m in group["members"]})
    config = merge_configs(configs)
    config["setups"] = [*config["setups"], *setups]
    config["expect_supply"] = sorted(set(config["expect_supply"]) | set(expect_supply))
    config["save_after_checks"] = bool(save_after_checks)  # probe 0.2.26: save once after the day-1 checks
    if save_reload_after_days > 0:  # next probe version: fingerprint, save and reload stage (save_reload_run)
        config["save_reload"] = {"after_days": int(save_reload_after_days), "slot_note": save_reload_note}
    if scenarios:  # PROBE_SCENARIO.json steps for the probe's ScenarioRunner (docs/PROBE_SCENARIOS.md)
        from bridgeforge.probe.probe_scenario import probe_config_keys

        config.update(probe_config_keys([s["scenario"] for s in scenarios]))
    common = rig / "saves" / "common"
    common.mkdir(parents=True, exist_ok=True)
    _reset_combat_round(common)
    atomic_write_text(common / CONFIG_FILE, json.dumps(config, indent=2, sort_keys=True))
    if not (common / RIG_MARKER_FILE).is_file():
        (common / RIG_MARKER_FILE).write_text("rig\n", encoding="utf-8")
    if install_probe:
        _install_probe_mod(rig)
    probe_mission_added = _add_probe_mission_to_replacing_members(rig, {m["mod_id"]: mods_dir / m["workspace"] for m in group["members"]})
    enabled = []
    for member in group["members"]:
        current = [d.get("id") for d in _mod_info(queue / member["workspace"] / "working").get("dependencies") or []
                   if isinstance(d, dict) and isinstance(d.get("id"), str)]
        wanted = [dep for dep in dict.fromkeys([*member["dependencies"], *current]) if dep != member["mod_id"]]
        needed, _ = dependency_closure(mods_dir, wanted)
        for mod_id in [*needed, member["mod_id"]]:
            if mod_id not in enabled:
                enabled.append(mod_id)
    extras = expand_also_enable(also_enable or [], rig_mod_ids(mods_dir))
    if extras:
        needed_extra, _ = dependency_closure(mods_dir, extras)
        for mod_id in [*needed_extra, *extras]:
            if mod_id not in enabled:
                enabled.append(mod_id)
    add_lunalib, lunalib_why, advice = lunalib_rule(enabled, rig_mod_ids(mods_dir), mods_dir, with_lunalib=with_lunalib, no_lunalib=no_lunalib)
    if add_lunalib:
        enabled.append(LUNALIB_ID)
    enabled.append(PROBE_MOD_ID)
    if SPEEDUP_MOD_ID in rig_mod_ids(mods_dir) and SPEEDUP_MOD_ID not in enabled:
        enabled.append(SPEEDUP_MOD_ID)
    enabled_path = mods_dir / "enabled_mods.json"
    backup = enabled_path.with_name("enabled_mods.json.pre-bftest.bak")
    if enabled_path.is_file() and not backup.exists():
        shutil.copy2(enabled_path, backup)
    atomic_write_text(enabled_path, json.dumps({"enabledMods": enabled}))
    return {"schema_version": SCHEMA_VERSION, "mode": "PROBE_GROUP_INSTALL", "group": group_number,
            "members": [m["workspace"] for m in group["members"]], "copied": copied, "staged_providers": staged, "enabled_mods": enabled,
            "dependency_version_conflicts": dependency_version_conflicts(mods_dir, enabled),
            "moved_aside": moved_aside, "saves_aside": saves_aside, "incomplete_providers": incomplete_provider_copies(rig, enabled),
            "scenarios": [{k: v for k, v in s.items() if k != "scenario"} for s in scenarios],
            "probe_mission_added": probe_mission_added, "lunalib_advice": advice, "lunalib": lunalib_why,
            "config_path": str(common / CONFIG_FILE), "checked_ids": len(config["content_variants"]["ship"]) + len(config["content_variants"]["other"])
            + len(config["content_wings"]) + len(config["content_special_items"])}


