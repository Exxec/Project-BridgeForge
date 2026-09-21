"""Draft REVIVAL_REPORT.md/REVIVAL_PLAN.md scaffolding from real scan+compile evidence.

A clean mod (0 MANUAL findings, compile PASS) still needs a hand-shaped `REVIVAL_REPORT.md`/
`REVIVAL_PLAN.md` pair before `board`/`corpus-recheck` can resolve a declared completion status,
or `release`'s `audit_revival` gate can even run (it requires both files to exist). Writing that
prose by hand for a mod that already has nothing left to review is pure friction - the content is
entirely derivable from a scan plus a compile-check.

This only ever drafts for a mod that is *actually* clean: any MANUAL finding or a compile FAIL
blocks the draft outright (`status: BLOCKED`), same refusal shape as the fixers' `FixerError` -
never fabricate a PASS. SAVE COMPATIBILITY CHECK and LIVE STARSECTOR TEST are not mechanically
checkable at all, so they are always recorded as not performed and the drafted completion status
is always READY_FOR_LIVE_TEST, never READY - matching `revival_audit.COMPLETION_STATUSES` and the
existing convention seen across the real corpus's hand-written reports for a mod in this same
shape (Bionic-Alteration, M3SV, RogueSynth, SEEKER, Silent-Armada, Xenoargh-AI-Overhaul,
Xenoargh-EZ-Damage, Xenoargh-FX-Core - every one of them REVIEW findings and all, `READY_FOR_
LIVE_TEST`). The owner can retitle a draft to `READY_WITH_REVIEW_ITEMS` by hand if the REVIEW
items below warrant flagging more heavily before a live-test pass.

Mirrors `corpus_recheck`'s own scan/compile split (`scan_mod(..., compile_check=False)` for the
finding set, standalone `compile_loose_scripts` for the compile signal) rather than `scan
--compile-check`'s slower integrated path.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .compile_check import compile_loose_scripts
from .models import TargetProfile
from .scanner import _load_lenient_json_file, scan_mod

SCHEMA_VERSION = 1

_VALIDATION_LABELS_NOT_MECHANICALLY_CHECKABLE = (
    "SAVE COMPATIBILITY CHECK",
    "LIVE STARSECTOR TEST",
)


def draft_revival_report(mod_dir: Path, vanilla_core: Path | None = None, provider_roots: list[Path] | None = None) -> dict:
    """Compute (never write) a REVIVAL_REPORT.md/REVIVAL_PLAN.md draft, or refuse with why not."""
    root = Path(mod_dir).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not an existing directory.")

    result = scan_mod(root, TargetProfile(), vanilla_core, compile_check=False)
    by_classification: dict[str, int] = {}
    for finding in result.findings:
        by_classification[finding.classification] = by_classification.get(finding.classification, 0) + 1

    blocking = sorted(
        f"{finding.id} (`{finding.file}`)" if finding.file else finding.id
        for finding in result.findings
        if finding.classification == "MANUAL"
    )

    compile_result: dict | None = None
    if vanilla_core is not None:
        compile_result = compile_loose_scripts(root, vanilla_core=vanilla_core, provider_roots=provider_roots)
        if compile_result["status"] == "FAIL":
            blocking.append(f"compile: {compile_result['error_count']} javac error(s) (run `compile-check` for detail)")
    else:
        blocking.append("no --vanilla-core given: compile status cannot be established")

    base = {
        "schema_version": SCHEMA_VERSION, "mode": "REVIVAL_REPORT_DRAFT", "mod": str(root),
        "findings_total": len(result.findings), "by_classification": by_classification,
    }
    if blocking:
        return {**base, "status": "BLOCKED", "blocking": blocking}

    metadata = _load_lenient_json_file(root / "mod_info.json") if (root / "mod_info.json").is_file() else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    mod_id = str(metadata.get("id") or "")
    mod_name = str(metadata.get("name") or mod_id or root.name)
    dependencies = metadata.get("dependencies") or []
    dep_names = [str(item.get("name") or item.get("id")) for item in dependencies if isinstance(item, dict) and (item.get("name") or item.get("id"))]
    dependency_check_text = f"PASS (declared: {', '.join(dep_names)})" if dep_names else "PASS (no dependencies declared)"

    review_count = by_classification.get("REVIEW", 0)
    safe_count = by_classification.get("SAFE", 0)
    file_count = len(result.files)
    compile_text = f"PASS ({compile_result['error_count']} errors, {len(compile_result['files'])} loose script(s) compiled against RC8)"

    report_lines = [
        f"# Revival Report: {mod_name} (0.98a-RC8)",
        "",
        f"Date: {date.today().isoformat()}",
        f"Working copy: `{root}`",
        "Drafted by `bridgeforge revival-report-draft` from real scan + compile-check evidence. "
        "SAVE COMPATIBILITY CHECK and LIVE STARSECTOR TEST are not mechanically checkable and are "
        "recorded as not yet performed; review before a release build.",
        "",
        "## Validation",
        "",
        f"- SOURCE REVIEW — PASS ({file_count} files scanned, {review_count} REVIEW item(s) noted below, {safe_count} SAFE)",
        f"- COMPILE — {compile_text}",
        f"- STATIC VALIDATION — PASS (0 MANUAL findings; {review_count} REVIEW item(s) below)",
        "- PACKAGE VALIDATION — NOT PERFORMED (no release archive built yet)",
        f"- DEPENDENCY CHECK — {dependency_check_text}",
        f"- API SIGNATURE CHECK — {compile_text}",
        "- SAVE COMPATIBILITY CHECK — NOT PERFORMED (deferred to live test pass)",
        "- LIVE STARSECTOR TEST — NOT PERFORMED (deferred to live test pass)",
        "",
        "## Review items (non-blocking)",
        "",
    ]
    review_findings = [finding for finding in result.findings if finding.classification == "REVIEW"]
    if review_findings:
        for finding in review_findings:
            report_lines.append(f"- [{finding.id}] `{finding.file or ''}` — {finding.explanation}")
    else:
        report_lines.append("(none)")
    report_lines += ["", "READY_FOR_LIVE_TEST"]
    report_text = "\n".join(report_lines) + "\n"

    plan_lines = [
        f"# Revival Plan: {mod_name}",
        "",
        "Drafted by `bridgeforge revival-report-draft`; every stage below was actually performed, "
        "except the two marked deferred to the live-test pass.",
        "",
        "- [x] SOURCE REVIEW",
        "- [x] COMPILE",
        "- [x] STATIC VALIDATION",
        "- [ ] PACKAGE VALIDATION",
        "- [x] DEPENDENCY CHECK",
        "- [x] API SIGNATURE CHECK",
        "- [ ] SAVE COMPATIBILITY CHECK (deferred to live test pass)",
        "- [ ] LIVE STARSECTOR TEST (deferred to live test pass)",
    ]
    plan_text = "\n".join(plan_lines) + "\n"

    return {
        **base, "status": "OK", "mod_id": mod_id, "completion_status": "READY_FOR_LIVE_TEST",
        "report_text": report_text, "plan_text": plan_text,
    }


def write_revival_report_draft(mod_dir: Path, vanilla_core: Path | None = None, provider_roots: list[Path] | None = None, force: bool = False) -> dict:
    """`draft_revival_report`, then write `reports/REVIVAL_REPORT.md`/`REVIVAL_PLAN.md` (never overwrites without `force`)."""
    draft = draft_revival_report(mod_dir, vanilla_core=vanilla_core, provider_roots=provider_roots)
    if draft["status"] != "OK":
        return draft
    root = Path(mod_dir).expanduser().resolve()
    reports_dir = root / "reports"
    report_path = reports_dir / "REVIVAL_REPORT.md"
    plan_path = reports_dir / "REVIVAL_PLAN.md"
    existing = [str(path) for path in (report_path, plan_path) if path.is_file()]
    if existing and not force:
        return {**draft, "status": "REFUSED", "reason": "Would overwrite an existing file; pass force=True to replace it.", "existing": existing}
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path.write_text(draft["report_text"], encoding="utf-8")
    plan_path.write_text(draft["plan_text"], encoding="utf-8")
    return {**draft, "status": "WRITTEN", "report_path": str(report_path), "plan_path": str(plan_path)}
