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


class PackagingTests(unittest.TestCase):
    def test_duplicate_entries_wrong_version_and_folder_drift(self) -> None:
        import zipfile

        from bridgeforge.done_audit import packaging_problems

        with resolved_temp_dir() as root:
            folder = root / "Mod"
            _write(folder / "Mod" / "mod_info.json", '{"id": "m", "version": "1+bf.2"}')
            _write(folder / "Mod" / "data" / "campaign" / "rules.csv", "id\n")
            with zipfile.ZipFile(folder / "Mod-1+bf.2.zip", "w") as z:
                z.writestr("Mod/mod_info.json", '{"id": "m", "version": "1+bf.1"}')
                z.writestr("Mod/data/campaign/rules.csv", "id\n")
                z.writestr("Mod/Data/campaign/rules.csv", "id\n")
            problems = packaging_problems(folder, folder / "Mod")
            (folder / "Mod-1+bf.2.zip").unlink()
            missing = packaging_problems(folder, folder / "Mod")
        text = " | ".join(problems)
        self.assertIn("entry twice", text)
        self.assertIn("declares '1+bf.1', not '1+bf.2'", text)
        self.assertIn("zip differs from the folder", text)  # mod_info.json bytes differ
        self.assertEqual(missing, ["no zip beside the mod folder"])
