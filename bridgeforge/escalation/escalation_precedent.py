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

import hashlib
import json
import re
from collections import Counter
from datetime import date
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


def load_log(queue: Path) -> list[dict]:
    """Every line of ESCALATION_RULINGS.jsonl: rulings, and revocations (`{"revokes": id, ...}`)."""
    path = Path(queue) / RULINGS_FILE
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue  # a cut-short last line; the file is append-only
        if isinstance(row, dict):
            rows.append(row)
    return rows


def load_rulings(queue: Path) -> list[dict]:
    return [row for row in load_log(queue) if row.get("finding") and row.get("ruling")]


# --- Versioned semantic predicates (ROADMAP item 73 R4) -------------------------------------------------------------
# The question shape above only groups rows for reading. A ruling is reusable for another mod only when both answer the
# same *predicate*: finding id, the check's revision, and the evidence items that carry the ids/values the question is about.
# The ruling adds its operation and intent. Anything the code does not know is a refusal, never a wildcard.
PREDICATE_VERSION = 1
PREDICATE_FIELDS = frozenset({"version", "finding", "check_revision", "classification", "constraints"})
CHECK_REVISIONS: dict[str, int] = {}  # bump an id here when its check's meaning changes: older rulings stop matching
PERSON_ONLY_CATEGORIES = frozenset({"gameplay", "balance", "save", "save-compat"})
PERSON_ONLY_WORDS = ("save", "balance", "gameplay")
_VOLATILE_EVIDENCE = re.compile(r"^(?:line|count|overridden|vanilla-keys|files?)[: ]\s*\d*$|^[\w-]+:\d+$")


def person_only(finding: dict) -> bool:
    """MANUAL/UNKNOWN findings, and gameplay, balance and save decisions, are never answered by a standing ruling."""
    ident = str(finding.get("id") or "")
    return (finding.get("classification") in ("MANUAL", "UNKNOWN") or finding.get("category") in PERSON_ONLY_CATEGORIES
            or any(word in ident for word in PERSON_ONLY_WORDS))


def question_predicate(findings: list[dict]) -> dict:
    """The predicate of one mod's open question: its findings of one id. Counts and line numbers are dropped; every other
    evidence item (ids, keys, providers, values) is kept, so two mods match only when they ask about the same things."""
    first = findings[0]
    constraints = sorted({str(e) for f in findings for e in f.get("evidence") or [] if not _VOLATILE_EVIDENCE.match(str(e))})
    return {"version": PREDICATE_VERSION, "finding": first["id"], "check_revision": CHECK_REVISIONS.get(first["id"], 1),
            "classification": first.get("classification") or "", "constraints": constraints}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def predicate_hash(predicate: dict) -> str:
    return hashlib.sha256(_canonical(predicate).encode("utf-8")).hexdigest()[:16]


def ruling_id(entry: dict) -> str:
    """Identity of a ruling: a hash of its content (the `id` itself and `baseline_keys` bookkeeping left out)."""
    body = {k: v for k, v in entry.items() if k not in ("id", "baseline_keys")}
    return "R" + hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()[:12]


def predicate_problem(entry: dict) -> str | None:
    """Why a ruling cannot act as a standing source, or None. No predicate at all is a historical free-text ruling."""
    predicate = entry.get("predicate")
    if not isinstance(predicate, dict):
        return "no predicate (historical ruling: precedent only)"
    unknown = sorted(set(predicate) - PREDICATE_FIELDS)
    if unknown or predicate.get("version") != PREDICATE_VERSION:
        return f"unknown predicate fields or version ({', '.join(unknown) or predicate.get('version')})"
    if entry.get("predicate_hash") != predicate_hash(predicate):
        return "predicate hash does not match its predicate"
    if not predicate.get("constraints") or not str(entry.get("intent") or "").strip() or not str(entry.get("reason") or "").strip():
        return "incomplete evidence (constraints, intent and reason are all required)"
    return None


def invalid_ids(log: list[dict], today: str | None = None) -> set[str]:
    """Rulings that no longer stand: revoked, expired, or derived from a source that is invalid (propagates to a fixpoint)."""
    today = today or date.today().isoformat()
    rulings = {r["id"]: r for r in log if r.get("id") and r.get("ruling")}
    bad = {r["revokes"] for r in log if r.get("revokes")}
    bad |= {i for i, r in rulings.items() if r.get("expires") and str(r["expires"]) < today}
    changed = True
    while changed:
        changed = False
        for ident, entry in rulings.items():
            if ident not in bad and any(source in bad for source in entry.get("derived_from") or []):
                bad.add(ident)
                changed = True
    return bad


def standing_eligibility(queue: Path, findings: list[dict], mod: str, operation: str = "accept", today: str | None = None) -> dict:
    """Whether earlier rulings already answer `mod`'s open question (`findings`: its findings of one id). Eligible only when
    three or more *other* mods were each ruled on the same predicate with the same operation and intent, no valid ruling on
    that predicate says otherwise, and the evidence is complete. `reasons` lists every refusal."""
    refusals: list[str] = []
    if operation != "accept":
        refusals.append(f"operation '{operation}' is never applied as a standing ruling")
    if any(person_only(f) for f in findings):
        refusals.append("MANUAL/UNKNOWN, gameplay, balance and save decisions are person-only")
    predicate = question_predicate(findings)
    if not predicate["constraints"]:
        refusals.append("incomplete evidence: the findings carry no ids or values to match on")
    result = {"eligible": False, "reasons": refusals, "predicate": predicate, "predicate_hash": predicate_hash(predicate),
              "sources": [], "source_hashes": [], "intent": "", "reason": "", "independent_mods": []}
    if refusals:
        return result
    log = load_log(queue)
    bad = invalid_ids(log, today)
    matching = [r for r in log if r.get("ruling") and not r.get("derived_from") and r.get("id") and r["id"] not in bad
                and r.get("finding") == predicate["finding"] and r.get("predicate_hash") == result["predicate_hash"]]
    usable, unusable = [], []
    for entry in matching:
        problem = predicate_problem(entry)
        (unusable if problem else usable).append((entry, problem))
    for entry, problem in unusable:
        refusals.append(f"ruling {entry['id']}: {problem}")
    answers = {(e["ruling"], str(e.get("intent") or "").strip()) for e, _ in usable}
    if len(answers) > 1:
        refusals.append("conflicting rulings on the same predicate: " + "; ".join(f"{op} ({intent})" for op, intent in sorted(answers)))
    mods = sorted({m for e, _ in usable for m in e.get("mods") or [] if m != mod})
    if not refusals and len(mods) < STANDING_THRESHOLD:
        refusals.append(f"{len(mods)} independent prior mod(s) with this predicate; {STANDING_THRESHOLD} needed")
    if not refusals and next(iter(answers))[0] != operation:
        refusals.append(f"the prior rulings are '{next(iter(answers))[0]}', not '{operation}'")
    if refusals:
        return result
    chosen = [e for e, _ in usable]
    result.update(eligible=True, sources=[e["id"] for e in chosen], source_hashes=sorted({e["predicate_hash"] for e in chosen}),
                  intent=next(iter(answers))[1], reason=Counter(e["reason"] for e in chosen).most_common(1)[0][0], independent_mods=mods)
    return result


def revoke_ruling(queue: Path, target_id: str, reason: str, today: str | None = None) -> dict:
    """Withdraw one ruling. Every standing application derived from it (transitively) falls with it, and the accepted-finding
    keys any of them put into mod baselines are taken back out; a revoked fixer approval leaves AUTOMATION_POLICY.json."""
    from bridgeforge.baseline import remove_findings
    from bridgeforge.safeio import atomic_write_text

    queue = Path(queue)
    if not reason.strip():
        raise ValueError("a revocation needs a reason.")
    log = load_log(queue)
    rulings = {r["id"]: r for r in log if r.get("id") and r.get("ruling")}
    if target_id not in rulings:
        raise ValueError(f"no ruling with id {target_id} in {RULINGS_FILE}.")
    before = invalid_ids(log)
    if target_id in before:
        raise ValueError(f"ruling {target_id} is already invalid.")
    entry = {"date": today or date.today().isoformat(), "revokes": target_id, "reason": reason}
    after = invalid_ids([*log, entry])
    with (queue / RULINGS_FILE).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    newly = sorted(after - before)
    for ident in newly:
        ruling = rulings.get(ident) or {}
        for mod, keys in (ruling.get("baseline_keys") or {}).items():
            remove_findings(queue / mod / "working", keys)
        if ruling.get("ruling") == "approve-fixer":
            policy = queue / "AUTOMATION_POLICY.json"
            if policy.is_file():
                data = json.loads(policy.read_text(encoding="utf-8"))
                (data.get("approved_fixers") or {}).pop(ruling["finding"], None)
                atomic_write_text(policy, json.dumps(data, indent=2) + "\n")
    return {"revoked": target_id, "invalidated": newly}


def baseline_precedents(queue: Path, finding_id: str, *, exclude: str | None = None) -> list[dict]:
    """Reasons recorded in workspace baselines for keys of `finding_id`, one precedent per mod and reason."""
    from bridgeforge.baseline import mod_baseline_path

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
                          "date": stamp.get("date"), "mods": [workspace.name], "predicate_problem": "baseline reason, no predicate (precedent only)"})
    return found


def precedents(queue: Path, finding_id: str, *, exclude: str | None = None) -> list[dict]:
    """Every earlier answer to `finding_id`, newest first. A baseline reason that a ruling already covers (same reason
    text, the mod listed in the ruling) is the same answer, not a second one."""
    log = load_log(queue)
    bad = invalid_ids(log)
    # Standing applications (derived_from) are logged but are not precedent: counting them would let a rule reinforce itself.
    rulings = [{"source": "ruling", "finding": finding_id, "answer": r["ruling"], "reason": r.get("reason") or "",
                "date": r.get("date"), "mods": list(r.get("mods") or []), "id": r.get("id"), "intent": r.get("intent") or "",
                "predicate": r.get("predicate"), "predicate_hash": r.get("predicate_hash"), "revoked": r.get("id") in bad,
                "predicate_problem": predicate_problem(r)}
               for r in log if r.get("ruling") and r.get("finding") == finding_id and not r.get("derived_from")]
    covered = {(mod, entry["reason"]) for entry in rulings for mod in entry["mods"]}
    extra = [entry for entry in baseline_precedents(queue, finding_id, exclude=exclude) if (entry["mods"][0], entry["reason"]) not in covered]
    return sorted(rulings + extra, key=lambda e: (e.get("date") or "", e["source"]), reverse=True)


def standing_answer(entries: list[dict], threshold: int = STANDING_THRESHOLD) -> dict | None:
    """`{answer, reason, count}` when `threshold` or more precedents agree on one answer (the most common reason among
    them), else None. Disagreeing precedents never prefill: the answer must be one every earlier ruling gave."""
    entries = [e for e in entries if not e.get("revoked")]  # a withdrawn ruling suggests nothing
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
