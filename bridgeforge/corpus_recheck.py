"""Re-scan every mod with real revival work recorded (ROADMAP P14 item 32).

Generalizes item 23's full corpus recheck (2026-09-21, done by hand with a throwaway script) into
a reusable command. Mod discovery reuses `project_board`'s own tested layout logic rather than
re-deriving it: a mod qualifies when it has a `working/mod_info.json` AND a `REVIVAL_REPORT.md`
(real revival work recorded) - this naturally excludes the Ironclads intake queue (no `working/`
copy exists for any of it yet) and non-canonical copies (`scratch/`, `builds/`, `_rig/mods/`,
anything starting with `_`) without special-casing them.

Uses the corrected item-23 procedure, not the literal roadmap text: `scan_mod(...,
compile_check=False)` for the finding set, plus the standalone `compile_loose_scripts` (which
defaults `provider_roots` the same way the `compile-check` CLI command does) for the compile
signal - `scan --compile-check`'s own code path could not resolve a declared dependency at all
before item 29's fix, and even after it, calling the two separately keeps this module decoupled
from a full scan's slower compile-check integration.
"""

from __future__ import annotations

from pathlib import Path

from .baseline import load_baseline_keys, mod_baseline_path as _mod_baseline_path, split_by_baseline
from .compile_check import compile_loose_scripts
from .models import TargetProfile
from .project_board import project_board
from .scanner import scan_mod

SCHEMA_VERSION = 1


def _qualifying_mods(repo_root: Path, require_report: bool = True) -> list[dict[str, object]]:
    board = project_board(repo_root)
    return [row for row in board["mods"] if row["working"] and (row["evidence"]["report"] or not require_report)]


def _recheck_one(name: str, working: Path, vanilla_core: Path | None, declared_status: str | None, declared_status_confidence: str | None) -> dict[str, object]:
    try:
        result = scan_mod(Path(working), TargetProfile(), vanilla_core, compile_check=False)
    except ValueError as exc:
        return {"mod": name, "error": str(exc)}
    findings = result.findings
    baseline_path = _mod_baseline_path(Path(working))
    baselined_count = 0
    if baseline_path is not None:
        try:
            keys = load_baseline_keys(baseline_path)
        except (OSError, ValueError):
            baseline_path = None
        else:
            kept, _resolved = split_by_baseline(findings, keys)
            baselined_count = len(findings) - len(kept)
            findings = kept
    by_classification: dict[str, int] = {}
    for finding in findings:
        by_classification[finding.classification] = by_classification.get(finding.classification, 0) + 1
    manual_ids = sorted({finding.id for finding in findings if finding.classification == "MANUAL"})
    compile_status = None
    compile_errors = None
    if vanilla_core is not None:
        compile_result = compile_loose_scripts(Path(working), vanilla_core=vanilla_core)
        compile_status = compile_result.get("status")
        compile_errors = compile_result.get("error_count")
    return {
        "mod": name,
        "working": str(working),
        "files": len(result.files),
        "findings_total": len(findings),
        "baselined_findings": baselined_count,
        "baseline": str(baseline_path) if baseline_path is not None else None,
        "by_classification": by_classification,
        "manual_ids": manual_ids,
        "compile_status": compile_status,
        "compile_errors": compile_errors,
        "declared_completion_status": declared_status,
        "declared_completion_status_confidence": declared_status_confidence,
    }


def corpus_recheck(repo_root: Path, vanilla_core: Path | None = None, require_report: bool = True,
                   checkpoint: Path | None = None, progress=None) -> dict[str, object]:
    """Re-scan every mod with real revival work recorded under `repo_root`'s `In operation/`.

    See the module docstring for scope and the finding/compile-signal split. `vanilla_core` is
    optional (matching `scan`'s own default), but every vanilla-dependent check - which is most of
    them - returns UNKNOWN without it, and no compile signal is produced at all.

    `require_report=False` (ROADMAP P14 item 8 triage pass) widens scope to every mod with a
    `working/mod_info.json`, report or not - the Ironclads intake queue's own 265 workspaces have
    never had a revival pass (no `REVIVAL_REPORT.md`), but share the identical `working/` layout,
    so the same scan/compile-check machinery applies unchanged. The `REGRESSION` status check below
    still only fires for a mod with a declared ready status, so intake-only mods (which have none)
    never trigger it - this widening only adds coverage, it never changes what counts as a
    regression.
    """
    repo = repo_root.expanduser().resolve()
    vanilla_root = vanilla_core.expanduser().resolve() if vanilla_core is not None else None
    if vanilla_root is not None and not vanilla_root.is_dir():
        vanilla_root = None
    import time

    from .progress import Checkpoint

    mods = []
    rows = sorted(_qualifying_mods(repo, require_report), key=lambda r: r["folder"])
    header = {"checkpoint": SCHEMA_VERSION, "repo": str(repo), "vanilla_core": str(vanilla_root) if vanilla_root else None,
              "require_report": require_report}
    with Checkpoint(checkpoint, header) as saved:
        for number, row in enumerate(rows, 1):
            started = time.monotonic()
            result = saved.get(row["folder"])
            resumed = result is not None
            if result is None:
                result = _recheck_one(
                    row["folder"], Path(row["working"]), vanilla_root,
                    row.get("declared_completion_status"), row.get("declared_completion_status_confidence"),
                )
                saved.add(row["folder"], result)
            if progress:
                progress(number, len(rows), result, None if resumed else time.monotonic() - started)
            mods.append(result)
    regressions = [
        m for m in mods
        if "error" not in m and m["declared_completion_status"] in ("READY", "READY_FOR_LIVE_TEST", "READY_WITH_REVIEW_ITEMS")
        and m["by_classification"].get("MANUAL", 0) > 0
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": "corpus-recheck",
        "status": "REGRESSION" if regressions else "OK",
        "repo_root": str(repo),
        "vanilla_core": str(vanilla_root) if vanilla_root is not None else None,
        "mod_count": len(mods),
        "regressions": [m["mod"] for m in regressions],
        "mods": mods,
    }


def render_markdown(recheck: dict[str, object]) -> str:
    """A roll-up table matching item 23's own hand-written format, for `--write-markdown`."""
    lines = [
        "# Corpus recheck",
        "",
        f"{recheck['mod_count']} mod(s) with real revival work recorded, under `{recheck['repo_root']}`.",
        "",
    ]
    if recheck["regressions"]:
        lines.append(f"**Regression: {len(recheck['regressions'])} mod(s) with a declared ready status now carry a MANUAL finding:** " + ", ".join(f"`{m}`" for m in recheck["regressions"]))
        lines.append("")
    lines.append("| Mod | Files | MANUAL | REVIEW | Compile | Errs | Declared status | MANUAL finding ids |")
    lines.append("| --- | ---: | ---: | ---: | --- | ---: | --- | --- |")
    for mod in recheck["mods"]:
        if "error" in mod:
            lines.append(f"| {mod['mod']} | — | — | — | ERROR | — | — | {mod['error']} |")
            continue
        manual = mod["by_classification"].get("MANUAL", 0)
        review = mod["by_classification"].get("REVIEW", 0)
        compile_status = mod["compile_status"] or "—"
        compile_errors = mod["compile_errors"] if mod["compile_errors"] is not None else "—"
        declared = mod["declared_completion_status"] or "—"
        if mod["declared_completion_status_confidence"] == "BEST_EFFORT":
            declared += " (best-effort)"
        ids = ", ".join(mod["manual_ids"]) or "—"
        lines.append(f"| {mod['mod']} | {mod['files']} | {manual} | {review} | {compile_status} | {compile_errors} | {declared} | {ids} |")
    return "\n".join(lines) + "\n"
