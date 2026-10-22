"""Concept presence across the case's trees and the Atlas-indexed peers (82.1: what differs and what is supported). STATIC only.

A concept is present in a tree when the Atlas extractor or the archaeology graph found it there for a feature term (union of the two).
Changes are judged between the baseline tree (the dropped-features old tree, else the first original) and the working copy:
kept, moved (present in both, no file in common), absent-in-working, added-in-working. A change is a fact about files; why it
happened is only ever stated by a REMOVALS record, which is quoted, not judged. Concepts only peers carry are counted, not listed.
"""
from __future__ import annotations

from .research_reconcile import Concept
from .research_terms import STATIC

MAX_SHARED_LISTED = 15
MAX_FILES_SHOWN = 4


def merge(*sides: dict[str, Concept] | None) -> dict[str, Concept]:
    out: dict[str, Concept] = {}
    for side in sides:
        for key, concept in (side or {}).items():
            target = out.setdefault(key, Concept())
            target.names |= concept.names
            target.roles |= concept.roles
            target.kinds |= concept.kinds
            target.files |= concept.files
            target.terms |= concept.terms
            target.locations += [loc for loc in concept.locations if loc not in target.locations][:6 - len(target.locations)]
    return out


def baseline_label(trees: dict[str, dict[str, Concept]], labels: dict[str, str]) -> str | None:
    """The tree id changes are judged from: old-tree, else the first original (None when the case has neither)."""
    for wanted in ("old-tree", "original"):
        for tree_id in trees:
            if labels[tree_id] == wanted:
                return tree_id
    return None


def _change(base: Concept | None, work: Concept | None) -> str:
    if base and work:
        return "kept" if base.files & work.files else "moved"
    if base:
        return "absent-in-working"
    return "added-in-working" if work else "peers-only"


def _records_for(names: set[str], key: str, records: list[dict]) -> list[str]:
    needles = {key.split("$")[0], *(name.lower().split("$")[0] for name in names)}  # an inner class follows its outer class's record
    return [f"{r['category']} {r['target']}: {r['reason']} [{r['source']}, {r['date']}]" for r in records
            if any(n and n in f"{r['target']} {r['reason']}".lower() for n in needles)]


def replacement_links(work: dict[str, Concept], records: list[dict]) -> list[dict]:
    """For each artifact a REMOVALS reason names (and that exists in working/): the feature concepts found in it, so a record that says
    'Re-created as jars/X.jar' is tied to what X actually contains. A fact about files; whether X behaves the same stays unknown."""
    by_artifact: dict[str, dict] = {}
    for record in records:
        for check in record["artifact_checks"]:
            if check["exists_in_working"]:
                entry = by_artifact.setdefault(check["artifact"], {"artifact": check["artifact"], "records": [], "concepts": []})
                entry["records"].append(f"{record['category']} {record['target']}")
    for entry in by_artifact.values():
        entry["concepts"] = sorted(key for key, concept in work.items() if entry["artifact"] in concept.files)
        entry["label"] = STATIC
    return [by_artifact[a] for a in sorted(by_artifact)]


def compare(trees: dict[str, dict[str, Concept]], labels: dict[str, str], peers: list[dict], records: list[dict]) -> dict:
    """The concept matrix. `trees` maps tree id -> concepts, `labels` tree id -> working/original/old-tree, `peers` Atlas database mods."""
    base_id = baseline_label(trees, labels)
    work_id = next((t for t in trees if labels[t] == "working"), None)
    peer_keys = {f"atlas:{p['mod']} {p['version']}": set(p["concept_keys"]) for p in peers}
    keys = sorted(set().union(*trees.values()))
    rows = []
    for key in keys:
        concept = merge(*({key: t[key]} for t in trees.values() if key in t))[key]
        change = _change(trees[base_id].get(key), trees[work_id].get(key)) if base_id and work_id else "no-baseline"
        holders = sorted(subject for subject, found in peer_keys.items() if key in found)
        rows.append({"concept": key, "names": sorted(concept.names)[:6], "terms": sorted(concept.terms), "change": change,
                     "present": {t: key in c for t, c in trees.items()},
                     "files": {t: sorted(c[key].files)[:MAX_FILES_SHOWN] for t, c in trees.items() if key in c},
                     "peers": holders, "removal_records": _records_for(concept.names, key, records), "label": STATIC})
    peers_only = sorted(set().union(*peer_keys.values()) - set(keys)) if peer_keys else []
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["change"]] = counts.get(row["change"], 0) + 1
    overlap = []
    work = trees.get(work_id, {}) if work_id else {}
    for peer in peers:
        theirs = peer_keys[f"atlas:{peer['mod']} {peer['version']}"]
        overlap.append({"mod": peer["mod"], "version": peer["version"], "shared": len(set(work) & theirs), "case_only": len(set(work) - theirs),
                        "peer_only": len(theirs - set(work)), "shared_examples": sorted(set(work) & theirs)[:MAX_SHARED_LISTED], "label": STATIC})
    return {"baseline": base_id, "working": work_id, "subjects": list(trees), "rows": rows, "change_counts": dict(sorted(counts.items())),
            "peers_only_concepts": len(peers_only), "peer_overlap": overlap, "replacement_links": replacement_links(work, records), "label": STATIC}
