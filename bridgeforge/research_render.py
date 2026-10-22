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


def _jar_classes(report: dict) -> list[str]:
    rows = report["jar_classes"]
    lines = ["Jar classes found for the feature terms, one row per class (a class present in several trees is one row; STATIC):", ""]
    lines += _table(["class", "terms", "trees", "found by"], [[r["class"], ", ".join(r["terms"]), ", ".join(r["trees"]), "class name" if r["by_name"] else "bytes only"] for r in rows[:MAX_ROWS]])
    if len(rows) > MAX_ROWS:
        lines.insert(-1, f"... {len(rows) - MAX_ROWS} more class(es) in the JSON")
    return lines


def _decompiled(report: dict) -> list[str]:
    section = report["decompiled"]
    status = section["status"]
    if status == "SKIPPED":
        return ["Readable code: skipped (--no-decompile).", ""]
    if status == "MISSING":
        return [f"Readable code: not produced, {section['note']}. To get it: {section['how_to_get']}.", ""]
    if status == "NO_CLASSES":
        return ["Readable code: no jar class matched the feature terms, nothing to decompile.", ""]
    lines = [f"Readable code (STATIC, derived reading aid): Vineflower {section['vineflower']}, JDK {section['jdk']}, {section['decompiled_classes']} class version(s) of {section['candidates']} class(es) found "
             f"(cap {section['max_classes']} classes); cache {section['cache']}. Decompiled text is not evidence of behaviour and is never copied into a mod.", ""]
    for item in section["classes"]:
        head = f"{item['class']}  [trees {', '.join(item['trees'])}; {item['jar']} sha256 {item['jar_sha256'][:16]}; {item['status']}]"
        if not item["excerpt"]["lines"]:
            lines += [f"- {head}: no source ({item['log'] or item['status']})", ""]
            continue
        what = f"{item['excerpt']['methods']} method(s) naming a term" if item["excerpt"]["kind"] == "methods" else "no method names a term, class header only"
        lines += [f"- {head}: {what}", "", "```java"] + [f"{number:>5}  {text}" for number, text in item["excerpt"]["lines"]] + ["```", ""]
    return lines


def _changelogs(report: dict) -> list[str]:
    log = report["changelogs"]
    lines = ["Author changelog hints (AUTHOR CLAIM: what the author says changed; weaker than STATIC, confirm in code):", ""]
    lines += _claims(report, "changelog", "- (no changelog line names the feature)") + [""]
    grouped: dict[tuple, list[dict]] = {}
    for q in log["quotes"]:
        grouped.setdefault((q["file"].rsplit("/", 1)[-1], q["version"], q["term"], q["text"]), []).append(q)
    rows = [[", ".join(q["tree"] for q in qs), "; ".join(f"{q['file']}:{q['line']}" for q in qs[:1]) + (f" (+{len(qs) - 1} tree(s) with the same line)" if len(qs) > 1 else ""),
             key[1] or "-", key[2], key[3]] for key, qs in grouped.items()][:MAX_ROWS]
    lines += _table(["trees", "file:line", "version", "term", "line"], rows)
    if len(grouped) > MAX_ROWS:
        lines.insert(-1, f"... {len(grouped) - MAX_ROWS} more distinct line(s) in the JSON")
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
    quotes = report["changelogs"]["quotes"]
    lines.append(f"- [AUTHOR CLAIM] {len(quotes)} author changelog line(s) name the feature in {len({(q['tree'], q['file']) for q in quotes})} file(s); hints, not evidence.")
    lines.append(f"- [STATIC] readable code: {report['decompiled']['status']}" + (f", {report['decompiled']['decompiled_classes']} class version(s)" if report["decompiled"]["status"] == "DONE" else "") + ".")
    lines.append(f"- {len(report['hypotheses'])} hypothesis(es) unproven, {len(report['unknowns'])} unknown(s) listed with their tests below.")
    return lines


def render_markdown(report: dict) -> str:
    out = [f"# Research report: {', '.join(report['feature'])}", "", f"Question: {report['question']}", "",
           f"Case: `{report['case']['workspace']}` (mod id {', '.join(report['case']['mod_ids']) or 'unknown'}). Read-only: no workspace was edited and the game was not run." + (f" Peer workspaces: {', '.join(report['peer_workspaces'])}." if report["peer_workspaces"] else ""),
           "", "Labels (weakest to strongest): AUTHOR CLAIM = a line the mod author wrote in a changelog or readme, a hint to confirm in code; STATIC = read from files, bytecode, an index or a record, including decompiled code as a derived reading aid; OBSERVED = seen in a recorded run or baseline; VALIDATED = a gate that is PASS with evidence. Labels are never upgraded.", ""]
    out += ["## Summary of what the evidence supports", ""] + _summary(report) + [""]
    out += ["## 1. What the feature is", ""]
    out += _claims(report, "feature") + [""]
    out += ["## 2. Which mods implement it, and how", "", "Case trees (concept present = found by the Atlas extractor or the archaeology graph for a feature term):", ""]
    out += _concept_table(report)
    peers = report["peers"]["shown"]
    out += [f"Other Atlas-indexed mods naming the feature ({report['peers']['mods_with_any']} in all, STATIC):", ""]
    out += _table(["mod", "version", "terms", "rows", "kinds", "example"], [[p["mod"], p["version"], ", ".join(p["terms"]), p["rows"], ", ".join(f"{k} {v}" for k, v in p["kinds"].items()), p["examples"][0] if p["examples"] else ""] for p in peers[:15]])
    out += _jar_classes(report) + _decompiled(report)
    out += ["## 3. Supported similarities and differences", ""]
    out += _claims(report, "changes") + _claims(report, "migrations", "- no Atlas migration pair names the feature (STATIC)") + [""]
    out += _table(["peer", "shared concepts", "case only", "peer only", "shared examples"], [[f"{o['mod']} {o['version']}", o["shared"], o["case_only"], o["peer_only"], ", ".join(o["shared_examples"][:6])] for o in report["comparison"]["peer_overlap"]])
    out += ["## 4. Evidence reconciliation (Atlas vs D-series)", ""] + _reconciliation(report)
    out += _claims(report, "reconciliation") + ["", "D-series behaviour map and captured runs:", ""] + _claims(report, "dseries") + [""]
    out += ["## 5. Records: removals, dropped features, live runs, gates", "", "Removals and dropped features (STATIC records):", ""] + _claims(report, "removals") + ["", "Live records (OBSERVED):", ""] + _claims(report, "live") + ["", "Gates:", ""] + _claims(report, "gates") + [""] + _changelogs(report) + [""]
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
             f"  jar classes {len(report['jar_classes'])}, readable {report['decompiled']['status']}, changelog lines {len(report['changelogs']['quotes'])}",
             f"  claims {len(report['claims'])}, hypotheses {len(report['hypotheses'])}, unknowns {len(report['unknowns'])}, peers {report['peers']['mods_with_any']}",
             "  missing inputs: " + (", ".join(i["name"] for i in report["inputs"] if i["status"] == "MISSING") or "none")]
    return "\n".join(lines + [f"  wrote {path}" for path in written])
