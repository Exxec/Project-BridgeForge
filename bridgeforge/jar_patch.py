"""`bridgeforge patch-jar-class`: recompile a few edited classes and swap them into a mod jar, checked with javap.

On 2026-09-29/30 this was done by hand eight times: FlowerGod, Broken Star, Flu-X, Molecular Replicator, Unusually
Gullible Hullmods, Vayra's Sector, Arkships, Pegasus Belt Council and First Persean Empire. Each time the mod's bundled
source did not rebuild the whole jar without losing a member (`rebuild-jar` refuses that, correctly), but the one
edited class compiled cleanly against RC8, the jar itself and the rig's libraries.

What it does:
- Compiles only the given sources, with the working jar on the classpath (the other classes it needs).
- Requires every produced class to replace a class already in the jar. A new top-level class is refused; a new
  inner class is reported.
- Compares each class with the shipped one: members (reusing rebuild-jar's class-file diff) and, with javap, the
  multiset of method calls and the number of null checks. String-concatenation and logging calls are listed apart,
  since compilers build concatenation differently.
- Installs only with install=True. A removed member refuses unless `allow_removed` names it, as when a hull-mod
  field moves to per-ship custom data. The old jar and the old sources go to scratch/jar-patch-<date>/, and each
  edited source is copied back to the source tree it came from when `source_root` is given.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from .java_toolchain import assemble_classpath, find_jdk, run_javac
from .rebuild_jar import _diff_class, _parse_class

SCHEMA_VERSION = 1
_NOISE = re.compile(r"StringBuilder|String\.valueOf|StringConcatFactory|makeConcat|Logger|getLogger")


class JarPatchError(ValueError):
    pass


def _javap_stats(javap: Path, class_file: Path) -> tuple[Counter, int]:
    out = subprocess.run([str(javap), "-c", "-p", str(class_file)], capture_output=True, text=True, check=False).stdout
    calls = Counter(m.group(1) for m in re.finditer(r"//\s*(?:Method|InterfaceMethod)\s+(\S+)", out))
    return calls, len(re.findall(r"\bif(?:non)?null\b", out))


def _package_path(source: Path) -> str:
    match = re.search(r"^\s*package\s+([\w.]+)\s*;", source.read_text(encoding="utf-8", errors="replace"), re.M)
    return match.group(1).replace(".", "/") if match else ""


def patch_jar_classes(workspace: Path, jar: str, sources: list[Path], *, vanilla_core: Path | None = None,
                      provider_roots: list[Path] | None = None, source_root: str | None = None,
                      allow_removed: list[str] | None = None, install: bool = False, jdk: Path | None = None) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    jar_path = (working / jar).resolve()
    if not jar_path.is_file():
        raise JarPatchError(f"{jar_path} is not a file.")
    sources = [Path(s).expanduser().resolve() for s in sources]
    missing = [str(s) for s in sources if not s.is_file()]
    if missing:
        raise JarPatchError("Missing sources: " + ", ".join(missing))
    jdk_info = find_jdk(jdk)
    if jdk_info is None:
        raise JarPatchError("No JDK found (checked --jdk, In operation/_rig/jdk-*, JAVA_HOME, PATH).")
    if provider_roots is None:
        rig_mods = workspace.parent / "_rig" / "mods"
        provider_roots = [rig_mods] if rig_mods.is_dir() else []
    classpath = assemble_classpath(working, vanilla_core, provider_roots).classpath()

    out_dir = Path(tempfile.mkdtemp(prefix="bf-jar-patch-"))
    run = run_javac(jdk_info.javac, classpath, sources, out_dir / "classes")
    result = {"schema_version": SCHEMA_VERSION, "mode": "PATCH_JAR_CLASS", "workspace": str(workspace), "jar": jar,
              "sources": [str(s) for s in sources], "compile": {"success": run.success, "errors": run.errors[:20]},
              "classes": [], "installed": False}
    if not run.success:
        return {**result, "status": "FAIL", "reason": "compile failed"}

    new_classes = {p.relative_to(out_dir / "classes").as_posix(): p.read_bytes() for p in (out_dir / "classes").rglob("*.class")}
    with zipfile.ZipFile(jar_path) as archive:
        shipped = {name: archive.read(name) for name in archive.namelist() if name in new_classes}
    allowed = set(allow_removed or [])
    refusals = []
    for name, data in sorted(new_classes.items()):
        entry: dict = {"class": name}
        old = shipped.get(name)
        if old is None:
            if "$" not in name.rsplit("/", 1)[-1]:
                refusals.append(f"{name} is not in {jar}: a new top-level class")
            entry["new"] = True
            result["classes"].append(entry)
            continue
        old_parsed, new_parsed = _parse_class(old), _parse_class(data)
        diff = _diff_class(name, old_parsed, new_parsed) or {}
        # Compare raw member names: the diff's labels join name and descriptor ("checkF").
        gone = ({key[0] for key in old_parsed.methods} - {key[0] for key in new_parsed.methods}) | \
               ({key[0] for key in old_parsed.fields} - {key[0] for key in new_parsed.fields})
        removed = sorted(member for member in gone if member not in allowed and not member.startswith(("lambda$", "access$")))
        if removed:
            refusals.append(f"{name}: removed {', '.join(removed)} (name them in allow_removed if intended)")
        with tempfile.TemporaryDirectory() as tmp:
            before, after = Path(tmp) / "before.class", Path(tmp) / "after.class"
            before.write_bytes(old)
            after.write_bytes(data)
            old_calls, old_null = _javap_stats(jdk_info.javap, before)
            new_calls, new_null = _javap_stats(jdk_info.javap, after)
        changed = {k: new_calls.get(k, 0) - old_calls.get(k, 0) for k in set(old_calls) | set(new_calls) if new_calls.get(k, 0) != old_calls.get(k, 0)}
        entry.update({
            "members": {k: diff.get(k, []) for k in ("methods_removed", "methods_added", "fields_removed", "fields_added") if diff.get(k)},
            "calls_changed": {k: v for k, v in sorted(changed.items()) if not _NOISE.search(k)},
            "concat_or_logging_calls_changed": sorted(k for k in changed if _NOISE.search(k)),
            "null_checks": [old_null, new_null],
            "forbidden_sandbox_references": diff.get("forbidden_sandbox_references", []),
        })
        if entry["forbidden_sandbox_references"]:
            refusals.append(f"{name}: forbidden sandbox references {entry['forbidden_sandbox_references']}")
        result["classes"].append(entry)
    result["status"] = "REFUSED" if refusals else "PASS"
    result["refusals"] = refusals
    if not install or refusals:
        return result

    backup = workspace / "scratch" / f"jar-patch-{date.today().isoformat()}"
    backup.mkdir(parents=True, exist_ok=True)
    kept = backup / f"{jar_path.name}.before"
    n = 2
    while kept.exists():
        kept = backup / f"{jar_path.name}.before-{n}"
        n += 1
    shutil.copy2(jar_path, kept)
    temp = jar_path.with_suffix(jar_path.suffix + ".tmp")
    with zipfile.ZipFile(kept) as source_jar, zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as target_jar:
        names = set(source_jar.namelist())
        for info in source_jar.infolist():
            target_jar.writestr(info, new_classes.get(info.filename) or source_jar.read(info.filename))
        for name, data in new_classes.items():
            if name not in names:
                target_jar.writestr(name, data)
    temp.replace(jar_path)
    copied = []
    if source_root:
        root = (working / source_root).resolve()
        for source in sources:
            target = root / _package_path(source) / source.name
            if target.resolve() == source:
                continue
            if target.is_file():
                (backup / "src-before" / target.relative_to(root)).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup / "src-before" / target.relative_to(root))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(str(target.relative_to(working)))
    result.update({"installed": True, "backup_jar": str(kept), "sources_copied": copied})
    (backup / f"PATCH-{jar_path.stem}.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def prepare_jar_packets(workspace: Path, *, vanilla_core: Path | None = None, provider_roots: list[Path] | None = None,
                        jdk: Path | None = None) -> dict:
    """For each jar-only escalation packet: find the class's source in the working copy, copy it to
    scratch/jar-packets/<packet>/ to edit, and compile the unedited copy with `patch_jar_classes` (no install).
    `faithful` means the source rebuilds the shipped class with no member or call change, so an edit there is
    safe to patch in; otherwise the bundled source is older or newer than the jar (VayraGhostShip, 2026-09-30)
    and the class must be edited from a decompile. Replaces the per-packet lookup done by hand for nine mods."""
    from .escalation import jar_only, list_packets

    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    sources_by_name: dict[str, list[Path]] = {}
    for path in working.rglob("*.java"):
        sources_by_name.setdefault(path.name, []).append(path)
    rows = []
    for packet in (p for p in list_packets(workspace) if p["kind"] == "agent" and jar_only(p)):
        for entry in packet["allowed_files"]:
            jar, _, class_path = entry.partition("!")
            outer = class_path.split("$", 1)[0].removesuffix(".class")
            wanted = outer + ".java"
            candidates = [p for p in sources_by_name.get(Path(wanted).name, []) if p.as_posix().endswith("/" + wanted)]
            row: dict = {"packet": packet["id"], "finding": packet["finding"], "jar": jar, "class": outer.replace("/", ".")}
            if not candidates:
                rows.append({**row, "source": None, "state": "NO_SOURCE", "next": "no source ships with the mod: decompile the jar (Vineflower/Fernflower; FlowerGod's src-decompiled/PROVENANCE.md has the command) and edit that class"})
                continue
            source = candidates[0]
            target = workspace / "scratch" / "jar-packets" / packet["id"] / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(source, target)
            check = patch_jar_classes(workspace, jar, [target], vanilla_core=vanilla_core, provider_roots=provider_roots, jdk=jdk)
            main_class = next((c for c in check["classes"] if c["class"] == outer + ".class"), {})
            faithful = check["status"] == "PASS" and not main_class.get("members") and not main_class.get("calls_changed")
            state = "FAITHFUL" if faithful else ("COMPILE_FAILED" if not check["compile"]["success"] else "SOURCE_DIFFERS")
            rows.append({**row, "source": str(source.relative_to(working)), "edit": str(target), "state": state,
                         "differences": {k: main_class.get(k) for k in ("members", "calls_changed") if main_class.get(k)} or None,
                         "errors": check["compile"]["errors"][:5] or None,
                         "next": f'edit {target.name}, then bridgeforge patch-jar-class "{workspace}" --jar {jar} "{target}"'
                                 + " --install" if faithful else "compare with the shipped class before editing; the source is not what shipped"})
    return {"schema_version": SCHEMA_VERSION, "mode": "JAR_PACKETS", "workspace": str(workspace), "packets": rows}
