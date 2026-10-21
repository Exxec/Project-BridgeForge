"""`baseline-accept-finding`: accept named findings into a workspace baseline, outside escalation packets (ROADMAP 77.14).

`escalation accept` only matches findings in escalation packets, and `scan --write-baseline` accepts every finding. This command
accepts the findings a SELECTOR names and nothing else. A selector is `FINDING_ID[:FILE_PART[:EVIDENCE_PART]]`: FILE_PART is a
substring of the finding's file, EVIDENCE_PART a substring of its first evidence line. A selector that matches nothing is an error.

The baseline keeps its `stamp` (the version and date it was accepted at); only `findings` and `reasons` change. The dated section
appended to reports/ESCALATION_REVIEW.md lists the reason and the accepted keys.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from .baseline import finding_baseline_key, mod_baseline_path
from .models import Finding
from .safeio import atomic_write_text

MIN_REASON_LENGTH = 20
REVIEW_RELATIVE = Path("reports") / "ESCALATION_REVIEW.md"


def parse_selector(selector: str) -> tuple[str, str, str]:
    """(finding id, file part, evidence part); missing parts are empty, which matches everything."""
    parts = (selector.split(":", 2) + ["", ""])[:3]
    return parts[0], parts[1], parts[2]


def select_findings(findings: list[Finding], selectors: list[str]) -> dict[str, list[str]]:
    """Map each selector to the sorted, de-duplicated baseline keys of the findings it matches."""
    matches: dict[str, list[str]] = {}
    for selector in selectors:
        finding_id, file_part, evidence_part = parse_selector(selector)
        keys = {
            finding_baseline_key(finding)
            for finding in findings
            if finding.id == finding_id
            and file_part in (finding.file or "")
            and evidence_part in (finding.evidence[0] if finding.evidence else "")
        }
        matches[selector] = sorted(keys)
    return matches


def _read_payload(path: Path) -> dict:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _append_review(review: Path, today: str, selectors: list[str], reason: str, added: list[str]) -> None:
    old = review.read_text(encoding="utf-8").rstrip() if review.is_file() else "# Escalation review"
    names = ", ".join(sorted({parse_selector(s)[0] for s in selectors}))
    lines = "\n".join(f"- `{key}`" for key in added)
    section = f"## {today}: {names} accepted by selector\n\n{reason}\n\n{lines}\n"
    atomic_write_text(review, f"{old}\n\n{section}")


def accept_selected(workspace: Path, selectors: list[str], reason: str, findings: list[Finding], today: str | None = None,
                    dry_run: bool = False) -> dict:
    """Accept the findings the selectors name into the workspace's baseline; idempotent (nothing new, nothing written)."""
    reason = reason.strip()
    if len(reason) < MIN_REASON_LENGTH:
        raise ValueError(f"the reason must be at least {MIN_REASON_LENGTH} characters (the evidence for accepting the finding).")
    if not selectors:
        raise ValueError("give at least one SELECTOR: FINDING_ID[:FILE_PART[:EVIDENCE_PART]].")
    matches = select_findings(findings, selectors)
    unmatched = [selector for selector, keys in matches.items() if not keys]
    if unmatched:
        raise ValueError(f"no finding matches: {', '.join(unmatched)} (run `bridgeforge scan` on the workspace to see its findings).")
    selected = sorted({key for keys in matches.values() for key in keys})
    working = Path(workspace) / "working"
    path = mod_baseline_path(working) or working / "reports" / "baseline.json"
    payload = _read_payload(path)
    existing = set(payload.get("findings", []))
    added = [key for key in selected if key not in existing]
    result = {"workspace": str(workspace), "baseline": str(path), "selected": selected, "added": added,
              "already_accepted": [key for key in selected if key in existing], "date": today or date.today().isoformat()}
    if not added or dry_run:
        return result
    payload["findings"] = sorted(existing | set(added))
    reasons = payload.get("reasons") if isinstance(payload.get("reasons"), dict) else {}
    for key in added:
        reasons.setdefault(key, reason)
    payload["reasons"] = reasons
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _append_review(Path(workspace) / REVIEW_RELATIVE, result["date"], selectors, reason, added)
    return result


def add_parser(subcommands) -> None:
    accept = subcommands.add_parser("baseline-accept-finding", help="accept named findings into a workspace baseline (SELECTOR FINDING_ID[:FILE_PART[:EVIDENCE_PART]]) with a reason; the reason and keys go to reports/ESCALATION_REVIEW.md")
    accept.add_argument("workspace", type=Path)
    accept.add_argument("selectors", nargs="+", metavar="SELECTOR", help="FINDING_ID[:FILE_PART[:EVIDENCE_PART]]: substrings of the finding's file and of its first evidence line")
    accept.add_argument("--reason", required=True, help=f"why these findings stand, with the evidence (at least {MIN_REASON_LENGTH} characters)")
    accept.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    from .scanner import scan_mod

    try:
        findings = scan_mod(Path(args.workspace) / "working").findings
        result = accept_selected(Path(args.workspace), args.selectors, args.reason, findings)
    except (OSError, ValueError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, indent=2))
    elif not result["added"]:
        print(f"Nothing new: all {len(result['selected'])} selected finding(s) are already accepted in {result['baseline']}.")
    else:
        print(f"Accepted {len(result['added'])} finding key(s) into {result['baseline']}:")
        for key in result["added"]:
            print(f"  {key}")
    return 0
