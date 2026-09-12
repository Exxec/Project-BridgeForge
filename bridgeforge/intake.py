"""P12 source-preserving intake; assessment is not approval to change a mod."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import shutil
import tempfile

from .archive_intake import _normalized_member_name, _sha256, _tree_sha256, inspect_zip_archive, stage_zip_archive
from .behavior_discovery import write_archaeology
from .boot_test import _is_link
from .dossier import build_dossier
from .models import TargetProfile
from .report import write_artifacts
from .scanner import scan_mod


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


def intake_archive(archive: Path, repo_root: Path, *, name: str | None = None,
                   selected_root: str | None = None, archaeology: bool = False) -> dict[str, object]:
    archive = archive.expanduser().resolve()
    preflight = inspect_zip_archive(archive)
    if not preflight["safe_to_stage"]:
        raise ValueError("intake blocked by archive preflight hazards")
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
                child.rename(destination / child.name)
                moved.append(child.name)
            marker.rename(destination / marker.name)
        except BaseException:
            for child_name in reversed(moved):
                (destination / child_name).rename(stage / child_name)
            destination.rmdir()
            raise
    return {**manifest, "destination": str(destination), "working": str(destination / "working"),
            "reports": str(destination / "reports")}
