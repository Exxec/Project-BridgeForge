"""82.2 evidence reconciliation: tabulate where Atlas and the D-series (archaeology) agree, per concept.

Both stacks read the same files, so agreement is corroborating STATIC evidence, never independent validation. A concept is one
normal-form name (`research_terms.concept_key`) found by a feature term. Per concept, each stack reports the roles it saw it in
(`code-class`, `registration`, `data-or-string`) and the container files (a jar entry counts as its jar). The category is:

  both-agree       both detect it, share a role group and at least one file
  atlas-only       Atlas detects it, the D-series does not (D-series coverage gap?)
  dseries-only     the D-series detects it, Atlas does not (Atlas blind spot?)
  both-different   both detect it but share no role group or no file (semantic disagreement)

A disagreement is kept as a row with its reason; nothing is resolved or dropped. Counts are the output.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .research_terms import STATIC

CATEGORIES = ("both-agree", "atlas-only", "dseries-only", "both-different")
ROLE_GROUPS = ("code-class", "registration", "data-or-string")


@dataclass
class Concept:
    """What one stack saw for one concept key."""
    names: set[str] = field(default_factory=set)
    roles: set[str] = field(default_factory=set)
    kinds: set[str] = field(default_factory=set)
    files: set[str] = field(default_factory=set)
    locations: list[str] = field(default_factory=list)
    terms: set[str] = field(default_factory=set)

    def add(self, name: str, role: str, kind: str, location: str, terms: list[str]) -> None:
        if is_tool_output(location):
            return
        self.names.add(name)
        self.roles.add(role)
        self.kinds.add(kind)
        self.files.add(container(location))
        if location not in self.locations and len(self.locations) < 6:
            self.locations.append(location)
        self.terms.update(terms)


def is_tool_output(location: str) -> bool:
    """A root-level `reports/` folder of a working copy holds BridgeForge's own output (REMOVALS.json, plans), not mod content."""
    return location.replace("\\", "/").startswith("reports/")


def container(location: str) -> str:
    """The file holding a location: `jars/A.jar!x/Y.class` -> `jars/A.jar`, `src/A.java:12` -> `src/A.java`."""
    text = location.replace("\\", "/").split("!", 1)[0]
    head, sep, tail = text.rpartition(":")
    return head if sep and tail.isdigit() else text


def _row(key: str, atlas: Concept | None, dseries: Concept | None) -> dict:
    if atlas is None or dseries is None:
        category, reasons = ("atlas-only", []) if dseries is None else ("dseries-only", [])
    else:
        reasons = []
        if not atlas.roles & dseries.roles:
            reasons.append("role: Atlas " + "/".join(sorted(atlas.roles)) + " vs D-series " + "/".join(sorted(dseries.roles)))
        if not atlas.files & dseries.files:
            reasons.append("files: no file in common")
        category = "both-different" if reasons else "both-agree"
    side = lambda c: None if c is None else {"names": sorted(c.names), "roles": sorted(c.roles), "kinds": sorted(c.kinds), "files": sorted(c.files), "locations": c.locations}  # noqa: E731
    terms = sorted((atlas.terms if atlas else set()) | (dseries.terms if dseries else set()))
    return {"concept": key, "category": category, "reasons": reasons, "terms": terms, "label": STATIC, "atlas": side(atlas), "dseries": side(dseries)}


def reconcile(atlas: dict[str, Concept] | None, dseries: dict[str, Concept] | None) -> dict:
    """The agreement table. A side that is None was not available (reported by the caller as a missing input), not empty."""
    if atlas is None or dseries is None:
        return {"status": "INCOMPLETE", "missing": [n for n, v in (("atlas", atlas), ("dseries", dseries)) if v is None],
                "counts": {name: 0 for name in CATEGORIES}, "rows": [], "label": STATIC,
                "note": "both stacks are needed to reconcile; the side that is missing is listed in inputs"}
    rows = [_row(key, atlas.get(key), dseries.get(key)) for key in sorted(set(atlas) | set(dseries))]
    counts = {name: sum(1 for r in rows if r["category"] == name) for name in CATEGORIES}
    return {"status": "OK", "missing": [], "counts": counts, "rows": rows, "label": STATIC,
            "note": "same code read twice: agreement corroborates, it does not validate"}
