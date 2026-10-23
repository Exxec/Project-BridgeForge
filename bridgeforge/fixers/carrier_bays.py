from __future__ import annotations
import csv
import io
import re
from pathlib import Path
from .common import FileChange, FixerError, _decode, _encode, _field_value, _line_field_spans, _quote_like, _split_terminator


# ---------------------------------------------------------------------------
# Fixer: carrier-bays-proposal
# ---------------------------------------------------------------------------

# RC8's own ship_data.csv (starsector-core/data/hulls/ship_data.csv, read 2026-09-15): the highest
# "fighter bays" value any vanilla hull carries is 6 (the Astral, RC8's dedicated fleet carrier;
# the Legion and both carrier hull-mod modules are 4). Nothing in vanilla goes higher, so a --hull
# value above this is refused rather than guessed at.
_MAX_FIGHTER_BAYS = 6


def _parse_hull_bay_assignments(raw: list[str]) -> dict[str, int]:
    if not raw:
        raise FixerError("--hull ID=N is required (repeatable) for carrier-bays-proposal.")
    assignments: dict[str, int] = {}
    for item in raw:
        hull_id, sep, value = item.strip().rpartition("=")
        if not sep:
            raise FixerError(f"--hull must be ID=N (got '{item}').")
        hull_id = hull_id.strip()
        value = value.strip()
        if not hull_id:
            raise FixerError(f"--hull '{item}' has no hull id.")
        if not re.fullmatch(r"-?\d+", value):
            raise FixerError(f"--hull {hull_id}=... value must be an integer (got '{value}').")
        count = int(value)
        if not 0 <= count <= _MAX_FIGHTER_BAYS:
            raise FixerError(f"--hull {hull_id}={count}: fighter bays must be 0-{_MAX_FIGHTER_BAYS} (vanilla's own maximum, the Astral, RC8 ship_data.csv).")
        if hull_id in assignments and assignments[hull_id] != count:
            raise FixerError(f"--hull {hull_id} was given more than once with different values.")
        assignments[hull_id] = count
    return assignments


def _fix_carrier_bays_proposal(root: Path, options: dict) -> list[FileChange]:
    """Write approved `--hull ID=N` fighter-bay counts into ship_data.csv (roadmap P14 item 6).

    "fighter bays" is RC8's own ship_data.csv header name for the column (read from the core, see
    _MAX_FIGHTER_BAYS above). If the mod's file predates it (the pre-0.8 `hangar` schema), the
    column is appended the same way `wing-data-missing-role-desc-column` adds `role desc`: blank for
    every hull not named on the command line, so untouched rows keep their author's silence rather
    than an invented 0. Every --hull id must already exist as a ship_data.csv row (comment/blank-id
    rows don't count); an id this file has no row for is refused rather than silently skipped.
    """
    assignments = _parse_hull_bay_assignments(options.get("hulls") or []) if options.get("hulls") else {}
    if options.get("hull_zero_no_evidence"):
        # Hulls with a hangar value but no LAUNCH_BAY slot and no variant wings: 0 is what the data supports (see
        # scanner.carrier_bays_without_evidence). Explicit --hull values win.
        from ..scanner import carrier_bays_without_evidence

        vanilla_core = Path(options["vanilla_core"]).expanduser().resolve() if options.get("vanilla_core") else None
        for hull_id in carrier_bays_without_evidence(root, vanilla_core):
            assignments.setdefault(hull_id, 0)
        if not assignments:
            raise FixerError("--hull-zero-no-evidence: no hull has a hangar value without launch-bay slots or variant wings.")
    elif not assignments:
        raise FixerError("--hull ID=N is required (repeatable) for carrier-bays-proposal (or --hull-zero-no-evidence).")
    return _carrier_bays_edit(root, assignments)


def _fix_ship_data_missing_fighter_bays_column(root: Path, options: dict) -> list[FileChange]:
    """Add RC8's 'fighter bays' column to a pre-0.8a ship_data.csv, blank for every hull (P15, 2026-09-26).

    Behaviour-neutral: a hull without the column already loads with 0 bays, and a blank cell reads the
    same, so this only makes the schema current. Carriers still need their counts from
    `carrier-bays-proposal` (--hull ID=N), which is an owner decision.
    """
    path = root / "data" / "hulls" / "ship_data.csv"
    header = next(csv.reader(io.StringIO(_decode(path.read_bytes())[0])), []) if path.is_file() else []
    if "fighter bays" in [cell.strip().lower() for cell in header]:
        raise FixerError(f"{path} already has a 'fighter bays' column.")
    return _carrier_bays_edit(root, {})


def _carrier_bays_edit(root: Path, assignments: dict[str, int]) -> list[FileChange]:
    path = root / "data" / "hulls" / "ship_data.csv"
    if not path.is_file():
        raise FixerError(f"No ship_data.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise FixerError(f"{path} is empty.")
    # Same quoted-multiline-field guard as wing-data-missing-role-desc-column: refuse rather than
    # guess row boundaries if a quoted field spans lines.
    records = [row for row in csv.reader(io.StringIO(text)) if row]
    if len(records) != sum(1 for line in lines if line.strip()):
        raise FixerError(f"{path} has a quoted field spanning several lines; add fighter bays by hand rather than guess the row boundaries.")

    header_content, header_term = _split_terminator(lines[0])
    header_fields = [_field_value(item[2]) for item in _line_field_spans(header_content)]
    normalized_header = [cell.strip().lower() for cell in header_fields]
    if "id" not in normalized_header:
        raise FixerError(f"{path} has no 'id' column.")
    id_index = normalized_header.index("id")
    width = len(header_fields)
    add_column = "fighter bays" not in normalized_header
    bay_index = width if add_column else normalized_header.index("fighter bays")

    def row_hull_id(content: str) -> str:
        spans = _line_field_spans(content)
        return _field_value(spans[id_index][2]).strip() if id_index < len(spans) else ""

    existing_ids = {
        row_hull_id(_split_terminator(line)[0])
        for line in lines[1:] if _split_terminator(line)[0].strip()
    }
    existing_ids = {hull_id for hull_id in existing_ids if hull_id and not hull_id.startswith("#")}
    unknown = sorted(set(assignments) - existing_ids)
    if unknown:
        raise FixerError(f"{path} has no row for hull id(s): {', '.join(unknown)}.")

    edited_lines = [header_content + (",fighter bays" if add_column else "") + (header_term or "\n")]
    touched: set[str] = set()
    for line in lines[1:]:
        content, term = _split_terminator(line)
        if not content.strip():
            edited_lines.append(line)
            continue
        spans = _line_field_spans(content)
        hull_id = row_hull_id(content)
        present = len(spans)
        if hull_id in assignments and not hull_id.startswith("#"):
            count = assignments[hull_id]
            touched.add(hull_id)
            if add_column:
                padded = content + ("," * max(0, width - present))
                edited_lines.append(padded + "," + str(count) + term)
            elif present <= bay_index:
                padded = content + ("," * (bay_index - present + 1))
                pad_start, pad_end, _pad_raw = _line_field_spans(padded)[bay_index]
                edited_lines.append(padded[:pad_start] + str(count) + padded[pad_end:] + term)
            else:
                start, end, raw_field = spans[bay_index]
                edited_lines.append(content[:start] + _quote_like(raw_field, str(count)) + content[end:] + term)
        elif add_column:
            # Not an approved hull: pad so the new blank column still lands at the same position.
            edited_lines.append(content + ("," * max(0, width - present)) + "," + term)
        else:
            edited_lines.append(line)

    missed = sorted(set(assignments) - touched)
    if missed:
        raise FixerError(f"{path}: could not locate row(s) for hull id(s): {', '.join(missed)}.")
    return [FileChange(path=path, before=raw, after=_encode("".join(edited_lines), had_bom))]
