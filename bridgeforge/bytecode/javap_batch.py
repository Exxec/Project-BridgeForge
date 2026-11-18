"""One javap launch per jar, not one per class (ROADMAP-3 96.5 P1).

The settings-key and procgen-argument checks read a jar's classes with `javap -c -p -constants`. One launch per class was
40-77% of a scan's time (UAF: 252 launches, 52.8 of 68.6 s; measured 2026-11-17). javap takes many classes in one call and
prints each one's listing in turn:
- an optional `Compiled from "X.java"` line;
- the declaration at column 0, which names the class;
- the members, indented;
- `}` at column 0.

javap escapes control characters in constants and comments, so a string constant cannot fake those lines. A class it cannot
read goes to stderr and leaves no listing. Each listing split from one call equals that class's own call byte for byte
(JDK 25, checked 2026-11-17 on an inner class, an enum, a generic interface, a class without a SourceFile attribute, string
constants holding newlines and braces, and a missing class).

A listing names the class its file declares, which need not be the class asked for: an entry `p/Foo.class` whose bytes
declare `p.A` prints as `p.A`, with a warning on stderr (review 2026-11-17). One call per class still credited that listing
to `p/Foo.class`. So a batch's listings are used only when they name exactly the classes asked for, in order; any other
batch is read again one class at a time, which gives what the old loop gave. Nothing in a jar can then hide or replace
another class's listing.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from bridgeforge.zipsafe import javap_class_name

FLAGS = ("-c", "-p", "-constants")
# Windows limits a command line to 32,767 characters. Each argument is counted with a separating space and two quotes.
COMMAND_LINE_BUDGET = 30_000
_DECLARATION = re.compile(r"(?:^|\s)(?:class|interface)\s+([^\s<{]+)")


def listing_segments(output: str) -> list[tuple[str, str]]:
    """(declared class name, listing), in the order javap printed them, from one call over several classes."""
    segments: list[tuple[str, str]] = []
    current: list[str] = []
    name: str | None = None
    for line in output.splitlines(keepends=True):
        if name is None:
            if line.startswith("Compiled from "):
                current = [line]
                continue
            declaration = None if line[:1] in (" ", "\t") else _DECLARATION.search(line)
            if declaration is None:
                current = []  # not part of a listing
                continue
            name = declaration.group(1)
            current.append(line)
            continue
        current.append(line)
        if line.rstrip("\r\n") == "}":
            segments.append((name, "".join(current)))
            current, name = [], None
    return segments


def split_listings(output: str) -> dict[str, str]:
    """{declared class name: listing}; the first listing wins for a name printed twice."""
    listings: dict[str, str] = {}
    for name, text in listing_segments(output):
        listings.setdefault(name, text)
    return listings


def _chunks(names: list[str], budget: int) -> list[list[str]]:
    chunks: list[list[str]] = []
    chunk: list[str] = []
    size = 0
    for name in names:
        cost = len(name) + 3
        if chunk and size + cost > budget:
            chunks.append(chunk)
            chunk, size = [], 0
        chunk.append(name)
        size += cost
    if chunk:
        chunks.append(chunk)
    return chunks


def class_listings(javap: Path, jar: Path, entries: list[str]) -> dict[str, str]:
    """{entry: listing} for a jar's class entries, from as few javap launches as the command line allows.

    An entry whose name is not a plain binary name is left out (`zipsafe.javap_class_name`, ROADMAP-3 93.45). An entry javap
    could not read maps to "", as with one call per class. A name listed twice is read once."""
    names: dict[str, str] = {}
    for entry in entries:
        if (name := javap_class_name(entry)) is not None:
            names.setdefault(name, entry)
    fixed = [str(javap), *FLAGS, "-cp", str(jar)]

    def run(classes: list[str]) -> str:
        return subprocess.run([*fixed, *classes], capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    budget = COMMAND_LINE_BUDGET - sum(len(part) + 3 for part in fixed)
    listings: dict[str, str] = {}
    for chunk in _chunks(list(names), budget):
        segments = listing_segments(run(chunk))
        if [declared for declared, _ in segments] == chunk:
            listings.update(zip(chunk, (text for _, text in segments)))
        else:  # a class javap could not read, or a file declaring another class: one call each, as before P1
            listings.update((name, run([name])) for name in chunk)
    return {entry: listings.get(name, "") for name, entry in names.items()}
