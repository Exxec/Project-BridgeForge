"""Claims, hypotheses and unknowns of `research report` (82.1). Every statement is derived by a fixed rule from the collected evidence.

A claim carries a label (STATIC / OBSERVED / VALIDATED) and evidence locations. A hypothesis is a reading the evidence is consistent
with and does not prove; its label is the weakest label of its basis. An unknown names the test that would settle it: an existing
gate when one matches, else the command or run that would produce the missing evidence, else an explicit "no existing gate".
"""
from __future__ import annotations

from .research_terms import OBSERVED, STATIC, VALIDATED, weakest

MAX_NAMES = 12


class Ledger:
    """Collects claims, hypotheses and unknowns with stable ids (C1.., H1.., U1..)."""

    def __init__(self) -> None:
        self.claims: list[dict] = []
        self.hypotheses: list[dict] = []
        self.unknowns: list[dict] = []

    def claim(self, section: str, text: str, label: str, evidence: list[str], source: str) -> str:
        ident = f"C{len(self.claims) + 1}"
        self.claims.append({"id": ident, "section": section, "text": text, "label": label, "evidence": evidence, "source": source})
        return ident

    def hypothesis(self, text: str, basis: list[str]) -> str:
        ident = f"H{len(self.hypotheses) + 1}"
        labels = [c["label"] for c in self.claims if c["id"] in basis]
        self.hypotheses.append({"id": ident, "text": text, "basis": basis, "status": "UNPROVEN", "label": weakest(labels)})
        return ident

    def unknown(self, text: str, test: dict, about: list[str]) -> str:
        ident = f"U{len(self.unknowns) + 1}"
        self.unknowns.append({"id": ident, "text": "unknown: " + text, "about": about, "test": test})
        return ident


def _names(items: list[str]) -> str:
    shown = ", ".join(items[:MAX_NAMES])
    return shown + (f" (+{len(items) - MAX_NAMES} more)" if len(items) > MAX_NAMES else "")


def _test_for(gates: list[dict], fallback: str, commands: list[str] | None = None, names: list[str] | None = None) -> dict:
    """The test that settles an unknown: matching open gates first, else the commands/proposal given (never invented gate ids).

    `names` are the things the unknown is about; each gate lists which of them its id, title or commands mention, so a gate that matches
    the feature but never names the item is not presented as settling it."""
    term_gates = [g for g in gates if g["open"] and any(r.startswith("term") for r in g["reasons"])]
    mod_gates = [g for g in gates if g["open"] and g not in term_gates]
    chosen = term_gates or mod_gates
    if chosen:
        def mentioned(gate: dict) -> list[str]:
            text = f"{gate['id']} {gate['title']} {' '.join(gate['commands'])}".lower()
            return [n for n in (names or []) if n.lower() in text]
        listed = [{"id": g["id"], "state": g["state"], "title": g["title"], "names_mentioned": mentioned(g)} for g in chosen]
        unnamed = bool(names) and not any(g["names_mentioned"] for g in listed)
        proposed = f"no listed gate names these items: confirm that {listed[0]['id']}'s run observes them, extend it, or record a decision that they stay dropped" if unnamed else None
        return {"kind": "gate", "gates": listed, "commands": commands or [], "proposed": proposed}
    return {"kind": "none-existing", "gates": [], "commands": commands or [], "proposed": fallback}


def _where(row: dict, compare: dict) -> str:
    """`tree-id:file` of a concept row: the working copy's files when it has any, else the baseline's, else the first tree's."""
    for tree_id in (compare["working"], compare["baseline"], *row["files"]):
        if tree_id in row["files"]:
            return f"{tree_id}:{', '.join(row['files'][tree_id][:2])}"
    return "(no file)"


def feature_claims(ledger: Ledger, trees: list[dict]) -> None:
    for tree in trees:
        for term, info in tree["term_summary"].items():
            ledger.claim("feature", f"`{term}` occurs {info['hits']} time(s) in {info['files']} file(s) of the {tree['label']} tree ({tree['rel']})", STATIC,
                         [f"{tree['rel']}/{e}" for e in info["examples"]], "text-search")
        absent = [t for t in tree["terms"] if t not in tree["term_summary"]]
        if absent:
            ledger.claim("feature", f"no occurrence of {_names(absent)} in the {tree['label']} tree ({tree['rel']})", STATIC, [tree["rel"]], "text-search")


def removal_claims(ledger: Ledger, removals: dict, dropped: dict) -> dict[str, str]:
    """Claims from REMOVALS.json (one per distinct decision) and dropped-features; returns removal target -> claim id."""
    ids: dict[str, str] = {}
    decisions: dict[tuple, list[dict]] = {}
    for entry in removals["entries"]:
        decisions.setdefault((entry["source"], entry["date"], entry["reason"]), []).append(entry)
    for (source, date, reason), entries in sorted(decisions.items()):
        checks = sorted({(c["artifact"], c["exists_in_working"]) for e in entries for c in e["artifact_checks"]})
        extra = "; artifacts named: " + ", ".join(f"{a} {'exists' if ok else 'NOT FOUND'} in working/" for a, ok in checks) if checks else ""
        targets = [f"{e['category']} {e['target']}" for e in entries]
        claim = ledger.claim("removals", f"recorded decision ({source}, {date}) on {len(entries)} item(s): {reason}{extra}. Items: {_names(targets)}", STATIC,
                             [f"{entries[0]['evidence'].split(' (')[0]} ({t})" for t in targets[:3]], "removals")
        ids.update({e["target"]: claim for e in entries})
    unexplained = [f"{i['category']} {i['item']}" for i in dropped["items"] if not i["explained"]]
    explained = [i for i in dropped["items"] if i["explained"]]
    if dropped["items"]:
        ledger.claim("removals", f"dropped-features against the old tree lists {len(dropped['items'])} item(s) naming the feature: {len(explained)} explained by a record, {len(unexplained)} not. Unexplained: {_names(unexplained)}", STATIC,
                     [f"dropped-features {u}" for u in unexplained[:MAX_NAMES]] or ["dropped-features"], "dropped-features")
    return ids


def parity_claims(ledger: Ledger, parity: dict) -> None:
    row = parity["row"]
    if row is not None:
        shown = [f"{i['class']}: {i['item']}" for i in row["items"]]
        ledger.claim("removals", f"content-parity of the shipped {row['shipped']} against its original: verdict {row['verdict']}; {len(shown)} item(s) mention the feature" + (f": {_names(shown)}" if shown else ""),
                     STATIC, ["Done/CONTENT_PARITY.json"], "content-parity")


def live_claims(ledger: Ledger, live: dict) -> None:
    for run in live["runs"]:
        scope = "and the record names the feature" if run["names_feature"] else "the record does not name the feature, so it shows the mod loaded and ran, not that the feature behaved"
        triage = ", ".join(f"{k} {v}" for k, v in sorted(run["triage"].items()))
        ledger.claim("live", f"run {run['test_id']} ({run['date']}) recorded verdict {run['verdict']} for {run['mod']} {run['version'] or ''} (workspace {run['workspace']}); {scope}" + (f"; triage {triage}" if triage else ""),
                     OBSERVED, [run["evidence"]], "live-record")


def gate_claims(ledger: Ledger, gates: list[dict]) -> None:
    for gate in gates:
        if gate["label"] == VALIDATED:
            ledger.claim("gates", f"gate {gate['id']} is PASS with evidence ({', '.join(gate['evidence'])}): {gate['title']}", VALIDATED, [f"gates.json {gate['id']}"], "gates")
        else:
            ledger.claim("gates", f"gate {gate['id']} is {gate['state']}: {gate['title']} (not validated)", STATIC, [f"gates.json {gate['id']}"], "gates")


def change_hypotheses(ledger: Ledger, compare: dict, removal_ids: dict[str, str], gates: list[dict]) -> None:
    """One claim and one hypothesis per kind of change between the baseline and working trees, with the unknown each leaves."""
    if compare["baseline"] is None or compare["working"] is None:
        ledger.unknown("which parts of the feature changed between versions: the case has no baseline (old-tree or original) beside working/",
                       _test_for(gates, "intake the original archive beside working/ and rerun the report", []), [])
        return
    groups: dict[str, list[dict]] = {}
    for row in compare["rows"]:
        groups.setdefault(row["change"], []).append(row)
    runtime_test = _test_for(gates, "a live run of the revived mod that logs the feature's stages (a gate with needs.scenario would schedule it)", [])
    for change, text in (("absent-in-working", "absent from the working copy but present in the baseline"), ("moved", "present in both trees but in different files"),
                         ("added-in-working", "present in the working copy only"), ("kept", "present in both trees in the same files")):
        rows = groups.get(change, [])
        if not rows:
            continue
        names = [r["concept"] for r in rows]
        evidence = [f"{r['concept']} @ {_where(r, compare)}" for r in rows[:MAX_NAMES]]
        claim = ledger.claim("changes", f"{len(rows)} concept(s) {text}: {_names(names)}", STATIC, evidence, "atlas+dseries")
        if change == "kept":
            continue
        recorded = [r for r in rows if r["removal_records"]]
        if change == "absent-in-working":
            unrecorded = [r["concept"] for r in rows if not r["removal_records"]]
            basis = list(dict.fromkeys([claim] + [removal_ids[t] for t in removal_ids if any(t.lower() in r["concept"] or r["concept"] in t.lower() for r in recorded)]))
            if recorded:
                ledger.hypothesis(f"{len(recorded)} of these concept(s) ({_names([r['concept'] for r in recorded])}) were removed or re-created on purpose, as a REMOVALS record states; the record is a decision, not proof the replacement behaves the same", basis)
            if unrecorded:
                ledger.hypothesis(f"{len(unrecorded)} of these concept(s) ({_names(unrecorded)}) were dropped with no recorded decision, or now live under a name the feature terms do not match", [claim])
                test = _test_for(gates, "an owner decision recorded in REMOVALS.json, or a name search of working/ for the replacement",
                                 ["python -m bridgeforge dropped-features <workspace>", "python -m bridgeforge lookup <class> --mod <working>"], unrecorded)
                ledger.unknown(f"whether {_names(unrecorded)} were dropped, renamed or redistributed", test, [claim])
        elif change == "moved":
            ledger.hypothesis(f"{len(rows)} concept(s) ({_names(names)}) were redistributed between files (same name, different file)", [claim])
        else:
            ledger.hypothesis(f"{len(rows)} concept(s) ({_names(names)}) were added or re-created after the baseline", [claim])
    for link in compare["replacement_links"]:
        claim = ledger.claim("changes", f"{len(link['records'])} REMOVALS record(s) name {link['artifact']} as where the feature lives now; it exists in working/ and holds {len(link['concepts'])} feature concept(s): {_names(link['concepts'])}", STATIC,
                             [f"{link['artifact']} (concepts), reports/REMOVALS.json"], "removals+atlas+dseries")
        ledger.hypothesis(f"the removed classes were re-created in {link['artifact']} (the records say so and the artifact holds the feature's new classes); that it behaves like the original is not shown", [claim])
    ledger.unknown("whether the working copy's feature behaves as the original did at runtime (static presence does not show behaviour)", runtime_test, [])
