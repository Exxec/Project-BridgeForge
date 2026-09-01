from __future__ import annotations

from collections import Counter
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
import re
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
    """Read ZIP metadata only; reject unsafe members before any extraction workflow."""
    path = path.expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != ".zip":
        raise ValueError(f"Archive is not a readable ZIP file: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Archive is not a readable ZIP file: {path}") from exc
    total = sum(entry.file_size for entry in entries)
    unsafe = sorted(entry.filename for entry in entries if _normalized_member_name(entry.filename) is None)
    symlinks = sorted(entry.filename for entry in entries if stat.S_ISLNK(entry.external_attr >> 16))
    normalized = [_normalized_member_name(entry.filename) for entry in entries]
    duplicates = sorted(name for name, count in Counter(name for name in normalized if name).items() if count > 1)
    mod_info = sorted(entry.filename for entry in entries if Path(entry.filename).name == "mod_info.json")
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
    return {"schema_version": 1, "mode": "ZIP_PREFLIGHT_ONLY", "archive": path.name, "entry_count": len(entries), "uncompressed_bytes": total, "mod_info_entries": mod_info, "findings": findings, "safe_to_extract": not findings}
