"""Reads the probe's save-and-reload fingerprint lines (next probe version, ROADMAP item 75 R6 evidence emitter).

The probe (`save_reload: {after_days, slot_note}` in the probe config) logs, in the first run, `fingerprint|INFO|phase=before|section=<s>;
count=;len=;fnv=` for each section, then `fingerprint|INFO|save|cmdSave returned true;ts=`. On the next load of that save it logs the stored
digests again (`phase=before`, `source=file`), the recomputed ones (`phase=after`) and `fingerprint|<status>|compare|equal=<bool>;diff=<sections>`.

`parse_fingerprint` is trust-minimal: it never takes the probe's own `equal=` on its word. `milestones.reload_after_save` (the field name
Project Go's RunRecordImport reads) is true only when a compare line was observed; the `fingerprint.equal` flag is true only when the compare
line says equal AND every section has a before and an after digest that match. Pure; reads a log text, launches nothing.
"""
from __future__ import annotations

import re

SECTIONS = ("markets", "systems", "rings", "fleets", "player", "cargo", "mod", "totals")
_LINE = re.compile(r"BF-PROBE\|[^|]*\|fingerprint\|(?P<status>[A-Z]+)\|(?P<subject>[^|]*)\|(?P<detail>[^|\r\n]*)")


def _fields(detail: str) -> dict[str, str]:
    return {key: value for key, _, value in (part.partition("=") for part in detail.split(";") if "=" in part)}


def parse_fingerprint(text: str) -> dict | None:
    """The fingerprint block for a log, or None when the log has no fingerprint line at all."""
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    compare: dict | None = None
    saved: bool | None = None
    seen = False
    for match in _LINE.finditer(text):
        seen = True
        subject, fields = match.group("subject"), _fields(match.group("detail"))
        if subject in ("phase=before", "phase=after") and fields.get("section") in SECTIONS and fields.get("fnv"):
            (before if subject == "phase=before" else after)[fields["section"]] = fields["fnv"]
        elif subject == "compare":
            compare = {"equal_logged": fields.get("equal") == "true",
                       "diff_logged": [s for s in fields.get("diff", "").split(",") if s]}
        elif subject == "save":
            saved = match.group("detail").startswith("cmdSave returned true")
    if not seen:
        return None
    differing = [s for s in SECTIONS if before.get(s) != after.get(s) or s not in before]
    observed = compare is not None
    equal = bool(observed and compare["equal_logged"] and not differing and not compare["diff_logged"])
    diff = sorted(set(differing) | set(compare["diff_logged"] if compare else [])) if observed else []
    return {"compare_observed": observed, "equal": equal, "diff_sections": diff, "save_returned_true": saved,
            "sections_before": len(before), "sections_after": len(after), "digests_before": before, "digests_after": after}
