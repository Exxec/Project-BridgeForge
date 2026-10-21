"""Mod Atlas census (ROADMAP-3 item 81): what each mod uses of the game API, how risky its saves are, which libraries it calls.

One read of a mod's loaded jars (class-file constant pools, via `atlas_classfile`) plus its loose Java (regex, comments
blanked) yields rows of (area, kind, symbol, count, example). `count` is the number of classes/files that reference the
symbol, not call frequency: the constant pool lists a member once per class. Everything is STATIC evidence: bytecode is
read, never run. Loose-script calls resolve only static calls and constants through an import (`Misc.getFactionMarkets(`);
an instance call such as `sector.addMessage(` has no type in text, so only its class import is counted.

Areas: `api` (com.fs.* classes/methods/fields, item 81.1), `save` (81.3, `atlas_census_save`), `lib` (81.4,
`atlas_census_libs`). Tables `census` and `census_deps` live in the atlas database (`atlas.SCHEMA`).
"""
from __future__ import annotations

import re
import struct
import zipfile
from pathlib import Path
from typing import NamedTuple

from .atlas_classfile import ClassFormatError, ClassInfo, _read_pool, parse_class
from .scanner import _blank_java_comments, _load_lenient_json_file, _loaded_mod_jars
from .zipsafe import MAX_CLASS_BYTES, read_limited

API_PREFIX = "com/fs/"
MAX_JAR_ENTRIES = 200_000
_IMPORT_RE = re.compile(r"^\s*import\s+(static\s+)?([\w.]+?)(\.\*)?\s*;", re.MULTILINE)
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_CONSTANT_RE = re.compile(r"[A-Z][A-Z0-9_]+")


class Row(NamedTuple):
    area: str
    kind: str  # class | method | field | key | risk | ...
    symbol: str
    count: int
    example: str


class Ref(NamedTuple):
    kind: str  # class | method | field
    owner: str  # internal name (a/b/C)
    name: str  # member name; "" for a class


class ClassRefs(NamedTuple):
    rel: str  # jar!entry
    name: str  # this class, internal
    refs: frozenset
    info: ClassInfo


def _class_ref_name(raw: str) -> str:
    name = raw.lstrip("[")
    return name[1:-1] if name.startswith("L") and name.endswith(";") else name


def class_refs(data: bytes) -> tuple[str, frozenset]:
    """This class's internal name and every Class/Fieldref/Methodref constant-pool reference."""
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise ClassFormatError("not a class file")
    try:
        pool, pos = _read_pool(data)
        this_idx = struct.unpack_from(">H", data, pos + 2)[0]
        refs = set()
        for tag, a, b in pool.entries.values():
            if tag == 7:
                name = _class_ref_name(pool.text(a))
                if "/" in name or len(name) > 1:
                    refs.add(Ref("class", name, ""))
            elif tag in (9, 10, 11) and b in pool.entries:
                owner = _class_ref_name(pool.class_name(a))
                refs.add(Ref("field" if tag == 9 else "method", owner, pool.text(pool.entries[b][1])))
        return pool.class_name(this_idx), frozenset(refs)
    except (struct.error, IndexError, KeyError) as exc:
        raise ClassFormatError(str(exc)) from exc


def read_jar_classes(root: Path, jar: Path, watch: frozenset[str]) -> list[ClassRefs]:
    rel_jar, out = jar.relative_to(root).as_posix(), []
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.endswith(".class")]
            if len(names) > MAX_JAR_ENTRIES:
                return out
            for entry in names:
                try:
                    data = read_limited(archive, entry, MAX_CLASS_BYTES)
                    this, refs = class_refs(data)
                    out.append(ClassRefs(f"{rel_jar}!{entry}", this, refs, parse_class(data, watch)))
                except (ClassFormatError, zipfile.BadZipFile, OSError, RuntimeError, EOFError):
                    continue
    except (zipfile.BadZipFile, OSError):
        pass
    return out


def dotted(internal: str) -> str:
    return internal.replace("/", ".")


def member_symbol(ref: Ref) -> str:
    return dotted(ref.owner) + (f".{ref.name}" if ref.name else "")


class Tally:
    """Counts one row per (area, kind, symbol): how many classes/files mention it, and the first place that did."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str], list] = {}

    def add(self, area: str, kind: str, symbol: str, example: str) -> None:
        entry = self.rows.setdefault((area, kind, symbol), [0, example])
        entry[0] += 1

    def result(self) -> list[Row]:
        return [Row(*key, count, example) for key, (count, example) in sorted(self.rows.items())]


# ---------------------------------------------------------------- loose java

class LooseFile(NamedTuple):
    rel: str
    text: str  # comments blanked
    package: str

    @property
    def imports(self) -> dict[str, str]:
        """simple name -> fully qualified name, for single-type (non-static, non-wildcard) imports."""
        return {m.group(2).rsplit(".", 1)[-1]: m.group(2) for m in _IMPORT_RE.finditer(self.text)
                if not m.group(1) and not m.group(3)}


def read_loose(root: Path) -> list[LooseFile]:
    data_dir = root / "data"
    out = []
    for path in sorted(data_dir.rglob("*.java")) if data_dir.is_dir() else []:
        try:
            text = _blank_java_comments(path.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            continue
        package = _PACKAGE_RE.search(text)
        out.append(LooseFile(path.relative_to(root).as_posix(), text, package.group(1) if package else ""))
    return out


def qualified_uses(item: LooseFile, simple: str) -> list[tuple[str, str]]:
    """(kind, member) for `Simple.member(` static calls and `Simple.CONSTANT` reads in a loose file."""
    seen, out = set(), []
    for match in re.finditer(r"\b" + re.escape(simple) + r"\.(\w+)(\s*\()?", item.text):
        name, is_call = match.group(1), bool(match.group(2))
        if name in seen or name == "class":
            continue
        seen.add(name)
        if is_call:
            out.append(("method", name))
        elif _CONSTANT_RE.fullmatch(name):
            out.append(("field", name))
    return out


# ---------------------------------------------------------------- API (81.1)

def api_from_jar(classes: list[ClassRefs], tally: Tally) -> None:
    for entry in classes:
        for ref in entry.refs:
            if ref.owner.startswith(API_PREFIX) and ref.name not in ("<init>", "<clinit>"):
                tally.add("api", ref.kind, member_symbol(ref), entry.rel)


def api_from_loose(files: list[LooseFile], tally: Tally) -> None:
    for item in files:
        for simple, full in item.imports.items():
            if not full.startswith("com.fs."):
                continue
            tally.add("api", "class", full, item.rel)
            for kind, name in qualified_uses(item, simple):
                tally.add("api", kind, f"{full}.{name}", item.rel)


# ---------------------------------------------------------------- driver

def declared_dependencies(root: Path) -> list[tuple[str, str, str]]:
    info = _load_lenient_json_file(root / "mod_info.json")
    deps = info.get("dependencies") if isinstance(info, dict) else None
    return [(str(dep.get("id") or ""), str(dep.get("name") or ""), str(dep.get("version") or ""))
            for dep in (deps if isinstance(deps, list) else []) if isinstance(dep, dict) and (dep.get("id") or dep.get("name"))]


def extract_census(root: Path) -> list[Row]:
    """All census rows for one mod folder (never executes anything from it)."""
    tally = Tally()
    classes: list[ClassRefs] = []
    for jar in _loaded_mod_jars(root):
        classes += read_jar_classes(root, jar, frozenset())
    loose = read_loose(root)
    api_from_jar(classes, tally)
    api_from_loose(loose, tally)
    return tally.result()
