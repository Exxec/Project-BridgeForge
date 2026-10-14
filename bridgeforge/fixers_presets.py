"""Fixer: preset-entry-drops-vanilla-fields (ROADMAP item 73, B4).

engine_styles.json, hull_styles.json, custom_entities.json and planets.json merge by whole-entry replace, so a mod entry
keyed like a vanilla entry drops every field vanilla's current copy has and the mod's lacks, game-wide (Zorg18's old
engine-style template, 2026-09-20). This fixer adds each missing top-level field back with RC8's value and keeps every
value the mod wrote. Text is edited in place: indentation, comments, key order, line endings and BOM survive.

Refused: no `vanilla_core` option; `sounds.json` (nested categories); an entry whose loss is inside a nested object
(only top-level fields are restored); an entry the text scanner cannot place.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# Helpers are imported at call time (`from . import fixers as _f`): fixers.py imports this module.

_REFUSED_FILES = ("sounds.json",)


def _object_bounds(text: str, open_index: int) -> tuple[int, int] | None:
    """(closing brace index, index of the last code character before it) for the object opened at `open_index`."""
    depth, last_code, i, n = 0, open_index, open_index, len(text)
    while i < n:
        char = text[i]
        if char in "\"'":
            quote, i = char, i + 1
            while i < n and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            last_code = i
        elif char == "#" or (char == "/" and text[i + 1:i + 2] == "/"):
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        elif char in "{[":
            depth += 1
            last_code = i
        elif char in "}]":
            depth -= 1
            if depth == 0:
                return i, last_code
            last_code = i
        elif not char.isspace():
            last_code = i
        i += 1
    return None


def _line_end(text: str, index: int) -> int:
    for position in range(index, len(text)):
        if text[position] in "\r\n":
            return position
    return len(text)


def _entry_edits(text: str, key: str, missing: dict[str, object], depths: list[int]) -> list[tuple[int, str]] | None:
    """Insertions (position, text) that add `missing` to the top-level entry `key`, or None when it cannot be placed."""
    from . import fixers as _f

    pattern = re.compile(r"(?P<key>[\"']" + re.escape(key) + r"[\"'])\s*:\s*\{")
    match = _f._find_top_level_key(text, pattern, depths)
    if match is None:
        return None
    bounds = _object_bounds(text, match.end() - 1)
    if bounds is None:
        return None
    close, last_code = bounds
    eol = "\r\n" if "\r\n" in text else "\n"
    members = [f"{json.dumps(name)}: {json.dumps(value)}" for name, value in missing.items()]
    empty = last_code == match.end() - 1
    comma = "" if (empty or text[last_code] == ",") else ","
    body = text[match.end():close]
    if empty or ("\n" not in body and "\r" not in body):
        return [(last_code + 1, comma + ("" if empty else " ") + ", ".join(members))]
    first_code = re.search(r"\S", body)
    indent_source = match.end() + first_code.start()
    line_start = max(text.rfind("\n", 0, indent_source), text.rfind("\r", 0, indent_source)) + 1
    indent = re.match(r"[ \t]*", text[line_start:]).group(0)
    at = _line_end(text, last_code)
    if at > close:
        at = last_code + 1
    block = "".join(eol + indent + member + "," for member in members[:-1]) + eol + indent + members[-1]
    if at == last_code + 1:
        return [(at, comma + block)]
    return [(last_code + 1, comma), (at, block)] if comma else [(at, block)]


def _apply(text: str, edits: list[tuple[int, str]]) -> str:
    for position, addition in sorted(edits, key=lambda edit: edit[0], reverse=True):
        text = text[:position] + addition + text[position:]
    return text


def _fix_preset_entry_drops_vanilla_fields(root: Path, options: dict) -> list:
    from . import fixers as _f
    from .build_tag import _structural_depths
    from .scan_json import _load_lenient_json_file
    from .scan_shadowing import PRESET_MERGE_FILES

    core = options.get("vanilla_core")
    if not core:
        raise _f.FixerError("preset-entry-drops-vanilla-fields needs --vanilla-core: the missing fields' values are RC8's.")
    files = sorted({f.file for f in _f._findings_of(root, options, "preset-entry-drops-vanilla-fields") if f.file})
    if not files:
        raise _f.FixerError("No preset-entry-drops-vanilla-fields finding for this mod.")
    changes, refused = [], []
    for relative in files:
        name = Path(relative).name
        if name in _REFUSED_FILES or name not in PRESET_MERGE_FILES:
            refused.append(f"{relative} (nested categories; left to a person)")
            continue
        path, vanilla_path = root / relative, Path(core) / relative
        mod_data, vanilla_data = _load_lenient_json_file(path), _load_lenient_json_file(vanilla_path)
        if not (isinstance(mod_data, dict) and isinstance(vanilla_data, dict)):
            refused.append(f"{relative} (mod or vanilla file unreadable)")
            continue
        raw = path.read_bytes()
        text, had_bom = _f._decode(raw)
        depths = _structural_depths(text)
        edits: list[tuple[int, str]] = []
        for key in sorted(set(mod_data) & set(vanilla_data)):
            mod_entry, vanilla_entry = mod_data[key], vanilla_data[key]
            if not (isinstance(mod_entry, dict) and isinstance(vanilla_entry, dict)):
                continue
            missing = {k: v for k, v in vanilla_entry.items() if k not in mod_entry}
            if not missing:
                continue
            placed = _entry_edits(text, key, missing, depths)
            if placed is None:
                refused.append(f"{relative} ({key}: entry not found as a top-level object)")
                continue
            edits.extend(placed)
        if not edits:
            continue
        new_text = _apply(text, edits)
        _verify(new_text, mod_data, vanilla_data, relative)
        changes.append(_f.FileChange(path=path, before=raw, after=_f._encode(new_text, had_bom)))
    if not changes:
        raise _f.FixerError("No missing top-level vanilla field could be restored" + (f" (refused: {'; '.join(refused[:5])})" if refused else "") + ".")
    return changes


def _verify(new_text: str, mod_data: dict, vanilla_data: dict, relative: str) -> None:
    """The edited text parses, keeps every mod value, and now has every top-level vanilla field."""
    from . import fixers as _f
    from .scan_json import _parse_json

    try:
        parsed, _ = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise _f.FixerError(f"{relative}: the edited text no longer parses ({exc}); nothing written.") from exc
    for key, mod_entry in mod_data.items():
        entry = parsed.get(key) if isinstance(parsed, dict) else None
        if not isinstance(mod_entry, dict) or not isinstance(entry, dict):
            continue
        if any(entry.get(k) != v for k, v in mod_entry.items()):
            raise _f.FixerError(f"{relative}: '{key}' lost or changed one of the mod's own values; nothing written.")
        vanilla_entry = vanilla_data.get(key)
        if isinstance(vanilla_entry, dict) and any(k not in entry for k in vanilla_entry):
            raise _f.FixerError(f"{relative}: '{key}' still lacks a vanilla field after the edit; nothing written.")
