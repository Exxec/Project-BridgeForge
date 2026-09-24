"""`bridgeforge rebuild-from-reference`: port a mod's edited copies of vanilla files to RC8 (ROADMAP P14 item 21).

An old rebalance mod (Xenoargh's Rebal: 642 files) ships whole modified copies of vanilla files under
vanilla's own paths, and the game loads the mod's copy in place of vanilla's. Dropped onto RC8 those
copies silently revert every change vanilla made since. The E11 method, done by hand once, is a
three-way merge per file: the reference install's vanilla file (what the mod edited), the mod's copy,
and RC8's vanilla file. Everything RC8 changed or added is kept; only the mod's own edits are applied
on top. Where the mod and RC8 both changed the same value there is no safe answer, so the RC8 value
is kept and the field is reported as a conflict for review.

Scope: the whole-file JSON-dialect classes the scanner's `vanilla-path-shadowing` check reports
(`scanner.SHADOW_PATH_EXTENSIONS` minus `.java`). Read-only on the mod and both cores; `--output`
writes merged files (strict JSON: comments and key formatting are not kept) to a separate folder.
"""
from __future__ import annotations

import json
from pathlib import Path

from .data_diff import _diff
from .scanner import SHADOW_PATH_EXTENSIONS, _load_lenient_json_file

SCHEMA_VERSION = 1
FILE_CLASSES = tuple(sorted(ext for ext in SHADOW_PATH_EXTENSIONS if ext != ".java"))
_MISSING = object()


class RebuildReferenceError(ValueError):
    """Raised for bad inputs: a missing folder, an unknown file class, or an output inside an input."""


def _equal(a: object, b: object) -> bool:
    if a is _MISSING or b is _MISSING:
        return a is b
    changes: list[dict] = []
    _diff(a, b, "", changes)
    return not changes


def _id_list(value: object) -> dict[str, dict] | None:
    if not isinstance(value, list) or not all(isinstance(item, dict) and isinstance(item.get("id"), str) for item in value):
        return None
    keyed = {item["id"]: item for item in value}
    return keyed if len(keyed) == len(value) else None


def _merge(ref: object, mod: object, cur: object, path: str, conflicts: list[dict], applied: list[str]) -> object:
    """Three-way merge of one value. Returns the merged value, or _MISSING to drop it."""
    if _equal(mod, ref):
        return cur  # the mod did not touch it: RC8's value (or RC8's removal) stands
    if _equal(cur, ref) or _equal(cur, mod):
        if not _equal(cur, mod):
            applied.append(path or "<root>")
        return mod  # only the mod changed it, or both made the same change
    if isinstance(ref, dict) and isinstance(mod, dict) and isinstance(cur, dict):
        merged: dict = {}
        for key in list(cur) + [key for key in mod if key not in cur]:
            value = _merge(ref.get(key, _MISSING), mod.get(key, _MISSING), cur.get(key, _MISSING),
                           f"{path}.{key}" if path else str(key), conflicts, applied)
            if value is not _MISSING:
                merged[key] = value
        return merged
    keyed = [_id_list(value) for value in (ref, mod, cur)]
    if all(item is not None for item in keyed):
        ref_by_id, mod_by_id, cur_by_id = keyed
        merged_list = []
        for key in list(cur_by_id) + [key for key in mod_by_id if key not in cur_by_id]:
            value = _merge(ref_by_id.get(key, _MISSING), mod_by_id.get(key, _MISSING), cur_by_id.get(key, _MISSING),
                           f"{path}[id={key}]", conflicts, applied)
            if value is not _MISSING:
                merged_list.append(value)
        return merged_list
    conflicts.append({"path": path or "<root>", "reference": _show(ref), "mod": _show(mod), "rc8": _show(cur)})
    return cur


def _show(value: object) -> object:
    return "<absent>" if value is _MISSING else value


def merge_file(reference: Path, mod: Path, current: Path) -> dict:
    """Merge one file; status UNCHANGED_COPY, MERGED, CONFLICT or UNPARSEABLE."""
    loaded = [_load_lenient_json_file(path) for path in (reference, mod, current)]
    unparseable = [str(path) for path, data in zip((reference, mod, current), loaded) if data is None]
    if unparseable:
        return {"status": "UNPARSEABLE", "unparseable": unparseable}
    ref, mod_data, cur = loaded
    if _equal(mod_data, ref):
        return {"status": "UNCHANGED_COPY", "note": "the mod's file is the reference vanilla file unchanged; on RC8 it only reverts vanilla, so drop it"}
    conflicts: list[dict] = []
    applied: list[str] = []
    merged = _merge(ref, mod_data, cur, "", conflicts, applied)
    return {"status": "CONFLICT" if conflicts else "MERGED", "applied": applied, "conflicts": conflicts, "merged": merged}


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def rebuild_from_reference(mod_dir: Path, reference_core: Path, current_core: Path,
                           file_classes: list[str] | None = None, output: Path | None = None) -> dict:
    mod_dir, reference_core, current_core = (Path(p).expanduser().resolve() for p in (mod_dir, reference_core, current_core))
    for label, folder in (("mod", mod_dir), ("reference core", reference_core), ("RC8 core", current_core)):
        if not folder.is_dir():
            raise RebuildReferenceError(f"{label} {folder} is not a folder.")
    classes = sorted({c if c.startswith(".") else f".{c}" for c in (file_classes or FILE_CLASSES)})
    unknown = [c for c in classes if c not in FILE_CLASSES]
    if unknown:
        raise RebuildReferenceError(f"unsupported file class(es) {unknown}; choose from {list(FILE_CLASSES)}.")
    if output is not None:
        output = Path(output).expanduser().resolve()
        for folder in (mod_dir, reference_core, current_core):
            if _inside(output, folder) or _inside(folder, output):
                raise RebuildReferenceError(f"--output {output} overlaps an input ({folder}); write somewhere separate.")

    files, not_in_reference, removed_from_rc8 = [], [], []
    data_root = mod_dir / "data"
    for path in sorted(data_root.rglob("*")) if data_root.is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in classes:
            continue
        relative = path.relative_to(mod_dir)
        reference, current = reference_core / relative, current_core / relative
        if not current.is_file():
            if reference.is_file():
                removed_from_rc8.append(relative.as_posix())  # vanilla dropped it; the mod's copy is now new content
            continue
        if not reference.is_file():
            not_in_reference.append(relative.as_posix())  # shadows RC8 but predates nothing we can diff against
            continue
        entry = {"file": relative.as_posix(), **merge_file(reference, path, current)}
        if output is not None and entry["status"] == "MERGED":
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(entry["merged"], indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
            entry["written"] = str(target)
        entry.pop("merged", None)
        files.append(entry)

    counts: dict[str, int] = {}
    for entry in files:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    return {
        "schema_version": SCHEMA_VERSION, "mode": "REBUILD_FROM_REFERENCE",
        "mod": str(mod_dir), "reference_core": str(reference_core), "rc8_core": str(current_core),
        "file_classes": classes, "output": str(output) if output else None,
        "counts": counts, "files": files,
        "shadowing_rc8_without_reference_copy": not_in_reference,
        "vanilla_removed_in_rc8": removed_from_rc8,
        "note": "Only MERGED files are written. CONFLICT keeps RC8's value at each listed path until a person decides; UNCHANGED_COPY files should be dropped from the mod.",
    }
