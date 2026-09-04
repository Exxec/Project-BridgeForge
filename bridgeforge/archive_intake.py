from __future__ import annotations

from collections import Counter
import hashlib
import json
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import stat


def _normalized_member_name(name: str) -> str | None:
    """Return a portable extraction target, or None when the ZIP member is unsafe."""
    portable = name.replace("\\", "/")
    if "\x00" in portable or portable.startswith("/") or re.match(r"^[A-Za-z]:/", portable):
        return None
    parts = PurePosixPath(portable).parts
    if ".." in parts:
        return None
    return "/".join(part for part in parts if part not in (".", "/"))


def inspect_zip_archive(path: Path, max_entries: int = 20_000, max_uncompressed_bytes: int = 800 * 1024 * 1024) -> dict:
    """Read ZIP metadata only; identify extraction hazards and mod-root ambiguity."""
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ValueError(f"Archive is not a readable ZIP file: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Archive is not a readable ZIP file: {path}") from exc
    total = sum(entry.file_size for entry in entries)
    normalized = [_normalized_member_name(entry.filename) for entry in entries]
    unsafe = sorted(entry.filename for entry, name in zip(entries, normalized) if name is None)
    symlinks = sorted(entry.filename for entry in entries if stat.S_ISLNK(entry.external_attr >> 16))
    duplicates = sorted(name for name, count in Counter(name for name in normalized if name).items() if count > 1)
    mod_info = sorted(name for name in normalized if name and PurePosixPath(name).name == "mod_info.json")
    roots = sorted({str(PurePosixPath(name).parent) if str(PurePosixPath(name).parent) != "." else "." for name in mod_info})
    findings = []
    if len(entries) > max_entries:
        findings.append({"id": "archive-entry-limit", "classification": "REVIEW", "count": len(entries), "limit": max_entries})
    if total > max_uncompressed_bytes:
        findings.append({"id": "archive-size-limit", "classification": "REVIEW", "bytes": total, "limit": max_uncompressed_bytes})
    if unsafe:
        findings.append({"id": "archive-path-traversal", "classification": "MANUAL", "entries": unsafe})
    if symlinks:
        findings.append({"id": "archive-symlink-member", "classification": "MANUAL", "entries": symlinks})
    if duplicates:
        findings.append({"id": "archive-duplicate-member", "classification": "REVIEW", "entries": duplicates})
    if not mod_info:
        findings.append({"id": "archive-no-mod-info", "classification": "REVIEW", "explanation": "No mod_info.json member was found; extraction may not yield a selectable mod root."})
    elif len(mod_info) > 1:
        findings.append({"id": "archive-multiple-mod-info", "classification": "MANUAL", "entries": mod_info, "explanation": "Multiple candidate mod roots require explicit ownership selection."})
    elif roots != ["."]:
        findings.append({"id": "archive-wrapper-directory-layout", "classification": "REVIEW", "mod_root": roots[0], "explanation": "The archive has one wrapper directory; select the nested mod root after staging."})
    blocking_ids = {"archive-entry-limit", "archive-size-limit", "archive-path-traversal", "archive-symlink-member", "archive-duplicate-member"}
    safe_to_stage = not any(item["id"] in blocking_ids for item in findings)
    return {"schema_version": 1, "mode": "ZIP_PREFLIGHT_ONLY", "archive": path.name, "entry_count": len(entries), "uncompressed_bytes": total, "mod_info_entries": mod_info, "candidate_mod_roots": roots, "findings": findings, "safe_to_stage": safe_to_stage, "safe_to_extract": safe_to_stage}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_zip_archive(path: Path, destination: Path, selected_root: str | None = None, manifest_output: Path | None = None) -> Path:
    """Extract a preflight-safe ZIP into a new or empty explicit destination only."""
    path = path.expanduser().resolve()
    destination = destination.expanduser().resolve()
    archive_sha256 = _sha256(path)
    report = inspect_zip_archive(path)
    if not report["safe_to_stage"]:
        raise ValueError("Archive staging is blocked by preflight extraction hazards.")
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Archive staging destination must be new or empty.")
    if destination == path.parent:
        raise ValueError("Archive staging destination must not be the archive's containing directory.")
    roots = report["candidate_mod_roots"]
    if selected_root is not None and selected_root not in roots:
        raise ValueError("Selected archive mod root is not a preflight candidate.")
    if len(roots) > 1 and selected_root is None:
        raise ValueError("Archive has multiple mod roots; select one explicitly before staging.")
    selected_root = selected_root or (roots[0] if len(roots) == 1 else None)
    manifest = (manifest_output.expanduser().resolve() if manifest_output else destination.parent / f"{destination.name}.bridgeforge-stage.json")
    if manifest == path or manifest.is_relative_to(destination):
        raise ValueError("Archive stage manifest must be outside the staged destination and must not replace the input archive.")
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for entry in archive.infolist():
            name = _normalized_member_name(entry.filename)
            if not name or entry.is_dir():
                continue
            target = destination.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"schema_version": 1, "mode": "EXPLICIT_ARCHIVE_STAGE", "archive": path.name, "archive_sha256": archive_sha256, "destination": destination.name, "staged_tree_sha256": _tree_sha256(destination), "selected_mod_root": selected_root, "preflight": report, "input_preserved": archive_sha256 == _sha256(path)}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def _tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((item for item in root.rglob("*") if item.is_file()), key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()
