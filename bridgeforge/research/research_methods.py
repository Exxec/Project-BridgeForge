"""Method link (ROADMAP-3 82.8): which decompiled lines are which bytecode method, and back.

Vineflower (`--bytecode-source-mapping=1 --dump-code-lines=1`, archive output) writes, per decompiled class, the pairs
(original source line, decompiled line) into the zip entry's extra field (header id `FF`, version 1, little-endian shorts). The bytecode
helper behind `bytecode-inspect` gives every method's `LineNumberTable` lines. Joining the two puts each method's range in the decompiled
file under the identity `a/b/C#name descriptor` (the class is the internal name, as in `bytecode-inspect` and Atlas), so a finding made in readable code
points at the exact bytecode method and the other way round. A method the join cannot place (no line table, no mapped line, lines spread over
several decompiled methods) is UNMAPPED with the reason, never guessed. Everything here is STATIC: a derived reading aid, bytecode stays authoritative.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path

from ..bytecode import BytecodeUnavailable, inspect_bytecode
from ..safeio import atomic_write_json

MAPPED, UNMAPPED = "MAPPED", "UNMAPPED"
MAP_SCHEMA = 1
_EXTRA_ID = b"FF"
_EXTRA_VERSION = 1


def method_identity(class_name: str, name: str, descriptor: str) -> str:
    """`a/b/C#name descriptor`, e.g. `data/scripts/Foo#advance (F)V`; the class is the internal (slash) name."""
    return f"{class_name}#{name} {descriptor}"


def split_identity(identity: str) -> tuple[str, str, str]:
    """Inverse of `method_identity`; ValueError for text that is not an identity."""
    cls, sep, rest = identity.partition("#")
    name, space, descriptor = rest.partition(" ")
    if not (cls and sep and name and space and descriptor.startswith("(")):
        raise ValueError(f"not a method identity (expected 'a/b/C#name (descriptor)ret'): {identity!r}")
    return cls, name, descriptor


def parse_line_pairs(extra: bytes) -> list[tuple[int, int]] | None:
    """(original line, decompiled line) pairs from a Vineflower zip entry's extra field; None when the field is absent or of another version."""
    pos = 0
    while pos + 4 <= len(extra):
        header, size = extra[pos:pos + 2], struct.unpack_from("<H", extra, pos + 2)[0]
        body = extra[pos + 4:pos + 4 + size]
        pos += 4 + size
        if header != _EXTRA_ID:
            continue
        if not body or body[0] != _EXTRA_VERSION:
            return None
        count = (len(body) - 1) // 4
        values = struct.unpack_from(f"<{count * 2}H", body, 1)
        return [(values[i], values[i + 1]) for i in range(0, count * 2, 2)]
    return None


def jar_method_index(jar: Path, inspector=inspect_bytecode) -> tuple[dict[str, list[dict]] | None, str]:
    """({internal class name: [{name, descriptor, lines, body_digest}]}, "") from the bytecode helper, or (None, why it is unavailable). The one place tests replace."""
    try:
        result = inspector([jar])
    except (BytecodeUnavailable, OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {str(exc).strip()[:200]}"
    return {item["class_name"]: [{"name": m["name"], "descriptor": m["descriptor"], "lines": list(m.get("lines", [])), "body_digest": m.get("body_digest", "")}
                                 for m in item.get("method_details", [])] for item in result["classes"]}, ""


def resolve_methods(class_name: str, details: list[dict], pairs: list[tuple[int, int]], spans: list[tuple[int, int]]) -> list[dict]:
    """One row per bytecode method of `class_name`: its identity and decompiled line range (1-based, inclusive), or UNMAPPED with a reason.
    `spans` are the decompiled file's method bodies as 0-based (first, last) line indexes (`research_decompile.method_spans`)."""
    decompiled_for: dict[int, set[int]] = {}
    for original, new in pairs:
        decompiled_for.setdefault(original, set()).add(new)
    rows = []
    for method in sorted(details, key=lambda m: (m["name"], m["descriptor"])):
        row = {"id": method_identity(class_name, method["name"], method["descriptor"]), "status": UNMAPPED, "lines": None, "basis": "", "why": ""}
        if not method["lines"]:
            rows.append({**row, "why": "the bytecode method has no line-number table (abstract, synthetic or stripped)"})
            continue
        mapped = sorted({d for line in method["lines"] for d in decompiled_for.get(line, ())})
        if not mapped:
            rows.append({**row, "why": f"Vineflower mapped none of its {len(method['lines'])} source line(s)"})
            continue
        touched = sorted({i for line in mapped for i, (a, b) in enumerate(spans) if a + 1 <= line <= b + 1})
        if len(touched) > 1:
            rows.append({**row, "why": f"its lines fall in {len(touched)} different decompiled methods"})
        elif touched:
            a, b = spans[touched[0]]
            rows.append({**row, "status": MAPPED, "lines": [a + 1, b + 1], "basis": "method"})
        else:
            rows.append({**row, "status": MAPPED, "lines": [mapped[0], mapped[-1]], "basis": "lines"})
    return rows


def write_map(folder: Path, outer: str, pairs: list[tuple[int, int]], methods: list[dict], index_note: str) -> None:
    """`<outer>.lines.json` (what Vineflower said) and `<outer>.methods.json` (identity -> range), beside `<outer>.java`."""
    atomic_write_json(folder / f"{outer}.lines.json", {"schema_version": MAP_SCHEMA, "pairs": [list(p) for p in pairs], "label": "STATIC"})
    atomic_write_json(folder / f"{outer}.methods.json", {"schema_version": MAP_SCHEMA, "class": outer, "index": index_note or "ok", "methods": methods, "label": "STATIC"})


@dataclass(frozen=True)
class MethodMap:
    """Both-way lookup for one decompiled top-level class (its `$` inner classes are inside the same file)."""

    outer: str
    methods: tuple[dict, ...]
    index: str = "ok"

    @classmethod
    def load(cls, folder: Path, outer: str) -> MethodMap | None:
        try:
            data = json.loads((Path(folder) / f"{outer}.methods.json").read_text(encoding="utf-8"))
            return cls(outer, tuple(data["methods"]), str(data.get("index", "ok")))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def lines_for(self, identity: str) -> tuple[int, int] | None:
        """Decompiled (first, last) line of a method identity; None when unmapped or unknown."""
        for row in self.methods:
            if row["id"] == identity and row["status"] == MAPPED:
                return row["lines"][0], row["lines"][1]
        return None

    def status_of(self, identity: str) -> dict | None:
        return next((row for row in self.methods if row["id"] == identity), None)

    def identities_at(self, line: int) -> list[str]:
        """Identities whose range holds `line` (1-based), narrowest first; several when a method shares its body with its lambdas."""
        hits = [row for row in self.methods if row["status"] == MAPPED and row["lines"][0] <= line <= row["lines"][1]]
        return [row["id"] for row in sorted(hits, key=lambda r: (r["lines"][1] - r["lines"][0], r["id"]))]

    def identities_for_range(self, first: int, last: int) -> list[str]:
        """Identities placed exactly on the decompiled range (the method a quoted excerpt shows)."""
        return sorted(row["id"] for row in self.methods if row["status"] == MAPPED and row["lines"] == [first, last])


def lookup_line(cache: Path, jar_sha256: str, file: str, line: int) -> list[str]:
    """file:line -> identities, from the cache beside the decompiled output: `lookup_line(cache, sha, "data/scripts/Foo.java", 27)`."""
    outer = file[:-len(".java")] if file.endswith(".java") else file
    found = MethodMap.load(Path(cache) / jar_sha256, outer)
    return found.identities_at(line) if found else []


def lookup_identity(cache: Path, jar_sha256: str, identity: str) -> tuple[str, int, int] | None:
    """identity -> (decompiled file, first line, last line); the file is the top-level class's `.java` under `<cache>/<jar-sha256>/`."""
    try:
        outer = split_identity(identity)[0].split("$", 1)[0]
    except ValueError:
        return None
    found = MethodMap.load(Path(cache) / jar_sha256, outer)
    span = found.lines_for(identity) if found else None
    return (f"{outer}.java", span[0], span[1]) if span else None
