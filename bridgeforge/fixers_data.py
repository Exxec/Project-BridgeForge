"""Data-row fixers (ROADMAP item 73). REVIEW tier: the values written are a proposal copied from a sibling row.

B6 `local-weapon-spec-unregistered`: a `.wpn` whose id has no row in the mod's `data/weapons/weapon_data.csv`. When the
`.wpn` is readable, every sprite it names exists (in the mod or RC8's core) and the CSV already registers another
weapon of the same mount `type` and `size` (the `.wpn`'s own fields, not the CSV's damage-type column), a row is
appended: `name` is the id, `id` the id, and every numeric cell plus the damage `type` cell is copied from the sibling
(preferring one with the same `specClass`). Strings that gate content (`tags`, `hints`, manufacturer, tooltip text) are
left blank. A `#` comment row above the new row lists every copied value, so a reader sees exactly what is a guess.
Real case: Valkyrians' `laserblaster.wpn` (2026-10-14 fixture from its `original/`).
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

_SPRITE_KEY = re.compile(r"Sprite$")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_WEAPON_CSV = "data/weapons/weapon_data.csv"
_ALWAYS_COPIED = ("type",)  # the damage type (KINETIC, ENERGY, ...): a blank one fails to load
_NEVER_COPIED = ("id", "name")


def _fixers():
    from . import fixers as _f

    return _f


def _read_wpn(path: Path):
    from .scanner import _parse_json

    try:
        data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _spec_key(data: dict) -> tuple[str, str]:
    return str(data.get("type") or "").upper(), str(data.get("size") or "").upper()


def _missing_sprites(data: dict, root: Path, vanilla_core: Path | None) -> list[str]:
    missing = []
    for key, value in data.items():
        if not _SPRITE_KEY.search(key) or not isinstance(value, str) or not value.strip():
            continue
        if not (root / value).is_file() and not (vanilla_core is not None and (vanilla_core / value).is_file()):
            missing.append(value)
    return missing


def _fix_local_weapon_spec_unregistered(root: Path, options: dict) -> list:
    _f = _fixers()
    csv_path = root / _WEAPON_CSV
    if not csv_path.is_file():
        raise _f.FixerError(f"local-weapon-spec-unregistered: {_WEAPON_CSV} does not exist; nothing to register the weapon in.")
    raw = csv_path.read_bytes()
    text, had_bom = _f._decode(raw)
    newline = "\r\n" if "\r\n" in text else "\n"
    rows = list(csv.reader(io.StringIO(text, newline="")))
    if not rows:
        raise _f.FixerError("local-weapon-spec-unregistered: weapon_data.csv is empty.")
    header = [cell.strip().lower() for cell in rows[0]]
    if "id" not in header:
        raise _f.FixerError("local-weapon-spec-unregistered: weapon_data.csv has no id column.")
    id_col = header.index("id")
    registered = {row[id_col].strip(): row for row in rows[1:] if len(row) > id_col and row[id_col].strip() and not (row[0].strip().startswith("#"))}
    vanilla_core = Path(options["vanilla_core"]) if options.get("vanilla_core") else None
    specs = {path.name: _read_wpn(root / path) for path in {Path(f.file) for f in _f._findings_of(root, options, "local-weapon-spec-unregistered") if f.file}}
    sibling_specs = _registered_specs(root, registered)
    additions, refused = [], []
    for finding in _f._findings_of(root, options, "local-weapon-spec-unregistered"):
        data = specs.get(Path(finding.file).name) if finding.file else None
        weapon = next((str(e)[len("weapon:"):] for e in finding.evidence or [] if str(e).startswith("weapon:")), "")
        if not weapon or weapon in registered or any(a[0] == weapon for a in additions):
            continue
        outcome = _row_for(weapon, data, root, vanilla_core, header, registered, sibling_specs)
        if isinstance(outcome, str):
            refused.append(f"{weapon}: {outcome}")
        else:
            additions.append((weapon, *outcome))
    if not additions:
        if refused:
            raise _f.FixerError("local-weapon-spec-unregistered: " + "; ".join(refused))
        return []
    body = text if text.endswith(("\n", "\r")) or not text else text + newline
    for weapon, sibling, copied, cells in additions:
        note = f"# BridgeForge proposal for {weapon}: copied from {sibling} ({', '.join(f'{k}={v}' for k, v in copied)}); review these values"
        body += _csv_line([note] + [""] * (len(header) - 1), newline) + _csv_line(cells, newline)
    return [_f.FileChange(path=csv_path, before=raw, after=_f._encode(body, had_bom))]


def _csv_line(cells: list[str], newline: str) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=newline).writerow(cells)
    return buffer.getvalue()


def _registered_specs(root: Path, registered: dict[str, list[str]]) -> dict[str, dict]:
    """Registered weapon id -> its parsed .wpn, for the ids whose spec is in this mod."""
    from .scan_campaign import _declared_spec_ids

    found = {}
    for identifier, path in _declared_spec_ids(root / "data" / "weapons", "*.wpn", "id").items():
        if identifier in registered:
            data = _read_wpn(path)
            if data is not None:
                found[identifier] = data
    return found


def _row_for(weapon, data, root, vanilla_core, header, registered, sibling_specs):
    """(sibling id, copied (column, value) pairs, row cells), or a refusal reason."""
    if data is None:
        return "the .wpn could not be read"
    kind, size = _spec_key(data)
    if not kind or not size:
        return "the .wpn names no type or size"
    missing = _missing_sprites(data, root, vanilla_core)
    if missing:
        return "sprite not found: " + ", ".join(missing[:3])
    spec_class = str(data.get("specClass") or "")
    candidates = [i for i, spec in sibling_specs.items() if _spec_key(spec) == (kind, size)]
    if not candidates:
        return f"no registered weapon of type {kind} and size {size} to copy values from"
    candidates.sort(key=lambda i: str(sibling_specs[i].get("specClass") or "") != spec_class)
    sibling = candidates[0]
    source = registered[sibling]
    cells, copied = [""] * len(header), []
    for column, name in enumerate(header):
        if name in _NEVER_COPIED or column >= len(source):
            continue
        value = source[column].strip()
        if value and (name in _ALWAYS_COPIED or _NUMBER.match(value)):
            cells[column] = value
            copied.append((name, value))
    cells[header.index("id")] = weapon
    if "name" in header:
        cells[header.index("name")] = weapon
    return sibling, copied, cells
