"""CSV rows as the game's loader keeps them (docs/RC8_BEHAVIOUR.md RC8-47, ROADMAP-3 94.G2 slice 16).

The loader's parser (0.98.5a-RC7 `com.fs.starfarer.loading.void.o00000(String)`, RC8 `com.fs.starfarer.loading.G`; javap
2026-11-22) raises a flag when the first character of a row is `#` and never adds that row to the JSONArray. The test is
on the raw text, before quotes are read: a row starting `#Atropos,atropos` is gone whatever its id, while vanilla's
`"#Light Mortar (High Delay, Fighter)",lightmortar_fighter` and a row starting ` #` are kept.
"""
from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from pathlib import Path


def lines(text: str) -> list[str]:
    """The text's lines as the csv module counts them: split at \\n, \\r or \\r\\n, endings kept (newline='')."""
    return io.StringIO(text, newline="").readlines()


def records(text: str) -> Iterator[tuple[list[str], int, int, bool]]:
    """(cells, first line, end line, commented) per CSV record, the header first; lines index `lines(text)`. A blank line
    is a record of no cells. `commented` is the game's rule: the record's first line starts with '#'."""
    physical = lines(text)
    reader = csv.reader(io.StringIO(text, newline=""))
    start = 0
    for cells in reader:
        yield cells, start, reader.line_num, start < len(physical) and physical[start].startswith("#")
        start = reader.line_num


def game_rows(path: Path) -> list[dict[str, str]] | None:
    """The data rows the game keeps, exactly as `csv.DictReader` gives them, or None when the file cannot be read or parsed.

    Read like scan_json._read_csv_rows_lenient (utf-8-sig, errors='replace', newline=''), so the cells, and the row hashes and
    gene identities made from them, are unchanged; only the rows the game drops are left out."""
    try:
        with Path(path).open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            text = handle.read()
        # DictReader takes the first record as the header, even a blank one, and then skips blank records; pair its rows with
        # the records the same way (review 2026-11-22: a leading blank line misaligned them).
        flags = [commented for cells, _first, _end, commented in list(records(text))[1:] if cells]
        rows = list(csv.DictReader(io.StringIO(text, newline="")))
    except (OSError, csv.Error):
        return None
    return [row for row, commented in zip(rows, flags, strict=True) if not commented]
