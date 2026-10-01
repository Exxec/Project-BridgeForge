"""Batch jar work that the 2026-09-30 session did with scratch scripts (ROADMAP P15 item 33).

- `relink_workspace` / `relink_queue` (`bridgeforge relink`): recompile each class `jar-linkage-unresolved` names from
  its shipped or decompiled source, unedited, and patch it in only when every changed call is a return-type relink
  and no member changes. 19 queued mods and four archived ones were relinked this way by hand.
- `patch_jar_sources` (`bridgeforge patch-jar-sources`): edits made in a jar's source tree (a fixer or agent, with a
  `*.pre-bf-*` backup beside each file) change nothing until the jar is rebuilt. Prove the pre-edit source rebuilds
  the shipped class, then patch the edited class in, reporting what changed. Five jars were patched this way.
- `repair_decompile`: Vineflower re-declares a variable across one switch scope ("variable disc is already defined",
  RogueSynth); a later bare `Type name;` declaration of the same variable is commented out and the compile retried.
"""
from __future__ import annotations

import re
import shutil
import time
import zipfile
from pathlib import Path

from .jar_patch import _decompiled_tree, _only_return_type_relinks, find_decompiler, patch_jar_classes
from .java_toolchain import find_jdk
from .linkage import unresolved_references
from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1
JAR_SOURCE_ROOTS = ("src", "jars/src", "jar/src")


def _info(working: Path) -> dict:
    if not (working / "mod_info.json").is_file():
        return {}
    info = _load_lenient_json_file(working / "mod_info.json")
    return info if isinstance(info, dict) else {}


def rig_providers(rig_mods: Path, exclude_id: str | None) -> list[Path]:
    """Jars the rig's other mods declare (not every jar in their folders: FlowerGod's build/cp held a game jar)."""
    found = []
    for info_path in sorted(Path(rig_mods).glob("*/mod_info.json")) if Path(rig_mods).is_dir() else []:
        info = _load_lenient_json_file(info_path) or {}
        if isinstance(info, dict) and info.get("id") != exclude_id:
            found += [info_path.parent / j for j in info.get("jars") or [] if isinstance(j, str) and (info_path.parent / j).is_file()]
    return found


def _drop_overloads(calls: dict[str, int], overloads: set[str]) -> dict[str, int]:
    """Remove calls to an allowed `owner.name` whose descriptors changed but whose count balances (same call sites)."""
    rest = dict(calls)
    for site in overloads:
        hits = {c: d for c, d in rest.items() if c.split(":", 1)[0] == site}
        if len(hits) >= 2 and sum(hits.values()) == 0:
            for c in hits:
                del rest[c]
    return rest


# RC8 renames with the same descriptor, verified against the RC8 jar before use (2026-10-01).
RENAMED_METHODS = {
    # Kadur Remnant missions; RC8 keeps (FactionAPI, FullName.Gender) -> String and prefers an unused portrait.
    "com/fs/starfarer/api/impl/campaign/events/OfficerManagerEvent.pickPortrait": "pickPortraitPreferNonDuplicate",
}


def _benign(check: dict, overloads: set[str] | None = None) -> bool:
    def ok(calls: dict[str, int]) -> bool:
        calls = _drop_overloads(calls, overloads or set())
        return not calls or bool(_only_return_type_relinks(calls))
    return check["status"] == "PASS" and all(
        not c.get("members") and (not c.get("calls_changed") or ok(c["calls_changed"]))
        for c in check["classes"] if not c.get("new"))


def repair_decompile(source: Path, errors: list[dict]) -> bool:
    """Comment out later bare re-declarations javac reports as already defined. True if anything changed."""
    names = {m.group(1) for e in errors if e.get("file") and Path(e["file"]).name == source.name
             for m in [re.search(r"variable (\w+) is already defined", e.get("message", ""))] if m}
    if not names:
        return False
    lines = source.read_text(encoding="utf-8").split("\n")
    changed = False
    for name in names:
        seen = False
        for i, line in enumerate(lines):
            if re.fullmatch(rf"\s*[\w.<>\[\]]+\s+{re.escape(name)};\s*", line):
                if seen:
                    lines[i] = re.sub(r"\S.*", f"// BridgeForge: decompiler re-declared {name} in a shared scope", line)
                    changed = True
                seen = True
    if changed:
        source.write_text("\n".join(lines), encoding="utf-8")
    return changed


def _source_for(ws: Path, working: Path, jar_rel: str, outer: str, java: Path | None) -> tuple[Path | None, bool]:
    source = next((p for p in working.rglob(Path(outer).name + ".java") if p.as_posix().endswith(outer + ".java")), None)
    if source is not None:
        return source, False
    decompiler = find_decompiler(ws)
    tree = _decompiled_tree(ws, jar_rel, java, decompiler) if decompiler and java else None
    if tree is not None and (tree / (outer + ".java")).is_file():
        return tree / (outer + ".java"), True
    return None, False


def relink_workspace(workspace: Path, vanilla_core: Path, *, apply: bool = False, stamp: str = "relink") -> dict:
    ws = Path(workspace).expanduser().resolve()
    working = ws / "working"
    info = _info(working)
    jars = [working / j for j in info.get("jars") or [] if isinstance(j, str) and (working / j).is_file()]
    providers = rig_providers(Path(vanilla_core).resolve().parent / "mods", info.get("id"))
    problems = unresolved_references(jars, vanilla_core, providers)
    result = {"workspace": ws.name, "jars": [], "missing_source": [], "state": "CLEAN" if not problems else None}
    if not problems:
        return result
    hard = [p for v in problems.values() for p in v if not p.get("return_type_only")]
    # An RC8 overload of the same name may still take the old arguments (Void-Tec: addCustom(CustomPanelAPI, float)
    # became addCustom(UIComponentAPI, float), and CustomPanelAPI is a UIComponentAPI): the unedited source then
    # recompiles onto it. Tried only when every such reference has a same-name RC8 candidate; checked after compiling.
    from .linkage import core_index
    core = core_index(str(Path(vanilla_core).resolve()))
    renames = {}
    for p in hard:
        new_name = RENAMED_METHODS.get(f"{p['owner']}.{p['name']}")
        if new_name and (new_name, p["descriptor"]) in (core.get(p["owner"]).methods if core.get(p["owner"]) else set()):
            renames[f"{p['owner']}.{p['name']}"] = new_name
    hard = [p for p in hard if f"{p['owner']}.{p['name']}" not in renames]
    result["renamed"] = sorted(f"{k} -> {v}" for k, v in renames.items())
    overload = all(p["kind"] == "method" and p.get("candidates") for p in hard)
    if hard and not overload:
        result["state"] = "NEEDS_PORT"
        result["port"] = sorted({f"{p['owner']}.{p['name']}" for p in hard})[:12]
        return result
    result["overload_relink"] = sorted({f"{p['owner']}.{p['name']}{p['descriptor']}" for p in hard}) if hard else []
    jdk = find_jdk(None)
    java = jdk.javac.with_name("java.exe" if jdk.javac.suffix else "java") if jdk else None
    by_jar: dict[str, list[tuple[Path, bool]]] = {}
    for entry in problems:
        jar_name, _, member = entry.partition("!")
        jar_rel = next(j for j in jars if j.name == jar_name).relative_to(working).as_posix()
        outer = member.removesuffix(".class").split("$", 1)[0]
        target = ws / "scratch" / stamp / (outer + ".java")
        decompiled = False
        if not target.exists():
            source, decompiled = _source_for(ws, working, jar_rel, outer, java)
            if source is None:
                result["missing_source"].append(outer)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            text = target.read_text(encoding="utf-8", errors="replace")
            for old_ref, new_name in renames.items():
                owner, name = old_ref.rsplit(".", 1)
                text = re.sub(rf"\b({re.escape(owner.rsplit('/', 1)[-1])}\s*\.\s*){re.escape(name)}(\s*\()",
                              lambda m, new_name=new_name: m.group(1) + new_name + m.group(2), text)
            target.write_text(text, encoding="utf-8")
        by_jar.setdefault(jar_rel, []).append((target, decompiled))
    for jar_rel, pairs in by_jar.items():
        sources = sorted({s for s, _ in pairs})
        check = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core)
        if not check["compile"]["success"] and not all(d for _, d in pairs) and java is not None and find_decompiler(ws):
            # The shipped source does not build (Bounties Expanded's needs Lombok): try the jar's own classes, decompiled.
            tree = _decompiled_tree(ws, jar_rel, java, find_decompiler(ws))
            swapped = []
            for target, decompiled in pairs:
                package = re.search(r"^\s*package\s+([\w.]+)\s*;", target.read_text(encoding="utf-8", errors="replace"), re.M)
                candidate = tree / ((package.group(1).replace(".", "/") + "/") if package else "") / target.name if tree else None
                if not decompiled and candidate is not None and candidate.is_file():
                    shutil.copy2(candidate, target)
                    decompiled = True
                swapped.append((target, decompiled))
            pairs = swapped
            check = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core)
        for _ in range(3):  # decompile repairs, then recompile
            if check["compile"]["success"] or not any(repair_decompile(s, check["compile"]["errors"]) for s, d in pairs if d):
                break
            check = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core)
        row = {"jar": jar_rel, "classes": len(sources), "decompiled": any(d for _, d in pairs)}
        overloads = {o.split("(", 1)[0] for o in result.get("overload_relink") or []}
        renamed_calls = {f"{k}": f"{k.rsplit('.', 1)[0]}.{v}" for k, v in renames.items()}
        for c in check["classes"]:  # a renamed call: old name -n, new name +n at the same sites
            calls = c.get("calls_changed") or {}
            for old_site, new_site in renamed_calls.items():
                olds = {k: v for k, v in calls.items() if k.split(":", 1)[0] == old_site}
                news = {k: v for k, v in calls.items() if k.split(":", 1)[0] == new_site}
                if olds and news and sum(olds.values()) == -sum(news.values()):
                    for k in [*olds, *news]:
                        calls.pop(k)
        if not _benign(check, overloads):
            row["state"] = "NOT_PATCHED"
            row["why"] = check["compile"]["errors"][:2] or [
                {c["class"]: {"members": c.get("members"), "calls": list((c.get("calls_changed") or {}))[:3]}}
                for c in check["classes"] if c.get("members") or c.get("calls_changed")][:2]
        elif apply:
            done = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core, install=True)
            left = unresolved_references([working / jar_rel], vanilla_core, providers)
            row.update({"state": "RELINKED" if not left else "PARTIAL", "backup": done.get("backup_jar"),
                        "relinks": sorted({r for c in check["classes"] for r in _only_return_type_relinks(c.get("calls_changed") or {})
                                           if c.get("calls_changed")})})
        else:
            row["state"] = "WOULD_RELINK"
        result["jars"].append(row)
    states = {r["state"] for r in result["jars"]}
    result["state"] = ("RELINKED" if states <= {"RELINKED"} and not result["missing_source"] else
                       "WOULD_RELINK" if states <= {"WOULD_RELINK"} and not result["missing_source"] else "PARTIAL")
    return result


def relink_queue(queue: Path, vanilla_core: Path, *, apply: bool = False, quiet: bool = False, restart: bool = False) -> dict:
    from .progress import Checkpoint, report

    queue = Path(queue).expanduser().resolve()
    workspaces = [p for p in sorted(queue.iterdir()) if p.is_dir() and not p.name.startswith("_") and (p / "working" / "mod_info.json").is_file()
                  and _info(p / "working").get("jars")]
    checkpoint_path = queue / "RELINK.partial.jsonl"
    if restart:
        checkpoint_path.unlink(missing_ok=True)
    rows = []
    with Checkpoint(checkpoint_path, {"mode": "RELINK", "apply": apply, "queue": str(queue)}) as checkpoint:
        for number, ws in enumerate(workspaces, 1):
            started = time.perf_counter()
            cached = checkpoint.get(ws.name)
            row = cached if cached is not None else relink_workspace(ws, vanilla_core, apply=apply)
            if cached is None:
                checkpoint.add(ws.name, row)
            rows.append(row)
            if not quiet:
                report(number, len(workspaces), ws.name, row["state"], None if cached is not None else time.perf_counter() - started)
        checkpoint.finish()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1
    return {"schema_version": SCHEMA_VERSION, "mode": "RELINK_QUEUE", "apply": apply, "counts": counts,
            "workspaces": [r for r in rows if r["state"] != "CLEAN"]}


# RC8 interface contract changes with a mechanical source port (2026-10-01; Wotani, Polaris Prime, UNGP).
# key: the missing "owner.name(desc)" as missing_interface_methods reports it.
_ONHIT = "com/fs/starfarer/api/combat/OnHitEffectPlugin.onHit(Lcom/fs/starfarer/api/combat/DamagingProjectileAPI;Lcom/fs/starfarer/api/combat/CombatEntityAPI;Lorg/lwjgl/util/vector/Vector2f;ZLcom/fs/starfarer/api/combat/listeners/ApplyDamageResultAPI;Lcom/fs/starfarer/api/combat/CombatEngineAPI;)V"
_DIALOG = "com/fs/starfarer/api/campaign/CustomDialogDelegate.createCustomDialog(Lcom/fs/starfarer/api/ui/CustomPanelAPI;Lcom/fs/starfarer/api/campaign/CustomDialogDelegate$CustomDialogCallback;)V"
_BUTTON = "com/fs/starfarer/api/campaign/CustomUIPanelPlugin.buttonPressed(Ljava/lang/Object;)V"


def _port_onhit(text: str) -> str | None:
    # The 5-argument onHit gains ApplyDamageResultAPI before CombatEngineAPI; the body is unchanged.
    pattern = re.compile(r"(public\s+void\s+onHit\s*\([^)]*?\bboolean\s+\w+\s*,\s*)((?:final\s+)?(?:[\w.]+\.)?CombatEngineAPI\s+\w+\s*\))")
    if len(pattern.findall(text)) != 1:
        return None
    return pattern.sub(r"\1com.fs.starfarer.api.combat.listeners.ApplyDamageResultAPI damageResult, \2", text)


def _port_dialog(text: str) -> str | None:
    # createCustomDialog(CustomPanelAPI) gains RC8's callback parameter; the body is unchanged.
    pattern = re.compile(r"(public\s+void\s+createCustomDialog\s*\(\s*(?:final\s+)?(?:[\w.]+\.)?CustomPanelAPI\s+\w+)\s*\)")
    if not pattern.search(text):
        return None
    return pattern.sub(r"\1, com.fs.starfarer.api.campaign.CustomDialogDelegate.CustomDialogCallback callback)", text)


def _port_button(text: str, simple_name: str) -> str | None:
    # A top-level CustomUIPanelPlugin gains RC8's buttonPressed, empty as in BaseCustomUIPanelPlugin.
    if re.search(r"\bvoid\s+buttonPressed\s*\(", text):
        return None
    head = re.search(rf"\bclass\s+{re.escape(simple_name)}\b[^{{]*\{{", text)
    end = text.rstrip().rfind("}")
    if not head or end < head.end():
        return None
    method = ("\n    // BridgeForge: RC8 added this to CustomUIPanelPlugin; empty, as BaseCustomUIPanelPlugin's.\n"
              "    public void buttonPressed(Object buttonId) {\n    }\n")
    return text[:end] + method + text[end:]


# A class that implements one of these interfaces directly, extending nothing, gets RC8's added methods from vanilla's
# own base class (checked 2026-10-01: each is concrete and implements every method of its interface); the mod's own
# methods still override. HullModEffect alone: 24 classes in four mods (getSModDescriptionParam and eight more).
BASE_CLASSES = {
    "com/fs/starfarer/api/combat/HullModEffect": "com.fs.starfarer.api.combat.BaseHullMod",
    "com/fs/starfarer/api/campaign/CustomProductionPickerDelegate": "com.fs.starfarer.api.campaign.BaseCustomProductionPickerDelegateImpl",
    "com/fs/starfarer/api/campaign/CampaignEntityPickerListener": "com.fs.starfarer.api.campaign.BaseCampaignEntityPickerListener",
    "com/fs/starfarer/api/campaign/CustomUIPanelPlugin": "com.fs.starfarer.api.campaign.BaseCustomUIPanelPlugin",
    "com/fs/starfarer/api/campaign/CustomDialogDelegate": "com.fs.starfarer.api.campaign.BaseCustomDialogDelegate",
}


def _port_base(text: str, simple_name: str, owners: set[str]) -> str | None:
    if len(owners) != 1 or next(iter(owners)) not in BASE_CLASSES:
        return None
    head = re.search(rf"(\bclass\s+{re.escape(simple_name)}\b)(\s*(?:<[^>]*>)?)(\s+implements\b)", text)
    if not head or re.search(rf"\bclass\s+{re.escape(simple_name)}\b[^{{]*\bextends\b", text):
        return None
    base = BASE_CLASSES[next(iter(owners))]
    return text[:head.end(2)] + f" extends {base}" + text[head.end(2):]


def port_interfaces(workspace: Path, vanilla_core: Path, *, apply: bool = False) -> dict:
    """Port jar classes `jar-interface-method-missing` names when every missing method has a known mechanical port:
    edit the shipped or decompiled source, compile, and patch only if each class changes by exactly those
    signatures (plus return-type relinks). Anything else is left with the reason."""
    from .linkage import missing_interface_methods

    ws = Path(workspace).expanduser().resolve()
    working = ws / "working"
    info = _info(working)
    jars = [working / j for j in info.get("jars") or [] if isinstance(j, str) and (working / j).is_file()]
    providers = rig_providers(Path(vanilla_core).resolve().parent / "mods", info.get("id"))
    missing = missing_interface_methods(jars, vanilla_core, providers)
    jdk = find_jdk(None)
    java = jdk.javac.with_name("java.exe" if jdk.javac.suffix else "java") if jdk else None
    result = {"workspace": ws.name, "classes": len(missing), "jars": [], "unported": []}
    by_jar: dict[str, list[Path]] = {}
    for entry, methods in sorted(missing.items()):
        jar_name, _, member = entry.partition("!")
        jar_rel = next(j for j in jars if j.name == jar_name).relative_to(working).as_posix()
        class_path = member.removesuffix(".class")
        owners = {m.split(".", 1)[0] for m in methods}
        via_base = not set(methods) <= {_ONHIT, _DIALOG, _BUTTON} and len(owners) == 1 and next(iter(owners)) in BASE_CLASSES
        if "$" in class_path or not (set(methods) <= {_ONHIT, _DIALOG, _BUTTON} or via_base):
            result["unported"].append({"class": class_path, "missing": methods,
                                       "why": "inner or anonymous class" if "$" in class_path else "no known mechanical port"})
            continue
        target = ws / "scratch" / "port-interfaces" / (class_path + ".java")
        # Always from a fresh copy: a dry run's edited copy would no longer match the port's pattern.
        source, _ = _source_for(ws, working, jar_rel, class_path, java)
        if source is None:
            result["unported"].append({"class": class_path, "missing": methods, "why": "no source"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        text = target.read_text(encoding="utf-8")
        if via_base:
            text = _port_base(text, Path(class_path).name, owners)
        for method in [] if via_base else methods:
            text = (_port_onhit(text) if method == _ONHIT else _port_dialog(text) if method == _DIALOG else
                    _port_button(text, Path(class_path).name)) if text is not None else None
        if text is None:
            result["unported"].append({"class": class_path, "missing": methods, "why": "the source did not match the port's pattern"})
            continue
        target.write_text(text, encoding="utf-8")
        by_jar.setdefault(jar_rel, []).append(target)
    allowed = {"onHit", "createCustomDialog", "buttonPressed"}
    base_inits = {b.replace(".", "/") + '."<init>":()V' for b in BASE_CLASSES.values()}

    def calls_ok(calls: dict[str, int]) -> bool:
        # The base-class port swaps the constructor's super call (Object.<init> -> BaseHullMod.<init>); nothing else.
        rest = dict(calls)
        swapped = [c for c in rest if c in base_inits]
        if swapped and rest.get('java/lang/Object."<init>":()V', 0) == -sum(rest[c] for c in swapped):
            for c in [*swapped, 'java/lang/Object."<init>":()V']:
                rest.pop(c, None)
        return not rest or bool(_only_return_type_relinks(rest))

    for jar_rel, sources in by_jar.items():
        check = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core)
        bad = [c["class"] for c in check["classes"] if not c.get("new") and (
            any(m.split("(")[0] not in allowed for k in ("methods_removed", "methods_added") for m in (c.get("members") or {}).get(k, []))
            or (c.get("members") or {}).get("fields_removed") or (c.get("members") or {}).get("fields_added")
            or (c.get("calls_changed") and not calls_ok(c["calls_changed"])))]
        row = {"jar": jar_rel, "classes": len(sources)}
        if check["status"] != "PASS" or bad:
            row.update({"state": "NOT_PATCHED", "why": check["compile"]["errors"][:2] or bad[:4]})
        elif apply:
            done = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core, install=True)
            row.update({"state": "PORTED", "backup": done.get("backup_jar")})
        else:
            row["state"] = "WOULD_PORT"
        result["jars"].append(row)
    if apply:
        result["left"] = missing_interface_methods(jars, vanilla_core, providers)
    return result


def patch_jar_sources(workspace: Path, vanilla_core: Path, *, apply: bool = False) -> dict:
    """Edited jar-source files (each with a `*.pre-bf-*` backup) -> their jar, when the pre-edit source is faithful."""
    ws = Path(workspace).expanduser().resolve()
    working = ws / "working"
    info = _info(working)
    jars = [j for j in info.get("jars") or [] if isinstance(j, str) and (working / j).is_file()]
    edited: dict[Path, Path] = {}
    for root in JAR_SOURCE_ROOTS:
        for backup in sorted((working / root).rglob("*.java.pre-bf-*"), key=lambda p: p.stat().st_mtime) if (working / root).is_dir() else []:
            current = backup.with_name(backup.name.split(".pre-bf-")[0])
            if current.is_file() and current not in edited and current.read_bytes() != backup.read_bytes():
                edited[current] = backup  # the earliest backup: the source as shipped
    by_jar: dict[str, list[tuple[Path, Path]]] = {}
    unshipped = []
    for current, backup in edited.items():
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", current.read_text(encoding="utf-8", errors="replace"), re.M)
        entry = (package.group(1).replace(".", "/") + "/" if package else "") + current.stem + ".class"
        jar = next((j for j in jars if entry in zipfile.ZipFile(working / j).namelist()), None)
        if jar is None:
            unshipped.append(str(current.relative_to(working)))
        else:
            by_jar.setdefault(jar, []).append((current, backup))
    rows = []
    for jar, pairs in by_jar.items():
        before_dir = ws / "scratch" / "patch-jar-sources" / "before"
        before = []
        for current, backup in pairs:
            (before_dir / current.name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, before_dir / current.name)
            before.append(before_dir / current.name)
        faithful = patch_jar_classes(ws, jar, before, vanilla_core=vanilla_core)
        row = {"jar": jar, "files": [str(c.relative_to(working)) for c, _ in pairs]}
        if not _benign(faithful):
            row.update({"state": "SOURCE_NOT_FAITHFUL", "why": faithful["compile"]["errors"][:2]})
        else:
            after = patch_jar_classes(ws, jar, [c for c, _ in pairs], vanilla_core=vanilla_core, install=apply)
            row.update({"state": ("PATCHED" if after.get("installed") else "READY") if after["status"] == "PASS" else after["status"],
                        "refusals": after.get("refusals"), "errors": after["compile"]["errors"][:2],
                        "classes": {c["class"]: {"null_checks": c.get("null_checks"), "calls": c.get("calls_changed"),
                                                 "members": c.get("members")} for c in after["classes"]}})
        rows.append(row)
    return {"schema_version": SCHEMA_VERSION, "mode": "PATCH_JAR_SOURCES", "workspace": ws.name, "jars": rows,
            "not_in_any_jar": unshipped}


def port_interfaces_queue(queue: Path, vanilla_core: Path, *, apply: bool = False, quiet: bool = False, restart: bool = False) -> dict:
    from .progress import Checkpoint, report

    queue = Path(queue).expanduser().resolve()
    workspaces = [p for p in sorted(queue.iterdir()) if p.is_dir() and not p.name.startswith("_") and (p / "working" / "mod_info.json").is_file()
                  and _info(p / "working").get("jars")]
    checkpoint_path = queue / "PORT_INTERFACES.partial.jsonl"
    if restart:
        checkpoint_path.unlink(missing_ok=True)
    rows = []
    with Checkpoint(checkpoint_path, {"mode": "PORT_INTERFACES", "apply": apply, "queue": str(queue)}) as checkpoint:
        for number, ws in enumerate(workspaces, 1):
            started = time.perf_counter()
            cached = checkpoint.get(ws.name)
            row = cached if cached is not None else port_interfaces(ws, vanilla_core, apply=apply)
            row.pop("left", None)
            if cached is None:
                checkpoint.add(ws.name, row)
            rows.append(row)
            if not quiet:
                states = ",".join(j["state"] for j in row["jars"]) or ("CLEAN" if not row["classes"] else "UNPORTED")
                report(number, len(workspaces), ws.name, f"{row['classes']} class(es) {states}", None if cached is not None else time.perf_counter() - started)
        checkpoint.finish()
    return {"schema_version": SCHEMA_VERSION, "mode": "PORT_INTERFACES_QUEUE", "apply": apply, "workspaces": [r for r in rows if r["classes"]]}
