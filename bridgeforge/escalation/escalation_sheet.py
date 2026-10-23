"""`bridgeforge escalation sheet`: one CSV that answers every open decision across a queue (ROADMAP item 73, C1, revised by R4).

`escalation queue` says which findings block the ESCALATED mods; this turns the decision-tier ones into rows to answer.
Open decision findings are grouped by (finding id, question shape): the finding's explanation with ids, paths and
numbers replaced by placeholders. The grouping is presentation only. Each row carries the earlier answers
(`escalation_precedent`); when three or more agree, `answer` and `reason` are *suggested* (`prefilled=yes`).

What `--apply` does (owner decision 2, 2026-10-14, with the R4 limits):
- A row the owner answered is applied. A pre-filled row counts as answered only when the owner edited it or wrote
  `confirm=yes`: an untouched suggestion is not an approval. `skip` leaves the row, and every mod in it, open.
- A row with no answer (or an untouched suggestion) is applied to a mod only when that mod is *eligible for a standing
  ruling* (`escalation_precedent.standing_eligibility`): three other mods were ruled on the same versioned predicate with
  the same operation and intent, nothing valid conflicts, the evidence is complete, and the finding is not person-only.
  Each such application logs the source ruling ids and predicate hash with "standing approval from N prior rulings".
- The owner's `intent` column makes an explicit `accept` reusable later; without it the ruling is precedent only.
Applying calls `escalation_queue.rule`, the one mechanism for rulings. Writes only the sheet, and on apply what `rule` writes.
"""
from __future__ import annotations

import csv
import io
import json
import time
from pathlib import Path

from bridgeforge.baseline import finding_dict_baseline_key, mod_baseline_keys
from bridgeforge.escalation.escalation_precedent import precedents, question_predicate, question_shape, standing_answer, standing_eligibility
from bridgeforge.progress import Checkpoint, report
from bridgeforge.report_status import is_closed
from bridgeforge.safeio import atomic_write_text

SCHEMA_VERSION = 2
CHECKPOINT_FILE = "ESCALATION_SHEET.partial.jsonl"
COLUMNS = ("group", "finding", "shape", "mods", "precedent_count", "precedent_answer", "precedent_reason", "prefilled",
           "standing_mods", "answer", "reason", "intent", "confirm", "queue")
ANSWERS = ("accept", "approve-fixer", "skip")
MODS_SEPARATOR = ";"
_KEPT_FIELDS = ("id", "classification", "category", "evidence")


class SheetError(ValueError):
    pass


def _open_decisions(workspace: Path) -> list[dict]:
    """The workspace's open decision findings as `{finding, shape, findings}`; accepted ones are left out."""
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
            entry = found.setdefault((finding["id"], shape), {"finding": finding["id"], "shape": shape, "findings": []})
            entry["findings"].append({k: finding.get(k) for k in _KEPT_FIELDS})
    return list(found.values())


def build_sheet(queue: Path, quiet: bool = False) -> list[dict]:
    queue = Path(queue).expanduser().resolve()
    workspaces = sorted(p for p in queue.iterdir() if p.is_dir() and not p.name.startswith("_")
                        and (p / "reports" / "revive" / "REVIVE.json").is_file() and not is_closed(p))
    header = {"schema_version": SCHEMA_VERSION, "queue": str(queue), "workspaces": [w.name for w in workspaces],
              "revive_mtimes": {w.name: (w / "reports" / "revive" / "REVIVE.json").stat().st_mtime for w in workspaces}}
    groups: dict[tuple[str, str], dict[str, list[dict]]] = {}
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
                groups.setdefault((item["finding"], item["shape"]), {})[workspace.name] = item["findings"]
        checkpoint.finish()
    rows = []
    for number, ((finding, shape), by_mod) in enumerate(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])), 1):
        mods = sorted(by_mod)
        # A mod's own earlier baseline reasons are not precedent for its own open question.
        earlier = [p for p in precedents(queue, finding) if not (p["mods"] and set(p["mods"]) <= set(mods))]
        suggestion = standing_answer(earlier)
        reasons = [p["reason"] for p in earlier if p["reason"]]
        standing = [m for m in mods if standing_eligibility(queue, by_mod[m], m)["eligible"]]
        rows.append({"group": f"G{number:03d}", "finding": finding, "shape": shape, "mods": MODS_SEPARATOR.join(mods),
                     "precedent_count": len(earlier),
                     "precedent_answer": suggestion["answer"] if suggestion else (earlier[0]["answer"] if earlier else ""),
                     "precedent_reason": suggestion["reason"] if suggestion else (reasons[0] if reasons else ""),
                     "prefilled": "yes" if suggestion else "no", "standing_mods": MODS_SEPARATOR.join(standing),
                     "answer": suggestion["answer"] if suggestion else "", "reason": suggestion["reason"] if suggestion else "",
                     "intent": "", "confirm": "", "queue": str(queue)})
    return rows


def write_sheet(queue: Path, destination: Path, quiet: bool = False) -> dict:
    rows = build_sheet(queue, quiet=quiet)
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    atomic_write_text(destination, buffer.getvalue(), newline="")
    return {"sheet": str(destination), "rows": len(rows), "prefilled": sum(1 for r in rows if r["prefilled"] == "yes"),
            "standing": sum(len(r["standing_mods"].split(MODS_SEPARATOR)) for r in rows if r["standing_mods"]),
            "mods": len({m for r in rows for m in r["mods"].split(MODS_SEPARATOR)})}


def read_sheet(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for column in ("group", "finding", "mods", "answer", "reason"):
        if rows and column not in rows[0]:
            raise SheetError(f"{path} has no '{column}' column; write the sheet with `escalation sheet QUEUE --write`.")
    return rows


def _explicit_answer(row: dict) -> tuple[str, str]:
    """(answer, reason) the owner gave, or ("", "") when the row is blank or still the untouched suggestion."""
    answer, reason = (row.get("answer") or "").strip(), (row.get("reason") or "").strip()
    if not answer:
        return "", ""
    untouched = (row.get("prefilled") == "yes" and answer == row.get("precedent_answer", "")
                 and reason == (row.get("precedent_reason") or "").strip())
    if untouched and (row.get("confirm") or "").strip().lower() != "yes":
        return "", ""
    return answer, reason


def _mod_findings(queue: Path, mod: str, finding: str, shape: str) -> list[dict]:
    for item in _open_decisions(queue / mod):
        if item["finding"] == finding and item["shape"] == shape:
            return item["findings"]
    return []


def _apply_explicit(queue: Path, row: dict, answer: str, reason: str, today: str | None, rule) -> list[dict]:
    mods = [m for m in row["mods"].split(MODS_SEPARATOR) if m]
    intent = (row.get("intent") or "").strip()
    if answer != "accept":
        return [rule(queue, row["finding"], approve_fixer=True, reason=reason, today=today)]
    if not intent:  # no intent: still recorded and applied, but never a standing source
        return [rule(queue, row["finding"], accept=True, reason=reason, today=today, only_mods=set(mods), shape=row.get("shape"))]
    by_predicate: dict[str, tuple[dict, set[str]]] = {}
    for mod in mods:
        found = _mod_findings(queue, mod, row["finding"], row.get("shape") or "")
        if found:
            predicate = question_predicate(found)
            by_predicate.setdefault(json.dumps(predicate, sort_keys=True), (predicate, set()))[1].add(mod)
    return [rule(queue, row["finding"], accept=True, reason=reason, today=today, only_mods=group, shape=row.get("shape"),
                 predicate=predicate, intent=intent) for predicate, group in by_predicate.values()]


def _apply_standing(queue: Path, row: dict, today: str | None, rule) -> tuple[list[dict], list[dict]]:
    applied, refused = [], []
    for mod in [m for m in (row.get("standing_mods") or "").split(MODS_SEPARATOR) if m]:
        found = _mod_findings(queue, mod, row["finding"], row.get("shape") or "")
        verdict = standing_eligibility(queue, found, mod, today=today) if found else None
        if verdict is None or not verdict["eligible"]:
            refused.append({"group": row["group"], "mod": mod, "reasons": verdict["reasons"] if verdict else ["no open finding"]})
            continue
        n = len(verdict["sources"])
        applied.append(rule(queue, row["finding"], accept=True, today=today, only_mods={mod}, shape=row.get("shape"),
                            reason=f"{verdict['reason']} (standing approval from {n} prior rulings: {', '.join(verdict['sources'])}; "
                                   f"predicate {verdict['predicate_hash']})",
                            predicate=verdict["predicate"], intent=verdict["intent"], derived_from=verdict["sources"]))
    return applied, refused


def apply_sheet(sheet: Path, queue: Path | None = None, today: str | None = None) -> dict:
    """Apply the explicitly answered rows, then standing rulings for mods the owner left open (see the module docstring)."""
    from bridgeforge.escalation.escalation_queue import rule

    rows = read_sheet(sheet)
    applied, skipped, errors, refused = [], [], [], []
    for row in rows:
        target = Path(queue or row.get("queue") or "")
        if not target.is_dir():
            errors.append({"group": row["group"], "error": f"queue folder '{target}' not found; pass it explicitly"})
            continue
        answer, reason = _explicit_answer(row)
        if answer == "skip":
            skipped.append(row["group"])
            continue
        try:
            if answer:
                if answer not in ANSWERS:
                    raise ValueError(f"answer '{answer}' is not one of {', '.join(ANSWERS)}")
                entries = _apply_explicit(target, row, answer, reason, today, rule)
                applied += [{"group": row["group"], "finding": row["finding"], "ruling": e["ruling"], "mods": e["mods"], "standing": None} for e in entries]
            else:
                entries, no = _apply_standing(target, row, today, rule)
                refused += no
                applied += [{"group": row["group"], "finding": row["finding"], "ruling": e["ruling"], "mods": e["mods"],
                             "standing": e.get("derived_from")} for e in entries]
                if not entries:
                    skipped.append(row["group"])
        except ValueError as exc:
            errors.append({"group": row["group"], "error": str(exc)})
    return {"sheet": str(sheet), "applied": applied, "skipped": skipped, "errors": errors, "standing_refused": refused}
