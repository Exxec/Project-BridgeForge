"""`bridgeforge archive`: package a finished revival into `Done/<Mod>/` (ROADMAP P15 item 20.1).

ClearCommands, RevenantLib and Zorg18 were archived by hand on 2026-09-27 with the same layout; this is
that layout as one command. `release` cannot do it for a local-only mod: its licence gate always blocks
one, and its behaviour gate wants D-series evidence even when nothing that runs changed.

Layout: `<Folder>/` (the shipped files, `copy_drift._collect`), `<Folder>-<version>.zip`, `original/`,
`workspace/` (the revival reports, plan, baselines and the workspace's own reports), and `ARCHIVE_NOTE.md`
written from the mod's own data: author, version, the release-policy decision, the report's final status,
and which shipped files differ from the original, saying outright when every jar is byte-identical (the
evidence behind waiving the behaviour gate). Refuses with no licence decision on record and never
overwrites an existing archive or deletes the source workspace.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from datetime import date
from pathlib import Path

from .copy_drift import _collect
from .scanner import _load_lenient_json_file

SCHEMA_VERSION = 1


class ArchiveError(ValueError):
    """Raised for a missing workspace, no licence decision, or an archive that already exists."""


def _version_text(version: object) -> str:
    """mod_info `version` as text: a string, or the {"major","minor","patch"} object some mods use (Anex Weapons)."""
    if isinstance(version, dict):
        parts = [str(version.get(key)) for key in ("major", "minor", "patch") if version.get(key) not in (None, "")]
        return ".".join(parts) or "unversioned"
    return str(version or "unversioned")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _original_root(workspace: Path) -> Path | None:
    infos = sorted((workspace / "original").rglob("mod_info.json"), key=lambda p: len(p.parts)) if (workspace / "original").is_dir() else []
    return infos[0].parent if infos else None


def _final_status(report: Path) -> str | None:
    from .report_status import report_status

    return report_status(report)


def archive_mod(workspace: Path, done_dir: Path, *, policy_path: Path | None = None, today: str | None = None,
                refresh: bool = False) -> dict:
    from .substitutes import revival_licence

    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    if not (working / "mod_info.json").is_file():
        raise ArchiveError(f"{workspace} has no working/mod_info.json.")
    info = _load_lenient_json_file(working / "mod_info.json") or {}
    mod_id, name, version = info.get("id"), str(info.get("name") or workspace.name), _version_text(info.get("version"))
    licence = revival_licence(mod_id, name, policy_path)
    if licence.get("decision") not in ("LOCAL_ONLY", "RELEASABLE"):
        raise ArchiveError(f"no licence decision for {mod_id}: record one first (bridgeforge release-policy set {mod_id} --local-only|--releasable --reason ...).")
    target = Path(done_dir).expanduser().resolve() / workspace.name
    if target.exists():
        if not refresh:
            raise ArchiveError(f"{target} already exists; archive into a fresh folder or remove it first (or pass --refresh).")
        _remove_previous_archive(target, Path(done_dir).expanduser().resolve())
    folder = target / workspace.name
    files = _collect(working)
    for relative, source in files.items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, folder / relative)
    safe_version = re.sub(r"[^\w.+-]", "_", version)
    zip_path = target / f"{workspace.name}-{safe_version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for relative in sorted(files):
            archive.write(folder / relative, f"{workspace.name}/{relative}")
    if (workspace / "original").is_dir():
        shutil.copytree(workspace / "original", target / "original")
    # A copy of the mod with only the author's original descriptions, kept when BridgeForge wrote missing ones
    # (owner request 2026-09-28); archived beside the revival with its own zip.
    # Rebuilt from working/ now, not taken from the copy made when the descriptions were applied (Broken Star r2).
    from .descriptions import rebuild_original_descriptions_copy
    alt = rebuild_original_descriptions_copy(workspace) or workspace / "alt-original-descriptions" / workspace.name
    if alt.is_dir():
        shutil.copytree(alt, target / "alt-original-descriptions" / workspace.name)
        with zipfile.ZipFile(target / f"{workspace.name}-{safe_version}-original-descriptions.zip", "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(p for p in alt.rglob("*") if p.is_file()):
                archive.write(item, f"{workspace.name}/{item.relative_to(alt).as_posix()}")
    kept = target / "workspace"
    kept.mkdir()
    for source_dir in (working / "reports", workspace / "reports"):
        if not source_dir.is_dir():
            continue
        for item in sorted(source_dir.iterdir()):
            if item.is_file() and (item.suffix.lower() == ".md" or item.name.startswith("baseline")) and not (kept / item.name).exists():
                shutil.copy2(item, kept / item.name)

    original = _original_root(workspace)
    changed, added, jars_identical, jar_names = [], [], None, []
    if original is not None:
        for relative, source in sorted(files.items()):
            before = original / relative
            if relative.lower().endswith(".jar"):
                jar_names.append(relative)
                same = before.is_file() and _digest(before) == _digest(source)
                jars_identical = same if jars_identical is None else (jars_identical and same)
            if not before.is_file():
                added.append(relative)
            elif _digest(before) != _digest(source):
                changed.append(relative)
    status = _final_status(working / "reports" / "REVIVAL_REPORT.md")
    note = _render_note(info, name, version, licence, status, changed, added, jars_identical, jar_names, original is not None,
                        zip_path.name, workspace.name, today or date.today().isoformat())
    (target / "ARCHIVE_NOTE.md").write_text(note, encoding="utf-8")
    # The mods' own changelog, beside Done/ (the repo root in use; a temp folder in tests).
    from .mod_changelog import add_entry
    add_entry(name, f"revived for RC8 and archived ({(status or 'no status').replace('_', ' ').lower()})", version=version,
              day=today or date.today().isoformat(), path=target.parent.parent / "MOD_CHANGELOG.md")
    return {"schema_version": SCHEMA_VERSION, "mode": "ARCHIVE", "archive": str(target), "files": len(files), "zip": str(zip_path),
            "licence": licence.get("decision"), "status": status, "changed": changed, "added": added,
            "jars_identical": jars_identical, "note": str(target / "ARCHIVE_NOTE.md")}


def _remove_previous_archive(target: Path, done_dir: Path) -> None:
    """Delete one earlier archive so it can be rebuilt (`--refresh`). Only a direct child of the Done folder that holds
    an ARCHIVE_NOTE.md, so a wrong path can never remove anything else."""
    if target.parent != done_dir:
        raise ArchiveError(f"refusing to remove {target}: it is not directly inside {done_dir}.")
    if not (target / "ARCHIVE_NOTE.md").is_file():
        raise ArchiveError(f"refusing to remove {target}: it has no ARCHIVE_NOTE.md, so it is not an archive made here.")
    shutil.rmtree(target)


_CONTENTS_SECTION = re.compile(r"(?ms)^## Contents[ \t]*\r?\n.*?(?=^#{1,2} |\Z)")


def write_readme_copies(target: Path) -> list[str]:
    """For each zip in an archive folder, write `<name>-with-readme.zip` holding the same files plus a `readme.txt` taken from
    ARCHIVE_NOTE.md without its Contents section, and the folder's own `readme.txt`. Replaces what
    tools/copy-done-archives-with-readme.ps1 did for the whole Done/ tree, for one archive."""
    target = Path(target)
    note = (target / "ARCHIVE_NOTE.md").read_text(encoding="utf-8")
    readme = (_CONTENTS_SECTION.sub("", note).rstrip() + "\r\n").encode("utf-8")
    (target / "readme.txt").write_bytes(readme)
    written = []
    for source in sorted(target.glob("*.zip")):
        if source.stem.lower().endswith("-with-readme"):
            continue
        copy = source.with_name(source.stem + "-with-readme.zip")
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(copy, "w", zipfile.ZIP_DEFLATED) as out:
            for item in original.infolist():
                if item.filename.lower() != "readme.txt":
                    out.writestr(item, original.read(item.filename))
            out.writestr("readme.txt", readme)
        written.append(copy.name)
    return written


def _render_note(info: dict, name: str, version: str, licence: dict, status: str | None, changed: list[str], added: list[str],
                 jars_identical: bool | None, jar_names: list[str], has_original: bool, zip_name: str, folder: str, today: str) -> str:
    author = str(info.get("author") or "").strip() or "not named in the mod"
    local = licence.get("decision") == "LOCAL_ONLY"
    lines = [f"# {name} {version}: archive note", "", f"**Original author: {author}.** Revival for Starsector 0.98a-RC8: BridgeForge by Exxec.", ""]
    if local:
        lines += ["## Status: local archive only, not for publication", "",
                  f"Recorded in BridgeForge's `release_policy.json` as `LOCAL_ONLY`: {licence.get('reason') or 'no reason recorded'}.",
                  "Do not upload or redistribute this copy.", ""]
    else:
        lines += ["## Status: releasable", "", f"Recorded in `release_policy.json` as `RELEASABLE`: {licence.get('reason') or 'no reason recorded'}.", ""]
    lines += [f"Revival report status: **{status or 'none recorded'}** (archived {today}).", "", "## What changed from the original", ""]
    if not has_original:
        lines.append("`original/` holds no unpacked mod (only the download as archives, or nothing), so the changes cannot be "
                     "listed file by file here; see `workspace/REVIVAL_REPORT.md`.")
    else:
        lines.append(f"{len(changed)} shipped file(s) changed and {len(added)} added, compared byte for byte with `original/`:")
        lines += [f"- changed: `{item}`" for item in changed[:40]] + [f"- added: `{item}`" for item in added[:20]]
        if jar_names:
            lines.append("")
            lines.append("Every jar is byte-identical to the author's: no compiled code changed, so behaviour evidence beyond the "
                         "revival report's scans was not required." if jars_identical else "At least one jar differs from the original: see the revival report for how it was rebuilt and tested.")
    lines += ["", "See `workspace/REVIVAL_REPORT.md` for every change with its evidence.", "", "## Contents", "",
              f"- `{folder}/` - the mod folder, ready to drop into `mods/`.", f"- `{zip_name}` - the same folder, zipped.",
              "- `original/` - the download as received, unmodified.",
              "- `workspace/` - revival report, plan, baselines and the workspace's own reports.", ""]
    return "\n".join(lines)
