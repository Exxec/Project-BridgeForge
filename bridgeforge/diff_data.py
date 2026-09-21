"""Value-diff two org.json-dialect files field by field, not a line diff (ROADMAP P14 item 19).

Found 2026-09-20 building E11's data-only rebuild plan for Rebal: diffing a mod's file against a
real historical vanilla reference showed the two use different key order and formatting
(pretty-printed vs. commented blocks), so a plain text diff is swamped by noise and hides the one
genuine semantic change actually present. Both files are loaded through `_load_lenient_json_file`
(the same `#`-comments/trailing-commas/org.json dialect every other Starsector JSON read in this
codebase goes through), so formatting and key-order differences never appear as changes at all -
only real value differences do.
"""

from __future__ import annotations

from pathlib import Path

from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1


def _format_path(path: str, key: object) -> str:
    if isinstance(key, int):
        return f"{path}[{key}]"
    return f"{path}.{key}" if path else str(key)


def _diff_values(path: str, a: object, b: object) -> list[dict[str, object]]:
    if a == b:
        return []
    if isinstance(a, dict) and isinstance(b, dict):
        changes: list[dict[str, object]] = []
        for key in sorted(set(a) | set(b), key=str):
            key_path = _format_path(path, key)
            if key not in b:
                changes.append({"path": key_path, "kind": "removed", "a": a[key], "b": None})
            elif key not in a:
                changes.append({"path": key_path, "kind": "added", "a": None, "b": b[key]})
            else:
                changes.extend(_diff_values(key_path, a[key], b[key]))
        return changes
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        changes = []
        for index, (item_a, item_b) in enumerate(zip(a, b)):
            changes.extend(_diff_values(_format_path(path, index), item_a, item_b))
        return changes
    return [{"path": path or "$", "kind": "changed", "a": a, "b": b}]


def diff_data(path_a: Path, path_b: Path) -> dict:
    """Report every real value difference between two org.json-dialect files.

    `path_a`/`path_b` are loaded through the same lenient parser every other Starsector JSON read
    in this codebase uses, so `#` comments, trailing commas and key-order/formatting differences
    never appear in `changes` - only genuine added/removed/changed field values do. A list is
    diffed element-by-index only when both lists have the same length; a length mismatch (or any
    other type mismatch) is reported as one whole-value "changed" entry at that path, since there
    is no reliable way to align differently-sized lists without knowing the data's own identity
    field (which varies per file class).
    """
    data_a = _load_lenient_json_file(path_a)
    data_b = _load_lenient_json_file(path_b)
    changes = _diff_values("", data_a, data_b)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "diff-data",
        "status": "DIFFERENT" if changes else "IDENTICAL",
        "file_a": str(path_a),
        "file_b": str(path_b),
        "changes": changes,
    }
