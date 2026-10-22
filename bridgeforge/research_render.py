"""Markdown rendering of a `research report` result (ROADMAP-3 82.1). Pure function of the report dict; deterministic."""
from __future__ import annotations

from .research_reconcile import CATEGORIES

MAX_ROWS = 40


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list[object]]) -> list[str]:
    if not rows:
        return ["(none)", ""]
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return lines + [""]


def _claims(report: dict, section: str, empty: str = "- (no claim)") -> list[str]:
    return [f"- [{c['label']}] {c['text']}  (evidence: {'; '.join(c['evidence'][:3]) or 'none'}) `{c['id']}`" for c in report["claims"] if c["section"] == section] or [empty]


def _test_text(test: dict) -> str:
    if test["kind"] == "gate":
        tail = (f"; then {'; '.join(test['commands'])}" if test["commands"] else "") + (f"; {test['proposed']}" if test.get("proposed") else "")
        return "gate " + ", ".join(_gate_text(g) for g in test["gates"]) + tail
    parts = [f"`{c}`" for c in test["commands"]]
    if test.get("proposed"):
        parts.append(f"no existing gate; proposed: {test['proposed']}")
    return "; ".join(parts) or "no existing gate"


def _gate_text(gate: dict) -> str:
    named = f"; names {', '.join(gate['names_mentioned'][:4])}" if gate.get("names_mentioned") else "; its text does not name the items in question"
    return f"{gate['id']} ({gate['state']}{named})"


def _concept_table(report: dict) -> list[str]:
    comp = report["comparison"]
    subjects = comp["subjects"]
    rows = [[r["concept"], ", ".join(r["terms"]), r["change"], *("yes" if r["present"].get(s) else "-" for s in subjects), len(r["peers"]), "; ".join(r["removal_records"][:1])[:140]] for r in comp["rows"][:MAX_ROWS]]
    lines = _table(["concept", "terms", "change", *subjects, "peers", "removal record"], rows)
    if len(comp["rows"]) > MAX_ROWS:
        lines.insert(-1, f"... {len(comp['rows']) - MAX_ROWS} more concept(s) in the JSON")
    return lines + [f"{comp['peers_only_concepts']} concept(s) are carried only by peers (listed in the JSON peers section, not here).", ""]


def _reconciliation(report: dict) -> list[str]:
    rec = report["reconciliation"]
    lines = ["| category | count |", "|---|---|"] + [f"| {name} | {rec['counts'][name]} |" for name in CATEGORIES] + [""]
    lines.append(f"{rec['note']}." + (f" Incomplete: {', '.join(rec['missing'])}." if rec["missing"] else ""))
    lines.append("")
    rows = []
    for tree_id, result in sorted(rec["trees"].items()):
        for row in result["rows"]:
            if row["category"] != "both-agree":
                rows.append([tree_id, row["concept"], row["category"], "; ".join(row["reasons"]) or "-", ", ".join((row["atlas"] or row["dseries"])["locations"][:1])])
    lines += _table(["tree", "concept", "category", "why", "location"], rows[:MAX_ROWS])
    return lines


def _summary(report: dict) -> list[str]:
    comp, rec = report["comparison"], report["reconciliation"]
    lines = []
    if comp["baseline"]:
        lines.append(f"- [STATIC] Feature concepts from {comp['baseline']} to working: " + (", ".join(f"{k} {v}" for k, v in comp["change_counts"].items()) or "none") + ".")
    else:
        lines.append("- unknown: the case has no baseline tree, so nothing can be said about what changed.")
    decisions = sorted({f"{e['source']} {e['date']}: {e['reason'][:90]}{'...' if len(e['reason']) > 90 else ''}" for e in report["removals"]})
    lines.append(f"- [STATIC] {len(report['removals'])} REMOVALS record(s) name the feature" + (": " + " | ".join(decisions[:3]) if decisions else " (none recorded)") + ". A record is a decision, not proof of behaviour.")
    unexplained = [f"{i['category']} {i['item']}" for i in report["dropped_features"]["items"] if not i["explained"]]
    lines.append(f"- [STATIC] dropped-features: {len(unexplained)} item(s) naming the feature have no record" + (": " + ", ".join(unexplained[:8]) + (" ..." if len(unexplained) > 8 else "") if unexplained else "") + ".")
    for link in comp["replacement_links"]:
        lines.append(f"- [STATIC] {link['artifact']} exists and holds {len(link['concepts'])} feature concept(s); {len(link['records'])} record(s) name it as the replacement.")
    runs = report["live_records"]
    lines.append(f"- [OBSERVED] {len(runs)} recorded live run(s) for this mod; {sum(r['names_feature'] for r in runs)} name the feature.")
    validated = [g["id"] for g in report["gates"] if g["label"] == "VALIDATED"]
    lines.append(f"- [VALIDATED] {', '.join(validated) if validated else 'nothing: no gate naming the feature or the mod is PASS with evidence'}.")
    lines.append("- Atlas vs D-series: " + ", ".join(f"{n} {rec['counts'][n]}" for n in CATEGORIES) + ".")
    lines.append(f"- {len(report['hypotheses'])} hypothesis(es) unproven, {len(report['unknowns'])} unknown(s) listed with their tests below.")
    return lines


def render_markdown(report: dict) -> str:
    out = [f"# Research report: {', '.join(report['feature'])}", "", f"Question: {report['question']}", "",
           f"Case: `{report['case']['workspace']}` (mod id {', '.join(report['case']['mod_ids']) or 'unknown'}). Read-only: no workspace was edited and the game was not run.",
           "", "Labels: STATIC = read from files, bytecode, an index or a record; OBSERVED = seen in a recorded run or baseline; VALIDATED = a gate that is PASS with evidence. Labels are never upgraded.", ""]
    out += ["## Summary of what the evidence supports", ""] + _summary(report) + [""]
    out += ["## 1. What the feature is", ""]
    out += _claims(report, "feature") + [""]
    out += ["## 2. Which mods implement it, and how", "", "Case trees (concept present = found by the Atlas extractor or the archaeology graph for a feature term):", ""]
    out += _concept_table(report)
    peers = report["peers"]["shown"]
    out += [f"Other Atlas-indexed mods naming the feature ({report['peers']['mods_with_any']} in all, STATIC):", ""]
    out += _table(["mod", "version", "terms", "rows", "kinds", "example"], [[p["mod"], p["version"], ", ".join(p["terms"]), p["rows"], ", ".join(f"{k} {v}" for k, v in p["kinds"].items()), p["examples"][0] if p["examples"] else ""] for p in peers[:15]])
    out += ["## 3. Supported similarities and differences", ""]
    out += _claims(report, "changes") + _claims(report, "migrations", "- no Atlas migration pair names the feature (STATIC)") + [""]
    out += _table(["peer", "shared concepts", "case only", "peer only", "shared examples"], [[f"{o['mod']} {o['version']}", o["shared"], o["case_only"], o["peer_only"], ", ".join(o["shared_examples"][:6])] for o in report["comparison"]["peer_overlap"]])
    out += ["## 4. Evidence reconciliation (Atlas vs D-series)", ""] + _reconciliation(report)
    out += _claims(report, "reconciliation") + ["", "D-series behaviour map and captured runs:", ""] + _claims(report, "dseries") + [""]
    out += ["## 5. Records: removals, dropped features, live runs, gates", "", "Removals and dropped features (STATIC records):", ""] + _claims(report, "removals") + ["", "Live records (OBSERVED):", ""] + _claims(report, "live") + ["", "Gates:", ""] + _claims(report, "gates") + [""]
    out += ["## 6. Hypotheses (not established)", ""]
    out += [f"- `{h['id']}` [{h['label']} basis, {h['status']}] {h['text']} (from {', '.join(h['basis'])})" for h in report["hypotheses"]] or ["- (none)"]
    out += ["", "## 7. Unknowns and the test that would settle each", ""]
    out += [f"- `{u['id']}` {u['text']}. Test: {_test_text(u['test'])}" for u in report["unknowns"]] or ["- (none)"]
    out += ["", "## 8. Inputs", ""]
    out += _table(["input", "status", "note", "command when missing"], [[i["name"], i["status"], i["note"], i["command"] if i["status"] == "MISSING" else ""] for i in report["inputs"]])
    return "\n".join(out) + "\n"


def stdout_summary(report: dict, written: list[str]) -> str:
    rec, comp = report["reconciliation"], report["comparison"]
    lines = [f"research report: {', '.join(report['feature'])} (case {report['case']['workspace']}, read-only)",
             f"  trees: {', '.join(t['id'] for t in report['trees'])}",
             "  reconciliation: " + ", ".join(f"{n} {rec['counts'][n]}" for n in CATEGORIES) + (f" (incomplete: {', '.join(rec['missing'])})" if rec["missing"] else ""),
             "  changes (baseline -> working): " + (", ".join(f"{k} {v}" for k, v in comp["change_counts"].items()) or "none"),
             f"  claims {len(report['claims'])}, hypotheses {len(report['hypotheses'])}, unknowns {len(report['unknowns'])}, peers {report['peers']['mods_with_any']}",
             "  missing inputs: " + (", ".join(i["name"] for i in report["inputs"] if i["status"] == "MISSING") or "none")]
    return "\n".join(lines + [f"  wrote {path}" for path in written])
