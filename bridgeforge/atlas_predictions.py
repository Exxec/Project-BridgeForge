"""Atlas predictions and their outcomes (ROADMAP 70 H3.1).

A forecast finding is a PREDICTION: a static reading of what two mods might do to each other. A probe run can confirm or refute it.
This module keeps those outcomes in `docs/atlas_predictions.json` (committed: it is evidence, with the run id), annotates findings
that match a recorded outcome, and reports how often each rule's predictions held (`atlas precision`).

Born from three cases in two days: DNEEP x AoTD (the static read of `farming` was confirmed by a live run: no food anywhere),
Legacy of Arkgneisis x AoTD (the predicted loss of the development bonus was refuted: orbital works kept), and the first guess that
Arkgneisis caused a save crash (refuted by the base rate). Outcomes: confirmed, refuted, inconclusive.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .safeio import atomic_write_text

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "docs" / "atlas_predictions.json"
OUTCOMES = ("confirmed", "refuted", "inconclusive")


def load(path: Path | None = None) -> list[dict]:
    try:
        data = json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("predictions", []) if isinstance(data, dict) else []
    return [e for e in entries if isinstance(e, dict) and e.get("rule") and e.get("outcome") in OUTCOMES]


def record(rule: str, mod: str, ident: str, outcome: str, run: str, note: str, other: str | None = None,
           path: Path | None = None, today: str | None = None) -> dict:
    """Append one outcome. A run id and a note are required: an outcome without evidence is not recorded."""
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {', '.join(OUTCOMES)}")
    if not run.strip() or not note.strip():
        raise ValueError("an outcome needs the run id that showed it and a note saying what was seen")
    entry = {"rule": rule, "mod": mod, "other": other, "id": ident, "outcome": outcome, "run": run.strip(), "note": note.strip(),
             "date": today or date.today().isoformat()}
    path = Path(path or DEFAULT_PATH)
    entries = load(path)
    entries.append(entry)
    atomic_write_text(path, json.dumps({"schema_version": 1, "predictions": entries}, indent=2, ensure_ascii=False) + "\n", newline="")
    return entry


def precision(entries: list[dict]) -> dict[str, dict]:
    """Per rule: counts by outcome and the share of decided predictions (confirmed + refuted) that were confirmed."""
    table: dict[str, dict] = {}
    for entry in entries:
        row = table.setdefault(entry["rule"], {"confirmed": 0, "refuted": 0, "inconclusive": 0})
        row[entry["outcome"]] += 1
    for row in table.values():
        decided = row["confirmed"] + row["refuted"]
        row["hit_rate"] = round(row["confirmed"] / decided, 2) if decided else None
    return table


def annotate(findings: list, entries: list[dict]) -> None:
    """Add `[prediction confirmed by RUN]` / `[prediction refuted by RUN]` to findings that match a recorded outcome: same rule, the
    entry's mod among the finding's mods (and its `other` too when given), and the entry's id among the finding's ids. In place."""
    for finding in findings:
        for entry in entries:
            if entry["rule"] != finding.rule or entry["mod"].lower() not in {m.lower() for m in finding.mods}:
                continue
            if entry.get("other") and entry["other"].lower() not in {m.lower() for m in finding.mods}:
                continue
            if entry["id"] not in finding.ids or "[prediction" in finding.summary:
                continue
            finding.summary += f" [prediction {entry['outcome']} by {entry['run']}: {entry['note']}]"
            break
