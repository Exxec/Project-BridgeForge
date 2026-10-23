from __future__ import annotations
import csv
import io
from pathlib import Path
from .common import FileChange, FixerError, _decode, _encode, _field_value, _line_field_spans, _split_terminator


# ---------------------------------------------------------------------------
# Fixer: wing-data-missing-role-desc-column
# ---------------------------------------------------------------------------


def _fix_wing_data_missing_role_desc_column(root: Path, options: dict) -> list[FileChange]:
    """Append a blank `role desc` column: without it RC8's FighterWingSpreadsheetLoader throws a
    JSONException and content loading dies before the main menu (live bug VAC-R002, Vacuum). Vacuum's
    live runs showed a blank value is accepted. Pre-0.8 faction mods (0.53-0.65) all lack it.
    """
    path = root / "data" / "hulls" / "wing_data.csv"
    if not path.is_file():
        raise FixerError(f"No wing_data.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise FixerError(f"{path} is empty.")
    # Count every record the reader returns (a padding row of bare commas is a record too; Cobalt Arms has
    # 44 of them), against every non-blank line: they differ only when a quoted field spans lines.
    records = [row for row in csv.reader(io.StringIO(text)) if row]
    if len(records) != sum(1 for line in lines if line.strip()):
        raise FixerError(f"{path} has a quoted field spanning several lines; add the column by hand rather than guess the row boundaries.")
    header_content, header_term = _split_terminator(lines[0])
    header_fields = [_field_value(item[2]) for item in _line_field_spans(header_content)]
    if "role desc" in [cell.strip().lower() for cell in header_fields]:
        raise FixerError(f"{path} already has a 'role desc' column.")
    width = len(header_fields)
    edited_lines = [header_content + ",role desc" + (header_term or "\n")]
    for line in lines[1:]:
        content, term = _split_terminator(line)
        if not content.strip():
            edited_lines.append(line)
            continue
        present = len(_line_field_spans(content))
        # Pad a short row first so the blank lands in the new column, not an earlier one.
        edited_lines.append(content + "," * max(0, width - present) + "," + term)
    return [FileChange(path=path, before=raw, after=_encode("".join(edited_lines), had_bom))]
