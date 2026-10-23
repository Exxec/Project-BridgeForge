from __future__ import annotations
import json
from pathlib import Path
from ..scanner import _parse_json
from .common import FileChange, FixerError, _decode, _encode, _findings_of


class _ObjectScan:
    """Index-based reader of lenient (org.json style) JSON that records every object's entries as
    (key, key_start, value_start, value_end), so a repeated key can be cut out by its exact text span."""

    def __init__(self, text: str) -> None:
        self.t = text
        self.n = len(text)
        self.objects: list[tuple[int, list[tuple[str, int, int, int]]]] = []
        self.in_array: set[int] = set()

    def ws(self, i: int) -> int:
        t = self.t
        while i < self.n:
            c = t[i]
            if c in " \t\r\n﻿":
                i += 1
            elif c == "#" or t.startswith("//", i):
                j = t.find("\n", i)
                i = self.n if j < 0 else j
            elif t.startswith("/*", i):
                j = t.find("*/", i + 2)
                i = self.n if j < 0 else j + 2
            else:
                break
        return i

    def string(self, i: int) -> int:
        quote = self.t[i]
        i += 1
        while i < self.n:
            c = self.t[i]
            if c == "\\":
                i += 2
                continue
            if c == quote:
                return i + 1
            i += 1
        raise ValueError("unterminated string")

    def value(self, i: int) -> int:
        i = self.ws(i)
        if i >= self.n:
            raise ValueError("value expected")
        c = self.t[i]
        if c == "{":
            return self.obj(i)
        if c == "[":
            return self.arr(i)
        if c in "\"'":
            return self.string(i)
        while i < self.n and self.t[i] not in ",;}]\n#" and not self.t.startswith("//", i):
            i += 1
        while self.t[i - 1] in " \t\r":
            i -= 1
        return i

    def arr(self, i: int) -> int:
        i += 1
        while True:
            i = self.ws(i)
            if i >= self.n:
                raise ValueError("unterminated array")
            if self.t[i] == "]":
                return i + 1
            if self.t[i] in ",;":
                i += 1
                continue
            if self.t[i] == "{":
                self.in_array.add(i)
            i = self.value(i)

    def obj(self, i: int) -> int:
        entries: list[tuple[str, int, int, int]] = []
        obj_start = i
        i += 1
        while True:
            i = self.ws(i)
            if i >= self.n:
                raise ValueError("unterminated object")
            c = self.t[i]
            if c == "}":
                self.objects.append((obj_start, entries))
                return i + 1
            if c in ",;":
                i += 1
                continue
            key_start = i
            if c in "\"'":
                key_end = self.string(i)
                key = self.t[key_start + 1:key_end - 1]
            else:
                key_end = key_start
                while key_end < self.n and (self.t[key_end].isalnum() or self.t[key_end] in "_.-$"):
                    key_end += 1
                if key_end == key_start:
                    raise ValueError("key expected")
                key = self.t[key_start:key_end]
            i = self.ws(key_end)
            if i >= self.n or self.t[i] not in ":=":
                raise ValueError("':' expected")
            value_start = self.ws(i + 1)
            value_end = self.value(value_start)
            entries.append((key, key_start, value_start, value_end))
            i = value_end


def _repeated_key_edits(text: str) -> tuple[list[tuple[int, int, str]], list[str]]:
    """Edits (begin, end, replacement) that clear repeated keys, and the keys left alone.

    - A later copy of a key whose value equals the first copy's is removed.
    - An object inside an array whose keys repeat as whole blocks in the same order (Arthr's Ships n Shit
      ass_solace.json: two markets without the `},{` between them) is several objects: a separator is inserted
      before each later block.
    Anything else (a repeat with a different value) is left for the owner."""
    from ..scanner import _parse_json

    scan = _ObjectScan(text)
    scan.value(scan.ws(0))

    def parsed(fragment: str):
        try:
            return _parse_json(fragment)[0]
        except (json.JSONDecodeError, ValueError):
            return fragment.strip()

    edits: list[tuple[int, int, str]] = []
    differing: list[str] = []
    for obj_start, entries in scan.objects:
        keys = [entry[0] for entry in entries]
        if len(set(keys)) == len(keys):
            continue
        starts = [i for i, key in enumerate(keys) if i and key == keys[0]]
        blocks = [keys[a:b] for a, b in zip([0, *starts], [*starts, len(keys)])]
        identical_values = all(
            parsed(text[e[2]:e[3]]) == parsed(text[entries[j][2]:entries[j][3]])
            for block_start in starts for j, e in enumerate(entries[block_start:block_start + len(blocks[0])]))
        if (starts and obj_start in scan.in_array and all(block == blocks[0] for block in blocks) and len(blocks[0]) >= 2
                and not identical_values):
            for block_start in starts:
                previous_end = entries[block_start - 1][3]
                key_start = entries[block_start][1]
                between = text[previous_end:key_start]
                edits.append((previous_end, key_start, "\n\t\t},\n\t\t{" + between.replace(",", "", 1)))
            continue
        first: dict[str, tuple[int, int]] = {}
        for key, key_start, value_start, value_end in entries:
            if key not in first:
                first[key] = (value_start, value_end)
                continue
            f_start, f_end = first[key]
            if parsed(text[f_start:f_end]) != parsed(text[value_start:value_end]):
                differing.append(key)
                continue
            begin = key_start
            while begin > 0 and text[begin - 1] in " \t":
                begin -= 1
            at_line_start = begin == 0 or text[begin - 1] == "\n"
            end = value_end
            while end < len(text) and text[end] in " \t":
                end += 1
            if end < len(text) and text[end] in ",;":
                end += 1
                while end < len(text) and text[end] in " \t\r":
                    end += 1
                if at_line_start and end < len(text) and text[end] == "\n":
                    end += 1
            elif not at_line_start:
                begin = key_start
            edits.append((begin, end, ""))
    edits.sort()
    kept: list[tuple[int, int, str]] = []
    for edit in edits:
        if kept and edit[0] < kept[-1][1]:
            continue
        kept.append(edit)
    return kept, differing


def _fix_json_duplicate_key(root: Path, options: dict) -> list[FileChange]:
    """Remove a later copy of a key repeated inside one JSON object when its value equals the first copy's (RC8's
    org.json stops at startup on any repeat: Ironclads pirates.faction, GRP10E-20261005). A repeat with a different
    value is left for the owner: which copy the mod meant is not decidable here."""
    from ..scanner import _json_duplicate_keys

    files = sorted({f.file for f in _findings_of(root, options, "json-duplicate-key") if f.file})
    if not files:
        raise FixerError("No json-duplicate-key finding for this mod.")
    changes, left = [], []
    for relative in files:
        path = root / relative
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        try:
            edits, differing = _repeated_key_edits(text)
        except (ValueError, IndexError):
            left.append(f"{relative} (could not locate the repeated key)")
            continue
        if differing:
            left.append(f"{relative}: {', '.join(sorted(set(differing)))} repeated with a different value")
        if not edits:
            continue
        new_text = text
        for begin, end, replacement in reversed(edits):
            new_text = new_text[:begin] + replacement + new_text[end:]
        left_repeats = _json_duplicate_keys(new_text)
        if len(left_repeats) != len(differing):
            left.append(f"{relative} (the edit left {len(left_repeats)} repeat(s), expected {len(differing)})")
            continue
        try:
            _parse_json(new_text)
        except json.JSONDecodeError as exc:
            left.append(f"{relative} (the edit no longer parses: {exc.msg})")
            continue
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("Nothing removed: " + "; ".join(left or ["no identical repeat found"]))
    return changes
