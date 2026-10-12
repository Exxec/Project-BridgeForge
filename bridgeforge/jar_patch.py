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


def _in_nest(call: str, class_entry: str) -> bool:
    """`call` ("owner.name:desc", or "name:desc" for the class itself) targets the class's own nest."""
    outer = class_entry.removesuffix(".class").split("$", 1)[0]
    owner = call.split(":", 1)[0].rsplit(".", 1)[0] if "." in call.split(":", 1)[0] else outer
    return owner == outer or owner.startswith(outer + "$")


def _javap_stats(javap: Path, class_file: Path) -> tuple[Counter, int]:
    out = subprocess.run([str(javap), "-c", "-p", str(class_file)], capture_output=True, text=True, check=False).stdout
    calls: Counter = Counter()
    previous = ""
    for line in out.splitlines():
        found = re.search(r"//\s*(?:Method|InterfaceMethod)\s+(\S+)", line)
        if found:
            # Objects.requireNonNull(this) is javac checking `this` before a static constant written as
            # `this.CONSTANT` (decompiler output; Special Hullmod Upgrades, Bounties Expanded, 2026-10-01). `this` is
            # never null, so the check does nothing and is not counted as a call.
            if not (found.group(1).startswith("java/util/Objects.requireNonNull:") and re.search(r":\s*aload_0\s*$", previous)):
                calls[found.group(1)] += 1
        if re.search(r"^\s*\d+:", line):
            previous = line
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
    rig_mods = workspace.parent / "_rig" / "mods"
    if provider_roots is None:
        provider_roots = [rig_mods] if rig_mods.is_dir() else []
    # Declared dependencies are also looked up in the queue: Magellan Shenanigans needs Magellan Protectorate's
    # classes, a queued mod not in the rig (2026-10-01). Only the rig's jars are added wholesale (below).
    dependency_roots = [*provider_roots, workspace.parent] if workspace.parent not in provider_roots else list(provider_roots)
    classpath = assemble_classpath(working, vanilla_core, dependency_roots).classpath()
    # Also every jar the rig's mods declare: the game loads them together, and a mod can use a library it never
    # declared (Vayra's Sector and LazyLib, 2026-09-30). Only declared jars: FlowerGod's build/cp held a game jar copy.
    import os

    from .scanner import _load_lenient_json_file
    extra = []
    for root in provider_roots:
        for info_path in sorted(Path(root).glob("*/mod_info.json")):
            info = _load_lenient_json_file(info_path) or {}
            if isinstance(info, dict):
                extra += [str(info_path.parent / j) for j in info.get("jars") or [] if isinstance(j, str) and (info_path.parent / j).is_file()]
    if extra:
        classpath = os.pathsep.join([classpath, *extra]) if classpath else os.pathsep.join(extra)

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
            "calls_changed": {k: v for k, v in sorted(changed.items()) if not _NOISE.search(k) and not _in_nest(k, name)},
            "concat_or_logging_calls_changed": sorted(k for k in changed if _NOISE.search(k)),
            # Calls inside the class's own nest: an old javac reached a private inner member through a synthetic
            # access$NNN bridge, Java 11+ calls it directly (VayraGhostShip$NanobotData, 2026-09-30). Shown, not counted.
            "nest_calls_changed": {k: v for k, v in sorted(changed.items()) if not _NOISE.search(k) and _in_nest(k, name)},
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
    # A jar that just appeared in the workspace may be held open briefly by an indexer (VS Code's Java extension,
    # Arkgneisis 2026-09-30: WinError 5); retry before giving up, and never leave the temp behind.
    import time

    for attempt in range(10):
        try:
            temp.replace(jar_path)
            break
        except PermissionError:
            if attempt == 9:
                temp.unlink(missing_ok=True)
                raise
            time.sleep(1)
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


_OBJECT_METHODS = ("equals:(Ljava/lang/Object;)Z", "hashCode:()I", "toString:()Ljava/lang/String;", "getClass:()Ljava/lang/Class;")


def _drop_object_owner_swaps(calls_changed: dict[str, int]) -> dict[str, int]:
    """Remove an Object method whose recorded owner changed (`Object.equals` -> `CampaignFleetAPI.equals`): javac
    versions name the receiver's static type or Object, the same method either way (Epta, Scy Nation, 2026-09-30)."""
    rest = dict(calls_changed)
    # javac 9+ checks an implicit null (an inner-class `outer.new`, a method reference) with Objects.requireNonNull
    # where older javac called getClass() (Special Hullmod Upgrades, 2026-10-01): the same check.
    swap = [c for c in rest if c.endswith(".getClass:()Ljava/lang/Class;")]
    need = "java/util/Objects.requireNonNull:(Ljava/lang/Object;)Ljava/lang/Object;"
    if swap and need in rest and rest[need] > 0 and sum(rest[c] for c in swap) == -rest[need]:
        for call in [*swap, need]:
            del rest[call]
    for method in _OBJECT_METHODS:
        hits = {call: delta for call, delta in rest.items() if call.endswith("." + method) or call == method}
        if hits and sum(hits.values()) == 0:
            for call in hits:
                del rest[call]
    return rest


def _only_return_type_relinks(calls_changed: dict[str, int]) -> list[str]:
    """The changed calls, when they pair up exactly as `owner.name:(args)OLD` -n / `owner.name:(args)NEW` +n: the same
    call sites linked to a new return type. Empty when anything else changed. Object-method owner swaps are ignored."""
    calls_changed = _drop_object_owner_swaps(calls_changed)
    if not calls_changed:
        return ["(Object-method owner only)"]
    by_site: dict[str, dict[int, str]] = {}
    for call, delta in calls_changed.items():
        site, _, returned = call.rpartition(")")
        by_site.setdefault(site, {})[delta] = returned
    relinks = []
    for site, deltas in by_site.items():
        if len(deltas) != 2 or sum(deltas) != 0:
            return []
        relinks.append(f"{site}){deltas[min(deltas)]} -> {deltas[max(deltas)]}")
    return sorted(relinks)


def find_decompiler(workspace: Path) -> Path | None:
    """Vineflower (the maintained Fernflower fork): $BF_DECOMPILER, else the queue's _tools/vineflower-*.jar. Fetched
    from Maven Central 2026-09-30 (1.12.0, SHA-1 checked); a local tool, never committed."""
    import os

    named = os.environ.get("BF_DECOMPILER")
    if named and Path(named).is_file():
        return Path(named)
    found = sorted(Path(workspace).parent.glob("_tools/vineflower-*.jar"))
    return found[-1] if found else None


def _decompiled_tree(workspace: Path, jar: str, java: Path, decompiler: Path) -> Path | None:
    out = workspace / "scratch" / "jar-packets" / "_decompiled" / Path(jar).stem
    if not out.is_dir():
        out.mkdir(parents=True)
        run = subprocess.run([str(java), "-jar", str(decompiler), "-log=WARN", "--kt-enable=false", str(workspace / "working" / jar), str(out)],
                             capture_output=True, text=True, check=False)
        (out / "PROVENANCE.txt").write_text(
            f"Decompiler output ({decompiler.name}), not the author's source.\nInput: working/{jar}\nExit: {run.returncode}\n"
            + (run.stderr or "")[-2000:], encoding="utf-8")
    return out if any(out.rglob("*.java")) else None


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
            row: dict = {"packet": packet["id"], "finding": packet["finding"], "jar": jar, "class": outer.replace("/", "."), "decompiled": False}
            if not candidates:
                decompiler, jdk_info = find_decompiler(workspace), find_jdk(jdk)
                tree = _decompiled_tree(workspace, jar, jdk_info.javac.with_name("java.exe" if jdk_info.javac.suffix else "java"), decompiler) \
                    if decompiler and jdk_info else None
                if tree is not None and (tree / wanted).is_file():
                    candidates, row["decompiled"] = [tree / wanted], True
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
            relinked = _only_return_type_relinks(main_class.get("calls_changed") or {})
            if relinked:
                # The shipped class calls a method whose return type RC8 changed (Too Much Information:
                # TooltipMakerAPI.beginTable(...)V is ...UIPanelAPI in RC8), a NoSuchMethodError as shipped;
                # the recompile links the RC8 descriptor. Same calls otherwise, so still faithful.
                row["relinked"] = relinked
            faithful = check["status"] == "PASS" and not main_class.get("members") and (not main_class.get("calls_changed") or bool(relinked))
            state = "FAITHFUL" if faithful else ("COMPILE_FAILED" if not check["compile"]["success"] else "SOURCE_DIFFERS")
            rows.append({**row, "source": str(source.relative_to(workspace)), "edit": str(target), "state": state,
                         "differences": {k: main_class.get(k) for k in ("members", "calls_changed") if main_class.get(k)} or None,
                         "errors": check["compile"]["errors"][:5] or None,
                         "next": f'edit {target.name}, then bridgeforge patch-jar-class "{workspace}" --jar {jar} "{target}"'
                                 + " --install" if faithful else "compare with the shipped class before editing; the source is not what shipped"})
    return {"schema_version": SCHEMA_VERSION, "mode": "JAR_PACKETS", "workspace": str(workspace), "packets": rows}
