"""`bridgeforge dropped-features`: what each workspace's older tree had that `working/` lacks (ROADMAP items 77.16, 77.19).

Read-only. The old tree is chosen so a multi-mod pack is never compared as a whole (the 2026-10-19 sweep showed one Yunru part
"dropping" the other eight): `PORT_SOURCE.json`'s `old_tree`; else the `original/` mod root whose `mod_info.json` id equals the
working copy's; else the only mod root in `original/`; else UNDETERMINED. Drops covered by `reports/REMOVALS.json` count as
explained. Verdicts: DROPS_UNEXPLAINED, UNDETERMINED, EXPLAINED, CLEAN (listed in that order, worst first).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

from .progress import Checkpoint, report
from .removals import RemovalsError, load_removals, split_explained
from .safeio import atomic_write_json, atomic_write_text
from .scan_json import _load_lenient_json_file
from .scan_port import CATEGORIES, dropped_features, load_port_source, resolve_old_tree

VERDICTS = ("DROPS_UNEXPLAINED", "UNDETERMINED", "EXPLAINED", "CLEAN")
SEARCH_DEPTH = 4
CHECKPOINT_NAME = "DROPPED_FEATURES.partial.jsonl"
SHOWN_PER_CATEGORY = 12
_ID = re.compile(r'"id"\s*:\s*"([^"]+)"')


def mod_id(mod_info: Path) -> str:
    """The `id` of a mod_info.json (lenient JSON, BOM, or a regex when it will not parse); '' when unreadable."""
    data = _load_lenient_json_file(mod_info)
    if isinstance(data, dict):
        return str(data.get("id") or "")
    try:
        found = _ID.search(mod_info.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return ""
    return found.group(1) if found else ""


def mod_roots(folder: Path, depth: int = SEARCH_DEPTH) -> list[Path]:
    """Folders with a mod_info.json at or below `folder` (not searching inside a mod root), shallowest first."""
    found: list[tuple[int, str, Path]] = []
    base = len(folder.parts)
    for current, dirs, files in os.walk(folder):
        here = Path(current)
        level = len(here.parts) - base
        if "mod_info.json" in files:
            found.append((level, here.as_posix().lower(), here))
            dirs[:] = []
        elif level >= depth:
            dirs[:] = []
        else:
            dirs.sort()
    return [p for _, _, p in sorted(found)]


def select_old_tree(workspace: Path) -> dict:
    """`{"tree": Path | None, "origin": ..., "reason": ...}` for a workspace (the folder holding `working/`)."""
    working = workspace / "working"
    record = load_port_source(working)
    if record is not None:
        tree = resolve_old_tree(working, record)
        if tree is not None and tree.resolve() != working.resolve():
            return {"tree": tree, "origin": "PORT_SOURCE.json", "reason": ""}
    original = workspace / "original"
    if not original.is_dir():
        return {"tree": None, "origin": "", "reason": "no PORT_SOURCE.json old_tree and no original/ folder"}
    roots = mod_roots(original)
    if not roots:
        return {"tree": None, "origin": "", "reason": "original/ holds no mod_info.json"}
    wanted = mod_id(working / "mod_info.json")
    if wanted:
        same = [r for r in roots if mod_id(r / "mod_info.json") == wanted]
        if same:
            return {"tree": same[0], "origin": "original (id match)", "reason": ""}
    if len(roots) == 1:
        return {"tree": roots[0], "origin": "original (only mod)", "reason": ""}
    why = f"none has id {wanted!r}" if wanted else "the working copy has no readable mod id"
    return {"tree": None, "origin": "", "reason": f"original/ holds {len(roots)} mod roots and {why}"}


def _relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def check_workspace(workspace: Path) -> dict:
    """The dropped-feature record of one workspace; reads only."""
    working = workspace / "working"
    row: dict = {"workspace": workspace.name, "verdict": "UNDETERMINED", "old_tree": None, "origin": "", "reason": "",
                 "dropped": {}, "total": 0, "explained": 0, "unexplained": 0, "removals_error": ""}
    choice = select_old_tree(workspace)
    if choice["tree"] is None:
        row["reason"] = choice["reason"]
        return row
    row["old_tree"], row["origin"] = _relative(choice["tree"], workspace), choice["origin"]
    try:
        removals = load_removals(working)
    except RemovalsError as exc:
        removals, row["removals_error"] = [], str(exc)
    split = split_explained(dropped_features(choice["tree"], working), removals)
    row["dropped"] = split
    row["explained"] = sum(len(v["explained"]) for v in split.values())
    row["unexplained"] = sum(len(v["unexplained"]) for v in split.values())
    row["total"] = row["explained"] + row["unexplained"]
    row["verdict"] = "DROPS_UNEXPLAINED" if row["unexplained"] else ("EXPLAINED" if row["total"] else "CLEAN")
    return row


def discover(queue: Path) -> list[Path]:
    return sorted((p for p in queue.iterdir() if p.is_dir() and (p / "working").is_dir()), key=lambda p: p.name.lower())


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: (VERDICTS.index(r["verdict"]), -r["unexplained"], -r["total"], r["workspace"].lower()))


def sweep_queue(queue: Path, *, checkpoint: Path | None = None, quiet: bool = False) -> dict:
    workspaces = discover(queue)
    header = {"checkpoint": 1, "queue": str(queue.resolve()), "workspaces": [w.name for w in workspaces]}
    rows: list[dict] = []
    with Checkpoint(checkpoint, header) as saved:
        for index, workspace in enumerate(workspaces, 1):
            started, row = time.monotonic(), saved.get(workspace.name)
            resumed = row is not None
            if row is None:
                row = check_workspace(workspace)
                saved.add(workspace.name, row)
            rows.append(row)
            if not quiet:
                if row["verdict"] == "UNDETERMINED":
                    detail = f"UNDETERMINED ({row['reason']})"
                else:
                    detail = f"{row['verdict']}, {row['unexplained']} unexplained of {row['total']}"
                report(index, len(workspaces), workspace.name, detail, None if resumed else time.monotonic() - started)
    counts = {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}
    return {"schema": 1, "queue": str(queue), "workspaces": len(rows), "verdicts": counts, "rows": sort_rows(rows)}


def _item_lines(category: str, entry: dict) -> list[str]:
    items = entry["unexplained"]
    if not items:
        return [f"- {CATEGORIES[category]}: all {len(entry['explained'])} explained"]
    shown = items[:SHOWN_PER_CATEGORY]
    more = f", ... +{len(items) - len(shown)} more" if len(items) > len(shown) else ""
    note = f" ({len(entry['explained'])} explained)" if entry["explained"] else ""
    return [f"- {CATEGORIES[category]}: {len(items)} unexplained{note}: " + ", ".join(shown) + more]


def render_row(row: dict) -> list[str]:
    head = f"{row['verdict']}  {row['workspace']}"
    if row["verdict"] == "UNDETERMINED":
        return [f"{head}: {row['reason']}"]
    lines = [f"{head}: old tree {row['old_tree']} ({row['origin']}); {row['unexplained']} unexplained, {row['explained']} explained of {row['total']}"]
    if row["removals_error"]:
        lines.append(f"- REMOVALS.json refused, nothing counted as explained: {row['removals_error']}")
    for category, entry in row["dropped"].items():
        lines += _item_lines(category, entry)
    return lines


def render_markdown(result: dict) -> str:
    verdicts = ", ".join(f"{k} {v}" for k, v in result["verdicts"].items())
    lines = ["# Dropped features", "", f"{result['workspaces']} workspace(s) in `{result['queue']}`: {verdicts}.", "",
             "Old tree: PORT_SOURCE.json, else the `original/` mod root with the same mod id, else the only mod in `original/`, else "
             "UNDETERMINED. Explained = covered by `working/reports/REMOVALS.json`. Worst first.", ""]
    for row in result["rows"]:
        first, *rest = render_row(row)
        lines += [f"- {first}", *[f"  {line}" for line in rest]]
    return "\n".join(lines) + "\n"


def add_parser(subcommands) -> None:
    cmd = subcommands.add_parser("dropped-features", help="what the older tree (PORT_SOURCE.json, else the matching original/ mod) had that working/ lacks, minus reports/REMOVALS.json; read-only (ROADMAP 77.16)")
    cmd.add_argument("workspace", type=Path, nargs="?", help="one workspace (the folder holding working/)")
    cmd.add_argument("--queue", type=Path, help="a folder of workspaces (In operation); sorted worst first")
    cmd.add_argument("--write", type=Path, metavar="DIR", help="with --queue: write DROPPED_FEATURES.md and dropped_features.json into DIR; progress is kept in DIR/DROPPED_FEATURES.partial.jsonl so an interrupted run resumes")
    cmd.add_argument("--restart", action="store_true", help="with --write: ignore an earlier interrupted run's partial file")
    cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    cmd.add_argument("--json", action="store_true")


def run_cli(args) -> int:
    if bool(args.workspace) == bool(args.queue):
        print("bridgeforge: give a WORKSPACE or --queue QUEUE_DIR, not both or neither", file=sys.stderr)
        return 2
    if args.workspace:
        if not (args.workspace / "working").is_dir():
            print(f"bridgeforge: {args.workspace} has no working/ folder", file=sys.stderr)
            return 2
        rows = [check_workspace(args.workspace)]
        result = {"schema": 1, "queue": str(args.workspace), "workspaces": 1, "rows": rows,
                  "verdicts": {v: sum(1 for r in rows if r["verdict"] == v) for v in VERDICTS}}
    else:
        if not args.queue.is_dir():
            print(f"bridgeforge: {args.queue} is not a directory", file=sys.stderr)
            return 2
        checkpoint = args.write / CHECKPOINT_NAME if args.write else None
        if checkpoint and args.restart and checkpoint.is_file():
            checkpoint.unlink()
        result = sweep_queue(args.queue, checkpoint=checkpoint, quiet=args.quiet)
        if args.write:
            atomic_write_text(args.write / "DROPPED_FEATURES.md", render_markdown(result))
            atomic_write_json(args.write / "dropped_features.json", result)
            if checkpoint and checkpoint.is_file():
                checkpoint.unlink()
            print(f"Written: {args.write / 'DROPPED_FEATURES.md'}", file=sys.stderr)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.workspace:
        print("\n".join(render_row(result["rows"][0])))
    else:
        print(render_markdown(result), end="")
    return 0
