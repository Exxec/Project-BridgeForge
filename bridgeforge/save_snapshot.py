from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from pathlib import Path

from .boot_test import _is_link, _running_java_under

"""Roadmap P3b-D: `save-snapshot {tag,list,restore}`.

Snapshots are plain file copies of a rig's own `<runtime_dir>/saves/<save_name>/` folder, taken and
restored entirely inside the rig -- never edited, never touched while the game might be writing to
them (both `_refuse_non_rig` and `_refuse_running` guard every entry point below, the same pattern
`boot_test`/`probe_config`/`compat_sets` already use). `saves/common` (the probe's own config/marker
files, never a save) is refused as a save name in both directions.
"""

SNAPSHOTS_DIR_NAME = "save_snapshots"
MANIFEST_FILE = "manifest.json"
COMMON_SAVE_NAME = "common"

_TAG_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")
_MOD_SPEC_BLOCK_RE = re.compile(r"<spec\b[^>]*>(?P<body>.*?)</spec>", re.DOTALL)
_MOD_NAME_RE = re.compile(r"<name>(?P<name>[^<]*)</name>")
_MOD_ID_RE = re.compile(r"<id>(?P<id>[^<]*)</id>")
# Matches build_tag.py's own "[LABEL rN]" name suffix convention (any label, not just "BF"), so a
# snapshot manifest records whatever build-tag label a mod in the save actually carries.
_BUILD_TAG_SUFFIX_RE = re.compile(r"\[(?P<label>[A-Za-z0-9]+)\s+r(?P<build>\d+)\]\s*$")


class SaveSnapshotError(ValueError):
    """Raised when a save snapshot cannot be tagged, listed, or restored."""


def _refuse_non_rig(runtime_dir: Path) -> None:
    core_path = runtime_dir / "starsector-core"
    if not _is_link(core_path):
        raise SaveSnapshotError(
            f"{core_path} is not a junction/symlink. save-snapshot refuses to touch a non-isolated "
            "runtime's saves folder."
        )


def _refuse_running(runtime_dir: Path) -> None:
    running = _running_java_under(runtime_dir)
    if running:
        pids = ", ".join(str(item.get("pid")) for item in running)
        raise SaveSnapshotError(
            f"java.exe already running under {runtime_dir} (pid {pids}). Stop it before a snapshot "
            "operation reads/writes saves/, which the running game may itself be writing to."
        )


def _saves_dir(runtime_dir: Path) -> Path:
    return runtime_dir / "saves"


def _snapshots_root(runtime_dir: Path) -> Path:
    return runtime_dir / SNAPSHOTS_DIR_NAME


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _hash_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _extract_bf_build_tags(descriptor_path: Path) -> dict[str, str]:
    """Best-effort {mod_id: mod_name} for every mod in a save's descriptor.xml whose <name> carries
    a build_tag.py-style "[LABEL rN]" suffix. Never raises: a missing/malformed descriptor.xml (or a
    mod entry missing either field) just contributes nothing, since this is manifest metadata, not
    something a snapshot should ever refuse over.
    """
    tags: dict[str, str] = {}
    try:
        text = descriptor_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return tags
    for block in _MOD_SPEC_BLOCK_RE.finditer(text):
        body = block.group("body")
        name_match = _MOD_NAME_RE.search(body)
        id_match = _MOD_ID_RE.search(body)
        if not name_match or not id_match:
            continue
        name = name_match.group("name")
        if _BUILD_TAG_SUFFIX_RE.search(name):
            tags[id_match.group("id")] = name
    return tags


def _validate_tag(tag: str) -> None:
    if not tag or not _TAG_RE.match(tag):
        raise SaveSnapshotError(f"Invalid snapshot tag {tag!r}; use only letters, digits, '_', '-', '.'.")


def _validate_save_name(name: str, *, what: str) -> None:
    if not name or name == COMMON_SAVE_NAME or "/" in name or "\\" in name or name in (".", ".."):
        raise SaveSnapshotError(f"Refusing to use {name!r} as a {what} (not a real save name).")


def snapshot_tag(runtime_dir: Path, save_name: str, tag: str) -> dict[str, object]:
    """Copy <runtime_dir>/saves/<save_name>/ into <runtime_dir>/save_snapshots/<tag>/<save_name>/.

    Writes a manifest.json alongside the copy: tag, source save, any BF-style build tags found in the
    copied descriptor.xml, a created timestamp, and a sha256 per file. Refuses unless
    runtime_dir/starsector-core is a junction/symlink, refuses if a rig java.exe is already running
    (it may be mid-write to the very save being copied), and refuses save_name == "common" (the
    probe's own config folder, never a save) or an already-used tag.
    """
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    _refuse_non_rig(runtime_dir)
    _refuse_running(runtime_dir)
    _validate_tag(tag)
    _validate_save_name(save_name, what="save name")

    source = _saves_dir(runtime_dir) / save_name
    if not source.is_dir() or not (source / "descriptor.xml").is_file():
        raise SaveSnapshotError(f"{source} is not an existing save directory (no descriptor.xml).")

    snapshot_root = _snapshots_root(runtime_dir) / tag
    dest = snapshot_root / save_name
    if snapshot_root.exists():
        raise SaveSnapshotError(f"{snapshot_root} already exists; choose a different tag.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)

    hashes = _hash_tree(dest)
    bf_build_tags = _extract_bf_build_tags(dest / "descriptor.xml")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "tag": tag,
        "source_save": save_name,
        "bf_build_tags": bf_build_tags,
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hashes": hashes,
    }
    manifest_path = snapshot_root / MANIFEST_FILE
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "schema_version": 1,
        "mode": "SAVE_SNAPSHOT_TAG",
        "runtime_dir": str(runtime_dir),
        "tag": tag,
        "source_save": save_name,
        "snapshot_dir": str(dest),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def snapshot_list(runtime_dir: Path) -> list[dict[str, object]]:
    """List every snapshot tag under <runtime_dir>/save_snapshots/, each with its parsed manifest."""
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    root = _snapshots_root(runtime_dir)
    if not root.is_dir():
        return []
    results: list[dict[str, object]] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest_path = child / MANIFEST_FILE
        manifest: dict[str, object] | None = None
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = None
        results.append({"tag": child.name, "path": str(child), "manifest": manifest})
    return results


def snapshot_restore(
    runtime_dir: Path,
    tag: str,
    *,
    as_name: str | None = None,
    replace: bool = False,
) -> dict[str, object]:
    """Copy a tagged snapshot's save folder back into <runtime_dir>/saves/<as_name or source_save>/.

    Never overwrites an existing save unless replace=True, and never touches saves/common (refused as
    both a snapshot source and a restore destination name). Refuses unless
    runtime_dir/starsector-core is a junction/symlink, and refuses if a rig java.exe is already
    running.
    """
    runtime_dir = Path(runtime_dir).expanduser().resolve()
    _refuse_non_rig(runtime_dir)
    _refuse_running(runtime_dir)
    _validate_tag(tag)

    snapshot_root = _snapshots_root(runtime_dir) / tag
    manifest_path = snapshot_root / MANIFEST_FILE
    if not manifest_path.is_file():
        raise SaveSnapshotError(f"No snapshot manifest at {manifest_path}; unknown tag {tag!r}.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SaveSnapshotError(f"{manifest_path} could not be read: {exc}") from exc

    source_save = manifest.get("source_save") if isinstance(manifest, dict) else None
    if not isinstance(source_save, str) or not source_save:
        raise SaveSnapshotError(f"{manifest_path} has no usable 'source_save'.")

    snapshot_save_dir = snapshot_root / source_save
    if not snapshot_save_dir.is_dir():
        raise SaveSnapshotError(f"{snapshot_save_dir} (the snapshot's copied save) is missing.")

    dest_name = as_name or source_save
    _validate_save_name(dest_name, what="restore destination name")
    dest = _saves_dir(runtime_dir) / dest_name

    if dest.exists() and not replace:
        raise SaveSnapshotError(f"{dest} already exists; pass replace=True (--replace) to overwrite it.")

    if dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(snapshot_save_dir, dest)

    return {
        "schema_version": 1,
        "mode": "SAVE_SNAPSHOT_RESTORE",
        "runtime_dir": str(runtime_dir),
        "tag": tag,
        "source_save": source_save,
        "restored_to": str(dest),
        "replaced": replace,
    }
