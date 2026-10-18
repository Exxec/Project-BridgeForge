"""`snapshot-restore-check`: prove a `state-snapshot` can actually be restored (ROADMAP item 75 R8, extends item 70 H4).

A hash-complete copy is necessary but does not show that the state is usable. This command restores a snapshot's `current/` into a NEW
isolated folder, never into the primary workspace, and records separate verdicts:

1. validate the snapshot (identity file, format version, no half-finished run, nothing unreadable, no link that could lead out of it);
2. refuse an unsafe destination (path traversal, a junction/symlink on the way, the snapshot or the source root itself or anything inside
   or around them, any `--forbid` root or the Fractal Softworks install folder, a destination that already holds files);
3. hash every snapshot file, copy into a staging folder beside the destination and move it into place only when complete;
4. re-hash the destination against step 3, optionally against an earlier restore manifest (`--compare-to`, detects bit rot between runs);
5. a structural status check of the restored layout, and a `restore-manifest.json` under `<destination>/.bridgeforge-restore/`.

The manifest keeps destination identity, verified hashes, environment, status check and rig scenario verdicts apart. Environment (the rig's
`starsector-core` junction, game binaries) is never rebuilt here: that needs rig-safe setup. The rig scenario is LIVE_PENDING, so the best
verdict is RESTORED_OFFLINE; `recoverable` stays false until a person runs the bounded rig scenario. Resume: hashing is checkpointed
(`<destination>.restore.partial.jsonl`, removed on success); the copy is staged, so an interrupted run leaves no half-filled destination.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

from . import __version__
from .progress import Checkpoint, report
from .safeio import _is_link, atomic_write_json, safe_rmtree

SUPPORTED_SNAPSHOT_FORMAT = 1
MANIFEST_SCHEMA = 1
MANIFEST_DIR, MANIFEST_NAME = ".bridgeforge-restore", "restore-manifest.json"
DEFAULT_FORBIDDEN = (Path("C:/Program Files (x86)/Fractal Softworks"), Path("C:/Program Files/Fractal Softworks"))
OMITTED_BY_DESIGN = ("In operation/_rig and the rig's starsector-core junction", "game binaries and the real install",
                     "versions/ (older file versions stay in the snapshot)", "anything outside the snapshot's source labels")


class RestoreRefused(ValueError):
    """The snapshot or the destination is not safe or usable; nothing was written."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _within(inner: Path, outer: Path) -> bool:
    return inner == outer or outer in inner.parents


def read_identity(snapshot: Path) -> tuple[dict, str]:
    """(identity dict, file name) of the newest `snapshot-<stamp>.json`; refuses a missing, unreadable or unsupported one."""
    if not (snapshot / "current").is_dir():
        raise RestoreRefused(f"{snapshot} has no current/ folder: not a state-snapshot destination")
    if (snapshot / "snapshot.partial.jsonl").exists():
        raise RestoreRefused("the snapshot has a snapshot.partial.jsonl: its last run did not finish, so it is not complete")
    files = sorted(snapshot.glob("snapshot-*.json"))
    if not files:
        raise RestoreRefused("no snapshot-<stamp>.json identity file: the snapshot cannot say what it holds")
    try:
        identity = json.loads(files[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RestoreRefused(f"{files[-1].name} is unreadable or corrupt: {exc}") from exc
    if not isinstance(identity, dict) or not isinstance(identity.get("source_labels"), list) or not identity.get("stamp"):
        raise RestoreRefused(f"{files[-1].name} lacks stamp or source_labels")
    if files[-1].name != f"snapshot-{identity['stamp']}.json":
        raise RestoreRefused(f"{files[-1].name} names stamp {identity['stamp']!r}: the identity file was renamed or copied from another run")
    version = identity.get("snapshot_format", SUPPORTED_SNAPSHOT_FORMAT)
    if version != SUPPORTED_SNAPSHOT_FORMAT:
        raise RestoreRefused(f"snapshot_format {version!r} is not supported (this tool restores format {SUPPORTED_SNAPSHOT_FORMAT})")
    if identity.get("errors"):
        raise RestoreRefused(f"the snapshot recorded {len(identity['errors'])} copy error(s): it is incomplete")
    return identity, files[-1].name


def check_destination(destination: Path, snapshot: Path, source_root: Path | None, forbidden: list[Path]) -> Path:
    """The resolved destination if it is safe to restore into, else RestoreRefused."""
    raw = Path(destination)
    if ".." in raw.parts:
        raise RestoreRefused(f"destination {raw} contains '..': path traversal is refused")
    absolute = Path(os.path.abspath(raw))
    for ancestor in [absolute, *absolute.parents]:
        if ancestor.exists() and _is_link(ancestor):
            raise RestoreRefused(f"{ancestor} is a junction/symlink on the way to the destination: it could lead anywhere")
    target = absolute.resolve()
    guarded = {"the snapshot": snapshot.resolve(), **({"the source root": source_root.resolve()} if source_root else {}),
               **{f"forbidden root {p}": Path(p).resolve() for p in forbidden}}
    for label, root in guarded.items():
        if _within(target, root) or _within(root, target):
            raise RestoreRefused(f"destination {target} is the same as, inside or around {label} ({root}): restore only into a new, isolated folder")
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise RestoreRefused(f"destination {target} already exists and is not an empty folder: a restore never overwrites")
    return target


def _walk_snapshot(current: Path, label: str) -> list[Path]:
    """Regular files under `current/<label>`; refuses a link or a name that escapes the folder."""
    folder = current / label
    files: list[Path] = []
    for here, dirs, names in os.walk(folder, followlinks=False):
        for entry in [*dirs, *names]:
            path = Path(here) / entry
            if _is_link(path):
                raise RestoreRefused(f"{path} is a junction/symlink inside the snapshot: it could lead out of it")
        files += [Path(here) / name for name in sorted(names) if not name.endswith(".bfpartial")]
    return files


def _hash_label(current: Path, label: str) -> dict:
    hashes, unreadable = {}, []
    for path in _walk_snapshot(current, label):
        relative = path.relative_to(current / label).as_posix()
        try:
            hashes[relative] = _sha256(path)
        except OSError as exc:
            unreadable.append(f"{relative}: {exc}")
    return {"hashes": hashes, "unreadable": unreadable}


def _copy_label(current: Path, staging: Path, label: str, hashes: dict[str, str]) -> None:
    for relative in hashes:
        target = staging / label / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current / label / relative, target)


def _verify(destination: Path, label: str, hashes: dict[str, str]) -> list[str]:
    problems = []
    for relative, expected in hashes.items():
        path = destination / label / relative
        try:
            actual = _sha256(path)
        except OSError as exc:
            problems.append(f"{label}/{relative}: {exc}")
            continue
        if actual != expected:
            problems.append(f"{label}/{relative}: hash differs after restore")
    return problems


def _status_check(destination: Path, labels: list[str]) -> dict:
    problems = [f"required state missing: {label}" for label in labels if not (destination / label).is_dir()]
    for state_file in sorted((destination / "bridgeforge-state").rglob("*.json")) if (destination / "bridgeforge-state").is_dir() else []:
        try:
            json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"bridgeforge-state/{state_file.relative_to(destination / 'bridgeforge-state').as_posix()}: not readable JSON ({exc})")
    for label in labels:
        if label.endswith("/working") and not (destination / label / "mod_info.json").is_file():
            problems.append(f"{label}: no mod_info.json at its top")
    return {"status": "FAIL" if problems else "PASS", "labels_checked": len(labels), "problems": problems}


def _earlier_differences(files: dict[str, dict], earlier_path: Path | None) -> list[str]:
    if earlier_path is None:
        return []
    try:
        earlier = json.loads(Path(earlier_path).read_text(encoding="utf-8"))["files"]
    except (OSError, ValueError, KeyError) as exc:
        raise RestoreRefused(f"--compare-to {earlier_path}: not a restore manifest ({exc})") from exc
    problems = []
    for label, hashes in earlier.items():
        for relative, expected in hashes.items():
            now = files.get(label, {}).get(relative)
            if now != expected:
                problems.append(f"{label}/{relative}: {'missing now' if now is None else 'differs from the earlier manifest'}")
    return problems


def restore_check(snapshot: Path, destination: Path, *, source_root: Path | None = None, forbid: list[Path] | None = None,
                  compare_to: Path | None = None, quiet: bool = False) -> dict:
    snapshot = Path(snapshot).resolve()
    identity, identity_name = read_identity(snapshot)
    forbidden = [Path(p) for p in (forbid or [])] + [p for p in DEFAULT_FORBIDDEN if p.exists()]
    root = Path(source_root) if source_root else (Path(identity["root"]) if identity.get("root") else None)
    target = check_destination(destination, snapshot, root, forbidden)
    current, labels = snapshot / "current", sorted(identity["source_labels"])
    missing = [label for label in labels if not (current / label).is_dir()]
    if missing:
        raise RestoreRefused(f"the snapshot's required state is missing from current/: {', '.join(missing)}")
    files: dict[str, dict] = {}
    unreadable: list[str] = []
    with Checkpoint(target.parent / f"{target.name}.restore.partial.jsonl", {"command": "snapshot-restore-check", "snapshot": str(snapshot), "stamp": identity["stamp"], "labels": labels}) as checkpoint:
        for number, label in enumerate(labels, 1):
            saved, started = checkpoint.get(label), time.monotonic()
            result = saved if saved is not None else _hash_label(current, label)
            if saved is None and not result["unreadable"]:
                checkpoint.add(label, result)
            files[label] = result["hashes"]
            unreadable += [f"{label}/{item}" for item in result["unreadable"]]
            if not quiet:
                report(number, len(labels), f"hash {label}", f"{len(result['hashes'])} file(s)" + (f", {len(result['unreadable'])} UNREADABLE" if result["unreadable"] else ""), None if saved is not None else time.monotonic() - started)
    if unreadable:
        raise RestoreRefused(f"{len(unreadable)} snapshot file(s) are unreadable, so it is incomplete: {unreadable[:5]}")
    staging = target.parent / f"{target.name}.bfrestore-staging"
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_rmtree(staging, [target.parent])
    try:
        for number, label in enumerate(labels, 1):
            started = time.monotonic()
            _copy_label(current, staging, label, files[label])
            if not quiet:
                report(number, len(labels), f"copy {label}", f"{len(files[label])} file(s)", time.monotonic() - started)
        if target.exists():
            target.rmdir()  # empty, checked above
        os.replace(staging, target)
    except OSError as exc:
        safe_rmtree(staging, [target.parent])
        raise RestoreRefused(f"copy failed, nothing was left at the destination: {exc}") from exc
    Checkpoint(target.parent / f"{target.name}.restore.partial.jsonl", {}).finish()
    problems = [problem for label in labels for problem in _verify(target, label, files[label])] + _earlier_differences(files, compare_to)
    status = _status_check(target, labels)
    count = sum(len(h) for h in files.values())
    verdict = "FAIL" if problems or status["status"] != "PASS" else "RESTORED_OFFLINE"
    manifest = {
        "schema_version": MANIFEST_SCHEMA, "mode": "SNAPSHOT_RESTORE_CHECK", "tool_version": __version__,
        "snapshot": {"path": str(snapshot), "identity_file": identity_name, "identity_sha256": _sha256(snapshot / identity_name), "stamp": identity["stamp"],
                     "snapshot_format": identity.get("snapshot_format", "legacy-unversioned"), "source_root": identity.get("root"), "snapshot_tool_version": identity.get("tool_version")},
        "destination": {"path": str(target), "created_new": True}, "required_state": labels, "omitted": list(OMITTED_BY_DESIGN), "unreadable": [],
        "hashes": {"files": count, "verified": count - len(problems), "problems": problems},
        "environment": {"status": "NOT_RECONSTRUCTED", "note": "rig junctions and game files need rig-safe setup (rig-create / bootstrap); this command never builds them"},
        "status_check": status,
        "rig_scenario": {"status": "LIVE_PENDING", "note": "run a bounded rig scenario against this restored copy; never against the primary workspace"},
        "verdict": verdict, "recoverable": False, "files": files,
    }
    atomic_write_json(target / MANIFEST_DIR / MANIFEST_NAME, manifest, indent=1)
    return {k: v for k, v in manifest.items() if k != "files"} | {"manifest": str(target / MANIFEST_DIR / MANIFEST_NAME)}


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("snapshot-restore-check", help="restore a state-snapshot into a NEW isolated folder, verify hashes and layout, write a restore manifest (rig scenario stays LIVE_PENDING)")
    command.add_argument("snapshot", type=Path, help="the state-snapshot destination folder (holds current/ and snapshot-<stamp>.json)")
    command.add_argument("--to", type=Path, required=True, help="NEW or empty folder to restore into; refused when populated, linked or inside the snapshot, the source root or a --forbid root")
    command.add_argument("--source-root", type=Path, help="the live repo root the snapshot was taken from (default: the root its identity file records)")
    command.add_argument("--forbid", type=Path, action="append", default=[], help="extra folder never to restore into or around (the Fractal Softworks install is always forbidden)")
    command.add_argument("--compare-to", type=Path, help="an earlier restore-manifest.json: every file must still hash the same")
    command.add_argument("--quiet", action="store_true", help="no per-label progress lines on stderr")
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    try:
        result = restore_check(args.snapshot, args.to, source_root=args.source_root, forbid=args.forbid, compare_to=args.compare_to, quiet=args.quiet)
    except RestoreRefused as exc:
        print(f"bridgeforge: REFUSED: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        hashes = result["hashes"]
        print(f"snapshot-restore-check {result['verdict']}: {hashes['verified']}/{hashes['files']} file(s) verified in {result['destination']['path']}; "
              f"status check {result['status_check']['status']}; environment {result['environment']['status']}; rig scenario {result['rig_scenario']['status']}.")
        for problem in (hashes["problems"] + result["status_check"]["problems"])[:20]:
            print(f"  {problem}", file=sys.stderr)
    return 0 if result["verdict"] == "RESTORED_OFFLINE" else 1
