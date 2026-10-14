"""Earlier answers to the same escalation question (ROADMAP item 73, C1/C2; owner decision 2 of 2026-10-14).

Two sources, both already written by `escalation rule` and `baseline-accept`:
- `<queue>/ESCALATION_RULINGS.jsonl`: one line per ruling (finding, `accept` or `approve-fixer`, reason, mods).
- any workspace's accepted-findings baseline (`baseline.mod_baseline_path`), whose `reasons` map a finding key
  (`id|file|evidence`) to why it was accepted.

A precedent is a `dict(source, finding, answer, reason, date, mods)`. When `STANDING_THRESHOLD` or more precedents for the
same finding agree on the answer, that answer may be pre-filled on a decision sheet (`escalation_sheet`) and applied once
the owner confirms or leaves it unchanged. Read-only.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

RULINGS_FILE = "ESCALATION_RULINGS.jsonl"
STANDING_THRESHOLD = 3
PACKET_PRECEDENT_LIMIT = 5

_QUOTED = re.compile(r"`[^`]*`|\"[^\"]*\"|'[^']*'")
_PATH = re.compile(r"[\w.\-]*[/\\][\w./\\\-]*|\b[\w\-]+\.(?:java|json|csv|ship|wpn|variant|skin|system|faction|jar|png|ogg|jpg|txt|md)\b")
_ID = re.compile(r"\b(?=\w*[_\d])\w+\b|\b[a-z]+[A-Z]\w*\b")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def question_shape(explanation: str) -> str:
    """A finding's explanation with ids, paths and numbers replaced by placeholders, so the same question asked of
    different mods reads the same."""
    text = _QUOTED.sub("<ID>", explanation or "")
    text = _PATH.sub("<PATH>", text)
    text = _ID.sub("<ID>", text)
    text = _NUMBER.sub("<N>", text)
    return re.sub(r"\s+", " ", text).strip()


def load_rulings(queue: Path) -> list[dict]:
    path = Path(queue) / RULINGS_FILE
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a cut-short last line; the file is append-only
        if isinstance(row, dict) and row.get("finding") and row.get("ruling"):
            rows.append(row)
    return rows


def baseline_precedents(queue: Path, finding_id: str, *, exclude: str | None = None) -> list[dict]:
    """Reasons recorded in workspace baselines for keys of `finding_id`, one precedent per mod and reason."""
    from .baseline import mod_baseline_path

    queue = Path(queue)
    found = []
    for workspace in sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_") and p.name != exclude):
        path = mod_baseline_path(workspace / "working")
        if path is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        reasons = payload.get("reasons") if isinstance(payload, dict) else None
        if not isinstance(reasons, dict):
            continue
        stamp = payload.get("stamp") if isinstance(payload.get("stamp"), dict) else {}
        for reason in sorted({str(r).strip() for key, r in reasons.items() if str(key).startswith(finding_id + "|") and str(r).strip()}):
            found.append({"source": "baseline", "finding": finding_id, "answer": "accept", "reason": reason,
                          "date": stamp.get("date"), "mods": [workspace.name]})
    return found


def precedents(queue: Path, finding_id: str, *, exclude: str | None = None) -> list[dict]:
    """Every earlier answer to `finding_id`, newest first. A baseline reason that a ruling already covers (same reason
    text, the mod listed in the ruling) is the same answer, not a second one."""
    rulings = [{"source": "ruling", "finding": finding_id, "answer": r["ruling"], "reason": r.get("reason") or "",
                "date": r.get("date"), "mods": list(r.get("mods") or [])} for r in load_rulings(queue) if r["finding"] == finding_id]
    covered = {(mod, entry["reason"]) for entry in rulings for mod in entry["mods"]}
    extra = [entry for entry in baseline_precedents(queue, finding_id, exclude=exclude) if (entry["mods"][0], entry["reason"]) not in covered]
    return sorted(rulings + extra, key=lambda e: (e.get("date") or "", e["source"]), reverse=True)


def standing_answer(entries: list[dict], threshold: int = STANDING_THRESHOLD) -> dict | None:
    """`{answer, reason, count}` when `threshold` or more precedents agree on one answer (the most common reason among
    them), else None. Disagreeing precedents never prefill: the answer must be one every earlier ruling gave."""
    answers = Counter(e["answer"] for e in entries)
    if len(answers) != 1:
        return None
    answer, count = answers.most_common(1)[0]
    if count < threshold:
        return None
    reasons = Counter(e["reason"] for e in entries if e["reason"])
    return {"answer": answer, "reason": reasons.most_common(1)[0][0] if reasons else "", "count": count}


def packet_precedent(queue: Path, finding_id: str, *, exclude: str | None = None) -> list[dict]:
    """The up-to-five newest earlier answers a decision packet shows under "Answered before"."""
    return precedents(queue, finding_id, exclude=exclude)[:PACKET_PRECEDENT_LIMIT]
