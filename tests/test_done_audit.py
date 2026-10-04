"""`done-audit` (owner request 2026-10-04): stale archives and crash-class findings in Done/."""
from __future__ import annotations

import unittest

from bridgeforge.done_audit import done_audit
from tests.support import resolved_temp_dir


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DoneAuditTests(unittest.TestCase):
    def test_reports_a_stale_archive_and_a_crash_class_finding(self) -> None:
        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "queue"
            plugin = ("package data.plugins;\npublic class P {\n    public void set(String name) {\n"
                      "        Global.getSector().getStarSystem(name).getPlanets();\n    }\n}\n")
            for base in (done / "Mod" / "Mod", queue / "Mod" / "working"):
                _write(base / "mod_info.json", '{"id": "m", "version": "1"}')
                _write(base / "data" / "plugins" / "P.java", plugin)
            _write(done / "Clean" / "Clean" / "mod_info.json", '{"id": "c"}')
            _write(queue / "Mod" / "working" / "mod_info.json", '{"id": "m", "version": "1+bf.1"}')  # fixed after archiving
            result = done_audit(done, queue, quiet=True)
            report = (done / "DONE_AUDIT.md").read_text(encoding="utf-8")
            checkpoint_left = (done / "DONE_AUDIT.partial.jsonl").exists()
        by = {r["mod"]: r for r in result["mods"]}
        self.assertEqual(by["Mod"]["status"], "STALE")
        self.assertIn("campaign-lookup-dereferenced-unguarded", [h["id"] for h in by["Mod"]["findings"]])
        self.assertIsNone(by["Clean"]["stale"])  # no queue workspace to compare with
        self.assertNotIn("campaign-lookup-dereferenced-unguarded", [h["id"] for h in by["Clean"]["findings"]])
        self.assertIn("re-archive it", report)
        self.assertFalse(checkpoint_left)


if __name__ == "__main__":
    unittest.main()
