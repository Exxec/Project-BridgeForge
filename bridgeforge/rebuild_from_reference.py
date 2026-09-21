"""Generalize E11's rebuild-from-a-reference-rig method into a command (ROADMAP P14 item 21).

Built by hand for Rebal's real defect class: an old mod ships modified copies of vanilla files
under vanilla's own paths, so `vanilla-path-shadowing` fires, but the mod's copy also carries real
authored rebalance changes that would be lost by simply dropping the file (E12 found exactly that
mistake). The fix that keeps both: for each such file, value-diff the mod's copy against a
historical reference version of vanilla (from a registered reference rig, ROADMAP P10) to find only
the mod's own genuine authored changes, then overlay just those changes onto a fresh copy of
*current* RC8 vanilla - so whatever RC8 added or fixed since the reference version is kept, and
only the mod's real edits carry forward.

Read-only by default: `rebuild_from_reference` reports what it would change (and any conflict,
where current RC8 vanilla itself diverged from the reference on a path the mod also touched - the
mod's value wins, but the conflict is surfaced rather than silently resolved). `--apply` writes the
rebuilt files under a separate `--output` directory; it never touches the mod's own working copy.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from .diff_data import _diff_values
from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1

_PATH_TOKEN = re.compile(r"\[(\d+)\]|([^.\[\]]+)")
_MISSING = object()


def _parse_path(path: str) -> list[int | str]:
    tokens: list[int | str] = []
    for match in _PATH_TOKEN.finditer(path):
        index, key = match.groups()
        tokens.append(int(index) if index is not None else key)
    return tokens


def _get_at_path(data: object, path: str) -> object:
    if path == "$":
        return data
    node = data
    for token in _parse_path(path):
        node = node[token]
    return node


def _set_at_path(data: object, path: str, value: object) -> None:
    tokens = _parse_path(path)
    node = data
    for token in tokens[:-1]:
        node = node[token]
    node[tokens[-1]] = value


def _delete_at_path(data: object, path: str) -> None:
    tokens = _parse_path(path)
    node = data
    for token in tokens[:-1]:
        node = node[token]
    del node[tokens[-1]]


def _rebuild_one_file(mod_data: object, reference_data: object, current_data: object, relative: str) -> dict:
    mod_changes = _diff_values("", reference_data, mod_data)
    if not mod_changes:
        return {"file": relative, "status": "NO_GENUINE_CHANGES", "changes_applied": [], "conflicts": []}
    rebuilt = copy.deepcopy(current_data)
    applied: list[str] = []
    conflicts: list[dict] = []
    for change in mod_changes:
        path = change["path"]
        try:
            current_value = current_data if path == "$" else _get_at_path(current_data, path)
            has_current_value = True
        except (KeyError, IndexError, TypeError):
            has_current_value = False
            current_value = None
        if has_current_value and change["kind"] != "added" and current_value != change["a"]:
            conflicts.append({
                "path": path,
                "reference_value": change["a"],
                "current_vanilla_value": current_value,
                "mod_value": change["b"],
                "note": "current RC8 vanilla differs from the reference on a path the mod also changed; the mod's value was kept",
            })
        try:
            if path == "$":
                rebuilt = copy.deepcopy(change["b"]) if change["kind"] != "removed" else rebuilt
            elif change["kind"] == "removed":
                try:
                    _delete_at_path(rebuilt, path)
                except (KeyError, IndexError, TypeError):
                    pass  # already absent from current vanilla - the intended end state, not a conflict
            else:
                _set_at_path(rebuilt, path, copy.deepcopy(change["b"]))
            applied.append(path)
        except (KeyError, IndexError, TypeError) as exc:
            conflicts.append({"path": path, "note": f"could not apply structurally - current vanilla's shape differs enough that this path doesn't exist there: {exc}"})
    return {
        "file": relative,
        "status": "CONFLICT" if conflicts else "REBUILT",
        "changes_applied": applied,
        "conflicts": conflicts,
        "rebuilt_data": rebuilt,
    }


def rebuild_from_reference(mod: Path, reference_core: Path, current_core: Path, glob: str = "**/*", output: Path | None = None) -> dict:
    """For every file in `mod` that shares a relative path with both `reference_core` and
    `current_core`, overlay the mod's own genuine authored changes (found by diffing against
    `reference_core`) onto a fresh copy of `current_core`'s file. `glob` scopes which files to
    consider (e.g. `data/hullmods/**/*.java`, `**/*.wpn`), so a large mod can be rebuilt in
    reviewable stages. Files with no counterpart in either vanilla copy, or with no genuine
    authored change versus the reference, are skipped. When `output` is given, every REBUILT or
    CONFLICT file's rebuilt content is written under `output` at its own relative path (JSON files
    only, since only JSON/org.json-dialect files can be value-diffed this way) - the mod's own
    working copy is never touched.
    """
    files: list[dict] = []
    for path in sorted(mod.rglob(glob)):
        if not path.is_file():
            continue
        relative = path.relative_to(mod)
        relative_str = str(relative).replace("\\", "/")
        reference_path = reference_core / relative
        current_path = current_core / relative
        if not reference_path.is_file() or not current_path.is_file():
            continue
        mod_data = _load_lenient_json_file(path)
        reference_data = _load_lenient_json_file(reference_path)
        current_data = _load_lenient_json_file(current_path)
        if mod_data is None or reference_data is None or current_data is None:
            continue
        result = _rebuild_one_file(mod_data, reference_data, current_data, relative_str)
        if output is not None and result["status"] in ("REBUILT", "CONFLICT"):
            import json
            out_path = output / relative
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(result["rebuilt_data"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["written_to"] = str(out_path)
        result.pop("rebuilt_data", None)
        files.append(result)
    counts = {status: sum(1 for f in files if f["status"] == status) for status in ("REBUILT", "CONFLICT", "NO_GENUINE_CHANGES")}
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "rebuild-from-reference",
        "status": "CONFLICT" if counts["CONFLICT"] else ("REBUILT" if counts["REBUILT"] else "NO_GENUINE_CHANGES"),
        "mod": str(mod),
        "reference_core": str(reference_core),
        "current_core": str(current_core),
        "glob": glob,
        "counts": counts,
        "files": files,
    }
