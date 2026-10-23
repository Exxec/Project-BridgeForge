"""Fixer: preset-entry-drops-vanilla-fields (ROADMAP item 73, B4).

engine_styles.json, hull_styles.json, custom_entities.json and planets.json merge by whole-entry replace, so a mod entry
keyed like a vanilla entry drops every field vanilla's current copy has and the mod's lacks, game-wide (Zorg18's old
engine-style template, 2026-09-20). A missing field may be intentional, so nothing is restored from the finding alone
(ROADMAP item 75 R4): the fixer adds back only the fields named in `options["approved_fields"]` (records of exactly
file, entry, field, file_sha256, produced by an approved `value-proposals` row), with RC8's value, and keeps every value
the mod wrote and every unapproved omission. `preset_field_proposals` gives the three-way evidence (old vanilla, mod, RC8)
a person reviews. Text is edited in place: indentation, comments, key order, line endings and BOM survive.

Refused: no `vanilla_core` option; no approval; an approval record with an unknown or missing key; a file changed since the
approval (stale); `sounds.json` (nested categories); a field RC8 lacks; an entry the text scanner cannot place.
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
    from .. import fixers as _f

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


_APPROVAL_KEYS = frozenset({"file", "entry", "field", "file_sha256"})


def file_sha256(path: Path) -> str | None:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def preset_field_proposals(root: Path, vanilla_core: Path, old_core: Path | None = None) -> list[dict]:
    """One row per top-level vanilla field a mod entry lacks, with three-way evidence (R4): the old vanilla copy the mod was
    written against (`old_core`, optional), the mod's entry, and RC8's. A field old vanilla lacked too is a stale template
    (RC8 added it later); a field old vanilla had and the mod removed may be deliberate. Reads only; nothing is modified."""
    from bridgeforge.scan.scan_json import _load_lenient_json_file
    from bridgeforge.scan.scan_shadowing import PRESET_MERGE_FILES

    rows = []
    for name in PRESET_MERGE_FILES:
        if name in _REFUSED_FILES:
            continue
        relative = f"data/config/{name}"
        mod_data, vanilla_data = _load_lenient_json_file(root / relative), _load_lenient_json_file(Path(vanilla_core) / relative)
        old_data = _load_lenient_json_file(Path(old_core) / relative) if old_core else None
        if not (isinstance(mod_data, dict) and isinstance(vanilla_data, dict)):
            continue
        sha = file_sha256(root / relative) or ""
        for key in sorted(set(mod_data) & set(vanilla_data)):
            mod_entry, vanilla_entry = mod_data[key], vanilla_data[key]
            if not (isinstance(mod_entry, dict) and isinstance(vanilla_entry, dict)):
                continue
            old_entry = old_data.get(key) if isinstance(old_data, dict) else None
            for field, value in vanilla_entry.items():
                if field in mod_entry:
                    continue
                if old_core is None:
                    state, old_value = "unknown: no old-vanilla reference given", None
                elif not isinstance(old_entry, dict):
                    state, old_value = "old vanilla has no such entry", None
                elif field in old_entry:
                    state, old_value = "old vanilla HAD this field: the mod removed it (possibly deliberate)", old_entry[field]
                else:
                    state, old_value = "old vanilla lacked it too: RC8 added it after the mod's template (likely stale)", None
                rows.append({"file": relative, "entry": key, "field": field, "rc8_value": json.dumps(value), "old_state": state,
                             "old_value": "" if old_value is None else json.dumps(old_value), "file_sha256": sha})
    return rows


def _approved_fields(raw, root: Path) -> dict[str, dict[str, set[str]]]:
    """{file: {entry: {fields}}} from the approval records; unknown keys, a missing key or a changed file are refusals."""
    from .. import fixers as _f

    if not raw:
        raise _f.FixerError("preset-entry-drops-vanilla-fields restores nothing without field-specific approval: a missing field may be "
                            "intentional. Write a `value-proposals` sheet, approve the fields, and apply it.")
    approved: dict[str, dict[str, set[str]]] = {}
    for record in raw:
        if not isinstance(record, dict) or set(record) != _APPROVAL_KEYS:
            raise _f.FixerError(f"approval record {record!r} must have exactly the keys {sorted(_APPROVAL_KEYS)}; unknown fields are refused, not ignored.")
        current = file_sha256(root / record["file"])
        if current is None or current != record["file_sha256"]:
            raise _f.FixerError(f"stale approval for {record['file']} {record['entry']}.{record['field']}: the file changed since it was approved; "
                                "write the sheet again.")
        approved.setdefault(record["file"], {}).setdefault(record["entry"], set()).add(record["field"])
    return approved


def _fix_preset_entry_drops_vanilla_fields(root: Path, options: dict) -> list:
    from .. import fixers as _f
    from ..build_tag import _structural_depths
    from bridgeforge.scan.scan_json import _load_lenient_json_file
    from bridgeforge.scan.scan_shadowing import PRESET_MERGE_FILES

    core = options.get("vanilla_core")
    if not core:
        raise _f.FixerError("preset-entry-drops-vanilla-fields needs --vanilla-core: the restored values are RC8's.")
    approved = _approved_fields(options.get("approved_fields"), root)
    changes, refused = [], []
    for relative, entries in sorted(approved.items()):
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
        for key, fields in sorted(entries.items()):
            mod_entry, vanilla_entry = mod_data.get(key), vanilla_data.get(key)
            if not (isinstance(mod_entry, dict) and isinstance(vanilla_entry, dict)):
                refused.append(f"{relative} ({key}: not an entry in both the mod and RC8)")
                continue
            absent_in_rc8 = sorted(f for f in fields if f not in vanilla_entry)
            if absent_in_rc8:
                refused.append(f"{relative} ({key}: RC8 has no field {', '.join(absent_in_rc8)})")
            # Only approved fields, in RC8's order; every other missing field stays as the mod wrote it.
            missing = {k: v for k, v in vanilla_entry.items() if k in fields and k not in mod_entry}
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
        _verify(new_text, mod_data, entries, vanilla_data, relative)
        changes.append(_f.FileChange(path=path, before=raw, after=_f._encode(new_text, had_bom)))
    if not changes:
        raise _f.FixerError("No approved top-level field could be restored" + (f" (refused: {'; '.join(refused[:5])})" if refused else "") + ".")
    return changes


def _verify(new_text: str, mod_data: dict, entries: dict[str, set[str]], vanilla_data: dict, relative: str) -> None:
    """The edited text parses, keeps every mod value, and has exactly the approved fields added (no other new field)."""
    from .. import fixers as _f
    from bridgeforge.scan.scan_json import _parse_json

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
        added = set(entry) - set(mod_entry)
        allowed = {f for f in entries.get(key, set()) if f in (vanilla_data.get(key) or {})}
        if not added <= allowed:
            raise _f.FixerError(f"{relative}: '{key}' gained an unapproved field ({', '.join(sorted(added - allowed))}); nothing written.")
        if any(entry.get(f) != vanilla_data[key][f] for f in added):
            raise _f.FixerError(f"{relative}: '{key}' has a restored value that differs from RC8's; nothing written.")
