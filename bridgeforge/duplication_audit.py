"""94.G1 WP6: where the package re-implements what one canonical function already does (docs/FEATURE_GENOME_ROADMAP.md 14).

The suite-architecture review (2026-11-17) asked for an audit of duplicated save reading, mod identity, lenient JSON and
class indexing, as a report only: BridgeForge stays Salvor's save-diagnosis provider (D4) and no shared package is added.
A survey on 2026-11-19 mapped them by hand. This module turns that map into rules a test can run, so the count can only go
down: `tests/duplication_baseline.json` lists every function each rule finds, and `tests/test_duplication_audit.py` fails
on a new one (call the canonical function instead) and on a stale entry (the baseline shrinks with each consolidation).

The rules are mechanical and per function (AST, no imports run), so they are approximate by design: they find the shape
of each re-implementation, and the canonical function itself is listed so a reader sees what to call.

- `classfile-pool`: walks a class file's constant pool, i.e. compares `tag` against Long/Double (5, 6), the two-slot
  entries every pool walker must special-case. Canonical: `scan/scan_classfile.py::_parse_class_file_uncached`.
- `jar-class-walk`: lists a zip's entries (`namelist`/`infolist`) and picks `.class` ones, without writing a zip (a jar
  writer must walk every entry). Canonical: `scan/scan_classfile.py::iter_class_files_in_jars`.
- `mod-info-read`: names `mod_info.json` and parses it itself (`_load_lenient_json_file`, `_parse_json`, `json.loads`)
  instead of calling `mod_files.read_mod_info`. Canonical: `mod_files.py::read_mod_info`.
- `version-text`: joins a mod_info `{major, minor, patch}` version itself. Canonical: `corpus/corpus_releases.py::version_text`.
- `save-xml-read`: names `campaign.xml` or `descriptor.xml` and opens or parses it itself, or runs a module-level `*TAG*`
  regex over a save's lines (a tokenizer of its own). Canonical: `save/save_reader.py::parse_descriptor` and
  `save/save_reader.py::iter_elements`.
- `json-comment-strip`: handles both `#` and `//` comments itself, outside the lenient JSON reader. Canonical:
  `scan/scan_json.py::_parse_json_uncached`.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

RULES = {
    "classfile-pool": "scan/scan_classfile.py::_parse_class_file_uncached",
    "jar-class-walk": "scan/scan_classfile.py::iter_class_files_in_jars",
    "mod-info-read": "mod_files.py::read_mod_info",
    "version-text": "corpus/corpus_releases.py::version_text",
    "save-xml-read": "save/save_reader.py::parse_descriptor, save/save_reader.py::iter_elements",
    "json-comment-strip": "scan/scan_json.py::_parse_json_uncached",
}
_PARSERS = {"_load_lenient_json_file", "_parse_json", "loads"}
_OPENERS = {"open", "read_text", "read_bytes", "parse", "iterparse", "fromstring"}
_REGEX_CALLS = {"match", "search", "finditer", "fullmatch", "findall"}
SELF = "duplication_audit.py"  # its own rule strings would match its rules


def _strings(node: ast.AST) -> set[str]:
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _called(node: ast.AST) -> set[str]:
    names = set()
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        func = call.func
        names.add(func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else "")
    return names


def _two_slot_tags(element: ast.AST) -> bool:
    values = {e.value for e in getattr(element, "elts", []) if isinstance(e, ast.Constant)}
    names = {(e.id if isinstance(e, ast.Name) else e.attr if isinstance(e, ast.Attribute) else "").upper()
             for e in getattr(element, "elts", [])}
    return {5, 6} <= values or (any(n.endswith("LONG") for n in names) and any(n.endswith("DOUBLE") for n in names))


def _pool_walker(node: ast.AST) -> bool:
    for compare in (n for n in ast.walk(node) if isinstance(n, ast.Compare)):
        if isinstance(compare.left, ast.Name) and compare.left.id == "tag" and any(_two_slot_tags(c) for c in compare.comparators):
            return True
    return False


def _tag_tokenizer(node: ast.AST, module: str) -> bool:
    """A regex named like `_TAG` / `_TAG_PATTERN` applied in this function, in a module under save/ (a save tokenizer)."""
    if not module.startswith("save/"):
        return False
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in _REGEX_CALLS and isinstance(func.value, ast.Name) \
                and "TAG" in func.value.id.upper():
            return True
    return False


def _rules_hit(node: ast.AST, module: str = "") -> list[str]:
    strings, called = _strings(node), _called(node)
    hits = []
    if _pool_walker(node):
        hits.append("classfile-pool")
    if called & {"namelist", "infolist"} and any(s.endswith(".class") for s in strings) and not called & {"writestr", "write"}:
        hits.append("jar-class-walk")
    if "mod_info.json" in strings and called & _PARSERS and "read_mod_info" not in called:
        hits.append("mod-info-read")
    if {"major", "minor", "patch"} <= strings:
        hits.append("version-text")
    if (strings & {"campaign.xml", "descriptor.xml"} and called & _OPENERS) or _tag_tokenizer(node, module):
        hits.append("save-xml-read")
    if {"#", "//"} <= strings:
        hits.append("json-comment-strip")
    return hits


def _functions(tree: ast.AST):
    """(qualified name, node) for every function, innermost first wins: a hit is credited to the innermost function only."""
    def walk(node: ast.AST, prefix: str):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                if not isinstance(child, ast.ClassDef):
                    yield name, child
                yield from walk(child, name + ".")
            else:
                yield from walk(child, prefix)
    yield from walk(tree, "")


def audit(package: Path) -> dict[str, list[str]]:
    """{rule: sorted ["relative/path.py::function", ...]} over every module of `package`."""
    found: dict[str, set[str]] = {rule: set() for rule in RULES}
    for path in sorted(Path(package).rglob("*.py")):
        relative = path.relative_to(package).as_posix()
        if relative == SELF:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = list(_functions(tree))
        inner = {id(n): {id(m) for _, m in functions if m is not n and any(m is x for x in ast.walk(n))} for _, n in functions}
        by_id = {id(n): n for _, n in functions}
        for name, node in functions:
            hits = set(_rules_hit(node, relative))
            for nested in inner[id(node)]:  # credited to the nested function, not again to this one
                hits -= set(_rules_hit(by_id[nested], relative))
            for rule in hits:
                found[rule].add(f"{relative}::{name}")
    return {rule: sorted(names) for rule, names in found.items()}


def report(found: dict[str, list[str]]) -> str:
    lines = []
    for rule, names in found.items():
        canonical = RULES[rule]
        others = [n for n in names if n not in canonical.split(", ")]
        lines.append(f"{rule}: {len(others)} re-implementation(s) besides {canonical}")
        lines += [f"  {name}" for name in others]
    return "\n".join(lines)


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("duplication-audit", help="where the package re-implements class indexing, mod identity, "
                                                               "save reading or lenient JSON instead of calling the canonical "
                                                               "function (94.G1 WP6); read-only")
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    found = audit(Path(__file__).resolve().parent)
    print(json.dumps(found, indent=2) if args.json else report(found))
    return 0


if __name__ == "__main__":
    sys.exit(run_cli(argparse.Namespace(json="--json" in sys.argv)))
