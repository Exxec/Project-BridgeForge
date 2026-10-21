"""Archive gates (ROADMAP-3 item 80.3): the dropped-feature sweep and the content-parity audit, run before an archive is written.

`archive_mod` and `revise finalize` call `pre_archive_checks`: DROPS_UNEXPLAINED (dropped features that no REMOVALS.json entry
explains) and LOSS_SUSPECTED (content parity) refuse; UNDETERMINED is a warning. `--allow-unexplained REASON` (at least
ALLOW_MIN_CHARS characters) lets the archive proceed and records the reason and the refused items in ARCHIVE_NOTE.md.

`probe-group record --accept` calls `archive_offer` after a candidate passed on probe 0.3.0 or later and prints the archive
command for it. It only offers the command; it never runs one.
"""
from __future__ import annotations

import re
from pathlib import Path

from .content_parity import LOSS_CATEGORIES, audit_shipped
from .dropped_sweep import check_workspace

ALLOW_MIN_CHARS = 20
SHOWN_ITEMS = 12
OFFER_FROM_PROBE = (0, 3, 0)
_PROBE_VERSION = re.compile(r"\d+\.\d+\.\d+")


def check_reason(reason: str | None) -> str | None:
    """The stripped `--allow-unexplained` reason, None when absent; ValueError when it is too short to be a reason."""
    if reason is None:
        return None
    text = reason.strip()
    if len(text) < ALLOW_MIN_CHARS:
        raise ValueError(f"--allow-unexplained needs a reason of at least {ALLOW_MIN_CHARS} characters saying why the refused items stay out")
    return text


def _listed(items: list[str]) -> str:
    more = len(items) - SHOWN_ITEMS
    return ", ".join(items[:SHOWN_ITEMS]) + (f" (+{more} more)" if more > 0 else "")


def _sweep_findings(sweep: dict) -> list[str]:
    return [f"dropped {category}: {_listed(entry['unexplained'])}"
            for category, entry in sorted(sweep["dropped"].items()) if entry.get("unexplained")]


def _parity_findings(parity: dict) -> list[str]:
    found = [f"missing from the archive: {_listed(parity['missing'])}"] if parity["missing"] else []
    for category in LOSS_CATEGORIES:
        if parity["unexplained"].get(category):
            found.append(f"unexplained {category}: {_listed(parity['unexplained'][category])}")
    return found


def pre_archive_checks(workspace: Path) -> dict:
    """`{"problems": [...], "warnings": [...]}`: what refuses the archive, and what to report without refusing. Reads only."""
    problems: list[str] = []
    warnings: list[str] = []
    sweep = check_workspace(workspace)
    if sweep["verdict"] == "DROPS_UNEXPLAINED":
        problems.append("dropped features no REMOVALS.json entry explains: " + "; ".join(_sweep_findings(sweep)))
    elif sweep["verdict"] == "UNDETERMINED":
        warnings.append(f"dropped-feature sweep undetermined: {sweep['reason']}")
    parity = audit_shipped(workspace / "working", workspace / "original", name=workspace.name, removals_dirs=[workspace / "working"])
    if parity["verdict"] == "LOSS_SUSPECTED":
        problems.append("content parity against original/: " + "; ".join(_parity_findings(parity)))
    elif parity["verdict"] == "UNDETERMINED":
        warnings.append("content parity undetermined: " + ("; ".join(parity["notes"]) or "no original to compare with"))
    return {"problems": problems, "warnings": warnings}


def override_section(reason: str, problems: list[str]) -> str:
    """The ARCHIVE_NOTE.md section for an archive written past its refusals with `--allow-unexplained`."""
    lines = ["", "## Archived past its checks (--allow-unexplained)", "", f"Reason recorded by the owner: {reason}", "",
             "Refused by the checks and accepted with that reason:", ""]
    return "\n".join(lines + [f"- {problem}" for problem in problems]) + "\n"


def _probe_version_tuple(text: str) -> tuple[int, ...] | None:
    return tuple(int(part) for part in text.split(".")) if _PROBE_VERSION.fullmatch(text or "") else None


def archive_offer(record: dict, queue: Path) -> list[str]:
    """Offer lines after `probe-group record --accept`: the archive command for each passing workspace, when the run used probe
    0.3.0 or later. Nothing is run; a pending `revise` revision gets its `revise finalize` command instead."""
    from .revise import pending_journals  # revise imports this module at load time

    version = _probe_version_tuple(str(record.get("probe_version", "")))
    if version is None or version < OFFER_FROM_PROBE:
        return []
    lines: list[str] = []
    for name in record.get("recorded", []):
        if name in record.get("archived", []):
            continue
        workspace = Path(queue) / name
        pending = pending_journals(workspace)
        if pending:
            command = f'bridgeforge revise finalize "{workspace}" --revision {pending[0]["revision_id"]} --test-id {record["test_id"]}'
        else:
            command = f'bridgeforge archive "{workspace}" --refresh'
        lines.append(f"  To archive {name} (offered, not run): {command}")
    return lines
