"""P12 deterministic layout/evidence board. Directory placement is not validation."""
from __future__ import annotations

import json
from pathlib import Path
import re

from .boot_test import _is_link
from .intake import operation_root
from .revival_audit import _completion_statuses
from .scanner import _load_lenient_json_file


NON_RELEASE_FOLDERS = {"original", "working", "reports", "builds", "scratch", "workspace"}
ROOT_FILES = {"README.md", "STATUS.md", "LIVE_TEST_INSTRUCTIONS.md", "OFFLINE_VALIDATION_GUIDE.md", "bf-test.ps1",
              "STATUS.generated.md", "STATUS.generated.json", "DEPENDENCY_GRAPH.json", "DEPENDENCY_GRAPH.md"}


def layout_findings(repo_root: Path, working_copies: dict[str, Path] | None = None) -> list[dict[str, str]]:
    repo = repo_root.expanduser().resolve()
    operation = operation_root(repo)
    findings = []

    def issue(code: str, path: Path, detail: str):
        findings.append({"code": code, "path": str(path), "detail": detail})

    if operation.is_dir():
        for child in sorted(operation.iterdir()):
            if child.name.startswith("_") or child.name in ROOT_FILES or (
                child.is_file() and child.name.startswith("SWEEP_") and child.suffix == ".md"):
                continue
            if not child.is_dir() or _is_link(child):
                issue("root-stray", child, "not a physical convention-layout mod folder")
            elif not (child / "working" / "mod_info.json").is_file():
                issue("missing-working-copy", child, "expected <Mod>/working/mod_info.json; no files moved")
            elif _is_link(child / "working"):
                issue("linked-working-copy", child / "working", "working copy is a link/junction; inspect ownership before editing")
    for mod_id, path in sorted((working_copies or {}).items()):
        path = path.expanduser().resolve()
        valid_operation = path.name == "working" and path.parent.parent == operation
        valid_done = path.parent.parent == repo / "Done" and path.name not in NON_RELEASE_FOLDERS
        if not (valid_operation or valid_done):
            issue("nonconforming-working-copy", path, f"{mod_id}: outside In operation/<Mod>/working or Done/<Mod>/<release>")
    return sorted(findings, key=lambda item: (item["path"], item["code"]))


def _object(path: Path | None, warnings: list[str]) -> dict | None:
    if path is None or not path.exists():
        return None
    if _is_link(path):
        warnings.append(f"linked evidence not read: {path.name}")
        return None
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(result, dict):
            raise ValueError("expected JSON object")
        return result
    except (ValueError, OSError) as exc:
        warnings.append(f"invalid evidence {path.name}: {exc}")
        return None


def _row(area: str, folder: Path, working: Path | None) -> dict[str, object]:
    warnings: list[str] = []
    metadata = _load_lenient_json_file(working / "mod_info.json") if working is not None else None
    metadata = metadata if isinstance(metadata, dict) else {}
    if working is not None and not metadata:
        warnings.append("working metadata unavailable")
    def evidence_path(relative: str) -> Path | None:
        candidates = [folder / "reports" / relative]
        if area == "Done" and working is not None:
            candidates.insert(0, folder / "reports" / working.name / relative)
        if working is not None:
            candidates.append(working / "reports" / relative)
        for candidate in candidates:
            if candidate.exists():
                if any(_is_link(parent) for parent in (candidate, *candidate.parents) if parent.is_relative_to(folder)):
                    warnings.append(f"linked evidence not read: {relative}")
                    continue
                return candidate
        return None
    stage = "WORKING_COPY_PRESENT" if working is not None else "LAYOUT_INCOMPLETE"
    if area == "Done":
        stage = "RELEASE_PRESENT_NOT_VERIFIED" if working is not None else "LAYOUT_INCOMPLETE"
    declared_status = None
    report = evidence_path("REVIVAL_REPORT.md")
    if report is not None and report.is_file() and not _is_link(report):
        try:
            statuses, final = _completion_statuses(report.read_text(encoding="utf-8"))
            if len(statuses) == 1 and final:
                declared_status = statuses[0]
                if working is not None:
                    stage = "REPORT_DECLARED_" + declared_status
                else:
                    warnings.append("report exists without a convention-layout active copy")
            else:
                warnings.append("REVIVAL_REPORT has no single final completion status")
        except (OSError, ValueError) as exc:
            warnings.append(f"report unreadable: {exc}")
    elif working is not None and evidence_path("REVIVAL_PLAN.md") is not None:
        stage = "PLAN_PRESENT_NOT_APPROVAL_VERIFIED"
    intake = _object(evidence_path("intake.json"), warnings)
    if intake and declared_status is None and working is not None:
        marker = _object(folder / "intake-complete.json", warnings)
        if not marker or marker.get("archive_sha256") != intake.get("archive_sha256"):
            stage = "INTAKE_INCOMPLETE"
        elif stage == "WORKING_COPY_PRESENT":
            stage = "ASSESSMENT_REQUIRED"
    risk_path = evidence_path("discovery/risks.json")
    if risk_path is None:
        risk_path = evidence_path("risks.json")
    risk_document = _object(risk_path, warnings)
    open_risks = None
    if risk_document is not None:
        risks = risk_document.get("risks")
        if isinstance(risks, list) and all(isinstance(item, dict) and isinstance(item.get("status"), str) for item in risks):
            open_risks = sum(item["status"] != "CLOSED" for item in risks)
        else:
            warnings.append("risk list missing/malformed; risk count unknown")
    test_path = evidence_path("last-test.json")
    last_test = _object(test_path, warnings)
    if last_test is not None and not all(isinstance(last_test.get(key), str) and last_test[key]
                                         for key in ("test_id", "status", "build")):
        warnings.append("last-test requires nonempty test_id/status/build; last test unknown")
        last_test = None
    dependencies = None
    dependency_path = evidence_path("dependencies.json")
    dependency_document = _object(dependency_path, warnings)
    if dependency_document is not None:
        blockers = [item.get("mod_id") for item in dependency_document.get("provider_set") or []
                    if isinstance(item, dict) and not item.get("targets_0.98a")]
        dependencies = {"strategy": dependency_document.get("strategy"), "needs_revival_of": blockers,
                        "unprovided": len(dependency_document.get("uncovered") or []),
                        "recorded": str(dependency_document.get("generated_at") or "unknown")[:10]}
        # Evidence, not a live answer: say so when the mod was rescanned after it was recorded.
        scans = sorted((folder / "reports").glob("scan-*/bridgeforge.compat.json"), key=lambda path: path.stat().st_mtime)
        if scans and dependency_path is not None and scans[-1].stat().st_mtime > dependency_path.stat().st_mtime:
            warnings.append("rescanned since dependencies.json was recorded; rerun dependency-substitutes --write")
    name = metadata.get("name")
    version = metadata.get("version")
    tags = re.findall(r"\[BF r(\d+)\]", str(name)) + re.findall(r"\+bf\.(\d+)", str(version))
    build_tag = "r" + tags[0] if tags and len(set(tags)) == 1 else None
    if len(set(tags)) > 1:
        warnings.append("name/version build tags disagree")
    if last_test is not None and last_test["build"] != build_tag:
        warnings.append("last test does not match current build tag")
    if area == "Done" and report is not None and report.is_file() and report.parent == folder / "reports":
        warnings.append("folder-level report is not independently bound to this release")
    return {"area": area, "folder": folder.name, "mod_id": metadata.get("id"),
            "working": str(working) if working is not None else None, "stage": stage,
            "declared_completion_status": declared_status, "build_tag": build_tag,
            "last_test": last_test, "open_risks": open_risks, "dependencies": dependencies, "warnings": warnings,
            "evidence": {"report": str(report) if report is not None else None,
                         "dependencies": str(dependency_path) if dependency_path is not None else None,
                         "risks": str(risk_path) if risk_path is not None else None,
                         "last_test": str(test_path) if test_path is not None else None}}


def project_board(repo_root: Path) -> dict[str, object]:
    repo = repo_root.expanduser().resolve()
    operation = operation_root(repo)
    rows = []
    for area, base in (("In operation", operation), ("Done", repo / "Done")):
        if not base.is_dir() or _is_link(base):
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith("_") and not _is_link(p)):
            if area == "In operation":
                candidate = folder / "working"
                working = candidate if not _is_link(candidate) and (candidate / "mod_info.json").is_file() else None
                rows.append(_row(area, folder, working))
            else:
                candidates = sorted(p for p in folder.iterdir() if p.is_dir() and
                                    p.name not in NON_RELEASE_FOLDERS and not _is_link(p) and (p / "mod_info.json").is_file())
                if candidates:
                    for working in candidates:
                        rows.append({**_row(area, folder, working), "release_folder": working.name})
                else:
                    rows.append(_row(area, folder, None))
    graph = None
    graph_path = operation / "DEPENDENCY_GRAPH.json"
    if graph_path.is_file() and not _is_link(graph_path):
        document = _object(graph_path, [])
        if document is not None and isinstance(document.get("revival_order"), list):
            graph = {"generated_at": document.get("generated_at"), "queued_mods": document.get("queued_mods"),
                     "revival_order": [{"name": entry.get("name"), "unblocks": entry.get("unblocks") or [],
                                        "licence": (entry.get("licence") or {}).get("decision")}
                                       for entry in document["revival_order"] if isinstance(entry, dict)]}
    return {"schema_version": 1, "mode": "PROJECT_BOARD", "repo_root": str(repo), "mods": rows,
            "dependency_graph": graph,
            "layout_findings": layout_findings(repo),
            "note": "Declared evidence only, not release/live validation. Missing risks/test evidence is unknown."}


def render_board(board: dict[str, object]) -> str:
    def cell(value):
        return str(value if value is not None else "unknown").replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["# BridgeForge generated status board", "", str(board["note"]), "",
             "| Area / mod | Stage | Build | Last declared test | Open risks | Dependencies |",
             "|---|---|---|---|---|---|"]
    warnings = []
    for row in board["mods"]:
        test = row["last_test"]
        test_label = f"{test['test_id']} {test['status']} ({test['build']})" if test else None
        label = row["area"] + " / " + row["folder"]
        if row.get("release_folder"):
            label += " / " + row["release_folder"]
        deps = row.get("dependencies")
        deps_label = None
        if deps:
            deps_label = str(deps["strategy"]) + (f": revive {', '.join(map(str, deps['needs_revival_of']))}" if deps["needs_revival_of"] else "") \
                + (f"; {deps['unprovided']} unprovided" if deps["unprovided"] else "") + f" (as of {deps['recorded']})"
        lines.append("| " + " | ".join(cell(value) for value in (label, row["stage"], row["build_tag"], test_label, row["open_risks"], deps_label)) + " |")
        for warning in row["warnings"]:
            warnings.append(f"- {cell(label)}: {cell(warning)}")
    graph = board.get("dependency_graph")
    if graph:
        lines.extend(["", f"## Revival order (dependency-graph, as of {cell(str(graph.get('generated_at'))[:10])})", ""])
        lines.extend(f"{number}. {cell(entry['name'])}: unblocks {len(entry['unblocks'])} ({cell(', '.join(entry['unblocks']))})"
                     + (f", licence {cell(entry['licence'])}" if entry.get("licence") else "")
                     for number, entry in enumerate(graph["revival_order"], 1))
        if not graph["revival_order"]:
            lines.append("Nothing queued needs an old dependency revived.")
    if warnings:
        lines.extend(["", "## Evidence warnings", "", *warnings])
    lines.extend(["", "## Layout findings", ""])
    lines.extend(f"- {item['code']}: {cell(item['path'])} — {cell(item['detail'])}" for item in board["layout_findings"])
    if not board["layout_findings"]:
        lines.append("None found by convention checks (not an exhaustive filesystem audit).")
    return "\n".join(lines) + "\n"


def write_board(board: dict[str, object], repo_root: Path) -> list[str]:
    operation = operation_root(repo_root, create=True)
    files = [(operation / "STATUS.generated.json", json.dumps(board, indent=2, sort_keys=True) + "\n"),
             (operation / "STATUS.generated.md", render_board(board))]
    for path, _ in files:
        if _is_link(path) or (path.exists() and not path.is_file()):
            raise ValueError(f"refusing linked/non-file board output: {path}")
    for path, text in files:
        path.write_text(text, encoding="utf-8")
    return [str(path) for path, _ in files]
