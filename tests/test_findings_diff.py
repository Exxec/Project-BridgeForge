"""ROADMAP-3 98.19: `findings-diff` compares two per-archive finding lists, old code against new."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from pathlib import Path

from bridgeforge import findings_diff
from tests.support import resolved_temp_dir


def _finding(finding_id: str, file: str, key: str) -> dict:
    return {"id": finding_id, "classification": "MANUAL", "file": file, "evidence": [f"key:{key}", "a second line"]}


def _audit(mods: list[dict]) -> dict:
    return {"schema_version": 1, "mode": "DONE_AUDIT", "done": "Done", "counts": {}, "mods": mods}


def _write(root: Path, name: str, data) -> Path:
    path = root / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


BEFORE = _audit([
    {"mod": "Alpha", "status": "FINDINGS", "findings": [_finding("check-a", "jars/a.jar", "k1"),
                                                        _finding("check-a", "jars/a.jar", "k2"),
                                                        _finding("check-b", "data/x.java", "call")]},
    {"mod": "Beta", "status": "FINDINGS", "findings": [_finding("check-a", "jars/b.jar", "k3")]},
    {"mod": "Gamma", "status": "CLEAN", "findings": []},
    {"mod": "Broken", "status": "FINDINGS", "findings": [_finding("check-a", "jars/c.jar", "k4")]},
    {"mod": "Gone", "status": "CLEAN", "findings": []},
])
AFTER = _audit([
    {"mod": "Alpha", "status": "FINDINGS", "findings": [_finding("check-a", "jars/a.jar", "k1"),
                                                        _finding("check-b", "data/x.java", "call")]},
    {"mod": "Beta", "status": "CLEAN", "findings": []},
    {"mod": "Gamma", "status": "FINDINGS", "findings": [_finding("check-a", "jars/g.jar", "k9")]},
    {"mod": "Broken", "status": "ERROR", "stale": None, "findings": [], "error": "scan failed"},
    {"mod": "New", "status": "CLEAN", "findings": []},
])


class DiffTests(unittest.TestCase):
    def _diff(self, before, after, ids=None) -> dict:
        with resolved_temp_dir() as root:
            return findings_diff.diff(_write(root, "a.json", before), _write(root, "b.json", after), ids)

    def test_dropped_and_new_findings_per_archive(self) -> None:
        result = self._diff(BEFORE, AFTER)
        self.assertEqual((result["archives_compared"], result["findings_before"], result["findings_after"]), (3, 4, 3))
        self.assertEqual((result["dropped"], result["appeared"]), (2, 1))
        changes = {c["archive"]: c for c in result["changes"]}
        self.assertEqual(sorted(changes), ["Alpha", "Beta", "Gamma"])
        self.assertEqual(changes["Alpha"]["dropped"], [["check-a", "jars/a.jar", "key:k2"]])
        self.assertEqual(changes["Alpha"]["appeared"], [])
        self.assertEqual(changes["Gamma"]["appeared"], [["check-a", "jars/g.jar", "key:k9"]])

    def test_an_archive_one_run_could_not_audit_is_not_compared(self) -> None:
        result = self._diff(BEFORE, AFTER)
        self.assertEqual(result["not_compared"], [{"archive": "Broken", "before": None, "after": "ERROR"}])
        self.assertNotIn("Broken", [c["archive"] for c in result["changes"]])
        self.assertEqual((result["only_before"], result["only_after"]), (["Gone"], ["New"]))

    def test_a_closed_archive_is_not_compared(self) -> None:
        closed = _audit([{"mod": "Alpha", "status": "SUPERSEDED", "stale": None, "findings": [], "closed": True}])
        result = self._diff(BEFORE, closed)
        self.assertEqual(result["not_compared"][0], {"archive": "Alpha", "before": None, "after": "SUPERSEDED"})
        self.assertEqual(result["dropped"], 0)
        # the flag decides even for a status this module does not know yet
        flagged = _audit([{"mod": "Alpha", "status": "RETIRED", "stale": None, "findings": [], "closed": True}])
        self.assertEqual(self._diff(BEFORE, flagged)["not_compared"][0]["after"], "RETIRED")
        self.assertEqual(set(findings_diff.NOT_AUDITED), {"ERROR", "NO_MOD_ROOT", "SUPERSEDED", "NOT_REVIVABLE"})

    def test_ids_limit_the_comparison(self) -> None:
        result = self._diff(BEFORE, AFTER, {"check-b"})
        self.assertEqual((result["findings_before"], result["dropped"], result["appeared"], result["changes"]), (1, 0, 0, []))
        self.assertEqual(result["ids"], ["check-b"])

    def test_the_98_8_sweep_shape_is_read(self) -> None:
        before = {"Alpha": [["jars/a.jar", "k1"], ["jars/a.jar", "k2"]], "Beta": []}
        after = {"Alpha": [["jars/a.jar", "k1"]], "Beta": [["jars/b.jar", "k3"]]}
        result = self._diff(before, after)
        self.assertEqual((result["findings_before"], result["findings_after"], result["dropped"], result["appeared"]), (2, 2, 1, 1))
        self.assertEqual(result["changes"][0]["dropped"], [["jars/a.jar", "k2"]])
        self.assertIn("  - jars/a.jar | k2", findings_diff.render(result))
        self.assertEqual(self._diff(before, after, {"check-a"})["findings_before"], 0)  # a bare list has no id

    def test_render_states_the_totals_and_each_change(self) -> None:
        text = findings_diff.render(self._diff(BEFORE, AFTER))
        self.assertTrue(text.startswith("4 findings become 3 over 3 archives: 2 dropped, 1 new, in 3 archive(s)."))
        self.assertIn("Alpha: -1 +0\n  - check-a jars/a.jar: key:k2", text)
        self.assertIn("not compared: Broken (before: audited; after: ERROR)", text)
        self.assertIn("in one run only (only before): Gone", text)

    def test_long_lists_are_cut_in_the_text_and_whole_in_json(self) -> None:
        many = findings_diff.SHOWN_PER_ARCHIVE + 3
        before = _audit([{"mod": "A", "status": "FINDINGS", "findings": [_finding("x", "f", str(i)) for i in range(many)]}])
        result = self._diff(before, _audit([{"mod": "A", "status": "CLEAN", "findings": []}]))
        self.assertEqual(len(result["changes"][0]["dropped"]), many)
        self.assertIn("and 3 more (--json lists all)", findings_diff.render(result))


class InputTests(unittest.TestCase):
    def test_unusable_inputs_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            good = _write(root, "good.json", BEFORE)
            for name, data in (("list.json", [1, 2]), ("scalars.json", {"A": 3}), ("nomod.json", _audit([{"status": "CLEAN"}])),
                               ("thing.json", {"A": [{"id": "x"}, 5]})):
                with self.subTest(name), self.assertRaises(findings_diff.FindingsFileError):
                    findings_diff.diff(good, _write(root, name, data))
            (root / "bad.json").write_text("{not json", encoding="utf-8")
            with self.assertRaises(findings_diff.FindingsFileError):
                findings_diff.diff(good, root / "bad.json")
            with self.assertRaises(findings_diff.FindingsFileError):
                findings_diff.diff(good, root / "missing.json")

    def test_the_command_prints_or_refuses(self) -> None:
        with resolved_temp_dir() as root:
            args = argparse.Namespace(before=_write(root, "a.json", BEFORE), after=_write(root, "b.json", AFTER), ids=None, json=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(findings_diff.run_cli(args), 0)
            self.assertEqual(json.loads(out.getvalue())["dropped"], 2)
            args.after = root / "missing.json"
            with contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(findings_diff.run_cli(args), 2)
            self.assertIn("cannot read", err.getvalue())


if __name__ == "__main__":
    unittest.main()
