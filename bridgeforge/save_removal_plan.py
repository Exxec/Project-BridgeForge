"""`bridgeforge save-removal-plan`: what removing a missing mod's objects from a save would take (Salvor groundwork,
2026-10-02). Read-only.

XStream writes every object once with an id (`z="N"`) and refers back to it elsewhere with `ref="N"`. Removing an
object that still has references from outside itself leaves them dangling, and the save then fails in a new way.
This finds, for each serialized object of a class `save-doctor` reports as CLASS_UNRESOLVED (a missing mod's), the
ids inside it and every reference to them from outside, and classifies it:

- DROPPABLE: nothing outside points in; removing the element (from a copy) leaves no dangling reference.
- BLOCKED: referenced from elsewhere; each outside reference is listed, so a person or a later Salvor fix can decide
  whether that reference can go too.

The parent element is recorded: an entry in a list or map can usually be removed outright, while a field of a game
object needs that field handled too. Nothing is written.
"""
from __future__ import annotations

import re
from pathlib import Path

from .save_doctor import diagnose
from .save_reader import campaign_xml_path

SCHEMA_VERSION = 1
_TAG = re.compile(r"<(/?)([A-Za-z_][\w.\-]*)((?:\s+[\w:.\-]+=\"[^\"]*\")*)\s*(/?)>")
_ATTR = re.compile(r'([\w:.\-]+)="([^"]*)"')


def plan_removal(save: Path, mods_dir: Path, vanilla_core: Path | None = None, *, max_listed: int = 20) -> dict:
    doctor = diagnose(save, mods_dir, vanilla_core)
    # The exact class names, not their packages: data.scripts is shared by many installed mods (Ward Franks).
    classes = {c for p in doctor["problems"] if p["class"] == "CLASS_UNRESOLVED" for c in p.get("classes") or []}
    packages = {p["package"] for p in doctor["problems"] if p["class"] == "CLASS_UNRESOLVED"}
    campaign_xml = campaign_xml_path(save)

    def unresolved(name: str) -> bool:
        return name in classes

    subtrees: list[dict] = []
    refs: list[tuple[str, int | None, str]] = []  # (ref id, index of the subtree it sits in or None, path)
    stack: list[tuple[str, int | None]] = []  # (tag, subtree index this element belongs to)
    if classes:
        with campaign_xml.open("r", encoding="utf-8", errors="replace") as handle:
            for line_no, line in enumerate(handle, 1):
                for match in _TAG.finditer(line):
                    closing, tag, attr_text, self_closing = match.groups()
                    if closing:
                        if stack and stack[-1][0] == tag:
                            stack.pop()
                        continue
                    attrs = dict(_ATTR.findall(attr_text))
                    inside = stack[-1][1] if stack else None
                    if inside is None and (unresolved(tag) or unresolved(attrs.get("cl", ""))):
                        inside = len(subtrees)
                        subtrees.append({"class": attrs.get("cl") or tag, "line": line_no,
                                         "parent": stack[-1][0] if stack else None,
                                         "path": "/" + "/".join(t for t, _ in stack[-6:] + [(tag, None)]), "ids": set()})
                    if inside is not None and "z" in attrs:
                        subtrees[inside]["ids"].add(attrs["z"])
                    if "ref" in attrs:
                        refs.append((attrs["ref"], inside, "/" + "/".join(t for t, _ in stack[-4:] + [(tag, None)])))
                    if not self_closing:
                        stack.append((tag, inside))
    owner = {z: index for index, tree in enumerate(subtrees) for z in tree["ids"]}
    external: dict[int, list[str]] = {}
    for ref, inside, path in refs:
        target = owner.get(ref)
        # Blocked only by references from outside every flagged object: removed together, a reference from another
        # flagged object goes too (Ward Franks: a DNEEP industry refers to its own LampRemover script).
        if target is not None and inside is None:
            external.setdefault(target, []).append(path)
    rows = []
    for index, tree in enumerate(subtrees):
        outside = external.get(index, [])
        rows.append({"class": tree["class"], "line": tree["line"], "parent": tree["parent"], "path": tree["path"],
                     "ids": len(tree["ids"]), "state": "BLOCKED" if outside else "DROPPABLE",
                     "external_refs": len(outside), "ref_examples": sorted(set(outside))[:3]})
    droppable = sum(1 for r in rows if r["state"] == "DROPPABLE")
    return {"schema_version": SCHEMA_VERSION, "mode": "READ_ONLY_SAVE_REMOVAL_PLAN", "save": doctor["save"],
            "packages": sorted(packages), "objects": len(rows), "droppable": droppable, "blocked": len(rows) - droppable,
            "rows": rows[:max_listed], "note": "Read-only. A plan for a copy; nothing in the save was changed."}
