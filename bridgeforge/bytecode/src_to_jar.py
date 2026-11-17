"""Carry edited jar sources into the jar the game loads (ROADMAP-3 item 92.25, 2026-11-16).

`escalation run --apply` and the source fixers edit `src/**/*.java`; nothing rebuilt the jar, so Navarchy of Tania's eight
applied agent fixes and Eridani Combine's one were inert in `tania.jar` / `ECE.jar` until done by hand. This module:

1. finds the sources to rebuild: `working/<source_root>` files that differ from the author's `original/` copy (plus any
   relink-only classes named by the caller);
2. proves the source tree is authoritative: each ORIGINAL source, compiled against the reference core at the shipped
   class's own Java release, gives bytecode identical to the jar's (`javap -c -p`, constant-pool indexes stripped). A jar
   built from other source is refused; replacing its class would silently revert whatever the jar has that src/ lacks;
3. compiles the edited sources against the target core and patches the jar with `patch_jar_classes` (its member-removal
   and class-header refusals, backup under scratch/jar-patch-<date>/ and atomic write all apply);
4. records each built source's sha256 in `working/reports/src-to-jar.json`, which the `jar-source-not-rebuilt` check reads.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from bridgeforge.bytecode.jar_patch import JarPatchError, _package_path, patch_jar_classes, shipped_release
from bridgeforge.bytecode.java_toolchain import find_jdk, run_javac

LEDGER = Path("reports") / "src-to-jar.json"
_CP_INDEX = re.compile(r"#\d+")


class SrcToJarError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def original_root(workspace: Path) -> Path | None:
    """The author's mod folder under original/ (intake: original/extracted/<Mod>/; older layout: original/<Mod>/)."""
    for pattern in ("extracted/*/mod_info.json", "*/mod_info.json", "*/*/mod_info.json"):
        found = sorted((Path(workspace) / "original").glob(pattern))
        if found:
            return found[0].parent
    return None


def changed_sources(workspace: Path, source_root: str = "src") -> list[str]:
    """Source files (relative to the source root) the working copy changed or added relative to the author's copy."""
    workspace = Path(workspace)
    working_src, orig = workspace / "working" / source_root, original_root(workspace)
    if not working_src.is_dir():
        return []
    orig_src = orig / source_root if orig else None
    changed = []
    for path in sorted(working_src.rglob("*.java")):
        rel = path.relative_to(working_src).as_posix()
        before = orig_src / rel if orig_src else None
        if before is None or not before.is_file() or before.read_bytes() != path.read_bytes():
            changed.append(rel)
    return changed


def read_ledger(working: Path) -> dict[str, str]:
    path = Path(working) / LEDGER
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (data.get("built") or {}).items() if isinstance(k, str) and isinstance(v, str)}


def _write_ledger(working: Path, built: dict[str, str]) -> None:
    from bridgeforge.safeio import atomic_write_json

    ledger = read_ledger(working) | built
    atomic_write_json(Path(working) / LEDGER, {"schema_version": 1, "built": dict(sorted(ledger.items()))})


def _javap_text(javap: Path, class_file: Path) -> str:
    # Bytes, decoded leniently: javap prints string constants in the platform encoding (cp1252 on Windows), so Bultach
    # Coalition's 'è' constants crashed a text-mode read (2026-11-16). Both sides are decoded alike, so the comparison holds.
    raw = subprocess.run([str(javap), "-c", "-p", str(class_file)], capture_output=True, check=False).stdout
    out = raw.decode("utf-8", errors="replace")
    return "\n".join(_CP_INDEX.sub("", line) for line in out.splitlines() if not line.startswith("Compiled from"))


def _class_entries(jar: Path, class_stem: str) -> dict[str, bytes]:
    """The jar's class `pkg/Name.class` and its inner classes `pkg/Name$*.class`."""
    from bridgeforge.zipsafe import MAX_CLASS_BYTES, read_limited

    with zipfile.ZipFile(jar) as archive:
        return {n: read_limited(archive, n, MAX_CLASS_BYTES) for n in archive.namelist()
                if n == f"{class_stem}.class" or (n.startswith(f"{class_stem}$") and n.endswith(".class"))}


def prove_authoritative(workspace: Path, jar_rel: str, rels: list[str], *, reference_core: Path, source_root: str = "src",
                        extra_classpath: list[Path] | None = None, reference_jar: Path | None = None,
                        jdk: Path | None = None) -> list[str]:
    """Problems (empty = authoritative): each original source must reproduce the shipped jar's class(es) exactly when
    compiled against the reference core at the shipped release. `reference_jar`: the pre-patch jar, when the working jar
    already holds an earlier patch of the same class."""
    workspace = Path(workspace).resolve()
    jar = Path(reference_jar) if reference_jar else workspace / "working" / jar_rel
    orig = original_root(workspace)
    jdk_info = find_jdk(jdk)
    if jdk_info is None:
        raise SrcToJarError("No JDK found (checked --jdk, In operation/_rig/jdk-*, JAVA_HOME, PATH).")
    sources = [orig / source_root / rel for rel in rels if orig and (orig / source_root / rel).is_file()]
    if not sources:
        return []  # only new sources: nothing shipped to reproduce
    classpath = os.pathsep.join([*(str(j) for j in sorted(Path(reference_core).glob("*.jar"))), *(str(j) for j in extra_classpath or []), str(jar)])
    problems = []
    with tempfile.TemporaryDirectory(prefix="bf-src2jar-") as tmp:
        out = Path(tmp) / "ref"
        run = run_javac(jdk_info.javac, classpath, sources, out, release=shipped_release(jar, sources))
        if not run.success:
            return [f"original source does not compile against the reference core: {e.get('file', '')}:{e.get('line', '')} "
                    f"{e.get('message', '')}" for e in run.errors[:5]]
        for source in sources:
            package = _package_path(source)
            stem = f"{package}/{source.stem}" if package else source.stem
            shipped = _class_entries(jar, stem)
            if f"{stem}.class" not in shipped:
                problems.append(f"{stem}.class: not in {jar.name}")
                continue
            for name, data in shipped.items():
                built = out / name
                if not built.is_file():
                    problems.append(f"{name}: in the jar but not produced by the original source")
                    continue
                shipped_file = Path(tmp) / "shipped" / name
                shipped_file.parent.mkdir(parents=True, exist_ok=True)
                shipped_file.write_bytes(data)
                if _javap_text(jdk_info.javap, built) != _javap_text(jdk_info.javap, shipped_file):
                    problems.append(f"{name}: the original source does not reproduce the jar class")
    return problems


def moved_state_fields(workspace: Path) -> list[str]:
    """Field names the workspace's `hullmod-instance-state` packets list (`field:NAME`): the fix moves exactly these to
    per-ship custom data, so their removal from the rebuilt class is intended (Bultach Coalition, 13 hull mods, 2026-11-16).
    Any other removed member still has to be named by a person (`--allow-removed`)."""
    names: set[str] = set()
    for packet in sorted((Path(workspace) / "reports" / "escalations").glob("hullmod-instance-state--*.json")):
        try:
            data = json.loads(packet.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for finding in data.get("findings") or []:
            names |= {e.split(":", 1)[1] for e in finding.get("evidence") or [] if isinstance(e, str) and e.startswith("field:")}
    return sorted(names)


def src_to_jar(workspace: Path, jar_rel: str, *, vanilla_core: Path, reference_core: Path | None, source_root: str = "src",
               extra_classpath: list[Path] | None = None, relink: list[str] | None = None, reference_jar: Path | None = None,
               apply: bool = False, jdk: Path | None = None, allow_removed: list[str] | None = None) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    if not (working / jar_rel).is_file():
        raise SrcToJarError(f"{working / jar_rel} is not a file.")
    rels = sorted(set(changed_sources(workspace, source_root)) | {r if r.endswith(".java") else f"{r}.java" for r in relink or []})
    # Only sources whose class this jar ships: a mod with two jars is rebuilt one jar at a time.
    with zipfile.ZipFile(Path(reference_jar) if reference_jar else working / jar_rel) as archive:
        shipped = set(archive.namelist())

    def in_jar(rel: str) -> bool:
        source = working / source_root / rel
        package = _package_path(source) if source.is_file() else ""
        return (f"{package}/{source.stem}.class" if package else f"{source.stem}.class") in shipped

    skipped = [rel for rel in rels if not in_jar(rel)]
    rels = [rel for rel in rels if rel not in skipped]
    result = {"schema_version": 1, "mode": "SRC_TO_JAR", "workspace": str(workspace), "jar": jar_rel, "sources": rels,
              "skipped": skipped, "apply": apply}
    if not rels:
        return {**result, "status": "NOTHING_TO_BUILD"}
    if reference_core is None:
        return {**result, "status": "REFUSED", "refusals": [
            "needs the core the jar was built against (--reference-core) to prove src/ reproduces the shipped classes"]}
    problems = prove_authoritative(workspace, jar_rel, rels, reference_core=reference_core, source_root=source_root,
                                   extra_classpath=extra_classpath, reference_jar=reference_jar, jdk=jdk)
    if problems:
        return {**result, "status": "REFUSED", "refusals": problems}
    try:
        patch = patch_jar_classes(workspace, jar_rel, [working / source_root / rel for rel in rels], vanilla_core=vanilla_core,
                                  install=apply, jdk=jdk, extra_classpath=extra_classpath,
                                  allow_removed=sorted(set(allow_removed or []) | set(moved_state_fields(workspace))))
    except JarPatchError as exc:
        return {**result, "status": "REFUSED", "refusals": [str(exc)]}
    result.update({"status": patch["status"], "compile": patch["compile"], "classes": [c["class"] for c in patch["classes"]],
                   "refusals": patch.get("refusals") or [], "installed": patch.get("installed", False),
                   "backup_jar": patch.get("backup_jar")})
    if patch.get("installed"):
        _write_ledger(working, {f"{source_root}/{rel}": _sha(working / source_root / rel) for rel in rels})
    return result


def unbuilt_sources(working: Path) -> list[str]:
    """Sources BridgeForge edited (a `.pre-bf-*.bak` beside them) in a jar mod, whose current bytes were never built into
    the jar (no matching sha256 in the ledger). Read by the `jar-source-not-rebuilt` check."""
    working = Path(working)
    info_path = working / "mod_info.json"
    try:
        from bridgeforge.scan.scanner import _load_lenient_json_file
        info = _load_lenient_json_file(info_path) if info_path.is_file() else None
    except Exception:  # noqa: BLE001 - a malformed mod_info is reported by its own check
        info = None
    if not isinstance(info, dict) or not [j for j in info.get("jars") or [] if isinstance(j, str) and (working / j).is_file()]:
        return []
    ledger = read_ledger(working)
    found = []
    for backup in sorted(working.rglob("*.java.pre-bf-*.bak")):
        source = backup.with_name(backup.name.split(".pre-bf-", 1)[0])
        if not source.is_file() or source.is_relative_to(working / "data"):
            continue  # loose scripts under data/ are compiled by the game itself
        rel = source.relative_to(working).as_posix()
        if ledger.get(rel) != _sha(source) and rel not in found:
            found.append(rel)
    return found
