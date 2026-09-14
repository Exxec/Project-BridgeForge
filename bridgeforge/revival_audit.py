from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any


REQUIRED_VALIDATIONS = (
    "SOURCE REVIEW",
    "COMPILE",
    "STATIC VALIDATION",
    "PACKAGE VALIDATION",
    "DEPENDENCY CHECK",
    "API SIGNATURE CHECK",
    "SAVE COMPATIBILITY CHECK",
    "LIVE STARSECTOR TEST",
)
COMPLETION_STATUSES = (
    "READY",
    "READY_WITH_REVIEW_ITEMS",
    "ESCALATION_REQUIRED",
    "READY_FOR_LIVE_TEST",
)
COMPLETION_STATUS_PATTERN = re.compile(
    rf"^\s*(?:\*\*)?({'|'.join(sorted(COMPLETION_STATUSES, key=len, reverse=True))})(?:\*\*)?\s*$"
)


def _sha256_stream(handle: Any) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest().upper()


def _directory_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        with path.open("rb") as handle:
            inventory[path.relative_to(root).as_posix()] = {
                "size": path.stat().st_size,
                "sha256": _sha256_stream(handle),
            }
    return inventory


def _zip_inventory(archive: Path) -> tuple[dict[str, dict[str, Any]], str | None]:
    inventory: dict[str, dict[str, Any]] = {}
    with zipfile.ZipFile(archive) as bundle:
        files = [item for item in bundle.infolist() if not item.is_dir()]
        parts = [PurePosixPath(item.filename.replace("\\", "/")).parts for item in files]
        wrapper = parts[0][0] if parts and all(len(item) > 1 and item[0] == parts[0][0] for item in parts) else None
        for item, path_parts in zip(files, parts):
            relative_parts = path_parts[1:] if wrapper else path_parts
            relative = PurePosixPath(*relative_parts).as_posix()
            if relative in inventory:
                raise ValueError(f"Archive contains duplicate normalized path: {relative}")
            with bundle.open(item) as handle:
                inventory[relative] = {"size": item.file_size, "sha256": _sha256_stream(handle)}
    return inventory, wrapper


def _issue(identifier: str, severity: str, explanation: str, evidence: list[str] | None = None) -> dict[str, Any]:
    return {"id": identifier, "severity": severity, "explanation": explanation, "evidence": evidence or []}


def _validation_evidence(report: str) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for label in REQUIRED_VALIDATIONS:
        match = re.search(rf"(?im)^\s*[-*]\s*{re.escape(label)}\s*(?:—|–|-)\s*(.+?)\s*$", report)
        if match:
            evidence[label] = match.group(1).strip()
    return evidence


# Library names reports use, with the mod_info dependency ids they stand for.
_LIBRARY_DEPENDENCY_IDS = {
    "LazyLib": {"lw_lazylib"},
    "MagicLib": {"MagicLib"},
    "GraphicsLib": {"shaderLib"},
    "Nexerelin": {"nexerelin"},
    "LunaLib": {"lunalib"},
}


def _stale_dependency_claims(dependency_check: str, mod_info_path: Path) -> list[str]:
    """Libraries a DEPENDENCY CHECK clause calls declared that mod_info.json doesn't declare.

    Flu-X's report kept "LazyLib, MagicLib present and declared" after both were dropped from mod_info.
    Clauses (split on ';') that call a library optional or undeclared are ignored.
    """
    if not dependency_check or not mod_info_path.is_file():
        return []
    from .scanner import _load_lenient_json_file

    metadata = _load_lenient_json_file(mod_info_path)
    if not isinstance(metadata, dict):
        return []
    declared: set[str] = set()
    for item in metadata.get("dependencies") or []:
        if isinstance(item, dict):
            declared.update(str(item.get(key) or "").lower() for key in ("id", "name"))
    stale = []
    for clause in re.split(r"[;(]", dependency_check):
        # "were declared ... and were removed" records history, not a current claim.
        if not re.search(r"(?i)\bdeclared\b", clause) or re.search(r"(?i)optional|undeclared|not declared|removed|dropped|no longer|never used|unused", clause):
            continue
        for name, ids in _LIBRARY_DEPENDENCY_IDS.items():
            if re.search(rf"(?i)\b{name}\b", clause) and name.lower() not in declared and not {i.lower() for i in ids} & declared:
                stale.append(name)
    return sorted(set(stale))


def _completion_statuses(report: str) -> tuple[list[str], bool]:
    """Return every standalone status and whether the sole one ends the report."""
    nonempty_lines = [line for line in report.splitlines() if line.strip()]
    declared = [
        match.group(1)
        for line in nonempty_lines
        if (match := COMPLETION_STATUS_PATTERN.fullmatch(line))
    ]
    final = bool(nonempty_lines and COMPLETION_STATUS_PATTERN.fullmatch(nonempty_lines[-1]))
    return declared, final


def audit_revival(candidate: Path, archive: Path | None = None, *, reports_dir: Path | None = None) -> dict[str, Any]:
    """Audit report completeness and attest an optional release ZIP without modifying inputs."""
    root = candidate.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Revival candidate is not a directory: {root}")
    reports = reports_dir.expanduser().resolve() if reports_dir is not None else root / "reports"
    report_path = reports / "REVIVAL_REPORT.md"
    plan_path = reports / "REVIVAL_PLAN.md"
    if not report_path.is_file():
        raise ValueError(f"Missing required revival report: {report_path}")
    if not plan_path.is_file():
        raise ValueError(f"Missing required revival plan: {plan_path}")

    report = report_path.read_text(encoding="utf-8-sig")
    plan = plan_path.read_text(encoding="utf-8-sig")
    issues: list[dict[str, Any]] = []
    validations = _validation_evidence(report)
    for label in REQUIRED_VALIDATIONS:
        if label not in validations:
            issues.append(_issue("validation-stage-missing", "ERROR", f"The final report does not record {label} separately.", [label]))

    declared, status_is_final = _completion_statuses(report)
    if len(declared) != 1 or not status_is_final:
        issues.append(
            _issue(
                "completion-status-invalid",
                "ERROR",
                "The final report must contain exactly one recognized completion status, and it must be the final non-empty line.",
                [*declared, f"final:{str(status_is_final).lower()}"],
            )
        )

    for label, value in validations.items():
        unchecked = re.search(rf"(?im)^\s*[-*]\s*\[\s\]\s*{re.escape(label)}\b", plan)
        passed = re.search(r"\b(PASS|PERFORMED)\b", value, re.IGNORECASE)
        if unchecked and passed:
            issues.append(_issue("plan-validation-state-stale", "WARNING", f"The plan leaves {label} unchecked while the final report records completed evidence.", [label, value]))

    stale_claims = _stale_dependency_claims(validations.get("DEPENDENCY CHECK", ""), root / "mod_info.json")
    if stale_claims:
        issues.append(_issue("dependency-claim-stale", "WARNING", "The report's DEPENDENCY CHECK says these libraries are declared, but mod_info.json no longer declares them. Update the report or the metadata.", stale_claims))

    if "Done" in root.parts and re.search(r"(?i)(?:working copy|output package).*In operation", report):
        issues.append(_issue("report-path-state-stale", "WARNING", "The completed copy's report still identifies an In operation path; record both source and final artifact locations explicitly."))

    directory_inventory = _directory_inventory(root)
    package: dict[str, Any] = {"checked": False, "directory_file_count": len(directory_inventory)}
    if archive is None:
        issues.append(_issue("package-archive-not-checked", "WARNING", "No release ZIP was supplied, so directory-to-archive identity is unverified."))
    else:
        archive_path = archive.expanduser().resolve()
        if not archive_path.is_file():
            raise ValueError(f"Release archive is not a file: {archive_path}")
        with archive_path.open("rb") as handle:
            archive_sha256 = _sha256_stream(handle)
        try:
            archive_inventory, wrapper = _zip_inventory(archive_path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ValueError(f"Release archive cannot be read: {exc}") from exc
        missing = sorted(set(directory_inventory) - set(archive_inventory))
        extra = sorted(set(archive_inventory) - set(directory_inventory))
        changed = sorted(path for path in set(directory_inventory) & set(archive_inventory) if directory_inventory[path] != archive_inventory[path])
        package = {
            "checked": True,
            "archive": str(archive_path),
            "archive_sha256": archive_sha256,
            "wrapper_directory": wrapper,
            "directory_file_count": len(directory_inventory),
            "archive_file_count": len(archive_inventory),
            "missing_from_archive": missing,
            "extra_in_archive": extra,
            "content_mismatches": changed,
            "exact_match": not (missing or extra or changed),
        }
        if missing or extra or changed:
            issues.append(_issue("package-content-mismatch", "ERROR", "The release ZIP is not byte-identical to the candidate directory.", [f"missing:{len(missing)}", f"extra:{len(extra)}", f"changed:{len(changed)}"]))

    status = "FAIL" if any(item["severity"] == "ERROR" for item in issues) else "REVIEW" if issues else "PASS"
    return {
        "schema_version": 1,
        "status": status,
        "candidate": str(root),
        "declared_completion_status": declared[0] if len(declared) == 1 and status_is_final else None,
        "validation_evidence": validations,
        "package_attestation": package,
        "issues": issues,
    }
