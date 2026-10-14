"""Promotion candidates with fixtures (ROADMAP item 73, A4): what the agents' verified fixes of one finding id have in common.

`finding-stats` already names the ids AI fixed and BridgeForge verified three or more times (`promote_to_fixer`). A fixer
cannot be written from a count, so this collects the edits themselves: for every verified agent packet of such an id, the
newest attempt's diff (`escalation_review.review_attempt`, the attempt folder under `scratch/escalations/` that
`escalation apply` copied from), split into hunks, each hunk reduced to a shape. A shape keeps keywords and punctuation and
replaces identifiers by `ID`, string literals by `STR`, numbers by `NUM`, and collapses whitespace, so the same edit on
different names groups together. `PROMOTION_CANDIDATES.md` lists, per id and shape: the count, the mods, the file kind and
one before/after pair (at most 40 lines each). B1, B2 and B3 write their fixers from these shapes.

Limits: only the newest attempt of a packet is read (the accepted one in the 2026-09 batches), and an attempt whose
`working/` moved on since it started has no usable diff and is counted under "skipped".
"""
from __future__ import annotations

import re
from pathlib import Path

from .escalation_review import review_attempt
from .finding_stats import VERIFIED_OUTCOMES, read_ledger
from .safeio import atomic_write_text

EXAMPLE_MAX_LINES = 40
_JAVA_KEEP = frozenset(
    "abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for "
    "if implements import instanceof int interface long new null package private protected public return short static super switch "
    "synchronized this throw throws try void volatile while true false var".split())
_TOKEN = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|\b\d[\w.]*|[A-Za-z_$][\w$]*')


def _token(match: re.Match) -> str:
    text = match.group(0)
    if text[0] in "\"'":
        return "STR"
    if text[0].isdigit():
        return "NUM"
    return text if text in _JAVA_KEEP else "ID"


def normalise(line: str) -> str:
    """One changed line reduced to its shape (identifiers ID, strings STR, numbers NUM, whitespace collapsed)."""
    return " ".join(_TOKEN.sub(_token, line).split())


def hunks(diff: list[str]) -> list[dict]:
    """Split a unified diff (lines without newlines) into {removed, added, old, new}; `old`/`new` include context."""
    found: list[dict] = []
    current: dict | None = None
    for line in diff:
        if line.startswith("@@"):
            current = {"removed": [], "added": [], "old": [], "new": []}
            found.append(current)
        elif current is None:
            continue  # the ---/+++ file headers before the first hunk
        elif line.startswith("-"):
            current["removed"].append(line[1:])
            current["old"].append(line[1:])
        elif line.startswith("+"):
            current["added"].append(line[1:])
            current["new"].append(line[1:])
        else:
            text = line[1:] if line.startswith(" ") else line
            current["old"].append(text)
            current["new"].append(text)
    return [h for h in found if h["removed"] or h["added"]]


def shape(hunk: dict) -> str:
    removed = [n for n in map(normalise, hunk["removed"]) if n]
    added = [n for n in map(normalise, hunk["added"]) if n]
    return "\n".join([f"- {n}" for n in removed] + [f"+ {n}" for n in added])


def _verified_packets(workspace: Path, finding_ids: set[str]) -> dict[str, str]:
    """Packet id -> finding id for the workspace's verified agent entries of the wanted ids."""
    return {entry["packet"]: entry["finding"] for entry in read_ledger(workspace)
            if entry.get("runner") == "agent" and entry.get("outcome") in VERIFIED_OUTCOMES
            and entry.get("packet") and entry.get("finding") in finding_ids}


def collect(workspaces: dict[str, Path], finding_ids: set[str]) -> dict:
    """{finding id: {(file kind, shape): {"count", "mods", "before", "after"}}} plus a "skipped" list of (mod, packet, why)."""
    shapes: dict[str, dict[tuple[str, str], dict]] = {fid: {} for fid in finding_ids}
    skipped: list[tuple[str, str, str]] = []
    for name, workspace in sorted(workspaces.items()):
        for packet_id, finding_id in sorted(_verified_packets(workspace, finding_ids).items()):
            review = review_attempt(workspace, packet_id)
            if review is None:
                skipped.append((name, packet_id, "no attempt folder under scratch/escalations"))
                continue
            usable = False
            for file, diff in review["diffs"].items():
                kind = Path(file).suffix.lower() or "(no suffix)"
                for hunk in hunks(diff):
                    usable = True
                    slot = shapes[finding_id].setdefault((kind, shape(hunk)), {"count": 0, "mods": set(), "before": hunk["old"], "after": hunk["new"]})
                    slot["count"] += 1
                    slot["mods"].add(name)
            if not usable:
                skipped.append((name, packet_id, "no usable diff (working/ moved on, or only binary files changed)"))
    return {"shapes": shapes, "skipped": skipped}


def _example(title: str, lines: list[str]) -> list[str]:
    shown = lines[:EXAMPLE_MAX_LINES]
    more = [f"... ({len(lines) - EXAMPLE_MAX_LINES} more lines)"] if len(lines) > EXAMPLE_MAX_LINES else []
    return [f"{title}:", "", "```", *shown, *more, "```", ""]


def render(collected: dict, promote_rows: list[dict]) -> str:
    lines = ["# Promotion candidates", "",
             "Ids that AI fixed and BridgeForge verified several times, grouped by the shape of each edit (identifiers `ID`, strings `STR`, "
             "numbers `NUM`). A shape seen in several mods is a fixer candidate; a singleton is a judgement call.", ""]
    for row in promote_rows:
        groups = sorted(collected["shapes"].get(row["id"], {}).items(), key=lambda kv: (-kv[1]["count"], kv[0]))
        lines += [f"## `{row['id']}` ({row['tier']}, {row['verified_fixes']} verified fixes in {len(row['mods'])} mods)", ""]
        if not groups:
            lines += ["No usable diff found (attempt folders missing or moved on).", ""]
        for number, ((kind, key), slot) in enumerate(groups, 1):
            lines += [f"### Shape {number}: {slot['count']} hunk(s) in {len(slot['mods'])} mod(s), file kind `{kind}`", "",
                      f"Mods: {', '.join(sorted(slot['mods']))}", "", "Normalised:", "", "```", key, "```", ""]
            lines += _example("Before", slot["before"]) + _example("After", slot["after"])
    if collected["skipped"]:
        lines += ["## Skipped", ""] + [f"- {mod} / {packet}: {why}" for mod, packet, why in collected["skipped"]] + [""]
    return "\n".join(lines)


def write_candidates(directory: Path, promote_rows: list[dict], workspaces: dict[str, Path]) -> Path:
    """Write `DIR/PROMOTION_CANDIDATES.md` for the `promote_to_fixer` rows of a `finding_stats` result."""
    collected = collect(workspaces, {row["id"] for row in promote_rows})
    return atomic_write_text(Path(directory) / "PROMOTION_CANDIDATES.md", render(collected, promote_rows), newline="\n")
