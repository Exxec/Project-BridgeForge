"""`bridgeforge diff-data`: compare two Starsector data files by value, not by line (ROADMAP P14 item 19).

A mod's copy of a vanilla file and the vanilla file itself often differ in key order, indentation,
`#` comments and trailing commas (org.json accepts all of them), so a text diff is swamped by noise
and hides the one field that actually changed. This loads both sides the way the scanner does and
reports only differences in value:

- JSON-dialect files (`.json`, `.ship`, `.variant`, `.wpn`, `.skin`, `.faction`, ...): nested objects
  by key; lists of objects that all carry a unique string `"id"` (weapon/engine slots) by that id;
  other lists index by index when the lengths match, or by content when both hold only scalars; a
  scalar list holding the same values in another order is one `reordered` change.
- CSV files: rows matched by the `id` column (else the first column), cells by column name, so row
  and column order never matter; `#` comment rows and rows with an empty key are skipped, as the
  game skips them.

Numbers compare by value (`10`, `10.0` and `"10.0"` in a CSV cell are equal). Read-only.
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1
_MISSING = object()


class DataDiffError(ValueError):
    """Raised when a side cannot be read or the two sides are different kinds of file."""


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _as_float(text: str) -> float | None:
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _same_scalar(a: object, b: object) -> bool:
    if _is_number(a) and _is_number(b):
        return a == b
    return type(a) is type(b) and a == b


def _change(changes: list[dict], path: str, a: object, b: object) -> None:
    if a is _MISSING:
        changes.append({"path": path, "change": "added", "b": b})
    elif b is _MISSING:
        changes.append({"path": path, "change": "removed", "a": a})
    else:
        changes.append({"path": path, "change": "changed", "a": a, "b": b})


def _id_keyed(items: list) -> dict[str, dict] | None:
    if not items or not all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in items):
        return None
    keyed = {item["id"]: item for item in items}
    return keyed if len(keyed) == len(items) else None


def _scalar_key(value: object) -> tuple[str, object]:
    return ("number", float(value)) if _is_number(value) else (type(value).__name__, value)


def _diff(a: object, b: object, path: str, changes: list[dict]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in list(a) + [key for key in b if key not in a]:
            child = f"{path}.{key}" if path else str(key)
            if key not in b:
                _change(changes, child, a[key], _MISSING)
            elif key not in a:
                _change(changes, child, _MISSING, b[key])
            else:
                _diff(a[key], b[key], child, changes)
        return
    if isinstance(a, list) and isinstance(b, list):
        a_keyed, b_keyed = _id_keyed(a), _id_keyed(b)
        if a_keyed is not None and b_keyed is not None:
            for key in list(a_keyed) + [key for key in b_keyed if key not in a_keyed]:
                child = f"{path}[id={key}]"
                if key not in b_keyed:
                    _change(changes, child, a_keyed[key], _MISSING)
                elif key not in a_keyed:
                    _change(changes, child, _MISSING, b_keyed[key])
                else:
                    _diff(a_keyed[key], b_keyed[key], child, changes)
            return
        scalars = all(not isinstance(item, (dict, list)) for item in a + b)
        if scalars and len(a) == len(b) and any(not _same_scalar(x, y) for x, y in zip(a, b)) \
                and sorted(map(_scalar_key, a), key=repr) == sorted(map(_scalar_key, b), key=repr):
            # Same values, other order: one line, not one per index. Order is meaningless for tags but
            # not for turretOffsets or colours, and the file cannot say which, so it is still reported.
            changes.append({"path": path, "change": "reordered", "a": a, "b": b})
            return
        if len(a) != len(b) and scalars:
            a_counts: dict[tuple, int] = {}
            for item in a:
                a_counts[_scalar_key(item)] = a_counts.get(_scalar_key(item), 0) + 1
            for item in b:
                key = _scalar_key(item)
                if a_counts.get(key):
                    a_counts[key] -= 1
                else:
                    _change(changes, f"{path}[]", _MISSING, item)
            for item in a:
                key = _scalar_key(item)
                if a_counts.get(key):
                    a_counts[key] -= 1
                    _change(changes, f"{path}[]", item, _MISSING)
            return
        for index in range(max(len(a), len(b))):
            child = f"{path}[{index}]"
            if index >= len(b):
                _change(changes, child, a[index], _MISSING)
            elif index >= len(a):
                _change(changes, child, _MISSING, b[index])
            else:
                _diff(a[index], b[index], child, changes)
        return
    if not _same_scalar(a, b):
        _change(changes, path, a, b)


def _csv_rows(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    # errors="replace" as _read_csv_rows_lenient does: vanilla's own CSVs carry stray CP-1252 bytes.
    try:
        with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            header = [name for name in (reader.fieldnames or []) if name]
    except (OSError, csv.Error) as exc:
        raise DataDiffError(f"{path} could not be read as CSV: {exc}") from None
    if not header:
        return [], {}
    key_column = "id" if "id" in header else header[0]
    keyed: dict[str, dict[str, str]] = {}
    for row in rows:
        key = (row.get(key_column) or "").strip()
        if not key or key.startswith("#"):
            continue
        name, suffix = key, 2
        while name in keyed:  # a repeated key keeps every row visible instead of hiding the later one
            name, suffix = f"{key}#{suffix}", suffix + 1
        keyed[name] = {column: (row.get(column) or "") for column in header}
    return header, keyed


def _same_cell(a: str, b: str) -> bool:
    if a == b:
        return True
    number_a, number_b = _as_float(a), _as_float(b)
    return number_a is not None and number_a == number_b


def _diff_csv(path_a: Path, path_b: Path, changes: list[dict]) -> None:
    header_a, rows_a = _csv_rows(path_a)
    header_b, rows_b = _csv_rows(path_b)
    for column in header_a:
        if column not in header_b:
            _change(changes, f"column {column}", column, _MISSING)
    for column in header_b:
        if column not in header_a:
            _change(changes, f"column {column}", _MISSING, column)
    shared = [column for column in header_a if column in header_b]
    for key in list(rows_a) + [key for key in rows_b if key not in rows_a]:
        if key not in rows_b:
            _change(changes, f"[{key}]", rows_a[key], _MISSING)
        elif key not in rows_a:
            _change(changes, f"[{key}]", _MISSING, rows_b[key])
        else:
            for column in shared:
                if not _same_cell(rows_a[key][column], rows_b[key][column]):
                    _change(changes, f"[{key}].{column}", rows_a[key][column], rows_b[key][column])


def diff_data(path_a: Path, path_b: Path) -> dict:
    """Value-level differences between two data files of the same kind (JSON dialect or CSV)."""
    path_a, path_b = Path(path_a).expanduser().resolve(), Path(path_b).expanduser().resolve()
    for path in (path_a, path_b):
        if not path.is_file():
            raise DataDiffError(f"{path} is not a file.")
    csv_a, csv_b = path_a.suffix.lower() == ".csv", path_b.suffix.lower() == ".csv"
    if csv_a != csv_b:
        raise DataDiffError("one file is CSV and the other is not; compare like with like.")
    changes: list[dict] = []
    if csv_a:
        _diff_csv(path_a, path_b, changes)
    else:
        data_a, data_b = _load_lenient_json_file(path_a), _load_lenient_json_file(path_b)
        for path, data in ((path_a, data_a), (path_b, data_b)):
            if data is None:
                raise DataDiffError(f"{path} could not be parsed as Starsector JSON.")
        _diff(data_a, data_b, "", changes)
    return {
        "schema_version": SCHEMA_VERSION, "mode": "DATA_DIFF", "kind": "csv" if csv_a else "json",
        "a": str(path_a), "b": str(path_b), "identical": not changes, "changes": changes,
    }
