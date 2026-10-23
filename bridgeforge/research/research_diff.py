"""`research diff OLD NEW` (ROADMAP-3 82.9): readable version diffs of only the methods whose bytecode changed. STATIC.

The bytecode decides which methods changed (`bytecode_diff.changed_methods`: per method, a digest of the opcodes and every operand, never line
numbers); the decompiled text of exactly those methods, found through the 82.8 method map, is then diffed so a reader can see what changed. A decompiled
diff only explains: a method Vineflower cannot place is reported UNMAPPED without a diff, and a method whose bytecode differs while its decompiled text
does not is reported as such. The same decompiler options and cache (by jar sha256) as `research report` are used; nothing is written into OLD or NEW.
"""
from __future__ import annotations

import difflib
import tempfile
from pathlib import Path

from bridgeforge.bytecode.bytecode_diff import changed_methods
from ..dropped_sweep import mod_roots
from .research_decompile import HOW_TO_GET, decompile_jar_classes, find_toolchain, jar_sha256, outer_name, run_vineflower
from .research_methods import MethodMap, jar_method_index
from .research_terms import STATIC, Matcher, parse_terms
from ..scan_classfile import _loaded_mod_jars

DEFAULT_MAX_METHODS = 20
DEFAULT_MAX_LINES = 60
CONTEXT_LINES = 2
MAX_LISTED_CLASSES = 25
CHANGES = ("changed", "added", "removed")


class DiffError(ValueError):
    """A side that cannot be read, or the bytecode helper being unavailable (it is the one that decides)."""


def side_jars(path: Path) -> list[Path]:
    """A jar, a mod folder (its loaded jars) or a folder holding mod folders (the shallowest one); DiffError when no jar is found."""
    path = Path(path).expanduser().resolve()
    if path.is_file():
        if path.suffix.lower() != ".jar":
            raise DiffError(f"{path} is not a .jar file or a folder")
        return [path]
    if not path.is_dir():
        raise DiffError(f"{path} does not exist")
    roots = [path] if (path / "mod_info.json").is_file() else mod_roots(path)
    jars = _loaded_mod_jars(roots[0]) if roots else sorted(path.rglob("*.jar"))
    if not jars:
        raise DiffError(f"{path} holds no jar")
    return jars


def class_table(jars: list[Path], indexer) -> tuple[dict[str, dict], list[str]]:
    """{internal class name: {"jar", "details"}} over the jars (the first jar in name order wins a duplicate), plus the duplicates found."""
    table: dict[str, dict] = {}
    duplicates: list[str] = []
    for jar in jars:
        index, why = indexer(jar)
        if index is None:
            raise DiffError(f"the bytecode helper is unavailable ({why}); the diff needs it to decide which methods changed (java and javac on PATH)")
        for name, details in index.items():
            if name in table:
                duplicates.append(f"{name} in {table[name]['jar'].name} and {jar.name} (the first is compared)")
            else:
                table[name] = {"jar": jar, "details": details}
    return table, duplicates


def compare_tables(old: dict[str, dict], new: dict[str, dict], matcher: Matcher | None) -> dict:
    """Bytecode verdict: classes only on one side, and every method that changed, was added or was removed in a class on both sides."""
    wanted = (lambda name: bool(matcher.any_name(name.replace("/", ".")))) if matcher else (lambda name: True)
    rows = []
    for name in sorted(n for n in set(old) & set(new) if wanted(n)):
        verdict = changed_methods({"method_details": old[name]["details"]}, {"method_details": new[name]["details"]})
        rows += [{"class": name, "id": f"{name}#{m['name']} {m['descriptor']}", "change": kind, "name": m["name"], "descriptor": m["descriptor"]}
                 for kind in CHANGES for m in verdict[kind]]
    return {"classes_compared": len([n for n in set(old) & set(new) if wanted(n)]), "added_classes": sorted(n for n in set(new) - set(old) if wanted(n)),
            "removed_classes": sorted(n for n in set(old) - set(new) if wanted(n)), "methods": rows}


def _read_side(label: str, table: dict[str, dict], rows: list[dict], cache: Path, toolchain, runner, indexer) -> dict[str, dict]:
    """{outer class: decompile info (path, status, map)} for the classes of the selected rows on one side, decompiled once per jar hash."""
    needed: dict[Path, set[str]] = {}
    for row in rows:
        entry = table.get(row["class"])
        if entry is not None and row["change"] in (("removed", "changed") if label == "old" else ("added", "changed")):
            needed.setdefault(entry["jar"], set()).add(outer_name(row["class"] + ".class"))
    out: dict[str, dict] = {}
    for jar, outers in sorted(needed.items()):
        out.update(decompile_jar_classes(jar, jar_sha256(jar), sorted(outers), cache, toolchain, runner, indexer))
    return out


def _sections(side: dict[str, dict], row: dict) -> tuple[list[str], tuple[int, int] | None, str]:
    """(decompiled lines of the method, their (first, last) range, why not) for one side of one row."""
    outer = outer_name(row["class"] + ".class")
    info = side.get(outer)
    if info is None or info["path"] is None:
        return [], None, f"class {outer.replace('/', '.')} was not decompiled ({info['status'] if info else 'not requested'}{': ' + info['log'] if info and info['log'] else ''})"
    method_map: MethodMap | None = info.get("map")
    status = method_map.status_of(row["id"]) if method_map else None
    span = method_map.lines_for(row["id"]) if method_map else None
    if span is None:
        return [], None, (status["why"] if status else (f"no method map ({method_map.index})" if method_map else "no method map")) or "unmapped"
    text = info["path"].read_text(encoding="utf-8", errors="replace").splitlines()
    return text[span[0] - 1:span[1]], span, ""


def _diff_row(row: dict, old_side: dict, new_side: dict, max_lines: int) -> dict:
    result = {**row, "label": STATIC, "status": "UNMAPPED", "old_lines": None, "new_lines": None, "diff": [], "truncated": 0, "why": ""}
    old_text, old_span, old_why = _sections(old_side, row) if row["change"] in ("changed", "removed") else ([], None, "")
    new_text, new_span, new_why = _sections(new_side, row) if row["change"] in ("changed", "added") else ([], None, "")
    result["old_lines"], result["new_lines"] = list(old_span) if old_span else None, list(new_span) if new_span else None
    why = [f"{side}: {text}" for side, text in (("old", old_why), ("new", new_why)) if text]
    if why:
        return {**result, "why": "; ".join(why)}
    diff = list(difflib.unified_diff(old_text, new_text, f"old {row['id']}", f"new {row['id']}", lineterm="", n=CONTEXT_LINES))
    if not diff:
        return {**result, "status": "SAME_TEXT", "why": "the bytecode differs but the decompiled text is identical (compiler or constant-level change the reading hides)"}
    return {**result, "status": "DIFFED", "diff": diff[:max_lines], "truncated": max(0, len(diff) - max_lines)}


def build_diff(old: Path, new: Path, classes: str = "", max_methods: int = DEFAULT_MAX_METHODS, max_lines: int = DEFAULT_MAX_LINES,
               cache_dir: Path | None = None, home: Path | None = None, indexer=None, runner=None) -> dict:
    """The `research diff` result: bytecode verdict, then the decompiled diff of at most `max_methods` changed methods (each at most `max_lines` lines)."""
    indexer, runner = _memoized(indexer or jar_method_index), runner or run_vineflower
    old_jars, new_jars = side_jars(old), side_jars(new)
    old_table, old_dups = class_table(old_jars, indexer)
    new_table, new_dups = class_table(new_jars, indexer)
    terms = parse_terms(classes) if classes else ()
    verdict = compare_tables(old_table, new_table, Matcher(terms) if terms else None)
    selected = verdict["methods"][:max_methods]
    toolchain, missing = find_toolchain(home) if selected else (None, "")
    readable: list[dict] = []
    notes = [f"duplicate class: {text}" for text in old_dups + new_dups]
    status = "NO_METHOD_CHANGES" if not verdict["methods"] else "DONE"
    if selected and toolchain is None:
        status, notes = "DECOMPILER_MISSING", notes + [f"{missing}. To get it: {HOW_TO_GET}"]
        readable = [{**row, "label": STATIC, "status": "NOT_DECOMPILED", "old_lines": None, "new_lines": None, "diff": [], "truncated": 0, "why": missing} for row in selected]
    elif selected:
        work = tempfile.TemporaryDirectory(prefix="bf-research-diff-") if cache_dir is None else None
        try:
            base = Path(work.name) if work else cache_dir
            old_side = _read_side("old", old_table, selected, base, toolchain, runner, indexer)
            new_side = _read_side("new", new_table, selected, base, toolchain, runner, indexer)
            readable = [_diff_row(row, old_side, new_side, max_lines) for row in selected]
        finally:
            if work:
                work.cleanup()
    return {"schema_version": 1, "mode": "RESEARCH_DIFF", "label": STATIC, "status": status, "old": _describe(old_jars, old_table), "new": _describe(new_jars, new_table),
            "classes_filter": list(terms), "limits": {"max_methods": max_methods, "max_lines": max_lines},
            "decompiler": {"vineflower": toolchain.vineflower_version, "jdk": toolchain.jdk} if toolchain else None,
            "bytecode": {"classes_compared": verdict["classes_compared"], "added_classes": verdict["added_classes"], "removed_classes": verdict["removed_classes"],
                         "methods_changed": sum(r["change"] == "changed" for r in verdict["methods"]), "methods_added": sum(r["change"] == "added" for r in verdict["methods"]),
                         "methods_removed": sum(r["change"] == "removed" for r in verdict["methods"]),
                         "classes_with_method_changes": len({r["class"] for r in verdict["methods"]})},
            "shown": len(readable), "not_shown": len(verdict["methods"]) - len(readable), "methods": readable, "notes": notes,
            "note": "bytecode decides which methods changed; the decompiled diff only explains it (a derived reading aid, STATIC, never evidence of runtime behaviour, never copied into a mod)"}


def _memoized(indexer):
    """The bytecode helper runs once per jar even though the comparison and the decompile step both ask for it."""
    seen: dict[Path, tuple] = {}

    def index(jar: Path) -> tuple:
        if jar not in seen:
            seen[jar] = indexer(jar)
        return seen[jar]
    return index


def _describe(jars: list[Path], table: dict[str, dict]) -> dict:
    return {"jars": [{"name": jar.name, "sha256": jar_sha256(jar)} for jar in jars], "classes": len(table)}


def render_markdown(result: dict) -> str:
    """Deterministic Markdown of a `build_diff` result."""
    bc = result["bytecode"]
    lines = ["# Research diff (STATIC)", "",
             f"Old: {', '.join(j['name'] for j in result['old']['jars'])} ({result['old']['classes']} classes). New: {', '.join(j['name'] for j in result['new']['jars'])} ({result['new']['classes']} classes).",
             f"Bytecode verdict ({bc['classes_compared']} class(es) on both sides compared): {bc['methods_changed']} method(s) changed, {bc['methods_added']} added, {bc['methods_removed']} removed, "
             f"in {bc['classes_with_method_changes']} class(es); {len(bc['added_classes'])} class(es) only in new, {len(bc['removed_classes'])} only in old.",
             f"Showing {result['shown']} method(s) (limits: {result['limits']['max_methods']} methods, {result['limits']['max_lines']} diff lines each); {result['not_shown']} not shown.",
             result["note"] + ".", ""]
    if result["decompiler"]:
        lines += [f"Decompiled with Vineflower {result['decompiler']['vineflower']}, JDK {result['decompiler']['jdk']}.", ""]
    lines += [f"- {note}" for note in result["notes"]] + ([""] if result["notes"] else [])
    for name, key in (("Classes only in new", "added_classes"), ("Classes only in old", "removed_classes")):
        if bc[key]:
            lines += [f"{name}: " + ", ".join(f"`{c}`" for c in bc[key][:MAX_LISTED_CLASSES]) + (f" and {len(bc[key]) - MAX_LISTED_CLASSES} more" if len(bc[key]) > MAX_LISTED_CLASSES else ""), ""]
    for row in result["methods"]:
        where = " ".join(f"{side} lines {span[0]}-{span[1]}" for side, span in (("old", row["old_lines"]), ("new", row["new_lines"])) if span)
        lines += [f"## `{row['id']}`", "", f"Bytecode: {row['change']} ({row['label']}). Readable diff: {row['status']}" + (f" ({where})" if where else "") + (f"; {row['why']}" if row["why"] else "") + ".", ""]
        if row["diff"]:
            lines += ["```diff"] + row["diff"] + (["... " + f"{row['truncated']} more diff line(s) not shown"] if row["truncated"] else []) + ["```", ""]
    return "\n".join(lines).rstrip() + "\n"


def stdout_summary(result: dict, written: list[str]) -> str:
    bc = result["bytecode"]
    shown = {}
    for row in result["methods"]:
        shown[row["status"]] = shown.get(row["status"], 0) + 1
    out = [f"research diff (STATIC, {result['status']}): bytecode {bc['methods_changed']} changed / {bc['methods_added']} added / {bc['methods_removed']} removed method(s) in "
           f"{bc['classes_with_method_changes']} class(es); {len(bc['added_classes'])} class(es) only in new, {len(bc['removed_classes'])} only in old",
           f"  shown {result['shown']} (not shown {result['not_shown']}): " + (", ".join(f"{k} {v}" for k, v in sorted(shown.items())) or "none")]
    return "\n".join(out + [f"  wrote {path}" for path in written])
