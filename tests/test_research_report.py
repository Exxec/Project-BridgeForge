"""ROADMAP-3 82.1 and 82.2: `research report` over synthetic fixtures (a tiny fake workspace, fake Atlas database, fake D-series outputs)."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.atlas import connect
from bridgeforge.cli import main
from bridgeforge.research_reconcile import Concept, reconcile
from bridgeforge.research_render import render_markdown
from bridgeforge.research_report import build_report
from bridgeforge.research_terms import Matcher, concept_key, parse_terms, weakest
from tests.support import resolved_temp_dir

QUESTION = "Was the Crusade removed or replaced?"
RULES_HEADER = "id,trigger,conditions,script,text,options,notes\n"
ORIGINAL_RULES = RULES_HEADER + "Crusade_rule,PopulateOptions,,,,,\nCrusade_atlasonly,PopulateOptions,,,,,\nCrusade_diff,PopulateOptions,,,,,\nGone_rule,PopulateOptions,,,,,\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_digest(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): _sha(p) for p in sorted(root.rglob("*")) if p.is_file()}


def make_workspace(root: Path, with_discovery: bool = True) -> Path:
    """workspace/original/extracted/Case (old), workspace/working (new), optional saved D-series output beside working."""
    ws = root / "In operation" / "Case"
    old = ws / "original" / "extracted" / "Case"
    _write(old / "mod_info.json", '{"id": "casemod", "name": "Case", "version": "1.0", "gameVersion": "0.9.1a"}')
    _write(old / "data" / "campaign" / "rules.csv", ORIGINAL_RULES)
    _write(old / "data" / "scripts" / "OldCrusade.java", "package data.scripts;\npublic class OldCrusade {\n}\n")
    _write(old / "data" / "console" / "commands.csv", "command,class\nTriggerCrusade,data.scripts.OldCrusade\n")
    work = ws / "working"
    _write(work / "mod_info.json", '{"id": "casemod", "name": "Case", "version": "1.1", "gameVersion": "0.98a-RC8"}')
    _write(work / "data" / "campaign" / "rules.csv", RULES_HEADER + "Crusade_rule,PopulateOptions,,,,,\nCrusade_atlasonly,PopulateOptions,,,,,\nCrusade_diff,PopulateOptions,,,,,\n")
    _write(work / "data" / "other.json", '{"ref": "Crusade_diff"}\n')
    _write(work / "data" / "extra.json", '{"ref": "Crusade_dseries"}\n')
    _write(work / "reports" / "REMOVALS.json", json.dumps({"schema": 1, "removals": [
        {"category": "classes", "item": "data.scripts.OldCrusade", "reason": "Re-created for RC8 as jars/New.jar", "source": "owner", "date": "2026-10-20"}]}))
    (work / "jars").mkdir(parents=True, exist_ok=True)
    (work / "jars" / "New.jar").write_bytes(b"PK")
    if with_discovery:
        write_saved_dseries(ws, work)
    return ws


def write_saved_dseries(ws: Path, work: Path) -> None:
    rules, other, extra = (work / "data/campaign/rules.csv"), work / "data/other.json", work / "data/extra.json"
    nodes = [{"id": f"file:{p.relative_to(work).as_posix()}", "kind": "data", "path": p.relative_to(work).as_posix(), "sha256": _sha(p), "size": p.stat().st_size} for p in (rules, other, extra)]
    nodes += [{"id": f"symbol:{name}", "kind": "symbol", "value": name} for name in ("Crusade_rule", "Crusade_diff", "Crusade_dseries")]
    edges = [{"source": "file:data/campaign/rules.csv", "target": "symbol:Crusade_rule", "relation": "data-reference", "evidence": "id"},
             {"source": "file:data/other.json", "target": "symbol:Crusade_diff", "relation": "data-reference", "evidence": "ref"},
             {"source": "file:data/extra.json", "target": "symbol:Crusade_dseries", "relation": "data-reference", "evidence": "ref"}]
    folder = ws / "reports" / "discovery" / "working"
    _write(folder / "archaeology" / "architecture.json", json.dumps({"schema_version": 1, "mod_id": "casemod", "nodes": nodes, "edges": edges, "lifecycle": {"hooks": [], "registrations": []}}))
    for name, key in (("behavior", "behaviors"), ("hypotheses", "hypotheses"), ("unknowns", "unknowns"), ("risks", "risks")):
        _write(folder / f"{name}.json", json.dumps({"schema_version": 1, key: []}))


def make_atlas(root: Path, peers: tuple[tuple[str, str, str], ...] = (("peermod", "2.0", "Crusade_rule"),)) -> Path:
    db = root / "atlas.sqlite"
    conn = connect(db, create=True)
    conn.execute("DROP TABLE census")  # an atlas built before the census existed, like the real one at the time of writing
    for mod, version, name in peers:
        conn.execute("INSERT INTO mods VALUES (?, ?, ?, ?, ?, ?)", (mod, version, mod, str(root / "peer" / mod), "h", "working"))
        conn.execute("INSERT INTO facts VALUES (?, ?, 'rule', ?, 'defines', 'data/campaign/rules.csv', 7, 'row', 'SAFE')", (mod, version, name))
    conn.commit()
    conn.close()
    return db


def make_live(root: Path) -> None:
    _write(root / "In operation" / "_live" / "RUN-1.json", json.dumps({"test_id": "RUN-1", "date": "2026-10-13", "members": [
        {"workspace": "Case", "mod_id": "casemod", "version": "1.1", "verdict": "PASS"}], "triage": {"FATAL": 0}}))


def make_repo(root: Path, gates: list[dict]) -> Path:
    repo = root / "repo"
    _write(repo / "gates.json", json.dumps({"schema": 1, "repo": "R", "gates": gates}))
    return repo


def gate(gate_id: str, state: str, title: str, evidence: list[str] | None = None) -> dict:
    return {"id": gate_id, "title": title, "state": state, "evidence": evidence or [], "needs": {"rig": True, "mods": ["casemod"]}, "commands": ["probe-group live <TESTID>"], "source_doc": {"path": "docs/X.md", "anchor": "X"}, "updated": "2026-10-21"}


class ReconcileUnitTests(unittest.TestCase):
    def _concept(self, role: str, location: str) -> Concept:
        concept = Concept()
        concept.add("X", role, "k", location, ["t"])
        return concept

    def test_four_agreement_categories_are_tabulated_and_disagreements_stay_as_rows(self) -> None:
        atlas = {"both": self._concept("code-class", "src/A.java:1"), "a_only": self._concept("data-or-string", "d.csv:2"),
                 "diff_files": self._concept("data-or-string", "one.csv:1"), "diff_role": self._concept("code-class", "same.java:3")}
        dseries = {"both": self._concept("code-class", "src/A.java"), "d_only": self._concept("registration", "B.java"),
                   "diff_files": self._concept("data-or-string", "two.json"), "diff_role": self._concept("registration", "same.java")}
        result = reconcile(atlas, dseries)
        self.assertEqual(result["counts"], {"both-agree": 1, "atlas-only": 1, "dseries-only": 1, "both-different": 2})
        by_name = {row["concept"]: row for row in result["rows"]}
        self.assertEqual(by_name["diff_files"]["reasons"], ["files: no file in common"])
        self.assertTrue(by_name["diff_role"]["reasons"][0].startswith("role:"))
        self.assertEqual({row["label"] for row in result["rows"]}, {"STATIC"})
        self.assertIn("does not validate", result["note"])

    def test_a_side_that_is_missing_makes_the_table_incomplete_instead_of_empty(self) -> None:
        result = reconcile({"a": self._concept("code-class", "A.java")}, None)
        self.assertEqual((result["status"], result["missing"], result["rows"]), ("INCOMPLETE", ["dseries"], []))

    def test_tool_output_folder_is_not_mod_content(self) -> None:
        concept = Concept()
        concept.add("X", "data-or-string", "k", "reports/REMOVALS.json", ["t"])
        self.assertFalse(concept.names)


class TermTests(unittest.TestCase):
    def test_labels_combine_to_the_weakest_and_are_never_upgraded(self) -> None:
        self.assertEqual(weakest(["VALIDATED", "STATIC"]), "STATIC")
        self.assertEqual(weakest(["VALIDATED", "OBSERVED"]), "OBSERVED")
        self.assertEqual(weakest([]), "STATIC")

    def test_wildcard_terms_start_at_an_identifier_and_plain_terms_are_substrings(self) -> None:
        matcher = Matcher(parse_terms("Crusade, player_* ,commands.csv"))
        self.assertEqual(matcher.name_hits("TEM_CrusadeEvent"), ["Crusade"])
        self.assertEqual(matcher.name_hits("player_intel"), ["player_*"])
        self.assertEqual(matcher.name_hits("battle_player_win"), [])
        self.assertEqual(matcher.file_hits("data/console/Commands.csv"), ["commands.csv"])

    def test_file_paths_and_dotted_path_names_share_one_key(self) -> None:
        self.assertEqual(concept_key("graphics.a.b.Tem.png"), concept_key("graphics/a/b/Tem.png"))
        self.assertEqual(concept_key("data.scripts.OldCrusade"), "oldcrusade")


class ReportTests(unittest.TestCase):
    def build(self, root: Path, **kwargs):
        ws = make_workspace(root)
        make_live(root)
        repo = make_repo(root, kwargs.pop("gates", [gate("g-open", "LIVE_PENDING", "Crusade live run")]))
        return ws, build_report("Crusade,TriggerCrusade,commands.csv", ws, QUESTION, atlas_db=kwargs.pop("atlas_db", make_atlas(root)), repo=repo, build=False)

    def test_atlas_and_dseries_are_tabulated_per_concept_for_the_working_copy(self) -> None:
        with resolved_temp_dir() as root:
            _, report = self.build(root)
        rows = {r["concept"]: r["category"] for r in report["reconciliation"]["trees"]["working"]["rows"]}
        self.assertEqual(rows["crusade_rule"], "both-agree")
        self.assertEqual(rows["crusade_atlasonly"], "atlas-only")
        self.assertEqual(rows["crusade_dseries"], "dseries-only")
        self.assertEqual(rows["crusade_diff"], "both-different")
        self.assertEqual(report["reconciliation"]["trees"]["working"]["counts"], {"both-agree": 1, "atlas-only": 1, "dseries-only": 1, "both-different": 1})

    def test_trees_without_saved_dseries_are_reported_missing_with_the_command_and_not_built_under_no_build(self) -> None:
        with resolved_temp_dir() as root:
            _, report = self.build(root)
        inputs = {i["name"]: i for i in report["inputs"]}
        self.assertEqual(inputs["archaeology (working)"]["status"], "PRESENT")
        self.assertEqual(inputs["archaeology (original)"]["status"], "MISSING")
        self.assertIn("python -m bridgeforge archaeology", inputs["archaeology (original)"]["command"])
        self.assertEqual(inputs["probe-baseline"]["status"], "MISSING")
        self.assertIn("probe-baseline", inputs["probe-baseline"]["command"])
        self.assertIn("behavior-diff", inputs["behavior-diff"]["command"])
        self.assertEqual(report["reconciliation"]["trees"]["original"]["status"], "INCOMPLETE")
        self.assertTrue(any("archaeology (original) is missing" in u["text"] and u["test"]["commands"] for u in report["unknowns"]))

    def test_missing_atlas_database_is_reported_with_the_atlas_build_command(self) -> None:
        with resolved_temp_dir() as root:
            _, report = self.build(root, atlas_db=root / "nope.sqlite")
        entry = next(i for i in report["inputs"] if i["name"] == "atlas-database")
        self.assertEqual((entry["status"], entry["command"]), ("MISSING", "python -m bridgeforge atlas build"))
        self.assertEqual(report["peers"]["mods_with_any"], 0)

    def test_atlas_peers_are_listed_and_the_missing_census_table_is_reported(self) -> None:
        with resolved_temp_dir() as root:
            _, report = self.build(root)
        self.assertEqual([p["mod"] for p in report["peers"]["shown"]], ["peermod"])
        self.assertEqual(next(i for i in report["inputs"] if i["name"] == "atlas-census")["status"], "MISSING")

    def test_changes_between_baseline_and_working_use_the_removals_record_without_judging_it(self) -> None:
        with resolved_temp_dir() as root:
            _, report = self.build(root)
        rows = {r["concept"]: r for r in report["comparison"]["rows"]}
        self.assertEqual(rows["oldcrusade"]["change"], "absent-in-working")
        self.assertTrue(rows["oldcrusade"]["removal_records"][0].startswith("classes data.scripts.OldCrusade: Re-created for RC8 as jars/New.jar"))
        removal_claim = next(c for c in report["claims"] if c["section"] == "removals")
        self.assertEqual(removal_claim["label"], "STATIC")
        self.assertIn("jars/New.jar exists in working/", removal_claim["text"])

    def test_labels_are_never_upgraded_observed_only_from_live_records_validated_only_from_pass_with_evidence(self) -> None:
        with resolved_temp_dir() as root:
            _, report = self.build(root)
        labels = {c["source"]: c["label"] for c in report["claims"]}
        self.assertEqual(labels["live-record"], "OBSERVED")
        self.assertNotIn("VALIDATED", {c["label"] for c in report["claims"]})
        self.assertEqual({c["label"] for c in report["claims"] if c["source"] not in ("live-record",)}, {"STATIC"})
        live = next(c for c in report["claims"] if c["source"] == "live-record")
        self.assertIn("does not name the feature", live["text"])
        self.assertTrue(all(h["label"] == "STATIC" and h["status"] == "UNPROVEN" for h in report["hypotheses"]))
        with resolved_temp_dir() as root:
            _, passed = self.build(root, gates=[gate("g-pass", "PASS", "Crusade live run", ["RUN-1"]), gate("g-open", "LIVE_PENDING", "Crusade stages")])
        gate_labels = {c["text"].split()[1]: c["label"] for c in passed["claims"] if c["section"] == "gates"}
        self.assertEqual(gate_labels, {"g-pass": "VALIDATED", "g-open": "STATIC"})

    def test_content_parity_is_reported_missing_or_quoted_with_its_verdict(self) -> None:
        with resolved_temp_dir() as root:
            _, absent = self.build(root)
        entry = next(i for i in absent["inputs"] if i["name"] == "content-parity")
        self.assertEqual(entry["status"], "MISSING")
        self.assertIn("done-audit --content-parity", entry["command"])
        with resolved_temp_dir() as root:
            _write(root / "Done" / "CONTENT_PARITY.json", json.dumps({"mods": [{"mod": "Case", "shipped": "Case-1.1.zip", "verdict": "LOSS_SUSPECTED", "missing": ["data/console/commands.csv", "data/other.csv"], "unexplained": {"reports.csv": ["tem_crusade/x"]}}]}))
            _, present = self.build(root)
        self.assertEqual(present["content_parity"]["verdict"], "LOSS_SUSPECTED")
        self.assertEqual([i["item"] for i in present["content_parity"]["items"]], ["data/console/commands.csv", "tem_crusade/x"])
        claim = next(c for c in present["claims"] if c["source"] == "content-parity")
        self.assertEqual(claim["label"], "STATIC")

    def test_unknowns_name_the_existing_gate_or_say_that_none_exists(self) -> None:
        with resolved_temp_dir() as root:
            _, with_gate = self.build(root)
        runtime = next(u for u in with_gate["unknowns"] if "behaves as the original" in u["text"])
        self.assertEqual((runtime["test"]["kind"], runtime["test"]["gates"][0]["id"]), ("gate", "g-open"))
        with resolved_temp_dir() as root:
            _, no_gate = self.build(root, gates=[])
        runtime = next(u for u in no_gate["unknowns"] if "behaves as the original" in u["text"])
        self.assertEqual(runtime["test"]["kind"], "none-existing")
        self.assertTrue(runtime["text"].startswith("unknown:"))

    def test_without_saved_dseries_archaeology_is_built_in_memory_and_the_workspace_is_unchanged(self) -> None:
        with resolved_temp_dir() as root:
            ws = make_workspace(root, with_discovery=False)
            repo, db = make_repo(root, []), make_atlas(root)
            before = _tree_digest(root / "In operation")
            report = build_report("Crusade", ws, QUESTION, atlas_db=db, repo=repo, build=True)
            self.assertEqual(_tree_digest(root / "In operation"), before)
        inputs = {i["name"]: i["status"] for i in report["inputs"]}
        self.assertEqual({inputs["archaeology (working)"], inputs["archaeology (original)"]}, {"BUILT_IN_MEMORY"})
        self.assertEqual(inputs["behavior-map+hypotheses"], "BUILT_IN_MEMORY")
        self.assertEqual(report["reconciliation"]["missing"], [])
        self.assertEqual(report["reconciliation"]["trees"]["working"]["status"], "OK")

    def test_the_report_never_writes_into_the_workspace_or_the_atlas_database(self) -> None:
        with resolved_temp_dir() as root:
            ws = make_workspace(root)
            make_live(root)
            repo = make_repo(root, [])
            db = make_atlas(root)
            before, atlas_before = _tree_digest(root / "In operation"), _sha(db)
            build_report("Crusade", ws, QUESTION, atlas_db=db, repo=repo, build=False)
            self.assertEqual(_tree_digest(root / "In operation"), before)
            self.assertEqual(_sha(db), atlas_before)
            with closing(sqlite3.connect(db)) as conn:
                self.assertEqual(conn.execute("SELECT name FROM sqlite_master WHERE name = 'census'").fetchall(), [])

    def test_output_is_deterministic(self) -> None:
        with resolved_temp_dir() as root:
            ws = make_workspace(root)
            make_live(root)
            repo, db = make_repo(root, [gate("g-open", "LIVE_PENDING", "Crusade")]), make_atlas(root)
            first = build_report("Crusade,commands.csv", ws, QUESTION, atlas_db=db, repo=repo, build=False)
            second = build_report("Crusade,commands.csv", ws, QUESTION, atlas_db=db, repo=repo, build=False)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(render_markdown(first), render_markdown(second))
        self.assertEqual(first["schema_version"], 2)

    def test_empty_feature_or_question_and_non_workspaces_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws = make_workspace(root)
            for feature, question, case in (("", QUESTION, ws), ("Crusade", "  ", ws), ("Crusade", QUESTION, root)):
                with self.assertRaises(ValueError):
                    build_report(feature, case, question, atlas_db=root / "x.sqlite", repo=root, build=False)


class CliTests(unittest.TestCase):
    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_write_produces_markdown_and_json_atomically_and_prints_a_summary(self) -> None:
        with resolved_temp_dir() as root:
            ws = make_workspace(root)
            repo, db, target = make_repo(root, []), make_atlas(root), root / "out"
            code, out, _ = self.run_cli("research", "report", "Crusade", "--case", str(ws), "--question", QUESTION, "--write", str(target), "--atlas-db", str(db), "--repo", str(repo), "--no-build")
            report = json.loads((target / "research-report.json").read_text(encoding="utf-8"))
            markdown = (target / "research-report.md").read_text(encoding="utf-8")
            leftovers = [p.name for p in target.iterdir() if p.suffix == ".tmp"]
        self.assertEqual(code, 0)
        self.assertEqual((report["schema_version"], report["read_only"], leftovers), (2, True, []))
        self.assertIn("reconciliation:", out)
        self.assertIn("## Summary of what the evidence supports", markdown)
        self.assertIn("## 7. Unknowns and the test that would settle each", markdown)

    def test_write_inside_the_workspace_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            ws = make_workspace(root)
            code, _, err = self.run_cli("research", "report", "Crusade", "--case", str(ws), "--question", QUESTION, "--write", str(ws / "reports"), "--atlas-db", str(root / "x.sqlite"), "--no-build")
            self.assertFalse((ws / "reports" / "research-report.md").exists())
        self.assertEqual(code, 2)
        self.assertIn("inside the case workspace", err)


if __name__ == "__main__":
    unittest.main()
