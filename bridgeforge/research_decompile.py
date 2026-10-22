"""Readable code for `research report` (ROADMAP-3 82.7): decompile only the jar classes a question touches, quote the relevant methods.

Vineflower output is a derived reading aid (STATIC): the bytecode stays authoritative, nothing here proves runtime behaviour and the
decompiled text is never written into a workspace. Classes (with their inner classes) are extracted from the jar into a temporary
folder, decompiled into `<cache>/<jar-sha256>/`, and cached by jar hash: a class already decompiled for that jar and Vineflower is not
decompiled again. A missing Vineflower or JDK is reported as missing, with how to get it; it is never an error.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .decompile import find_vineflower
from .java_toolchain import find_jdk
from .research_terms import STATIC, Matcher
from .safeio import atomic_write_bytes, atomic_write_json
from .zipsafe import MAX_CLASS_BYTES, read_limited

DEFAULT_MAX_CLASSES = 12
MAX_EXCERPT_METHODS = 4
MAX_METHOD_LINES = 25
MAX_HEADER_LINES = 20
VINEFLOWER_TIMEOUT_SECONDS = 300
HOW_TO_GET = ("put vineflower-*.jar (Vineflower 1.12.0) in In operation/_tools/ and install a JDK 17+ (a rig jdk-*, JAVA_HOME or PATH); "
              "see `python -m bridgeforge decompile-jar --help`")
_VERSION = re.compile(r"vineflower-([\w.]+?)\.jar$", re.IGNORECASE)
_CONTROL = re.compile(r"^(?:if|for|while|switch|catch|synchronized|else|try|do|return|new|throw)\b")
_STRINGS = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
_METHOD_END = re.compile(r"\)\s*(?:throws\s+[\w.,\s]+)?\{\s*$")


@dataclass(frozen=True)
class Toolchain:
    java: Path
    vineflower: Path
    vineflower_version: str
    jdk: str


def find_toolchain(home: Path | None = None) -> tuple[Toolchain | None, str]:
    """(toolchain, "") or (None, why it is missing). `home` is the checkout that holds `In operation/` (the case's queue folder's parent), tried
    when this package's own checkout has none (a git worktree). The one place tests replace to avoid running Java."""
    vineflower = find_vineflower()
    if vineflower is None and home is not None:
        found = sorted((Path(home) / "In operation" / "_tools").glob("vineflower*.jar"))
        vineflower = found[-1] if found else None
    if vineflower is None:
        return None, "Vineflower not found (In operation/_tools/vineflower-*.jar)"
    jdk = find_jdk() or (find_jdk(repo_root=home) if home is not None else None)
    if jdk is None:
        return None, "no JDK found"
    java = jdk.javac.with_name("java.exe" if jdk.javac.suffix == ".exe" else "java")
    found_version = _VERSION.search(vineflower.name)
    return Toolchain(java, vineflower, found_version.group(1) if found_version else vineflower.stem, f"{jdk.home.name} ({jdk.source})"), ""


def run_vineflower(toolchain: Toolchain, source: Path, output: Path) -> tuple[int, str]:
    """Run Vineflower over a folder of .class files into `output`; (exit code, log tail). The one place tests replace."""
    try:
        run = subprocess.run([str(toolchain.java), "-jar", str(toolchain.vineflower), "-dgs=1", str(source), str(output)], capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=VINEFLOWER_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, f"{type(exc).__name__}: {exc}"
    return run.returncode, (run.stdout + run.stderr)[-400:]


def jar_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def outer_name(entry: str) -> str:
    """`a/b/C$D.class` -> `a/b/C` (the top-level class an inner class decompiles inside)."""
    return entry[:-len(".class")].split("$", 1)[0]


def jar_class_rows(trees: dict[str, dict], analysis: dict[str, dict]) -> list[dict]:
    """One row per top-level jar class the search hit, listing every tree (and jar) holding it: duplicates across original/old/working collapse here."""
    rows: dict[str, dict] = {}
    for tree_id, item in analysis.items():
        for hit in item["hits"]:
            if hit["how"] not in ("jar-entry-name", "jar-class-bytes") or "!" not in hit["file"] or not hit["file"].endswith(".class"):
                continue
            jar_rel, entry = hit["file"].split("!", 1)
            row = rows.setdefault(outer_name(entry), {"class": outer_name(entry).replace("/", "."), "entry": outer_name(entry), "trees": [], "jars": [], "terms": set(), "by_name": False, "label": STATIC})
            if tree_id not in row["trees"]:
                row["trees"].append(tree_id)
            location = f"{tree_id}:{jar_rel}"
            if location not in row["jars"]:
                row["jars"].append(location)
            row["terms"].add(hit["term"])
            row["by_name"] = row["by_name"] or hit["how"] == "jar-entry-name"
    tree_order = list(trees)
    out = []
    for row in rows.values():
        row["trees"].sort(key=tree_order.index)
        out.append({**row, "terms": sorted(row["terms"])})
    return sorted(out, key=lambda r: (not r["by_name"], r["class"]))


def _safe_entry(name: str) -> bool:
    path = PurePosixPath(name)
    return name.endswith(".class") and not path.is_absolute() and ".." not in path.parts and ":" not in name


def _extract(jar: Path, outers: list[str], target: Path) -> list[str]:
    """Write each outer class and its `$` inner classes from `jar` under `target`; returns the entry names written."""
    written = []
    wanted = tuple(outers)
    with zipfile.ZipFile(jar) as archive:
        for info in archive.infolist():
            name = info.filename
            if not _safe_entry(name) or not any(name == f"{o}.class" or name.startswith(f"{o}$") for o in wanted):
                continue
            atomic_write_bytes(target / name, read_limited(archive, info, MAX_CLASS_BYTES))
            written.append(name)
    return written


def _is_method_start(code: str) -> bool:
    stripped = code.strip()
    return "(" in stripped and "=" not in stripped.split("(", 1)[0] and not _CONTROL.match(stripped) and bool(_METHOD_END.search(stripped))


def method_spans(lines: list[str]) -> list[tuple[int, int]]:
    """(first, last) line index of each outermost method body, found by brace depth (strings and `//` comments ignored)."""
    spans, depth, start, start_depth = [], 0, None, 0
    for index, line in enumerate(lines):
        code = _STRINGS.sub('""', line).split("//", 1)[0]
        if start is None and depth >= 1 and _is_method_start(code):
            start, start_depth = index, depth
        depth += code.count("{") - code.count("}")
        if start is not None and depth <= start_depth:
            spans.append((start, index))
            start = None
    return spans


def excerpt(source: str, matcher: Matcher) -> dict:
    """The methods naming a feature term (each bounded), else the class header; `lines` are `(number, text)` pairs of the decompiled file."""
    lines = source.splitlines()
    chosen = [(a, b) for a, b in method_spans(lines) if any(matcher.text_hits(lines[i]) for i in range(a, b + 1))][:MAX_EXCERPT_METHODS]
    shown: list[tuple[int, str]] = []
    if chosen:
        for a, b in chosen:
            block = list(range(a, b + 1))[:MAX_METHOD_LINES]
            shown += [(i + 1, lines[i]) for i in block]
            if b - a + 1 > MAX_METHOD_LINES:
                shown.append((block[-1] + 2, f"    // ... {b - a + 1 - MAX_METHOD_LINES} more line(s) of this method not shown"))
        return {"kind": "methods", "methods": len(chosen), "lines": shown}
    declared = next((i for i, line in enumerate(lines) if re.search(r"\b(?:class|interface|enum)\s+\w+", line)), 0)
    shown = [(i + 1, lines[i]) for i in range(declared, min(len(lines), declared + MAX_HEADER_LINES))]
    return {"kind": "header", "methods": 0, "lines": shown}


def _locate(trees: dict[str, dict], location: str) -> Path | None:
    tree_id, _, jar_rel = location.partition(":")
    return trees[tree_id]["path"] / jar_rel if tree_id in trees else None


def _cache_valid(meta_path: Path, toolchain: Toolchain) -> bool:
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("vineflower") == toolchain.vineflower_version
    except (OSError, ValueError):
        return False


def _decompile_jar_classes(jar: Path, sha: str, outers: list[str], cache: Path, toolchain: Toolchain, runner) -> dict[str, dict]:
    """Per outer class: {"status": CACHED|DECOMPILED|FAILED|NOT_IN_JAR, "path", "log"}; only classes not already cached are run."""
    folder = cache / sha
    meta_path = folder / "meta.json"
    fresh_cache = _cache_valid(meta_path, toolchain)
    out: dict[str, dict] = {}
    todo = []
    for outer in outers:
        target = folder / f"{outer}.java"
        if fresh_cache and target.is_file():
            out[outer] = {"status": "CACHED", "path": target, "log": ""}
        else:
            todo.append(outer)
    if todo:
        with tempfile.TemporaryDirectory(prefix="bf-research-classes-") as scratch:
            written = _extract(jar, todo, Path(scratch))
            present = {outer_name(n) for n in written}
            for outer in todo:
                if outer not in present:
                    out[outer] = {"status": "NOT_IN_JAR", "path": None, "log": ""}
            runnable = [o for o in todo if o in present]
            if runnable:
                folder.mkdir(parents=True, exist_ok=True)
                code, log = runner(toolchain, Path(scratch), folder)
                for outer in runnable:
                    target = folder / f"{outer}.java"
                    ok = target.is_file()
                    out[outer] = {"status": "DECOMPILED" if ok else "FAILED", "path": target if ok else None, "log": "" if ok else f"exit {code}: {log.strip()[-200:]}"}
                atomic_write_json(meta_path, {"schema_version": 1, "jar_sha256": sha, "vineflower": toolchain.vineflower_version, "jdk": toolchain.jdk,
                                              "label": STATIC, "note": "derived reading aid; the bytecode stays authoritative"})
    return out


def decompile_report_classes(trees: dict[str, dict], rows: list[dict], matcher: Matcher, cache: Path | None, max_classes: int, home: Path | None = None) -> dict:
    """The report's `decompiled` section. Never raises for a missing tool or a failed class: those become `status` fields."""
    if not rows:
        return {"status": "NO_CLASSES", "note": "the search found no jar class for the feature terms", "classes": [], "label": STATIC}
    toolchain, why = find_toolchain(home)
    if toolchain is None:
        return {"status": "MISSING", "note": why, "how_to_get": HOW_TO_GET, "classes": [], "candidates": len(rows), "label": STATIC}
    selected = rows[:max_classes]
    work = tempfile.TemporaryDirectory(prefix="bf-research-cache-") if cache is None else None
    base = Path(work.name) if work else cache
    try:
        classes = _decompile_selected(trees, selected, matcher, base, toolchain)
    finally:
        if work:
            work.cleanup()
    return {"status": "DONE", "vineflower": toolchain.vineflower_version, "jdk": toolchain.jdk, "candidates": len(rows), "decompiled_classes": len(classes),
            "max_classes": max_classes, "cache": str(cache) if cache else "(not kept: no --write)", "classes": classes, "label": STATIC,
            "note": "STATIC derived reading aid (decompiled by Vineflower); the bytecode stays authoritative and this text is never written into a workspace"}


def _decompile_selected(trees: dict[str, dict], selected: list[dict], matcher: Matcher, base: Path, toolchain: Toolchain, runner=None) -> list[dict]:
    """Each selected class is decompiled from every distinct jar (by hash) that holds it, so an old tree's version is read beside the working one."""
    runner = runner or run_vineflower
    shas: dict[Path, str] = {}
    versions: dict[tuple[str, str], dict] = {}
    jar_of: dict[str, Path] = {}
    for row in selected:
        for location in row["jars"]:
            jar = _locate(trees, location)
            if jar is None or not jar.is_file():
                continue
            sha = shas.setdefault(jar, jar_sha256(jar))
            jar_of.setdefault(sha, jar)
            entry = versions.setdefault((row["entry"], sha), {"row": row, "trees": []})
            tree_id = location.partition(":")[0]
            if tree_id not in entry["trees"]:
                entry["trees"].append(tree_id)
    results = []
    for sha, jar in sorted(jar_of.items()):
        outers = sorted({entry for (entry, s) in versions if s == sha})
        done = _decompile_jar_classes(jar, sha, outers, base, toolchain, runner)
        for outer in outers:
            info, row = done[outer], versions[(outer, sha)]["row"]
            text = info["path"].read_text(encoding="utf-8", errors="replace") if info["path"] else ""
            cut = excerpt(text, matcher) if text else {"kind": "none", "methods": 0, "lines": []}
            results.append({"class": row["class"], "trees": versions[(outer, sha)]["trees"], "jar": jar.name, "jar_sha256": sha, "status": info["status"], "log": info["log"],
                            "excerpt": {**cut, "lines": [[n, t] for n, t in cut["lines"]]}, "label": STATIC})
    return sorted(results, key=lambda r: (r["class"], r["jar_sha256"]))
