"""Triage of `vanilla-path-shadowing` files against the reference rig the mod targets (ROADMAP item 73 D3).

A mod file at a vanilla data-relative path replaces RC8's file. Two cases, told apart by the older install the mod was
made for (its reference rig's `starsector-core`):

- byte-identical to the reference rig's file: the mod shipped an unchanged copy of the old vanilla file. It only freezes
  the old version over RC8's, so it is moved to `<workspace>/scratch/removed-shadow/<same path>` (provable later by
  `explain_proofs.kept_elsewhere`) and the game falls back to RC8's file;
- anything else: the mod changed the file (or the reference has no such file). Nothing is moved; the value difference
  between the reference file and the mod's (`data_diff`; a line diff for `.java`) is reported for a person to judge.

Read-only: `triage` computes, the `vanilla-path-shadowing` fixer applies the moves.
"""
from __future__ import annotations

import difflib
import json
from pathlib import Path

from .scan_common import SHADOW_PATH_EXTENSIONS

MAX_DIFF_LINES = 40
REMOVED_SHADOW_FOLDER = "removed-shadow"


def destination_for(root: Path) -> Path:
    """`<workspace>/scratch/removed-shadow` for a workspace's `working/`, else `<root>.removed-shadow` beside it."""
    root = Path(root)
    return root.parent / "scratch" / REMOVED_SHADOW_FOLDER if root.name == "working" else root.parent / f"{root.name}.{REMOVED_SHADOW_FOLDER}"


def _value_diff(reference: Path, mine: Path) -> list[str]:
    """Short, readable lines: what changed from the reference file to the mod's."""
    if mine.suffix.lower() == ".java":
        old = reference.read_text(encoding="utf-8", errors="replace").splitlines()
        new = mine.read_text(encoding="utf-8", errors="replace").splitlines()
        lines = [line for line in difflib.unified_diff(old, new, "reference", "mod", lineterm="", n=0) if not line.startswith(("---", "+++", "@@"))]
        return lines[:MAX_DIFF_LINES] + ([f"... {len(lines) - MAX_DIFF_LINES} more changed line(s)"] if len(lines) > MAX_DIFF_LINES else [])
    from .data_diff import DataDiffError, diff_data

    try:
        changes = diff_data(reference, mine)["changes"]
    except DataDiffError as exc:
        return [f"not comparable by value: {exc}"]
    lines = []
    for change in changes:
        label = change["path"] or "<value>"
        if change["change"] == "changed":
            lines.append(f"{label}: {json.dumps(change['a'], ensure_ascii=False)} -> {json.dumps(change['b'], ensure_ascii=False)}")
        elif change["change"] == "added":
            lines.append(f"{label}: added {json.dumps(change['b'], ensure_ascii=False)}")
        elif change["change"] == "removed":
            lines.append(f"{label}: removed {json.dumps(change['a'], ensure_ascii=False)}")
        else:
            lines.append(f"{label}: {change['change']}")
    if not lines:
        return ["same values, different formatting"]
    return lines[:MAX_DIFF_LINES] + ([f"... {len(lines) - MAX_DIFF_LINES} more difference(s)"] if len(lines) > MAX_DIFF_LINES else [])


def triage(root: Path, vanilla_core: Path, reference_core: Path, skip: set[str] | None = None) -> dict:
    """{"identical": [relative...], "changed": [{"path", "diff"}], "no_reference": [{"path", "diff"}]} for every shadow in root/data.

    A shadow is a mod file whose data-relative path exists in `vanilla_core` with different bytes. `skip` names relative
    paths to leave out (files another step of the fixer already handles)."""
    root, vanilla_core, reference_core = (Path(p).expanduser().resolve() for p in (root, vanilla_core, reference_core))
    identical: list[str] = []
    changed: list[dict] = []
    no_reference: list[dict] = []
    data_root = root / "data"
    for path in sorted(data_root.rglob("*")) if data_root.is_dir() else []:
        relative = path.relative_to(root)
        if not path.is_file() or path.suffix.lower() not in SHADOW_PATH_EXTENSIONS or "disabled_files" in relative.parts:
            continue
        if relative.as_posix() in (skip or set()):
            continue
        current = vanilla_core / relative
        if not current.is_file():
            continue
        try:
            mine = path.read_bytes()
            if mine == current.read_bytes():
                continue  # identical to RC8: vanilla-file-identical-copy, not a shadow
            reference = reference_core / relative
            if not reference.is_file():
                no_reference.append({"path": relative.as_posix(), "diff": _value_diff(current, path)})
            elif reference.read_bytes() == mine:
                identical.append(relative.as_posix())
            else:
                changed.append({"path": relative.as_posix(), "diff": _value_diff(reference, path)})
        except OSError:
            continue
    return {"identical": identical, "changed": changed, "no_reference": no_reference}


def render_report(result: dict, reference_core: Path) -> str:
    lines = ["# Vanilla path shadowing: triage against the reference rig", "",
             f"Reference core: `{reference_core}`", "",
             f"- Moved to scratch/{REMOVED_SHADOW_FOLDER}/ (byte-identical to the reference file): {len(result['identical'])}",
             f"- Kept, differs from the reference file (mod changes below): {len(result['changed'])}",
             f"- Kept, no such file in the reference core (diff is against RC8): {len(result['no_reference'])}", ""]
    if result["identical"]:
        lines += ["## Moved (identical to the reference)", ""] + [f"- `{p}`" for p in result["identical"]] + [""]
    for title, key in (("Kept: changed from the reference", "changed"), ("Kept: not in the reference core", "no_reference")):
        if result[key]:
            lines += [f"## {title}", ""]
            for item in result[key]:
                lines += [f"### `{item['path']}`", ""] + [f"    {line}" for line in item["diff"]] + [""]
    return "\n".join(lines)


def plan_changes(root: Path, vanilla_core: Path, options: dict, handled: set[str], renamed: bool) -> list:
    """The `vanilla-path-shadowing` fixer's D3 step as FileChanges: move each file identical to the reference rig's to
    scratch/removed-shadow/, and write the diffs of the rest to <workspace>/reports/SHADOW_TRIAGE.md (when something moved
    or was renamed, or the report does not exist yet, so a rerun computes no change). The reference core is
    `options["reference_core"]`, else the registered rig whose version is the mod's gameVersion; with neither, nothing here."""
    from .fixers import FileChange, FixerError
    from .reference_rigs import reference_core_for_game_version
    from .scan_json import _load_lenient_json_file

    root = Path(root)
    reference = options.get("reference_core")
    if not reference:
        info = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else None
        reference = reference_core_for_game_version(info.get("gameVersion") if isinstance(info, dict) else None)
    if not reference:
        return []
    reference = Path(reference).expanduser().resolve()
    result = triage(root, vanilla_core, reference, skip=handled)
    destination = destination_for(root)
    changes: list = []
    for relative in result["identical"]:
        target = destination / relative
        if target.exists():
            raise FixerError(f"{target} already exists; move or remove it before rerunning this fixer.")
        data = (root / relative).read_bytes()
        changes.append(FileChange(path=target, before=b"", after=data, existed_before=False))
        changes.append(FileChange(path=root / relative, before=data, after=b"", removed=True))
    report = root.parent / "reports" / "SHADOW_TRIAGE.md" if root.name == "working" else root.parent / f"{root.name}.SHADOW_TRIAGE.md"
    if (result["changed"] or result["no_reference"]) and (changes or renamed or not report.exists()):
        before = report.read_bytes() if report.is_file() else b""
        changes.append(FileChange(path=report, before=before, after=render_report(result, reference).encode("utf-8"),
                                  existed_before=report.is_file()))
    return changes
