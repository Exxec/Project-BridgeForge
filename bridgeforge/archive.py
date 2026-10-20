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

from .zipsafe import read_limited

from .safeio import atomic_write_text

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


MAX_LISTED = 40


def _previous_version(previous_root: Path) -> str:
    info = _load_lenient_json_file(previous_root / "mod_info.json") if previous_root.is_dir() else None
    return _version_text(info.get("version")) if isinstance(info, dict) else "unknown version"


def _digest_tree(root: Path) -> dict[str, str]:
    """{relative path: sha256} of every file under a previous archive's mod folder (empty when there is none)."""
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): _digest(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _jar_entries(source: Path) -> dict[str, str] | None:
    """{entry name: sha256} of a jar's files, or None when it cannot be read as a zip."""
    try:
        with zipfile.ZipFile(source) as archive:
            return {i.filename: hashlib.sha256(read_limited(archive, i)).hexdigest() for i in archive.infolist() if not i.is_dir()}
    except (OSError, zipfile.BadZipFile):
        return None


def since_previous(previous_jars: dict[str, dict[str, str] | None], previous: dict[str, str], files: dict[str, Path]) -> dict:
    """What differs between the previous archive of this mod and the one being written: files changed, added and removed, and for each
    changed jar the classes inside it. Zorg18 V18+bf.7 was archived without two class-level fixes that an earlier line had carried;
    nothing showed it because the archive note only compared with the author's original (ROADMAP 70 H1.6)."""
    current = {relative: _digest(source) for relative, source in files.items()}
    changed = sorted(r for r in current if r in previous and current[r] != previous[r])
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    jars: dict[str, dict[str, list[str]]] = {}
    for relative in changed:
        if not relative.lower().endswith(".jar"):
            continue
        before, after = previous_jars.get(relative), _jar_entries(files[relative])
        if before is None or after is None:
            jars[relative] = {"changed": ["(a jar could not be read)"], "added": [], "removed": []}
            continue
        jars[relative] = {"changed": sorted(n for n in after if n in before and after[n] != before[n]),
                          "added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after))}
    return {"changed": changed, "added": added, "removed": removed, "jars": jars}


def _since_previous_section(previous_version: str, diff: dict) -> str:
    def listing(items: list[str]) -> str:
        shown = [f"  - `{i}`" for i in items[:MAX_LISTED]]
        return "\n".join(shown + ([f"  - ... {len(items) - MAX_LISTED} more"] if len(items) > MAX_LISTED else []))

    lines = [f"\n## Changes since the previous archive ({previous_version})\n"]
    if not (diff["changed"] or diff["added"] or diff["removed"]):
        return "".join(lines) + "\nNo shipped file differs from the previous archive.\n"
    for label, key in (("Changed", "changed"), ("Added", "added"), ("Removed", "removed")):
        if diff[key]:
            lines.append(f"\n{label} ({len(diff[key])}):\n{listing(diff[key])}\n")
    for jar, parts in diff["jars"].items():
        if any(parts.values()):
            lines.append(f"\nInside `{jar}`: " + "; ".join(f"{label} {len(items)}" for label, items in parts.items() if items) + "\n")
            for label, items in parts.items():
                if items:
                    lines.append(f"  {label}:\n{listing(items)}\n")
    lines.append("\nCheck this list against the changelog: a file that changed back to an earlier state, or a class that vanished, is a regression until explained.\n")
    return "".join(lines)


def _original_root(workspace: Path) -> Path | None:
    infos = sorted((workspace / "original").rglob("mod_info.json"), key=lambda p: len(p.parts)) if (workspace / "original").is_dir() else []
    return infos[0].parent if infos else None


def _final_status(report: Path) -> str | None:
    from .report_status import report_status

    return report_status(report)


def _live_line(workspace: Path) -> str:
    """The archive note's live sentence: always the date and test id of the last PASS, or why there are none (ROADMAP 65)."""
    from .live_trust import live_status

    live = live_status(workspace)
    if live.get("test_id"):
        state = ("the shipped files are the ones tested" if live["status"] == "CURRENT"
                 else "the run was not bound to staged inputs by a pre-launch manifest" if live["status"] == "UNBOUND"
                 else "the shipped files changed after that run")
        return f"Live-validated {live.get('date') or 'date not recorded'} (test {live['test_id']}); {state}."
    if live["status"] == "UNKNOWN_BUILD":
        return "Live-validated, but the date and test id were not recorded (a run before the 2026-10-04 run records)."
    return "Not live-tested: no passing run is recorded for this mod."


def _move_aside(target: Path, done_dir: Path, today: str, prefix: str = "_replaced") -> Path:
    """Move an existing Done/<Mod> to Done/_replaced-<date>/<Mod>[-N]; nothing is deleted. Refuses a holder that is a link."""
    from .boot_test import _is_link

    holder = done_dir / f"{prefix}-{today}"
    if holder.exists() and (_is_link(holder) or not holder.is_dir()):
        raise ArchiveError(f"refusing to move {target} into {holder}: it is a link or not a folder.")
    holder.mkdir(parents=True, exist_ok=True)
    destination = holder / target.name
    n = 2
    while destination.exists():
        destination = holder / f"{target.name}-{n}"
        n += 1
    shutil.move(str(target), str(destination))
    return destination


def archive_mod(workspace: Path, done_dir: Path, *, policy_path: Path | None = None, today: str | None = None,
                refresh: bool = False, move_aside: bool = False) -> dict:
    """Archive the workspace into done_dir/<workspace>. An earlier archive of the mod is never deleted: `refresh` (or `move_aside`)
    moves it to Done/_replaced-<date>/<Mod>[-N] first. If writing the new archive fails part-way, the partial one is moved to
    Done/_failed-<date>/ and the earlier archive is moved back; the ArchiveError says exactly where everything is (DOC-001)."""
    state: dict = {}
    try:
        return _archive_mod(workspace, done_dir, policy_path=policy_path, today=today, refresh=refresh, move_aside=move_aside, _state=state)
    except Exception as exc:
        moved = state.get("moved")
        if moved is None:
            raise
        replaced, target, done, day = moved
        notes = []
        try:
            if target.exists():
                notes.append(f"the partial new archive was moved to {_move_aside(target, done, day, '_failed')}")
            shutil.move(str(replaced), str(target))
            notes.append(f"the earlier archive was moved back to {target}")
        except (OSError, ArchiveError) as restore_error:
            notes.append(f"RESTORE FAILED ({restore_error}); the earlier archive is intact at {replaced}")
        raise ArchiveError(f"archiving failed ({type(exc).__name__}: {exc}); " + "; ".join(notes)) from exc


def _archive_mod(workspace: Path, done_dir: Path, *, policy_path: Path | None, today: str | None, refresh: bool, move_aside: bool,
                 _state: dict) -> dict:
    from .explain_proofs import prepare_for_audit
    from .master_log import write_master_log
    from .substitutes import revival_licence

    workspace = Path(workspace).expanduser().resolve()
    working = workspace / "working"
    if not (working / "mod_info.json").is_file():
        raise ArchiveError(f"{workspace} has no working/mod_info.json.")
    from .fixer_backups import orphaned_backups

    orphans = orphaned_backups(working)
    if orphans:
        shown = ", ".join(orphans[:5]) + (f" (+{len(orphans) - 5} more)" if len(orphans) > 5 else "")
        raise ArchiveError(f"refusing to archive {workspace.name}: fixer-backup-orphaned, a fixer backup has no file beside it ({shown}). "
                           "The fixed file was lost after the fix; restore it and rerun the fix (BUGS.md FIX-001).")
    info = _load_lenient_json_file(working / "mod_info.json") or {}
    mod_id, name, version = info.get("id"), str(info.get("name") or workspace.name), _version_text(info.get("version"))
    licence = revival_licence(mod_id, name, policy_path)
    if licence.get("decision") not in ("LOCAL_ONLY", "RELEASABLE"):
        raise ArchiveError(f"no licence decision for {mod_id}: record one first (bridgeforge release-policy set {mod_id} --local-only|--releasable --reason ...).")
    target = Path(done_dir).expanduser().resolve() / workspace.name
    prepared = prepare_for_audit(workspace)  # a zip original is extracted beside original/, translation records copied
    previous_root = target / workspace.name
    previous_digests = _digest_tree(previous_root)  # taken before the previous archive is moved aside or removed
    previous_version = _previous_version(previous_root)
    previous_jars = {r: _jar_entries(previous_root / r) for r in previous_digests if r.lower().endswith(".jar")}
    replaced = None
    done_resolved, day = Path(done_dir).expanduser().resolve(), today or date.today().isoformat()
    if target.exists() and refresh:
        if target.parent != done_resolved:
            raise ArchiveError(f"refusing to replace {target}: it is not directly inside {done_resolved}.")
        if not (target / "ARCHIVE_NOTE.md").is_file():
            raise ArchiveError(f"refusing to replace {target}: it has no ARCHIVE_NOTE.md, so it is not an archive made here.")
    if target.exists() and (move_aside or refresh):
        moved_to = _move_aside(target, done_resolved, day)
        replaced = str(moved_to)
        _state["moved"] = (moved_to, target, done_resolved, day)
    if target.exists():
        raise ArchiveError(f"{target} already exists; archive into a fresh folder or pass --refresh (the old one is moved aside, never deleted).")
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

    from .live_trust import original_root

    original = _original_root(workspace) or original_root(workspace)
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
                        zip_path.name, workspace.name, today or date.today().isoformat(), _live_line(workspace))
    diff = None
    if previous_digests:
        diff = since_previous(previous_jars, previous_digests, files)  # read before the previous archive was moved aside or removed
        note += _since_previous_section(previous_version, diff)
    atomic_write_text(target / "ARCHIVE_NOTE.md", note)
    # The mods' own changelog, beside Done/ (the repo root in use; a temp folder in tests).
    from .mod_changelog import add_entry
    add_entry(name, f"revived for RC8 and archived ({(status or 'no status').replace('_', ' ').lower()})", version=version,
              day=today or date.today().isoformat(), path=target.parent.parent / "MOD_CHANGELOG.md")
    try:
        master = write_master_log(target.parent)
    except OSError as exc:
        master = {"error": str(exc)}
    return {"schema_version": SCHEMA_VERSION, "mode": "ARCHIVE", "archive": str(target), "files": len(files), "zip": str(zip_path),
            "replaced": replaced, "prepared": prepared, "master_log": master,
            "licence": licence.get("decision"), "status": status, "changed": changed, "added": added, "since_previous": diff,
            "jars_identical": jars_identical, "note": str(target / "ARCHIVE_NOTE.md")}


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
                 jars_identical: bool | None, jar_names: list[str], has_original: bool, zip_name: str, folder: str, today: str, live_line: str = "") -> str:
    author = str(info.get("author") or "").strip() or "not named in the mod"
    local = licence.get("decision") == "LOCAL_ONLY"
    lines = [f"# {name} {version}: archive note", "", f"**Original author: {author}.** Revival for Starsector 0.98a-RC8: BridgeForge by Exxec.", ""]
    if local:
        lines += ["## Status: local archive only, not for publication", "",
                  f"Recorded in BridgeForge's `release_policy.json` as `LOCAL_ONLY`: {licence.get('reason') or 'no reason recorded'}.",
                  "Do not upload or redistribute this copy.", ""]
    else:
        lines += ["## Status: releasable", "", f"Recorded in `release_policy.json` as `RELEASABLE`: {licence.get('reason') or 'no reason recorded'}.", ""]
    lines += [f"Revival report status: **{status or 'none recorded'}** (archived {today}).", ""]
    if live_line:
        lines += [live_line, ""]
    lines += ["## What changed from the original", ""]
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
