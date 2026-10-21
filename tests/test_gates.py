"""gates.json schema, lint, record and the `board --live-pending` plan (ROADMAP-3 80.6 / 80.2), on synthetic repos."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge import cli
from bridgeforge.gates import lint_gates, live_pending_plan, load_gates, plan_blocks, record_gate, validate_gates


def make_gate(gate_id: str, state: str = "LIVE_PENDING", **needs) -> dict:
    return {"id": gate_id, "title": f"close {gate_id}", "state": state, "evidence": [],
            "needs": {"rig": True, **needs}, "commands": [f"run {gate_id}"],
            "source_doc": {"path": "STATUS.md", "anchor": gate_id}, "updated": "2026-10-21"}


def make_repo(root: Path, name: str, gates: list[dict], status: str = "") -> Path:
    repo = root / name
    repo.mkdir()
    (repo / "gates.json").write_text(json.dumps({"schema": 1, "repo": name, "gates": gates}), encoding="utf-8")
    (repo / "STATUS.md").write_text(status or "\n".join(gate["id"] for gate in gates), encoding="utf-8")
    return repo


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class GatesSchemaTests(unittest.TestCase):
    def doc(self, *gates: dict) -> dict:
        return {"schema": 1, "repo": "r", "gates": list(gates)}

    def test_valid_file_has_no_problems(self):
        self.assertEqual(validate_gates(self.doc(make_gate("a"))), [])

    def test_rejects_bad_state_duplicate_id_and_missing_rig(self):
        broken = make_gate("a", state="DONE")
        no_rig = make_gate("b")
        no_rig["needs"] = {"mods": []}
        problems = validate_gates(self.doc(broken, make_gate("a"), no_rig))
        self.assertTrue(any("state must be one of" in p for p in problems))
        self.assertTrue(any("duplicate id" in p for p in problems))
        self.assertTrue(any("needs.rig" in p for p in problems))

    def test_pass_needs_evidence(self):
        self.assertTrue(any("needs evidence" in p for p in validate_gates(self.doc(make_gate("a", state="PASS")))))

    def test_rejects_absolute_and_escaping_doc_paths_and_unknown_keys(self):
        gate = make_gate("a")
        gate["source_doc"] = {"path": "../x.md", "anchor": "a", "extra": 1}
        gate["needs"]["gpu"] = True
        problems = validate_gates(self.doc(gate))
        self.assertTrue(any("repo-relative" in p for p in problems))
        self.assertTrue(any("source_doc.extra" in p for p in problems))
        self.assertTrue(any("needs.gpu" in p for p in problems))

    def test_check_command_reports_exit_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "ok", [make_gate("a")])
            self.assertEqual(run_cli("gates", "check", str(repo))[0], 0)
            (repo / "gates.json").write_text("{}", encoding="utf-8")
            code, _, err = run_cli("gates", "check", str(repo))
            self.assertEqual(code, 2)
            self.assertIn("schema must be 1", err)


class GatesLintTests(unittest.TestCase):
    def lint(self, gate: dict, status: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "r", [gate], status)
            return lint_gates(repo, load_gates(repo))

    def test_status_line_with_state_word_passes_even_with_a_space(self):
        gate = make_gate("a")
        gate["source_doc"]["status_line"] = "| a |"
        self.assertEqual(self.lint(gate, "a\n| a | IMPLEMENTED, LIVE PENDING |"), [])

    def test_status_line_contradicting_state_fails(self):
        gate = make_gate("a", state="PASS")
        gate["evidence"] = ["run-1"]
        gate["source_doc"]["status_line"] = "| a |"
        problems = self.lint(gate, "a\n| a | LIVE_PENDING |")
        self.assertEqual(len(problems), 1)
        self.assertIn("state PASS but", problems[0])

    def test_missing_anchor_and_status_line_fail(self):
        gate = make_gate("a")
        gate["source_doc"]["status_line"] = "nowhere"
        gate["source_doc"]["anchor"] = "zz-anchor"
        problems = self.lint(gate, "unrelated")
        self.assertTrue(any("anchor" in p for p in problems))
        self.assertTrue(any("status line" in p for p in problems))

    def test_lint_command_exit_code(self):
        gate = make_gate("a", state="FAIL")
        gate["source_doc"]["status_line"] = "a"
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "r", [gate], "a is LIVE_PENDING")
            code, out, _ = run_cli("gates", "lint", str(repo))
            self.assertEqual(code, 1)
            self.assertIn("LINT:", out)


class GatesRecordTests(unittest.TestCase):
    def test_record_updates_only_that_gate_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "r", [make_gate("a"), make_gate("b")])
            status_before = (repo / "STATUS.md").read_text(encoding="utf-8")
            gate = record_gate(repo, "a", "PASS", ["run-7"], today="2026-11-01")
            data = load_gates(repo)
            self.assertEqual((gate["state"], gate["evidence"], gate["updated"]), ("PASS", ["run-7"], "2026-11-01"))
            self.assertEqual(data["gates"][1]["state"], "LIVE_PENDING")
            self.assertEqual((repo / "STATUS.md").read_text(encoding="utf-8"), status_before)
            self.assertEqual([p.name for p in repo.iterdir() if p.suffix == ".tmp"], [])

    def test_record_refuses_pass_without_evidence_unknown_gate_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "r", [make_gate("a")])
            with self.assertRaises(ValueError):
                record_gate(repo, "a", "PASS", [])
            with self.assertRaises(ValueError):
                record_gate(repo, "zzz", "FAIL", ["x"])
            with self.assertRaises(ValueError):
                record_gate(repo, "a", "BLOCKED", ["x"])
            self.assertEqual(load_gates(repo)["gates"][0]["state"], "LIVE_PENDING")

    def test_record_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "r", [make_gate("a")])
            code, out, _ = run_cli("gates", "record", "a", "--repo", str(repo), "--state", "FAIL", "--evidence", "log.txt")
            self.assertEqual(code, 0)
            self.assertIn("a: FAIL", out)
            self.assertEqual(load_gates(repo)["gates"][0]["evidence"], ["log.txt"])


class LivePendingPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.one = make_repo(root, "one", [
            make_gate("big", mods=["nex", "lazy"], java="25", launcher="direct", save=True),
            make_gate("small", mods=["lazy"], java="25"),
            make_gate("other-java", mods=["lazy"], java="17"),
            make_gate("no-rig", rig=False) | {"needs": {"rig": False}},
            make_gate("done", state="PASS") | {"evidence": ["e"]},
            make_gate("blocked", state="BLOCKED", mods=["x"]),
        ])
        self.two = make_repo(root, "two", [make_gate("also", mods=["nex"], save=True), make_gate("fail", state="FAIL", mods=["lazy"], java="25")])

    def test_subset_gates_ride_a_larger_launch_and_pinned_settings_split_blocks(self):
        from bridgeforge.gates import collect_open_gates
        planned, blocked = collect_open_gates([self.one, self.two])
        blocks = plan_blocks(planned)
        by_host = {frozenset(b.mods): sorted(g["id"] for _, g in b.gates) for b in blocks}
        self.assertEqual(by_host[frozenset({"nex", "lazy"})], ["also", "big", "fail", "small"])
        self.assertEqual(by_host[frozenset({"lazy"})], ["other-java"])
        self.assertEqual(len(blocks), 2)
        self.assertEqual([g["id"] for _, g in blocked], ["blocked"])

    def test_gate_needing_a_save_does_not_ride_a_saveless_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = make_repo(Path(tmp), "r", [make_gate("a", mods=["m", "n"]), make_gate("b", mods=["m"], save=True)])
            plan = live_pending_plan([repo])
            self.assertIn("2 launch block(s)", plan)

    def test_plan_text_lists_commands_and_excludes_pass_and_no_rig(self):
        plan = live_pending_plan([self.one, self.two])
        self.assertIn("run big", plan)
        self.assertIn("one:big", plan)
        self.assertNotIn("no-rig", plan)
        self.assertNotIn("one:done", plan)
        self.assertIn("## Blocked (not scheduled)", plan)

    def test_board_live_pending_writes_file(self):
        out_file = Path(self.tmp.name) / "plan.md"
        code, out, _ = run_cli("board", "--live-pending", "--repos", str(self.one), str(self.two), "--write", str(out_file))
        self.assertEqual(code, 0)
        self.assertEqual(out_file.read_text(encoding="utf-8").strip(), out.strip())
        self.assertIn("# Live-pending session plan", out)

    def test_board_live_pending_needs_repos_and_valid_files(self):
        self.assertEqual(run_cli("board", "--live-pending")[0], 2)
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(run_cli("board", "--live-pending", "--repos", str(empty))[0], 2)


if __name__ == "__main__":
    unittest.main()
