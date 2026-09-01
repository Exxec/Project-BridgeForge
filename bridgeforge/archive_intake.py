from __future__ import annotations

import zipfile
from pathlib import Path


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
    unsafe = sorted(entry.filename for entry in entries if Path(entry.filename).is_absolute() or ".." in Path(entry.filename).parts)
    mod_info = sorted(entry.filename for entry in entries if Path(entry.filename).name == "mod_info.json")
    findings = []
    if len(entries) > max_entries:
        findings.append({"id": "archive-entry-limit", "classification": "REVIEW", "count": len(entries), "limit": max_entries})
    if total > max_uncompressed_bytes:
        findings.append({"id": "archive-size-limit", "classification": "REVIEW", "bytes": total, "limit": max_uncompressed_bytes})
    if unsafe:
        findings.append({"id": "archive-path-traversal", "classification": "MANUAL", "entries": unsafe})
    return {"schema_version": 1, "mode": "ZIP_PREFLIGHT_ONLY", "archive": path.name, "entry_count": len(entries), "uncompressed_bytes": total, "mod_info_entries": mod_info, "findings": findings, "safe_to_extract": not findings}
