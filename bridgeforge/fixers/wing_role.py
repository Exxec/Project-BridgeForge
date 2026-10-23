from __future__ import annotations
from pathlib import Path
from .common import FileChange, FixerError, _decode, _encode, _field_value, _line_field_spans, _quote_like, _split_terminator


# ---------------------------------------------------------------------------
# Fixer: wing-role-assault-removed
# ---------------------------------------------------------------------------


# Retired 2026-09-14 and no longer registered: ASSAULT is still a valid RC8 WingRole (javap on
# com.fs.starfarer.api.loading.WingRole), so rewriting it to FIGHTER changed behaviour for nothing.
def _fix_wing_role_assault_removed(root: Path, options: dict) -> list[FileChange]:
    path = root / "data" / "hulls" / "wing_data.csv"
    if not path.is_file():
        raise FixerError(f"No wing_data.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    lines = text.splitlines(keepends=True)
    if not lines:
        raise FixerError(f"{path} is empty.")
    header_content, header_term = _split_terminator(lines[0])
    header_fields = [_field_value(item[2]) for item in _line_field_spans(header_content)]
    normalized = [cell.strip().lower() for cell in header_fields]
    if "role" not in normalized:
        raise FixerError(f"{path} has no 'role' column.")
    role_index = normalized.index("role")

    edited_lines = [lines[0]]
    changed_count = 0
    for line in lines[1:]:
        content, term = _split_terminator(line)
        if not content.strip():
            edited_lines.append(line)
            continue
        spans = _line_field_spans(content)
        first_value = _field_value(spans[0][2]) if spans else ""
        if first_value.strip().startswith("#") or role_index >= len(spans):
            edited_lines.append(line)
            continue
        start, end, raw_field = spans[role_index]
        value = _field_value(raw_field)
        if value.strip().upper() == "ASSAULT":
            new_raw = _quote_like(raw_field, "FIGHTER")
            content = content[:start] + new_raw + content[end:]
            changed_count += 1
        edited_lines.append(content + term)

    if changed_count == 0:
        raise FixerError(f"No wing_data.csv row has role ASSAULT; nothing to fix in {path}.")
    new_text = "".join(edited_lines)
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]
