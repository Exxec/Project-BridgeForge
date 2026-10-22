"""Case workspace inputs of `research report` (82.1): trees, REMOVALS.json, dropped features, live records and gates. Reads only."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .dropped_sweep import check_workspace, mod_roots, select_old_tree
from .gates import RECORDABLE, load_gates
from .live_ledger import read_runs
from .removals import REMOVALS_FILE, RemovalsError, load_removals
from .research_terms import OBSERVED, STATIC, VALIDATED, Matcher

OPEN_STATES = ("LIVE_PENDING", "NOT_TESTED", "BLOCKED")
_ARTIFACT = re.compile(r"[\w./-]+\.(?:jar|csv|json|java|ini)\b")


def locate_trees(workspace: Path) -> list[dict]:
    """`[{"label", "path", "rel"}]`: the working copy, every original mod root and the old tree dropped-features compares against."""
    found: list[tuple[str, Path]] = []
    working = workspace / "working"
    if working.is_dir():
        found.append(("working", working))
    original = workspace / "original"
    if original.is_dir():
        found += [("original", root) for root in mod_roots(original)]
    old = select_old_tree(workspace)
    if old["tree"] is not None:
        found.append(("old-tree", old["tree"]))
    seen: set[Path] = set()
    out = []
    for label, path in found:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            rel = resolved.relative_to(workspace.resolve()).as_posix()
        except ValueError:
            rel = str(resolved)
        out.append({"label": label, "path": path, "rel": rel})
    return out


def removals(workspace: Path, matcher: Matcher) -> dict:
    """REMOVALS.json entries mentioning a term, each with the artifacts its reason names checked for existence in working/."""
    path = workspace / "working" / REMOVALS_FILE
    record = {"name": "removals", "path": str(path), "command": "python -m bridgeforge remove --help   (REMOVALS.json is written by `remove` and by hand)"}
    if not path.is_file():
        return {"input": {**record, "status": "MISSING", "note": "no REMOVALS.json: no removal is recorded as decided"}, "entries": [], "total": 0}
    try:
        entries = load_removals(workspace / "working")
    except RemovalsError as exc:
        return {"input": {**record, "status": "MISSING", "note": f"unreadable: {exc}"}, "entries": [], "total": 0}
    picked = []
    for entry in entries:
        target = entry.get("item") or entry.get("pattern", "")
        terms = matcher.any_name(target, entry["reason"])
        if not terms:
            continue
        named = sorted({m for m in _ARTIFACT.findall(entry["reason"])})
        checks = [{"artifact": a, "exists_in_working": (workspace / "working" / a).exists()} for a in named if "/" in a or a.endswith(".jar")]
        picked.append({**entry, "terms": terms, "target": target, "artifact_checks": checks, "label": STATIC,
                       "evidence": f"{REMOVALS_FILE} ({entry['category']} {target})"})
    return {"input": {**record, "status": "PRESENT", "note": f"{len(entries)} entries, {len(picked)} mention the feature"}, "entries": picked, "total": len(entries)}


def dropped(workspace: Path, matcher: Matcher) -> dict:
    """dropped-features (`dropped_sweep.check_workspace`) restricted to items that mention a term."""
    record = {"name": "dropped-features", "command": f'python -m bridgeforge dropped-features "{workspace}"', "path": ""}
    try:
        row = check_workspace(workspace)
    except (OSError, ValueError) as exc:
        return {"input": {**record, "status": "MISSING", "note": f"failed: {exc}"}, "verdict": "UNDETERMINED", "items": []}
    if row["old_tree"] is None:
        return {"input": {**record, "status": "MISSING", "note": row["reason"]}, "verdict": row["verdict"], "items": []}
    items = [{"category": cat, "item": item, "explained": state == "explained", "label": STATIC}
             for cat, split in sorted(row["dropped"].items()) for state in ("unexplained", "explained") for item in split[state] if matcher.any_name(item)]
    note = f"old tree {row['old_tree']} ({row['origin']}); {row['total']} dropped item(s), {row['unexplained']} unexplained; {len(items)} mention the feature"
    return {"input": {**record, "status": "PRESENT", "note": note}, "verdict": row["verdict"], "items": items,
            "old_tree": row["old_tree"], "totals": {"total": row["total"], "explained": row["explained"], "unexplained": row["unexplained"]}}


def content_parity_for(workspace: Path, matcher: Matcher) -> dict:
    """The shipped-vs-original verdict of `Done/CONTENT_PARITY.json` (done-audit --content-parity) for this workspace, items kept to the feature."""
    path = workspace.parent.parent / "Done" / "CONTENT_PARITY.json"
    record = {"name": "content-parity", "path": str(path), "command": "python -m bridgeforge done-audit --content-parity --write <DIR>"}
    if not path.is_file():
        return {"input": {**record, "status": "MISSING", "note": "no CONTENT_PARITY.json: shipped zips were not compared with their originals"}, "row": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"input": {**record, "status": "MISSING", "note": f"unreadable: {exc}"}, "row": None}
    row = next((m for m in data.get("mods", []) if str(m.get("mod", "")).lower() == workspace.name.lower()), None)
    if row is None:
        return {"input": {**record, "status": "MISSING", "note": f"no row for {workspace.name} (not archived to Done/, or the audit predates it)"}, "row": None}
    items = [{"class": key, "item": item} for key in ("missing", "shadow", "renamed", "junk", "src") for item in row.get(key, []) if matcher.any_name(str(item))]
    items += [{"class": f"unexplained {cat}", "item": item} for cat, values in sorted((row.get("unexplained") or {}).items()) for item in values if matcher.any_name(str(item))]
    return {"input": {**record, "status": "PRESENT", "note": f"verdict {row.get('verdict')}; {len(items)} item(s) mention the feature"},
            "row": {"verdict": row.get("verdict"), "shipped": row.get("shipped"), "items": items, "label": STATIC}}


def live_records(workspace: Path, mod_ids: set[str], matcher: Matcher) -> dict:
    """Recorded live runs (`In operation/_live`) of this workspace or mod id, labelled OBSERVED, and whether the record names the feature."""
    queue = workspace.parent
    record = {"name": "live-records", "path": str(queue / "_live"), "command": "python -m bridgeforge probe-group live <TESTID>   then   probe-group record <TESTID> --accept"}
    wanted = {workspace.name.lower(), *{m.lower() for m in mod_ids}}
    rows = [r for r in read_runs(queue) if str(r.get("workspace") or "").lower() in wanted or str(r.get("mod") or "").lower() in wanted]
    out = []
    for row in rows:
        path = queue / ("_live" if row["source"] == "record" else "_regress") / f"{row['test_id']}.json"
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        triage = {}
        if text:
            try:
                data = json.loads(text)
                triage = data.get("triage", {}) if isinstance(data, dict) else {}
            except ValueError:
                pass
        out.append({**row, "triage": triage, "names_feature": bool(matcher.any_name(text)) if text else False, "label": OBSERVED,
                    "evidence": f"_live/{row['test_id']}.json" if row["source"] == "record" else f"_regress/{row['test_id']}.json"})
    if not out:
        return {"input": {**record, "status": "MISSING", "note": "no live run recorded for this workspace or mod id"}, "runs": []}
    return {"input": {**record, "status": "PRESENT", "note": f"{len(out)} run(s); {sum(r['names_feature'] for r in out)} name the feature"}, "runs": out}


def _gate_reasons(gate: dict, matcher: Matcher, mod_ids: set[str]) -> list[str]:
    needs = gate.get("needs") or {}
    reasons = [f"term {t}" for t in matcher.any_name(gate["id"], gate["title"], str(needs.get("scenario") or ""), *gate.get("commands", []),
                                                    str((gate.get("source_doc") or {}).get("anchor", "")))]
    lowered = {m.lower() for m in mod_ids}
    reasons += [f"needs mod {m}" for m in needs.get("mods", []) if m.lower() in lowered]
    return reasons


def gates_for(repo: Path, matcher: Matcher, mod_ids: set[str]) -> dict:
    """Gates of `repo/gates.json` that name a term or need the case's mod; PASS-with-evidence ones are the only VALIDATED source."""
    record = {"name": "gates", "path": str(repo / "gates.json"), "command": "python -m bridgeforge board --live-pending --repos <repo>"}
    try:
        data = load_gates(repo)
    except (OSError, ValueError) as exc:
        return {"input": {**record, "status": "MISSING", "note": f"no usable gates.json: {exc}"}, "gates": []}
    out = []
    for gate in data["gates"]:
        reasons = _gate_reasons(gate, matcher, mod_ids)
        if not reasons:
            continue
        validated = gate["state"] == "PASS" and bool(gate.get("evidence"))
        out.append({"id": gate["id"], "title": gate["title"], "state": gate["state"], "open": gate["state"] in OPEN_STATES, "evidence": gate.get("evidence", []),
                    "needs": gate.get("needs", {}), "commands": gate.get("commands", []), "reasons": reasons, "updated": gate.get("updated"),
                    "label": VALIDATED if validated else STATIC, "source_doc": gate.get("source_doc")})
    out.sort(key=lambda g: (not any(r.startswith("term") for r in g["reasons"]), g["id"]))
    return {"input": {**record, "status": "PRESENT", "note": f"{len(data['gates'])} gates, {len(out)} relevant; states {', '.join(RECORDABLE)} are recordable"}, "gates": out}
