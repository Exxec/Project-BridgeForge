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


def _benign(check: dict) -> bool:
    return check["status"] == "PASS" and all(
        not c.get("members") and (not c.get("calls_changed") or _only_return_type_relinks(c["calls_changed"]))
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
    if any(not p.get("return_type_only") for v in problems.values() for p in v):
        result["state"] = "NEEDS_PORT"
        result["port"] = sorted({f"{p['owner']}.{p['name']}" for v in problems.values() for p in v if not p.get("return_type_only")})[:12]
        return result
    jdk = find_jdk(None)
    java = jdk.javac.with_name("java.exe" if jdk.javac.suffix else "java") if jdk else None
    by_jar: dict[str, list[tuple[Path, bool]]] = {}
    for entry in problems:
        jar_name, _, member = entry.partition("!")
        jar_rel = next(j for j in jars if j.name == jar_name).relative_to(working).as_posix()
        outer = member.removesuffix(".class").split("$", 1)[0]
        target = ws / "scratch" / stamp / Path(outer).name / (Path(outer).name + ".java")
        decompiled = False
        if not target.exists():
            source, decompiled = _source_for(ws, working, jar_rel, outer, java)
            if source is None:
                result["missing_source"].append(outer)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        by_jar.setdefault(jar_rel, []).append((target, decompiled))
    for jar_rel, pairs in by_jar.items():
        sources = sorted({s for s, _ in pairs})
        check = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core)
        for _ in range(3):  # decompile repairs, then recompile
            if check["compile"]["success"] or not any(repair_decompile(s, check["compile"]["errors"]) for s, d in pairs if d):
                break
            check = patch_jar_classes(ws, jar_rel, sources, vanilla_core=vanilla_core)
        row = {"jar": jar_rel, "classes": len(sources), "decompiled": any(d for _, d in pairs)}
        if not _benign(check):
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
