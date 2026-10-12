"""ROADMAP 70 H3.2: one list of every recorded live run and regression pass."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from bridgeforge.cli import main
from bridgeforge.live_ledger import last_runs, read_runs
from tests.support import resolved_temp_dir


def _write(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _queue(root):
    _write(root / "_live" / "GRP-A-20261001.json", {"test_id": "GRP-A-20261001", "date": "2026-10-01",
                                                     "members": [{"mod_id": "zorg", "workspace": "Zorg18", "version": "V18+bf.7", "verdict": "PASS"},
                                                                 {"mod_id": "other", "workspace": "Other", "version": "1.0", "verdict": "PASS"}]})
    _write(root / "_live" / "bad.json", ["not", "a", "record"])
    (root / "_live" / "broken.json").write_text("{", encoding="utf-8")
    _write(root / "_regress" / "regress-20261012.json", {"date": "2026-10-12", "groups": [
        {"test_id": "REG-20261012-G1", "members": {"zorg": "PASS", "other": "FAIL"}},
        {"test_id": "REG-20261012-G2", "members": ["not", "a", "dict"]}]})
    return root


class LiveLedgerTests(unittest.TestCase):
    def test_runs_from_records_and_passes_are_joined_per_mod_and_unreadable_files_are_skipped(self) -> None:
        with resolved_temp_dir() as root:
            rows = read_runs(_queue(root))
        self.assertEqual([(r["test_id"], r["mod"], r["verdict"]) for r in rows],
                         [("GRP-A-20261001", "zorg", "PASS"), ("GRP-A-20261001", "other", "PASS"),
                          ("REG-20261012-G1", "zorg", "PASS"), ("REG-20261012-G1", "other", "FAIL")])
        per_mod = last_runs(rows)
        self.assertEqual(per_mod["zorg"]["last_pass"]["test_id"], "REG-20261012-G1")
        self.assertFalse(per_mod["zorg"]["attention"])
        self.assertEqual(per_mod["other"]["last_pass"]["test_id"], "GRP-A-20261001")  # the old PASS, before the failing regression
        self.assertTrue(per_mod["other"]["attention"])

    def test_the_command_lists_and_filters_by_attention(self) -> None:
        with resolved_temp_dir() as root:
            _queue(root)
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["live-ledger", "--queue", str(root), "--attention"]), 0)
            text = out.getvalue()
            data = io.StringIO()
            with redirect_stdout(data):
                main(["live-ledger", "--queue", str(root), "--json", "--mod", "zorg"])
        self.assertIn("other: last PASS GRP-A-20261001 1.0; last run REG-20261012-G1 FAIL  <- needs a look", text)
        self.assertNotIn("zorg:", text)
        self.assertEqual(list(json.loads(data.getvalue())["mods"]), ["zorg"])


if __name__ == "__main__":
    unittest.main()
