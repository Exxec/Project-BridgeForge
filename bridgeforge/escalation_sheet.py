"""`bridgeforge escalation sheet`: one CSV that answers every open decision across a queue (ROADMAP item 73, C1).

`escalation queue` says which findings block the ESCALATED mods; this turns the decision-tier ones into rows to answer.
Open decision findings are grouped by (finding id, question shape): the finding's explanation with ids, paths and
numbers replaced by placeholders, so one row asks one question of every mod it applies to. Each row carries the earlier
answers (`escalation_precedent`). When three or more earlier rulings agree, `answer` and `reason` are pre-filled and
the row is marked `prefilled=yes` (owner decision 2, 2026-10-14); `--apply` applies such a row only when the owner left
it unchanged or wrote `confirm=yes`, and logs it as "standing approval from N prior rulings". Applying calls
`escalation_queue.rule`, the one mechanism for rulings. Reads packets; writes only the sheet, and on apply the
baselines/policy/ruling log `rule` writes.
"""
from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

from .baseline import finding_dict_baseline_key, mod_baseline_keys
from .escalation_precedent import precedents, question_shape, standing_answer
from .progress import Checkpoint, report
from .report_status import is_closed
from .safeio import atomic_write_text

SCHEMA_VERSION = 1
CHECKPOINT_FILE = "ESCALATION_SHEET.partial.jsonl"
COLUMNS = ("group", "finding", "shape", "mods", "precedent_count", "precedent_answer", "precedent_reason", "prefilled",
           "answer", "reason", "confirm", "queue")
ANSWERS = ("accept", "approve-fixer", "skip")
MODS_SEPARATOR = ";"


class SheetError(ValueError):
    pass


def _open_decisions(workspace: Path) -> list[dict]:
    """The workspace's open decision findings as `{finding, shape}`, de-duplicated; accepted ones are left out."""
    revive = workspace / "reports" / "revive" / "REVIVE.json"
    try:
        status = json.loads(revive.read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError):
        return []
    if status != "ESCALATED":
        return []
    accepted = mod_baseline_keys(workspace / "working")
    found: dict[tuple[str, str], dict] = {}
    for path in sorted((workspace / "reports" / "escalations").glob("*--*.json")):
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if packet.get("tier") != "decision":
            continue
        for finding in packet.get("findings") or []:
            if finding_dict_baseline_key(finding) in accepted:
                continue
            shape = question_shape(finding.get("explanation") or "")
            found.setdefault((finding["id"], shape), {"finding": finding["id"], "shape": shape})
    return list(found.values())


def build_sheet(queue: Path, quiet: bool = False) -> list[dict]:
    queue = Path(queue).expanduser().resolve()
    workspaces = sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_")
                        and (p / "reports" / "revive" / "REVIVE.json").is_file() and not is_closed(p))
    header = {"schema_version": SCHEMA_VERSION, "queue": str(queue), "workspaces": [w.name for w in workspaces],
              "revive_mtimes": {w.name: (w / "reports" / "revive" / "REVIVE.json").stat().st_mtime for w in workspaces}}
    groups: dict[tuple[str, str], list[str]] = {}
    with Checkpoint(queue / CHECKPOINT_FILE, header) as checkpoint:
        for number, workspace in enumerate(workspaces, 1):
            started = time.perf_counter()
            cached = checkpoint.get(workspace.name)
            record = cached if cached is not None else {"decisions": _open_decisions(workspace)}
            if cached is None:
                checkpoint.add(workspace.name, record)
            if not quiet:
                report(number, len(workspaces), workspace.name, f"{len(record['decisions'])} decision(s)", None if cached is not None else time.perf_counter() - started)
            for item in record["decisions"]:
                groups.setdefault((item["finding"], item["shape"]), []).append(workspace.name)
        checkpoint.finish()
    rows = []
    for number, ((finding, shape), mods) in enumerate(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])), 1):
        # A mod's own earlier baseline reasons are not precedent for its own open question.
        earlier = [p for p in precedents(queue, finding) if not (p["mods"] and set(p["mods"]) <= set(mods))]
        standing = standing_answer(earlier)
        reasons = [p["reason"] for p in earlier if p["reason"]]
        rows.append({"group": f"G{number:03d}", "finding": finding, "shape": shape, "mods": MODS_SEPARATOR.join(sorted(mods)),
                     "precedent_count": len(earlier),
                     "precedent_answer": standing["answer"] if standing else (earlier[0]["answer"] if earlier else ""),
                     "precedent_reason": standing["reason"] if standing else (reasons[0] if reasons else ""),
                     "prefilled": "yes" if standing else "no",
                     "answer": standing["answer"] if standing else "", "reason": standing["reason"] if standing else "",
                     "confirm": "", "queue": str(queue)})
    return rows


def write_sheet(queue: Path, destination: Path, quiet: bool = False) -> dict:
    rows = build_sheet(queue, quiet=quiet)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(destination, buffer.getvalue(), newline="")
    return {"sheet": str(destination), "rows": len(rows), "prefilled": sum(1 for r in rows if r["prefilled"] == "yes"),
            "mods": len({m for r in rows for m in r["mods"].split(MODS_SEPARATOR)})}


def read_sheet(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for column in ("group", "finding", "mods", "answer", "reason"):
        if rows and column not in rows[0]:
            raise SheetError(f"{path} has no '{column}' column; write the sheet with `escalation sheet QUEUE --write`.")
    return rows


def _decide(row: dict) -> tuple[str, str, int | None]:
    """(answer, reason, standing_count): the row's effective answer. standing_count is set when a pre-filled row is applied
    as the standing answer: the owner left answer and reason as pre-filled, or wrote confirm=yes beside the pre-filled answer.
    A pre-filled row the owner changed is the owner's own answer (standing_count None)."""
    answer, reason = (row.get("answer") or "").strip(), (row.get("reason") or "").strip()
    if row.get("prefilled") != "yes" or not answer or answer != row.get("precedent_answer", ""):
        return answer, reason, None
    confirmed = (row.get("confirm") or "").strip().lower() == "yes"
    if reason == (row.get("precedent_reason") or "").strip() or confirmed:
        return answer, reason, int(row.get("precedent_count") or 0)
    return answer, reason, None


def apply_sheet(sheet: Path, queue: Path | None = None, today: str | None = None) -> dict:
    """Apply every answered row through `escalation_queue.rule`. A row with no answer, or `skip`, is left open. A pre-filled
    row is applied only when unchanged or confirmed; one the owner edited is applied as the owner's own answer."""
    from .escalation_queue import rule

    rows = read_sheet(sheet)
    applied, skipped, errors = [], [], []
    for row in rows:
        answer, reason, standing = _decide(row)
        if answer in ("", "skip"):
            skipped.append(row["group"])
            continue
        if answer not in ANSWERS:
            errors.append({"group": row["group"], "error": f"answer '{answer}' is not one of {', '.join(ANSWERS)}"})
            continue
        target = Path(queue or row.get("queue") or "")
        if not target.is_dir():
            errors.append({"group": row["group"], "error": f"queue folder '{target}' not found; pass it explicitly"})
            continue
        full_reason = f"{reason} (standing approval from {standing} prior rulings)" if standing else reason
        try:
            entry = rule(target, row["finding"], accept=answer == "accept", approve_fixer=answer == "approve-fixer", reason=full_reason,
                         today=today, only_mods=set(row["mods"].split(MODS_SEPARATOR)) if answer == "accept" else None,
                         shape=row.get("shape") if answer == "accept" else None)
        except ValueError as exc:
            errors.append({"group": row["group"], "error": str(exc)})
            continue
        applied.append({"group": row["group"], "finding": row["finding"], "ruling": entry["ruling"], "mods": entry["mods"], "standing": standing})
    return {"sheet": str(sheet), "applied": applied, "skipped": skipped, "errors": errors}
