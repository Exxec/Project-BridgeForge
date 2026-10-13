"""`state-snapshot`: an append-only copy of the state that cannot be rebuilt (ROADMAP 70 H4).

Copies `Done/`, `bridgeforge-state/`, every `In operation/<workspace>/working` and the Claude memory folder to a destination, to guard
against a wrong delete or an overwrite (it is not a disk-failure backup unless the destination is another disk). It never deletes: a
changed file's previous copy moves to `versions/<stamp>/` before the new one lands. Per-source progress lines and a resumable
checkpoint follow the long-running-command rule; `--quiet` turns the lines off.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

from .move_machine import claude_memory_dir
from .progress import Checkpoint, report
from .safeio import atomic_write_json

MTIME_SLACK_SECONDS = 2.0  # FAT/exFAT destinations store mtimes to two seconds


def snapshot_sources(root: Path, claude_home: Path) -> dict[str, Path]:
    """{label: folder}: the labels become folders under `current/`."""
    sources: dict[str, Path] = {}
    for name in ("Done", "bridgeforge-state"):
        if (root / name).is_dir():
            sources[name] = root / name
    queue = root / "In operation"
    if queue.is_dir():
        for workspace in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and (p / "working").is_dir()):
            sources[f"In operation/{workspace.name}/working"] = workspace / "working"
    memory = claude_memory_dir(root, claude_home)
    if memory.is_dir():
        sources["claude-memory"] = memory
    return sources


def _unchanged(source: Path, target: Path) -> bool:
    try:
        a, b = source.stat(), target.stat()
    except OSError:
        return False
    return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) <= MTIME_SLACK_SECONDS


def _copy_into(source: Path, target: Path, version_root: Path, label: str, relative: Path, stats: dict) -> None:
    if target.exists():
        if _unchanged(source, target):
            stats["skipped"] += 1
            return
        kept = version_root / label / relative
        kept.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(kept))
        stats["versioned"] += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".bfpartial")
    shutil.copy2(source, partial)
    if partial.stat().st_size != source.stat().st_size:
        partial.unlink()
        raise OSError(f"{source}: copy has a different size")
    os.replace(partial, target)
    stats["copied"] += 1
    stats["bytes"] += source.stat().st_size


def _copy_source(label: str, folder: Path, current: Path, version_root: Path) -> dict:
    stats = {"copied": 0, "versioned": 0, "skipped": 0, "bytes": 0, "errors": []}
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.name.endswith(".bfpartial"):
            continue
        relative = path.relative_to(folder)
        try:
            _copy_into(path, current / label / relative, version_root, label, relative, stats)
        except OSError as exc:
            stats["errors"].append(f"{relative}: {exc}")
    return stats


def take_snapshot(root: Path, destination: Path, claude_home: Path, quiet: bool = False, stamp: str | None = None) -> dict:
    root, destination = Path(root).resolve(), Path(destination).resolve()
    sources = snapshot_sources(root, Path(claude_home))
    for label, folder in sources.items():
        resolved = folder.resolve()
        if destination == resolved or resolved in destination.parents or destination in resolved.parents:
            raise ValueError(f"destination {destination} overlaps the source {label} ({resolved}); choose a folder outside every source")
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    current, version_root = destination / "current", destination / "versions" / stamp
    destination.mkdir(parents=True, exist_ok=True)
    totals = {"copied": 0, "versioned": 0, "skipped": 0, "bytes": 0, "errors": []}
    per_source: dict[str, dict] = {}
    with Checkpoint(destination / "snapshot.partial.jsonl", {"command": "state-snapshot", "root": str(root), "sources": sorted(sources)}) as checkpoint:
        for number, (label, folder) in enumerate(sources.items(), 1):
            saved = checkpoint.get(label)
            started = time.monotonic()
            stats = saved if saved is not None else _copy_source(label, folder, current, version_root)
            if saved is None and not stats["errors"]:
                checkpoint.add(label, stats)  # a source with errors is retried on the next run
            per_source[label] = stats
            for key in ("copied", "versioned", "skipped", "bytes"):
                totals[key] += stats[key]
            totals["errors"].extend(f"{label}/{error}" for error in stats["errors"])
            if not quiet:
                detail = f"{stats['copied']} copied, {stats['versioned']} kept as older version, {stats['skipped']} unchanged"
                report(number, len(sources), label, detail + (f", {len(stats['errors'])} ERROR(S)" if stats["errors"] else ""),
                       None if saved is not None else time.monotonic() - started)
    if not totals["errors"]:
        Checkpoint(destination / "snapshot.partial.jsonl", {}).finish()
    result = {"stamp": stamp, "root": str(root), "destination": str(destination), "sources": per_source, **totals}
    atomic_write_json(destination / f"snapshot-{stamp}.json", {k: v for k, v in result.items() if k != "sources"} | {"source_labels": sorted(per_source)})
    return result


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("state-snapshot", help="append-only copy of Done/, bridgeforge-state/, every In operation/*/working and the Claude memory folder to --to; changed files keep their older version, nothing is deleted")
    command.add_argument("--to", type=Path, required=True, help="destination folder, outside every source")
    command.add_argument("--root", type=Path, default=Path("."), help="repo root (default: current folder)")
    command.add_argument("--claude-home", type=Path, help="Claude config folder holding projects/ (default: ~/.claude)")
    command.add_argument("--quiet", action="store_true", help="no per-source progress lines on stderr")
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        result = take_snapshot(args.root, args.to, args.claude_home or Path.home() / ".claude", quiet=args.quiet)
    except ValueError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({k: v for k, v in result.items() if k != "sources"}, indent=2))
    else:
        print(f"Snapshot {result['stamp']} in {result['destination']}: {result['copied']} copied ({result['bytes'] / 1e6:.1f} MB), "
              f"{result['versioned']} older version(s) kept, {result['skipped']} unchanged, {len(result['errors'])} error(s).")
        for error in result["errors"][:20]:
            print(f"  ERROR {error}", file=sys.stderr)
    return 1 if result["errors"] else 0


CONFIG_RELATIVE = Path("bridgeforge-state") / "snapshot.json"


def snapshot_after_archive(done_dir: Path, claude_home: Path | None = None) -> str | None:
    """Owner rule 2026-10-12: snapshot after a major new revision, not on a weekly clock. Called after an archive lands in `done_dir`.

    Opt-in per repository: `<root>/bridgeforge-state/snapshot.json` holds {"to": "<destination folder>"}; with no such file this does nothing
    (so tests and other checkouts never copy anything). A failure is reported in the returned text and never raised: the archive is done."""
    root = Path(done_dir).resolve().parent
    config = root / CONFIG_RELATIVE
    if not config.is_file():
        return None
    try:
        destination = json.loads(config.read_text(encoding="utf-8"))["to"]
        result = take_snapshot(root, Path(destination), claude_home or Path.home() / ".claude", quiet=True)
    except (OSError, ValueError, KeyError) as exc:
        return f"snapshot after archive FAILED: {exc}"
    note = f"snapshot {result['stamp']}: {result['copied']} copied, {result['versioned']} older version(s) kept, {len(result['errors'])} error(s)"
    return note
