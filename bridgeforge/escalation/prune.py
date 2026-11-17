"""Prune finished escalation sandboxes (ROADMAP-3 item 92.36, 2026-11-16).

Every agent attempt keeps a full copy of the mod in `scratch/escalations/<packet>/attempt-N/working`: Bultach Coalition's
workspace was 2.1 GB, 1.7 GB of it 33 such copies. Once the ledger records an attempt's outcome, the copy has served its
purpose. Pruning keeps the prompt, note, agent output and START_TREE.json, saves each file the attempt changed (the
ledger's `changed` list, checked against START_TREE.json) under `attempt-N/changed/`, then deletes only `working/`.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from bridgeforge.safeio import atomic_write_json, safe_rmtree

TERMINAL = {"APPLIED", "FAILED", "REJECTED", "VERIFIED", "REFUSED", "ACCEPTED"}


def _ledger(workspace: Path) -> dict[tuple[str, int], dict]:
    entries: dict[tuple[str, int], dict] = {}
    path = workspace / "reports" / "escalations" / "ledger.jsonl"
    if not path.is_file():
        return entries
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("packet") and isinstance(entry.get("attempt"), int):
            entries[(entry["packet"], entry["attempt"])] = entry
    return entries


def _size(folder: Path) -> int:
    return sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())


def _changed(attempt: Path, entry: dict) -> list[str]:
    """Files the attempt changed: the ledger's list, plus anything whose hash differs from START_TREE.json."""
    working = attempt / "working"
    names = {c for c in entry.get("changed") or [] if isinstance(c, str)}
    try:
        start = json.loads((attempt / "START_TREE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        start = None
    if isinstance(start, dict):
        for path in working.rglob("*"):
            if path.is_file() and ".pre-bf-" not in path.name:
                rel = path.relative_to(working).as_posix()
                if start.get(rel) != hashlib.sha256(path.read_bytes()).hexdigest():
                    names.add(rel)
    return sorted(n for n in names if (working / n).is_file())


def prune_sandboxes(workspace: Path, *, apply: bool = False) -> dict:
    workspace = Path(workspace).expanduser().resolve()
    scratch = workspace / "scratch"
    root = scratch / "escalations"
    ledger = _ledger(workspace)
    rows, freed = [], 0
    for working in sorted(root.glob("*/attempt-*/working")) if root.is_dir() else []:
        attempt = working.parent
        packet = attempt.parent.name
        try:
            number = int(attempt.name.split("-", 1)[1])
        except (IndexError, ValueError):
            continue
        entry = ledger.get((packet, number))
        if entry is None or str(entry.get("outcome")) not in TERMINAL:
            rows.append({"packet": packet, "attempt": number, "state": "KEPT", "reason": "no finished outcome in the ledger"})
            continue
        size = _size(working)
        changed = _changed(attempt, entry)
        row = {"packet": packet, "attempt": number, "outcome": entry["outcome"], "bytes": size, "changed_kept": changed}
        if apply:
            for rel in changed:
                target = attempt / "changed" / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(working / rel, target)
            atomic_write_json(attempt / "PRUNED.json", {"schema_version": 1, "outcome": entry["outcome"], "bytes_freed": size,
                                                        "changed_kept": changed})
            safe_rmtree(working, [scratch])
        rows.append({**row, "state": "PRUNED" if apply else "WOULD_PRUNE"})
        freed += size
    return {"schema_version": 1, "workspace": str(workspace), "apply": apply, "bytes_freed": freed, "attempts": rows}
