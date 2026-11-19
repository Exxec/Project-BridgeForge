"""P12 source-preserving intake; assessment is not approval to change a mod."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .archive_intake import _normalized_member_name, _sha256, _tree_sha256, inspect_zip_archive, stage_zip_archive
from .behavior_discovery import write_archaeology
from .boot_test import _is_link
from .dossier import build_dossier
from .models import TargetProfile
from .report import write_artifacts
from bridgeforge.scan.scanner import scan_mod


def operation_root(repo_root: Path, *, create: bool = False) -> Path:
    repo = repo_root.expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"repository directory does not exist: {repo}")
    operation = repo / "In operation"
    if _is_link(operation):
        raise ValueError("In operation must be a physical directory, not a link/junction")
    if operation.exists() and not operation.is_dir():
        raise ValueError("In operation exists but is not a directory")
    if create:
        operation.mkdir(exist_ok=True)
    return operation


RENAME_ATTEMPTS = 12
RENAME_MAX_WAIT_SECONDS = 8.0


def _rename_with_retry(source: Path, target: Path, attempts: int = RENAME_ATTEMPTS, sleep=None) -> None:
    """Rename, retrying a Windows PermissionError: a freshly extracted tree is often held open for a moment by
    antivirus or indexing, so renaming it failed with 'Access is denied' twice in a row for the 9-mod Yunru pack
    (2026-10-04). The first scan of new bytes can take longer: Exotica RC4 (8 MB) and New Galactic Order (35 MB) both
    failed after the old ~14 s of retries and both passed on an immediate rerun of the same bytes (2026-10-26), so the
    waits now grow to 8 s each, about a minute in all. Any other error, or the last attempt's, is raised."""
    import time

    sleep = sleep or time.sleep
    for attempt in range(attempts):
        try:
            source.rename(target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            sleep(min(1.0 * (attempt + 1), RENAME_MAX_WAIT_SECONDS))


def _folder_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _.\-]*", name) or _normalized_member_name(name) != name:
        raise ValueError("mod folder name must be one portable component starting with a letter/digit")
    return name


def _relocate_reports(reports: Path, stage: Path, destination: Path) -> None:
    replacements = [(str(stage), str(destination)), (stage.as_posix(), destination.as_posix()),
                    (json.dumps(str(stage))[1:-1], json.dumps(str(destination))[1:-1])]
    for path in reports.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".md"}:
            text = path.read_text(encoding="utf-8")
            for old, new in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
                text = text.replace(old, new)
            path.write_text(text, encoding="utf-8")


def resolve_mod_folder(query: str, mods_dir: Path) -> Path:
    """The one folder under `mods_dir` a loose name means: each query word is matched to its closest word of the folder name
    ("koch" -> "Everybody loves KoC-1.05.49a", "eridiani combine" -> "Eridani Combine-1.0.3.6"). Refuses no match or a tie,
    naming the candidates (ROADMAP-3 item 92.5, 2026-11-16: six intakes each needed the exact folder name by hand)."""
    from difflib import SequenceMatcher

    def words(text: str) -> list[str]:
        return [w for w in re.findall(r"[a-z]+", text.casefold()) if len(w) > 1 or not text.strip()]

    wanted = words(query)
    if not wanted:
        raise ValueError(f"nothing to match in {query!r}")
    scored = []
    for folder in sorted(p for p in Path(mods_dir).iterdir() if p.is_dir()):
        have = words(folder.name)
        if not have:
            continue
        score = sum(max(SequenceMatcher(None, w, h).ratio() for h in have) for w in wanted) / len(wanted)
        scored.append((score, folder))
    scored.sort(key=lambda item: -item[0])
    if not scored or scored[0][0] < 0.8:
        raise ValueError(f"no folder in {mods_dir} matches {query!r}")
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        tied = ", ".join(f.name for s, f in scored[:3] if scored[0][0] - s < 0.05)
        raise ValueError(f"{query!r} is ambiguous in {mods_dir}: {tied}")
    return scored[0][1]


def _blocking(preflight: dict) -> list[dict]:
    return [f for f in preflight.get("findings") or [] if f.get("classification") in ("MANUAL", "UNKNOWN")]


def strip_junk_members(archive: Path, entries: list[str]) -> Path:
    """`<name>-clean.zip` beside the archive without exactly the named junk members (editor backups `*~`, `desktop.ini`,
    copies); the raw archive is kept. ROADMAP-3 item 92.4 (2026-11-16): 2 of 6 intakes (Scrapyard Armories: four `*.png~`;
    Navarchy of Tania: two `*.png~` and a `desktop.ini`) were blocked and rebuilt by hand."""
    from .zipsafe import read_limited

    clean = archive.with_name(f"{archive.stem}-clean{archive.suffix}")
    if clean.exists():
        raise ValueError(f"{clean.name} already exists; intake never overwrites it (remove it or intake it directly)")
    drop = set(entries)
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(clean, "w", zipfile.ZIP_DEFLATED) as target:
        for info in source.infolist():
            if info.filename not in drop:
                target.writestr(info, read_limited(source, info))
    return clean


def intake_archive(archive: Path, repo_root: Path, *, name: str | None = None,
                   selected_root: str | None = None, archaeology: bool = False, strip_junk: bool = False) -> dict[str, object]:
    archive = archive.expanduser().resolve()
    preflight = inspect_zip_archive(archive)
    raw_archive, stripped = None, []
    blocking = _blocking(preflight)
    if not preflight["safe_to_stage"] and strip_junk and blocking and all(f["id"] == "archive-junk-member" for f in blocking):
        stripped = sorted({entry for f in blocking for entry in f.get("entries") or []})
        raw_archive, archive = archive, strip_junk_members(archive, stripped)
        preflight = inspect_zip_archive(archive)
        blocking = _blocking(preflight)
    if not preflight["safe_to_stage"]:
        # Name the hazards: the bare message sent the user to `archive-preflight` to find out (2026-11-16).
        detail = "; ".join(f"{f['id']} ({f['classification']}): {', '.join((f.get('entries') or [])[:6]) or f.get('explanation', '')}"
                           for f in blocking) or "see `bridgeforge archive-preflight`"
        hint = " (only junk members: rerun with --strip-junk)" if blocking and all(f["id"] == "archive-junk-member" for f in blocking) else ""
        raise ValueError(f"intake blocked by archive preflight hazards: {detail}{hint}")
    roots = preflight["candidate_mod_roots"]
    if selected_root is None:
        if len(roots) != 1:
            raise ValueError("intake needs one mod root; use --selected-root for an ambiguous ZIP")
        selected_root = roots[0]
    if selected_root not in roots:
        raise ValueError("selected root is not an archive mod-root candidate")
    if name is not None:
        _folder_name(name)
    operation = operation_root(repo_root, create=True)
    original_hash = _sha256(archive)
    with tempfile.TemporaryDirectory(prefix="_intake-", dir=operation) as temporary:
        stage = Path(temporary).resolve()
        for directory in ("original", "reports", "builds", "scratch"):
            (stage / directory).mkdir()
        stored_archive = stage / "original" / "archive" / archive.name
        stored_archive.parent.mkdir()
        shutil.copyfile(archive, stored_archive)
        if _sha256(stored_archive) != original_hash or _sha256(archive) != original_hash:
            raise ValueError("archive changed during intake; no working copy published")
        extracted = stage / "original" / "extracted"
        stage_zip_archive(stored_archive, extracted, selected_root=selected_root,
                          manifest_output=stage / "reports" / "archive-stage.json")
        upstream_root = extracted if selected_root == "." else extracted.joinpath(*selected_root.split("/"))
        extracted_hash = _tree_sha256(extracted)
        upstream_hash = _tree_sha256(upstream_root)
        working = stage / "working"
        shutil.copytree(upstream_root, working)
        result = scan_mod(working, TargetProfile())
        if not isinstance(result.metadata.get("id"), str) or not result.metadata["id"].strip():
            raise ValueError("selected mod root must have parseable metadata with a nonempty string id")
        folder = _folder_name(name if name is not None else re.sub(
            r"[^A-Za-z0-9_.-]+", "-", result.metadata["id"]).strip("-._"))
        destination = operation / folder
        if any(child.name.casefold() == folder.casefold() for child in operation.iterdir()):
            raise ValueError(f"mod folder already exists; intake never overwrites it: {destination}")
        reports = stage / "reports"
        write_artifacts(result, reports / "scan")
        # The generic dossier writer intentionally refuses In operation/Done. Keep that
        # contract: serialize the read-only builder only into this fresh owned report tree.
        dossier = build_dossier(working)
        dossier_dir = reports / "dossier"
        dossier_dir.mkdir()
        (dossier_dir / "dossier.json").write_text(json.dumps(dossier["index"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (dossier_dir / "dossier.md").write_text(dossier["index_markdown"], encoding="utf-8")
        for part in dossier["parts"]:
            (dossier_dir / part["json_file"]).write_text(part["json_text"] + "\n", encoding="utf-8")
            (dossier_dir / part["markdown_file"]).write_text(part["markdown_text"], encoding="utf-8")
        if archaeology:
            write_archaeology(working, reports / "discovery")
        if (upstream_hash != _tree_sha256(working) or extracted_hash != _tree_sha256(extracted)
                or _sha256(stored_archive) != original_hash):
            raise ValueError("analysis changed preserved/working bytes; no intake published")
        manifest = {"schema_version": 1, "mode": "INTAKE", "status": "ASSESSMENT_REQUIRED",
                    "mod_id": result.metadata["id"], "mod_folder": folder,
                    "archive": archive.name, "archive_sha256": original_hash,
                    "selected_root": selected_root, "upstream_tree_sha256": upstream_hash,
                    "extracted_tree_sha256": extracted_hash,
                    "working_tree_sha256": upstream_hash,
                    "finding_counts": dict(sorted(Counter(f.classification for f in result.findings).items())),
                    "archaeology": archaeology, "live_test": "LIVE TEST NOT PERFORMED"}
        if raw_archive is not None:  # --strip-junk: what was dropped, and from which raw archive
            manifest.update({"raw_archive": raw_archive.name, "raw_archive_sha256": _sha256(raw_archive), "stripped_members": stripped})
        (reports / "intake.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (reports / "INTAKE_REPORT.md").write_text(
            "# Intake assessment\n\nArchive and upstream extract preserved; working bytes match selected upstream root.\n\n"
            "Scan/dossier are static evidence, not approval, compile proof or runtime assurance.\n"
            "Before editing: complete REVIVAL_PLAN.md, classify findings, score complexity and route review using\n"
            "docs/REVIVAL_WORKFLOW.md and docs/REVIVAL_TEMPLATE.md.\n\nLIVE TEST NOT PERFORMED\n\nASSESSMENT_REQUIRED\n",
            encoding="utf-8")
        _relocate_reports(reports, stage, destination)
        if _sha256(archive) != original_hash:
            raise ValueError("input archive changed before publication")
        marker = stage / "intake-complete.json"
        marker.write_text(json.dumps({"schema_version": 1, "archive_sha256": original_hash}) + "\n", encoding="utf-8")
        # Exclusive reservation prevents replacement, including on POSIX where rename
        # could otherwise replace an existing empty directory. Roll back only our moves.
        destination.mkdir()
        moved = []
        try:
            for child in sorted(p for p in stage.iterdir() if p != marker):
                _rename_with_retry(child, destination / child.name)
                moved.append(child.name)
            _rename_with_retry(marker, destination / marker.name)
        except BaseException:
            for child_name in reversed(moved):
                (destination / child_name).rename(stage / child_name)
            destination.rmdir()
            raise
    return {**manifest, "destination": str(destination), "working": str(destination / "working"),
            "reports": str(destination / "reports")}


RAW_ZIP_FOLDER = "_raw-zips"


def _mod_root_of(folder: Path) -> Path | None:
    """The folder holding mod_info.json: the folder itself or its only subfolder that does."""
    from .mod_files import nearest_mod_root

    return nearest_mod_root(folder)


def zip_raw_folder(folder: Path, repo_root: Path) -> Path:
    """Zip a raw mod folder (a mod dropped unpacked in the queue) to `In operation/_raw-zips/<name>.zip` so `intake` can take it
    in as an archive, as the owner did by hand for Yellowjackets and Neutrino (ROADMAP 65). The folder is only read, nothing is
    overwritten (an existing zip is reused only when it holds exactly these files), and links are never followed."""
    import zipfile

    folder = folder.expanduser().resolve()
    root = _mod_root_of(folder)
    if root is None:
        raise ValueError(f"{folder} is not a mod folder: no mod_info.json at its top or in its only subfolder.")
    # A modpack folder may carry a note in its name ("... V2.5.2 (DISABLE UI SCALING OR ELSE ...!)", 2026-10-13): the zip and its
    # inner folder get a portable spelling of it; the folder itself is not renamed.
    name = _folder_name(re.sub(r"[^A-Za-z0-9 _.\-]+", "-", folder.name).strip("-._ "))
    target_dir = operation_root(repo_root, create=True) / RAW_ZIP_FOLDER
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"{name}.zip"
    files = sorted(p for p in folder.rglob("*") if p.is_file() and not _is_link(p))
    if target.exists():
        with zipfile.ZipFile(target) as existing:
            same = sorted(existing.namelist()) == sorted(f"{name}/{p.relative_to(folder).as_posix()}" for p in files)
        if not same:
            raise ValueError(f"{target} already exists with different content; intake never overwrites it.")
        return target
    temporary = target.with_suffix(".zip.part")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"{name}/{path.relative_to(folder).as_posix()}")
    temporary.replace(target)
    return target


def unprocessed_raw_folders(queue: Path) -> list[dict[str, str]]:
    """Folders in the queue that hold a mod but are no workspace (no working/ copy, no original/): a mod dropped in unpacked
    and not yet taken in. The planner lists them so they are not forgotten (ROADMAP 65)."""
    queue = Path(queue)
    found = []
    for child in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_")) if queue.is_dir() else []:
        if (child / "working").is_dir() or (child / "original").is_dir():
            continue
        root = _mod_root_of(child)
        if root is not None:
            found.append({"folder": child.name, "mod_root": root.relative_to(child).as_posix(), "next": f'bridgeforge intake "{child}"'})
    return found
