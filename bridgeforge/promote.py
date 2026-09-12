"""P12 promotion: staged gates, recoverable prior releases, no speculative readiness."""
from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import uuid

from .archive_intake import _sha256, _tree_sha256
from .boot_test import _is_link
from .intake import _folder_name, operation_root
from .project_board import NON_RELEASE_FOLDERS
from .release import _release_basename, release_mod
from .revival_audit import audit_revival
from .scanner import _load_lenient_json_file


def _physical(path: Path):
    if any(_is_link(parent) for parent in (path, *path.parents)):
        raise ValueError(f"promotion refuses linked/junction paths: {path}")


def promote_mod(mod: str, repo_root: Path, *, original: Path, baseline: Path,
                behavior_diff: Path, behavior_risks: Path, behavior_unknowns: Path,
                expected_changes: Path | None = None, vanilla_core: Path | None = None,
                rig: Path | None = None, corpus_dir: Path | None = None,
                policy: Path | None = None, apply: bool = False) -> dict[str, object]:
    repo = repo_root.expanduser().resolve()
    folder = operation_root(repo) / _folder_name(mod)
    working = folder / "working"
    _physical(working)
    metadata = _load_lenient_json_file(working / "mod_info.json")
    if not isinstance(metadata, dict) or not isinstance(metadata.get("id"), str) or not metadata["id"]:
        raise ValueError("promotion requires a convention-layout working copy with a declared id")
    reports = folder / "reports"
    if not (reports / "REVIVAL_REPORT.md").is_file():
        reports = working / "reports"
    _physical(reports)
    result = {"schema_version": 1, "mode": "PROMOTE", "mod": mod,
              "working": str(working), "apply": apply, "status": "BLOCKED", "blocking_reasons": []}
    try:
        audit = audit_revival(working, reports_dir=reports)
    except (ValueError, OSError) as exc:
        return {**result, "blocking_reasons": [f"revival-evidence: {exc}"]}
    result["revival_audit"] = audit
    reasons = result["blocking_reasons"]
    if audit["status"] == "FAIL":
        reasons.append("revival-audit-failed")
    status = audit["declared_completion_status"]
    if status not in {"READY", "READY_WITH_REVIEW_ITEMS", "READY_FOR_LIVE_TEST"}:
        reasons.append("completion-status-does-not-permit-promotion")
    plan = (reports / "REVIVAL_PLAN.md").read_text(encoding="utf-8-sig")
    scores = re.findall(r"(?im)^\s*Total (?:complexity )?score:\s*(\d+)\s*$", plan)
    levels = re.findall(r"(?im)^\s*Complexity level:\s*(LOW|MEDIUM|HIGH)\s*$", plan)
    if len(scores) != 1 or len(levels) != 1:
        reasons.append("explicit-plan-score-and-level-required")
    elif (int(scores[0]) >= 8 and levels[0] != "HIGH") or (int(scores[0]) >= 4 and levels[0] == "LOW"):
        reasons.append("plan-level-below-authoritative-score-routing")
    for label in ("SOURCE REVIEW", "COMPILE", "STATIC VALIDATION", "PACKAGE VALIDATION",
                  "DEPENDENCY CHECK", "API SIGNATURE CHECK"):
        value = audit["validation_evidence"].get(label, "")
        if not re.search(r"\bPASS\b", value, re.I) or re.search(r"\b(?:FAIL(?:ED)?|UNKNOWN|PENDING|BLOCKED)\b", value, re.I):
            reasons.append(f"affirmative-validation-required:{label}")
    live = audit["validation_evidence"].get("LIVE STARSECTOR TEST", "")
    if status != "READY_FOR_LIVE_TEST" and (not re.search(r"\bPASS\b", live, re.I)
            or re.search(r"\b(?:FAIL(?:ED)?|UNKNOWN|PENDING|BLOCKED|NOT PERFORMED|REQUIRED)\b", live, re.I)):
        reasons.append("live-validation-required-or-use-READY_FOR_LIVE_TEST")
    for label, path in (("behavior-diff", behavior_diff), ("behavior-risks", behavior_risks), ("behavior-unknowns", behavior_unknowns)):
        if not path.is_file():
            reasons.append(f"required-evidence-missing:{label}")
    if reasons:
        return result
    basename = _release_basename(metadata["id"], metadata.get("version"), working)
    done = repo / "Done"
    target = done / mod
    for path in (target, target / "builds", target / "reports", target / "reports" / basename):
        _physical(path)
    prior: list[Path] = []
    if target.exists():
        if not target.is_dir():
            raise ValueError("Done mod target is not a directory")
        for candidate in sorted(target.iterdir()):
            if candidate.is_dir() and candidate.name not in NON_RELEASE_FOLDERS and (candidate / "mod_info.json").is_file():
                _physical(candidate)
                info = _load_lenient_json_file(candidate / "mod_info.json")
                if not isinstance(info, dict) or info.get("id") != metadata["id"]:
                    raise ValueError("Done contains a different/unknown mod; no prior release moved")
                prior.append(candidate)
                for sibling in (target / f"{candidate.name}.zip", target / f"{candidate.name}-RELEASE_NOTE.md",
                                target / "reports" / candidate.name):
                    if sibling.exists():
                        _physical(sibling)
                        prior.append(sibling)
    new_paths = [target / basename, target / f"{basename}.zip", target / f"{basename}-RELEASE_NOTE.md", target / "reports" / basename]
    for path in new_paths:
        if path.exists() and path not in prior:
            raise ValueError(f"promotion would overwrite unrelated content: {path}")
    options = dict(original=original, baseline=baseline, vanilla_core=vanilla_core, rig=rig,
                   corpus_dir=corpus_dir, policy_path=policy, behavior_diff_path=behavior_diff,
                   behavior_risks_path=behavior_risks, behavior_unknowns_path=behavior_unknowns,
                   expected_changes_path=expected_changes, require_behavior_evidence=True)
    release = release_mod(working, out_dir=folder / "scratch" / "promotion-dry-run", **options)
    result.update(release_gates=release["gates"], prior_releases=[str(p) for p in prior],
                  destination=str(target), completion_status=status)
    if release["status"] != "DRY_RUN_READY":
        reasons.extend("release-gate:" + name for name in release["blocking_gates"])
        return result
    if not apply:
        return {**result, "status": "DRY_RUN_READY"}
    scratch = folder / "scratch"
    _physical(scratch)
    scratch.mkdir(exist_ok=True)
    input_hash = _tree_sha256(working)
    evidence_hash = _tree_sha256(reports)
    with tempfile.TemporaryDirectory(prefix="promotion-", dir=scratch) as temporary:
        stage = Path(temporary).resolve()
        packaged = release_mod(working, out_dir=stage, apply=True, **options)
        if packaged["status"] != "RELEASED":
            return {**result, "blocking_reasons": ["release-gates-changed-during-staging"]}
        package_audit = audit_revival(Path(packaged["release_dir"]), Path(packaged["zip_path"]), reports_dir=reports)
        if package_audit["status"] == "FAIL" or not package_audit["package_attestation"]["exact_match"]:
            return {**result, "blocking_reasons": ["package-attestation-failed"], "package_audit": package_audit}
        if input_hash != _tree_sha256(working) or evidence_hash != _tree_sha256(reports):
            return {**result, "blocking_reasons": ["working-or-evidence-changed-during-staging"]}
        evidence = stage / "promotion-evidence"
        evidence.mkdir()
        for name in ("REVIVAL_PLAN.md", "REVIVAL_REPORT.md"):
            (evidence / name).write_bytes((reports / name).read_bytes())
        (evidence / "PROMOTION.json").write_text(json.dumps({"schema_version": 1, "working_tree_sha256": input_hash,
            "reports_tree_sha256": evidence_hash, "archive_sha256": _sha256(Path(packaged["zip_path"])),
            "declared_completion_status": status, "gates": packaged["gates"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        done.mkdir(exist_ok=True)
        target.mkdir(exist_ok=True)
        (target / "reports").mkdir(exist_ok=True)
        (target / "builds").mkdir(exist_ok=True)
        retention = target / "builds" / ("prior-" + uuid.uuid4().hex)
        moves: list[tuple[Path, Path]] = []
        planned = [(p, retention / p.relative_to(target)) for p in prior] + list(zip(
            [Path(packaged[key]) for key in ("release_dir", "zip_path", "release_note")] + [evidence], new_paths))
        lock = target / ".promotion.lock"
        journal = lock.open("x", encoding="utf-8")
        finalized = False
        try:
            journal.write(json.dumps({"schema_version": 1, "planned_moves": [
                {"source": str(source), "destination": str(destination)} for source, destination in planned]}) + "\n")
            journal.flush()
            for path in (target, target / "builds", target / "reports", *prior):
                _physical(path)
            if prior:
                retention.mkdir()
                for path in prior:
                    saved = retention / path.relative_to(target)
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    path.rename(saved)
                    moves.append((path, saved))
            for source, destination in zip([Path(packaged[key]) for key in ("release_dir", "zip_path", "release_note")] + [evidence], new_paths):
                if destination.exists():
                    raise ValueError(f"destination appeared during promotion: {destination}")
                source.rename(destination)
                moves.append((source, destination))
            finalized = True
        except BaseException:
            for source, destination in reversed(moves):
                source.parent.mkdir(parents=True, exist_ok=True)
                destination.rename(source)
            finalized = True
            # Leave only empty housekeeping/retention directories; never recursively
            # delete old/user data on a rollback. Interrupted attempts require review.
            raise
        finally:
            journal.close()
            if finalized:
                lock.unlink()
    return {**result, "status": "PROMOTED", "retained_at": str(retention) if prior else None,
            "package_audit": package_audit, "note": "Declared completion status preserved; promotion is not new live validation."}
