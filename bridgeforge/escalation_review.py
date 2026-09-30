"""Review aids for escalation agent batches (ROADMAP P15 item 32, 2026-09-30).

`review_sheet`: one Markdown sheet per workspace with each packet's newest attempt: outcome, the diff against the
file it started from, and flags for the changes that needed a human in the 2026-09-29/30 batches:
- a removed ship hint or tag (Covert Actions' agent removed SHIP_WITH_MODULES instead of fixing anything),
- Random, seed or persistent-data logic touched (Vesperon Combine's agent changed its anti-save-scum Random),
- a loop rewritten (Arthr's Faction Blender: an unneeded rewrite),
- an exception swallowed, or more lines deleted than added,
- an agent that asked to run outside its sandbox (dangerouslyDisableSandbox, seen once).
A flag is a pointer for the reviewer, not a verdict.

`snapshot_dir` / `diff_snapshots`: an agent can write the session's memory directory, so a batch records its state
before and reports what changed after.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
from pathlib import Path

FLAGS = (
    ("hint-or-tag-removed", "-", re.compile(r"\b(SHIP_WITH_MODULES|CARRIER|CIVILIAN|FREIGHTER|TANKER|UNBOARDABLE|HIDE_IN_CODEX|STATION|hints|tags)\b")),
    ("random-or-save-logic", "±", re.compile(r"\b(Random|getSeed|setSeed|getPersistentData|getMemoryWithoutUpdate|MathUtils\.getRandom)\b")),
    ("loop-rewritten", "±", re.compile(r"^\s*(for|while|do)\b|\.forEach\(|\bIterator\b")),
    ("exception-swallowed", "+", re.compile(r"catch\s*\(\s*(Throwable|Exception|RuntimeException)\b")),
)
TEXT_SUFFIXES = {".java", ".json", ".csv", ".ship", ".variant", ".wpn", ".skin", ".system", ".faction", ".txt", ".md", ".ini", ".settings"}


def snapshot_dir(root: Path) -> dict[str, str]:
    root = Path(root)
    if not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def diff_snapshots(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {"added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k])}


def flag_diff(lines: list[str]) -> list[str]:
    flags = set()
    removed = [line[1:] for line in lines if line.startswith("-") and not line.startswith("---")]
    added = [line[1:] for line in lines if line.startswith("+") and not line.startswith("+++")]
    for name, side, pattern in FLAGS:
        pool = removed if side == "-" else added if side == "+" else removed + added
        if name == "hint-or-tag-removed":
            if any(m.group(1) not in " ".join(added) for line in removed for m in pattern.finditer(line)):
                flags.add(name)
        elif any(pattern.search(line) for line in pool):
            flags.add(name)
    if len(removed) > len(added) + 5:
        flags.add("net-deletion")
    return sorted(flags)


def _baseline(working: Path, name: str, packet_id: str) -> Path:
    target = working / name
    backup = target.with_name(f"{target.name}.pre-bf-escalation-{packet_id}.bak")
    return backup if backup.is_file() else target


def _read(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []


def review_attempt(workspace: Path, packet_id: str) -> dict | None:
    root = Path(workspace) / "scratch" / "escalations" / packet_id
    attempts = sorted(root.glob("attempt-*"), key=lambda p: int(p.name.split("-")[1]) if p.name.split("-")[1].isdigit() else 0)
    if not attempts:
        return None
    attempt = attempts[-1]
    working, sandbox = Path(workspace) / "working", attempt / "working"
    start = json.loads((attempt / "START_TREE.json").read_text(encoding="utf-8")) if (attempt / "START_TREE.json").is_file() else {}
    now = {p.relative_to(sandbox).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sandbox.rglob("*") if p.is_file() and ".pre-bf-" not in p.name} if sandbox.is_dir() else {}
    changed = sorted(k for k in set(start) | set(now) if start.get(k) != now.get(k)) if start else []
    diffs, flags = {}, set()
    for name in changed:
        if Path(name).suffix.lower() not in TEXT_SUFFIXES:
            diffs[name] = ["(binary or unlisted type; not shown)"]
            continue
        base = _baseline(working, name, packet_id)
        if base.is_file() and start.get(name) and hashlib.sha256(base.read_bytes()).hexdigest() != start[name]:
            # working/ moved on since the attempt started (a hand merge, another packet): a diff would mislead.
            diffs[name] = ["(working/ changed since this attempt started; compare by hand)"]
            flags.add("baseline-moved")
            continue
        lines = list(difflib.unified_diff(_read(base), _read(sandbox / name), "before", "after", lineterm="", n=2))
        diffs[name] = lines
        flags.update(flag_diff(lines))
    output = (attempt / "AGENT_OUTPUT.txt").read_text(encoding="utf-8", errors="replace") if (attempt / "AGENT_OUTPUT.txt").is_file() else ""
    if "dangerouslyDisableSandbox" in output:
        flags.add("asked-to-leave-sandbox")
    note = (attempt / "NOTE.md").read_text(encoding="utf-8", errors="replace").strip() if (attempt / "NOTE.md").is_file() else ""
    return {"packet": packet_id, "attempt": attempt.name, "changed": changed, "flags": sorted(flags), "diffs": diffs, "note": note}


def _outcomes(workspace: Path) -> dict[str, str]:
    ledger = Path(workspace) / "reports" / "escalations" / "ledger.jsonl"
    found: dict[str, str] = {}
    for line in _read(ledger):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("runner") == "agent" and entry.get("packet"):
            found[entry["packet"]] = entry.get("outcome", "")
    return found


def review_sheet(workspace: Path, *, write: bool = True) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    outcomes = _outcomes(workspace)
    root = workspace / "scratch" / "escalations"
    reviews = [r for r in (review_attempt(workspace, p.name) for p in sorted(root.iterdir()) if p.is_dir()) if r] if root.is_dir() else []
    for review in reviews:
        review["outcome"] = outcomes.get(review["packet"], "")
    lines = [f"# Escalation review sheet: {workspace.name}", "",
             "Each packet's newest agent attempt. Flags point at what to read first; they are not verdicts.", ""]
    for r in reviews:
        lines += [f"## {r['packet']} ({r['attempt']}, {r['outcome'] or 'no ledger entry'})", "",
                  "Flags: " + (", ".join(r["flags"]) if r["flags"] else "none"), "",
                  "Changed: " + (", ".join(r["changed"]) if r["changed"] else "nothing"), ""]
        if r["note"]:
            lines += ["Agent note:", "", *[f"> {line}" for line in r["note"].splitlines()], ""]
        for name, diff in r["diffs"].items():
            lines += [f"`{name}`", "", "```diff", *diff, "```", ""]
    path = workspace / "reports" / "ESCALATION_REVIEW_SHEET.md"
    if write and reviews:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    return {"workspace": str(workspace), "reviews": reviews, "sheet": str(path) if write and reviews else None,
            "flagged": [r["packet"] for r in reviews if r["flags"]]}
