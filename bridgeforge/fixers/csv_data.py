from __future__ import annotations
import csv
import io
import json
import re
from pathlib import Path
from bridgeforge.scan.scanner import DESIGN_TYPE_CSV_TARGETS, _FULLWIDTH_NUMBER_CHARS, _NUMBER_CELL, _load_lenient_json_file, _parse_json, _read_csv_rows_lenient, _relative
from .common import FileChange, FixerError, _csv_escape, _csv_records, _decode, _encode, _findings_of, _line_field_spans, _parse_rgb, _split_terminator


# ---------------------------------------------------------------------------
# Fixer: csv-row-extra-columns
# ---------------------------------------------------------------------------


def _fix_csv_row_extra_columns(root: Path, options: dict) -> list[FileChange]:
    changes: list[FileChange] = []
    for path in sorted(root.rglob("*.csv")):
        try:
            raw = path.read_bytes()
            text, had_bom = _decode(raw)
        except (OSError, UnicodeDecodeError):
            continue
        records = _csv_records(text)
        if not records:
            continue
        header_start, header_end = records[0]
        header_content, _header_term = _split_terminator(text[header_start:header_end])
        try:
            header = next(csv.reader(io.StringIO(header_content)))
        except (csv.Error, StopIteration):
            continue
        if not header or not any(cell.strip() for cell in header):
            continue
        header_len = len(header)

        # A space before an opening quote (`SHIP, "text, with commas"`) stops the field being read as quoted: its
        # commas split it and its line breaks end the record early (SWP Triumphant's descriptions.csv, 2026-10-01).
        # Dropping that space everywhere, and only when every row then fits the header, restores the rows as authored.
        try:
            widths = [len(row) for row in csv.reader(io.StringIO(text))]
        except csv.Error:
            widths = []
        if any(width > header_len for width in widths[1:]):
            unspaced = re.sub(r'(^|,)[ \t]+"', r'\1"', text, flags=re.M)
            try:
                rewidths = [len(row) for row in csv.reader(io.StringIO(unspaced))]
            except csv.Error:
                rewidths = []
            if unspaced != text and rewidths and all(width <= header_len for width in rewidths[1:]):
                changes.append(FileChange(path=path, before=raw, after=_encode(unspaced, had_bom)))
                continue

        edits: list[tuple[int, int, str]] = []
        for rec_start, rec_end in records[1:]:
            record_text = text[rec_start:rec_end]
            content, term = _split_terminator(record_text)
            if not content.strip():
                continue
            try:
                fields = next(csv.reader(io.StringIO(content)))
            except (csv.Error, StopIteration):
                continue
            if len(fields) <= header_len:
                continue
            extras = fields[header_len:]
            # A space before an opening quote (`SHIP, "text, with commas"`) stops the field being read as quoted, so
            # its commas split it (SWP Triumphant's descriptions.csv, 2026-10-01). Dropping that space, and only
            # when the row then has exactly the header's width, restores the field as authored.
            unspaced = re.sub(r'(^|,)[ \t]+"', r'\1"', content)
            if unspaced != content:
                try:
                    respaced = next(csv.reader(io.StringIO(unspaced)))
                except (csv.Error, StopIteration):
                    respaced = []
                if len(respaced) == header_len:
                    edits.append((rec_start, rec_end, unspaced + term))
                    continue
            if any(value.strip() for value in extras):
                raise FixerError(
                    f"{_relative(root, path)}: a csv-row-extra-columns row has non-empty extra "
                    f"field(s) ({extras!r}); refusing to drop data."
                )
            spans = _line_field_spans(content)
            if header_len == 0 or header_len - 1 >= len(spans):
                continue
            cut_at = spans[header_len - 1][1]
            edits.append((rec_start, rec_end, content[:cut_at] + term))

        if not edits:
            continue
        new_text = text
        for rec_start, rec_end, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
            new_text = new_text[:rec_start] + replacement + new_text[rec_end:]
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))

    if not changes:
        raise FixerError("No csv-row-extra-columns rows with only empty extra fields were found to fix.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: csv-missing-design-type-column
# ---------------------------------------------------------------------------


def _fix_csv_missing_design_type_column(root: Path, options: dict) -> list[FileChange]:
    design_type = options.get("design_type")
    prefixes = options.get("id_prefixes") or []
    design_color = options.get("design_color")
    # Unattended (owner ruling 2026-09-30): add the column with every cell blank, as some vanilla rows are, so the
    # loader finds it; no design type is invented, so no settings.json colour is needed.
    blank = bool(options.get("blank_design_type"))
    if blank:
        design_type, prefixes = "", []
    elif not design_type:
        raise FixerError("--design-type is required for csv-missing-design-type-column.")
    if not blank and not prefixes:
        raise FixerError("At least one --id-prefix is required for csv-missing-design-type-column.")
    if not blank and not design_color:
        raise FixerError("--design-color R,G,B is required for csv-missing-design-type-column.")
    rgb = _parse_rgb(design_color) if not blank else None

    changes: list[FileChange] = []
    any_csv_fixed = False
    for parts in DESIGN_TYPE_CSV_TARGETS:
        path = root.joinpath(*parts)
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        lines = text.splitlines(keepends=True)
        if not lines:
            continue
        header_content, header_term = _split_terminator(lines[0])
        try:
            header_fields = next(csv.reader(io.StringIO(header_content)))
        except (csv.Error, StopIteration):
            continue
        normalized = [cell.strip().lower() for cell in header_fields]
        if any("tech" in cell or "manufacturer" in cell for cell in normalized):
            continue
        header_width = len(header_fields)

        new_lines = [header_content + "," + _csv_escape("tech/manufacturer") + header_term]
        for line in lines[1:]:
            content, term = _split_terminator(line)
            if not content.strip():
                new_lines.append(line)
                continue
            try:
                fields = next(csv.reader(io.StringIO(content)))
            except (csv.Error, StopIteration):
                new_lines.append(line)
                continue
            row_id = fields[0].strip() if fields else ""
            missing = header_width - len(fields)
            padded_content = content + ("," * missing if missing > 0 else "")
            value = design_type if any(row_id.startswith(prefix) for prefix in prefixes) else ""
            new_lines.append(padded_content + "," + _csv_escape(value) + term)

        new_text = "".join(new_lines)
        changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
        any_csv_fixed = True

    if not any_csv_fixed:
        raise FixerError("Neither ship_data.csv nor weapon_data.csv is missing a tech/manufacturer column.")

    settings_change = None if blank else _add_design_type_color(root / "data" / "config" / "settings.json", design_type, rgb)
    if settings_change is not None:
        changes.append(settings_change)
    return changes


def _add_design_type_color(path: Path, name: str, rgb: list[int]) -> FileChange | None:
    entry_text = f'"designTypeColors":{{"{name}":[{rgb[0]},{rgb[1]},{rgb[2]},255]}}'
    if not path.is_file():
        new_text = "{" + entry_text + "}\n"
        try:
            _parse_json(new_text)
        except json.JSONDecodeError as exc:
            raise FixerError(f"Generated {path} failed to parse: {exc}") from exc
        return FileChange(path=path, before=b"", after=new_text.encode("utf-8"), existed_before=False)

    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    data = _load_lenient_json_file(path)
    if isinstance(data, dict) and "designTypeColors" in data:
        return None
    brace_index = text.find("{")
    if brace_index == -1:
        raise FixerError(f"{path} has no '{{' to insert designTypeColors after.")
    new_text = text[: brace_index + 1] + entry_text + "," + text[brace_index + 1 :]
    try:
        parsed, _tolerances = _parse_json(new_text)
    except json.JSONDecodeError as exc:
        raise FixerError(f"Edited {path} failed to re-parse: {exc}") from exc
    if not isinstance(parsed, dict) or "designTypeColors" not in parsed:
        raise FixerError(f"Edited {path} did not round-trip designTypeColors as expected.")
    return FileChange(path=path, before=raw, after=_encode(new_text, had_bom))


def _fullwidth_cells(path: Path) -> dict[str, str]:
    """{raw cell: ASCII number} for every cell the scanner's csv-fullwidth-number check reports."""
    import unicodedata

    cells: dict[str, str] = {}
    for row in _read_csv_rows_lenient(path) or []:
        for value in row.values():
            if isinstance(value, str) and _FULLWIDTH_NUMBER_CHARS.search(value):
                normalised = unicodedata.normalize("NFKC", value.replace("。", ".")).strip()
                if _NUMBER_CELL.fullmatch(normalised):
                    cells[value] = normalised
    return cells


def _fix_csv_fullwidth_number(root: Path, options: dict) -> list[FileChange]:
    """Rewrite full-width numeric CSV cells ('１５００', '0。5') as the ASCII number they spell (P15, 2026-09-26).

    Only whole cells the scanner reports are touched, keeping their quoting; prose with Chinese
    punctuation is left alone because it doesn't normalise to a plain number. The value is the one
    the author wrote, so this is behaviour-neutral: the loader couldn't parse the original.
    """
    data = root / "data"
    changes: list[FileChange] = []
    for path in sorted(data.rglob("*.csv")) if data.is_dir() else []:
        cells = _fullwidth_cells(path)
        if not cells:
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new = text
        for value, number in cells.items():
            cell = re.compile(rf'(^|,)(")?{re.escape(value)}(?(2)")(?=,|\r|\n|$)', re.M)
            new = cell.sub(lambda m, number=number: m.group(1) + (m.group(2) or "") + number + (m.group(2) or ""), new)
            if cell.search(new) or new.count("\n") != text.count("\n"):
                raise FixerError(f"{path}: the full-width cell {value!r} could not be rewritten in place; fix it by hand.")
        if new == text:
            raise FixerError(f"{path}: the full-width cells sit inside multi-line or unusual quoting; fix them by hand.")
        changes.append(FileChange(path=path, before=raw, after=_encode(new, had_bom)))
    if not changes:
        raise FixerError("No CSV under data/ has a full-width numeric cell.")
    return changes


def _fix_rules_csv_duplicate_id(root: Path, options: dict) -> list[FileChange]:
    """Rename each later copy of a repeated rules.csv id to <id>_2, <id>_3 (RC8 'Duplicate key', Ironclads GRP10J-20261005),
    editing only the id cell so every other byte of the file stays."""
    from bridgeforge.scan.scanner import _csv_first_cells, _rules_duplicate_id_cells

    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        raise FixerError("No data/campaign/rules.csv in this mod.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    repeats = _rules_duplicate_id_cells(text)
    if not repeats:
        raise FixerError("No repeated rules.csv id found.")
    taken = {value.strip() for _s, _e, value, _q in _csv_first_cells(text)}
    renames = []
    for start, end, key, quoted, number in repeats:  # names in reading order, edits from the end so offsets hold
        while f"{key}_{number}" in taken:
            number += 1
        new_id = f"{key}_{number}"
        taken.add(new_id)
        renames.append((start, end, f'"{new_id}"' if quoted else new_id))
    new_text = text
    for start, end, replacement in reversed(renames):
        new_text = new_text[:start] + replacement + new_text[end:]
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


def _fix_rules_csv_whitespace_only_line(root: Path, options: dict) -> list[FileChange]:
    """Empty the whitespace-only lines of rules.csv conditions/script cells (RC8 'No tokens found in string: []', Ironclads
    GRP10K-20261005). Only those cells change; the rest of the file keeps its bytes."""
    from bridgeforge.scan.scanner import _rules_whitespace_only_line_cells

    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        raise FixerError("No data/campaign/rules.csv in this mod.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    cells = _rules_whitespace_only_line_cells(text)
    if not cells:
        raise FixerError("No whitespace-only line in a rules.csv conditions or script cell.")
    new_text = text
    for start, end, _name, value in reversed(cells):
        cell = '"' + value.replace('"', '""') + '"' if text[start] == '"' else value
        new_text = new_text[:start] + cell + new_text[end:]
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


def _fix_rules_csv_curly_quote_unreadable(root: Path, options: dict) -> list[FileChange]:
    """Change the curly double quotes of unreadable rules.csv text alternatives to straight ones (Metelson Industries,
    GRP4A-20261006). Only those cells change; the rest of the file keeps its bytes."""
    from bridgeforge.scan.scanner import _rules_curly_quote_cells

    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        raise FixerError("No data/campaign/rules.csv in this mod.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    cells = _rules_curly_quote_cells(text)
    if not cells:
        raise FixerError("No rules.csv text alternative holds an unreadable curly double quote.")
    new_text = text
    for start, end, value in reversed(cells):
        new_text = new_text[:start] + '"' + value.replace('"', '""') + '"' + new_text[end:]
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


def _fix_csv_vanilla_row_override(root: Path, options: dict) -> list[FileChange]:
    """Remove the rows of the mod's ship_data/weapon_data/wing_data whose id RC8 also defines, so RC8's own rows stand
    (Yellowjackets Mining Conglomerate, 2026-10-10: 12 hull and 3 weapon rows of 0.6-era values). Needs --vanilla-core. Tables
    the mod replaces in mod_info.json are left alone. Only those records change; the rest of each file keeps its bytes."""
    from .. import conversion_checks as cc

    vanilla_core = options.get("vanilla_core")
    if not vanilla_core:
        raise FixerError("--vanilla-core is required for csv-vanilla-row-override.")
    vanilla_core = Path(vanilla_core).expanduser().resolve()
    hits = cc.vanilla_row_overrides(root, vanilla_core)
    if not hits:
        raise FixerError("No row of the mod's ship, weapon or wing table repeats an id RC8 defines.")
    changes = []
    for table in sorted(hits):
        path = root / table
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        theirs, _bom = _decode((vanilla_core / table).read_bytes())
        vanilla_ids = {row_id for row_id, _s, _e, _c in cc._table_records(theirs) if row_id and not row_id.startswith("#")}
        new_text, removed = cc.remove_vanilla_rows(text, vanilla_ids)
        if removed:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    return changes


def _fix_person_names_duplicate_row(root: Path, options: dict) -> list[FileChange]:
    """Remove rows of data/characters/person_names.csv that repeat an earlier row (RC8 'Duplicate key' Fatal,
    Ironclads GRP10B-20261005). The first copy stays; every other byte, line endings included, is kept."""
    from bridgeforge.scan.scanner import _person_names_duplicate_lines

    path = root / "data" / "characters" / "person_names.csv"
    repeats = set(_person_names_duplicate_lines(path)) if path.is_file() else set()
    if not repeats:
        raise FixerError("No repeated person_names.csv row found.")
    raw = path.read_bytes()
    lines = raw.split(b"\n")
    after = b"\n".join(line for number, line in enumerate(lines, start=1) if number not in repeats)
    return [FileChange(path=path, before=raw, after=after)]


def _fix_csv_slash_quote_escape(root: Path, options: dict) -> list[FileChange]:
    """Rewrite each /"phrase/" (or \\"phrase\\") that `csv-slash-quote-escape` names as ""phrase"", the CSV escape
    vanilla's descriptions.csv uses (SEEKER 0.6.6 special_items.csv, 2026-09-28). Nothing else in the file changes."""
    from bridgeforge.scan.scanner import CSV_SLASH_QUOTE

    changes = []
    for relative in sorted({f.file for f in _findings_of(root, options, "csv-slash-quote-escape") if f.file}):
        path = root / relative
        if not path.is_file():
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        fixed = CSV_SLASH_QUOTE.sub(lambda m: '""' + m.group(1) + '""', text)
        if fixed != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(fixed, had_bom)))
    return changes
