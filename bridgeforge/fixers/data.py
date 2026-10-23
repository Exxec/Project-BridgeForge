"""Data-row fixers (ROADMAP item 73, revised 2026-10-18 by item 75 R4). REVIEW tier.

B6 `local-weapon-spec-unregistered`: a `.wpn` whose id has no row in the mod's `data/weapons/weapon_data.csv`.
Weapon numbers are balance, so a row is written only from evidence or an owner decision:

1. Exact evidenced row (preferred): another version of the same mod (`options["evidence_roots"]`, plus the workspace's
   own `original/` beside `working/`) registers this weapon id. When that version also ships the `.wpn`, its mount `type`
   and `size` must equal this one's. The row is mapped to this CSV's columns by header name; columns this CSV lacks are
   dropped, columns the source lacks stay blank. A `#` comment row records the source file.
2. Owner-approved proposal: `draft_weapon_row_proposals(root, out_dir)` writes `weapon-row-proposals.json` to a REPORTS
   folder (never the mod). Each entry carries a sibling-derived draft row, where every copied value came from, a
   fingerprint of the inputs (weapon_data.csv and the .wpn bytes) and `approved: false`. The owner edits `row` if
   needed and sets `approved: true`; the fixer then applies exactly that row, only while the fingerprint still matches.
   Same mount type and size is a hint for where to look, not balance evidence, so a draft is never applied unapproved.
3. Otherwise the fixer refuses and says how to draft.

`specClass` is not a name source: a draft's `name` is the weapon id, flagged `name_is_placeholder`. A weapon whose
sprites exist neither in the mod nor in RC8's core is refused. Fixture: Valkyrians' `original/` (2026-10-14).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

from ..safeio import atomic_write_json

_SPRITE_KEY = re.compile(r"Sprite$")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")
_WEAPON_CSV = "data/weapons/weapon_data.csv"
PROPOSALS_NAME = "weapon-row-proposals.json"
_ALWAYS_COPIED = ("type",)  # the damage type (KINETIC, ENERGY, ...): a blank one fails to load
_NEVER_COPIED = ("id", "name")


def _fixers():
    from .. import fixers as _f

    return _f


def _read_wpn(path: Path):
    from ..scanner import _parse_json

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


def _csv_rows(raw: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))


def _csv_line(cells: list[str], newline: str) -> str:
    buffer = io.StringIO()
    csv.writer(buffer, lineterminator=newline).writerow(cells)
    return buffer.getvalue()


def _fingerprint(csv_bytes: bytes, wpn_bytes: bytes) -> str:
    return hashlib.sha256(csv_bytes + b"\0" + wpn_bytes).hexdigest()


class _Context:
    """The mod's weapon CSV and the unregistered weapons the scan reported."""

    def __init__(self, root: Path, options: dict):
        _f = _fixers()
        self.root, self.options = root, options
        self.path = root / _WEAPON_CSV
        if not self.path.is_file():
            raise _f.FixerError(f"local-weapon-spec-unregistered: {_WEAPON_CSV} does not exist; nothing to register the weapon in.")
        self.raw = self.path.read_bytes()
        self.text, self.had_bom = _f._decode(self.raw)
        self.newline = "\r\n" if "\r\n" in self.text else "\n"
        rows = _csv_rows(self.raw)
        if not rows or "id" not in [c.strip().lower() for c in rows[0]]:
            raise _f.FixerError("local-weapon-spec-unregistered: weapon_data.csv has no id column.")
        self.header = [c.strip().lower() for c in rows[0]]
        self.id_col = self.header.index("id")
        self.registered = {r[self.id_col].strip(): r for r in rows[1:] if len(r) > self.id_col and r[self.id_col].strip() and not r[0].strip().startswith("#")}
        self.vanilla_core = Path(options["vanilla_core"]) if options.get("vanilla_core") else None
        self.unregistered: dict[str, Path] = {}
        for finding in _f._findings_of(root, options, "local-weapon-spec-unregistered"):
            weapon = next((str(e)[len("weapon:"):] for e in finding.evidence or [] if str(e).startswith("weapon:")), "")
            if weapon and weapon not in self.registered and finding.file:
                self.unregistered[weapon] = root / finding.file

    def fingerprint(self, wpn_path: Path) -> str:
        return _fingerprint(self.raw, wpn_path.read_bytes() if wpn_path.is_file() else b"")


def _evidence_roots(root: Path, options: dict) -> list[Path]:
    roots = [Path(p) for p in options.get("evidence_roots") or []]
    original = root.parent / "original"
    if original.is_dir():
        roots.append(original)
    return roots


def _exact_row(weapon: str, data: dict | None, ctx: _Context):
    """(row cells mapped to this CSV's header, source description) from another version of the mod, or None."""
    for base in _evidence_roots(ctx.root, ctx.options):
        for source_csv in sorted(base.rglob("weapon_data.csv"))[:20]:
            if source_csv.resolve() == ctx.path.resolve() or source_csv.parent.name != "weapons":
                continue
            try:
                rows = _csv_rows(source_csv.read_bytes())
            except (OSError, UnicodeDecodeError, csv.Error):
                continue
            if not rows or "id" not in [c.strip().lower() for c in rows[0]]:
                continue
            source_header = [c.strip().lower() for c in rows[0]]
            match = next((r for r in rows[1:] if len(r) > source_header.index("id") and not r[0].strip().startswith("#")
                          and r[source_header.index("id")].strip() == weapon), None)
            if match is None:
                continue
            twin = source_csv.parent / f"{weapon}.wpn"
            twin_data = _read_wpn(twin) if twin.is_file() else None
            if twin_data is not None and data is not None and _spec_key(twin_data) != _spec_key(data):
                continue  # same id, different weapon
            cells = [match[source_header.index(name)].strip() if name in source_header and source_header.index(name) < len(match) else "" for name in ctx.header]
            return cells, f"{source_csv}" + ("" if twin_data is not None else " (no .wpn there to compare type and size)")
    return None


def _approved_row(weapon: str, wpn_path: Path, ctx: _Context):
    """The owner-approved row for this weapon, ValueError text when it is stale or malformed, or None when none exists."""
    proposals = ctx.options.get("weapon_row_proposals")
    if proposals is None:
        return None
    if not isinstance(proposals, dict):
        proposals = json.loads(Path(proposals).read_text(encoding="utf-8"))
    entry = next((e for e in proposals.get("proposals", []) if e.get("weapon") == weapon and e.get("approved") is True), None)
    if entry is None:
        return None
    if entry.get("fingerprint") != ctx.fingerprint(wpn_path):
        return "the approved proposal is stale: weapon_data.csv or the .wpn changed since the draft; draft again and re-approve"
    row = entry.get("row")
    if not isinstance(row, list) or len(row) != len(ctx.header) or str(row[ctx.id_col]).strip() != weapon:
        return "the approved row does not match this CSV's columns or weapon id"
    return [str(c) for c in row], "owner-approved proposal"


def _fix_local_weapon_spec_unregistered(root: Path, options: dict) -> list:
    _f = _fixers()
    ctx = _Context(root, options)
    additions, refused = [], []
    for weapon, wpn_path in sorted(ctx.unregistered.items()):
        data = _read_wpn(wpn_path)
        if data is None:
            refused.append(f"{weapon}: the .wpn could not be read")
            continue
        missing = _missing_sprites(data, root, ctx.vanilla_core)
        if missing:
            refused.append(f"{weapon}: sprite not found: " + ", ".join(missing[:3]))
            continue
        found = _exact_row(weapon, data, ctx) or _approved_row(weapon, wpn_path, ctx)
        if found is None:
            refused.append(f"{weapon}: no exact row in another version and no owner-approved proposal; "
                           f"draft one with fixers_data.draft_weapon_row_proposals and have the owner approve it")
        elif isinstance(found, str):
            refused.append(f"{weapon}: {found}")
        else:
            additions.append((weapon, *found))
    if not additions:
        if refused:
            raise _f.FixerError("local-weapon-spec-unregistered: " + "; ".join(refused))
        return []
    body = ctx.text if ctx.text.endswith(("\n", "\r")) or not ctx.text else ctx.text + ctx.newline
    for weapon, cells, source in additions:
        note = f"# BridgeForge: row for {weapon} from {source}; review"
        body += _csv_line([note] + [""] * (len(ctx.header) - 1), ctx.newline) + _csv_line(cells, ctx.newline)
    return [_f.FileChange(path=ctx.path, before=ctx.raw, after=_f._encode(body, ctx.had_bom))]


def draft_weapon_row_proposals(root: Path, out_dir: Path, options: dict | None = None) -> Path:
    """Write `weapon-row-proposals.json` (reports only, never the mod) and return its path. Nothing is applied."""
    options = options or {}
    ctx = _Context(Path(root), options)
    from ..scan_campaign import _declared_spec_ids

    sibling_specs = {}
    for identifier, path in _declared_spec_ids(ctx.root / "data" / "weapons", "*.wpn", "id").items():
        spec = _read_wpn(path)
        if identifier in ctx.registered and spec is not None:
            sibling_specs[identifier] = spec
    entries = []
    for weapon, wpn_path in sorted(ctx.unregistered.items()):
        data = _read_wpn(wpn_path)
        entry = {"weapon": weapon, "file": str(wpn_path.relative_to(ctx.root)).replace("\\", "/"), "approved": False,
                 "fingerprint": ctx.fingerprint(wpn_path)}
        entries.append(entry)
        if data is None:
            entry["refused"] = "the .wpn could not be read"
            continue
        missing = _missing_sprites(data, ctx.root, ctx.vanilla_core)
        if missing:
            entry["refused"] = "sprite not found: " + ", ".join(missing[:3])
            continue
        exact = _exact_row(weapon, data, ctx)
        if exact is not None:
            entry["note"] = f"an exact row exists ({exact[1]}); the fixer applies it without a proposal"
            continue
        draft = _draft_from_sibling(weapon, data, ctx, sibling_specs)
        entry.update(draft)
    target = Path(out_dir) / PROPOSALS_NAME
    atomic_write_json(target, {"version": 1, "csv": _WEAPON_CSV, "header": ctx.header, "proposals": entries}, indent=2)
    return target


def _draft_from_sibling(weapon: str, data: dict, ctx: _Context, sibling_specs: dict[str, dict]) -> dict:
    kind, size = _spec_key(data)
    spec_class = str(data.get("specClass") or "")
    candidates = [i for i, spec in sibling_specs.items() if kind and size and _spec_key(spec) == (kind, size)]
    if not candidates:
        return {"refused": f"no registered weapon of type {kind or '?'} and size {size or '?'} to draw a comparison from"}
    candidates.sort(key=lambda i: str(sibling_specs[i].get("specClass") or "") != spec_class)
    sibling = candidates[0]
    source = ctx.registered[sibling]
    row, copied = [""] * len(ctx.header), []
    for column, name in enumerate(ctx.header):
        if name in _NEVER_COPIED or column >= len(source):
            continue
        value = source[column].strip()
        if value and (name in _ALWAYS_COPIED or _NUMBER.match(value)):
            row[column] = value
            copied.append({"column": name, "value": value, "source": f"{sibling} in {_WEAPON_CSV}"})
    row[ctx.id_col] = weapon
    if "name" in ctx.header:
        row[ctx.header.index("name")] = weapon
    return {
        "row": row, "copied": copied, "comparison": sibling, "name_is_placeholder": True,
        "evidence": "same mount type and size only; this is not balance evidence",
    }
