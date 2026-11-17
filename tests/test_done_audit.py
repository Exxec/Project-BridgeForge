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

    def test_an_archive_the_owner_closed_is_listed_not_audited(self) -> None:
        """ROADMAP-3 95.15: owner 2026-11-17, "nightcross armory has been superseded and can safely be ignored". `close` marks
        the archive (a dated section in workspace/REVIVAL_REPORT.md), and done-audit lists it without auditing it."""
        from bridgeforge.report_status import closed_archive_status
        from bridgeforge.workspace_tools import close_workspace

        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "queue"
            plugin = "package data.plugins;\npublic class P {\n    void s(String n) { Global.getSector().getStarSystem(n).getPlanets(); }\n}\n"
            _write(done / "Old" / "Old" / "mod_info.json", '{"id": "old", "version": "1"}')
            _write(done / "Old" / "Old" / "data" / "plugins" / "P.java", plugin)
            _write(done / "Old" / "workspace" / "REVIVAL_REPORT.md", "# Revival report\n\nLIVE_VALIDATED\n")
            before = closed_archive_status(done / "Old")
            written = close_workspace(done / "Old", "SUPERSEDED", "Owner 2026-11-17: superseded, can safely be ignored.", day="2026-11-17")
            result = done_audit(done, queue, quiet=True)
            report = (done / "DONE_AUDIT.md").read_text(encoding="utf-8")
        old = result["mods"][0]
        self.assertIsNone(before)
        self.assertTrue(written.endswith("REVIVAL_REPORT.md") and "workspace" in written)
        self.assertEqual((old["status"], old["findings"], old["closed"]), ("SUPERSEDED", [], True))
        self.assertIn("closed by the owner", report)

    def test_a_close_wins_over_a_checkpoint_record_from_before_it(self) -> None:
        """Review 2026-11-17: a done-audit interrupted before the close, resumed after it, reported the archive's old audit."""
        import json

        from bridgeforge.workspace_tools import close_workspace

        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "queue"
            _write(done / "Old" / "Old" / "mod_info.json", '{"id": "old", "version": "1"}')
            _write(done / "Old" / "workspace" / "REVIVAL_REPORT.md", "# Revival report\n\nLIVE_VALIDATED\n")
            header = {"done": str(done.resolve()), "queue": str(queue.resolve()), "vanilla_core": None}
            cached = {"mod": "Old", "status": "CLEAN", "stale": None, "findings": []}
            (done / "DONE_AUDIT.partial.jsonl").write_text(json.dumps(header) + "\n" + json.dumps({"key": "Old", "value": cached}) + "\n",
                                                           encoding="utf-8")
            close_workspace(done / "Old" / "Old", "SUPERSEDED", "Owner: superseded.")  # the shipped-copy path target-impact prints
            result = done_audit(done, queue, quiet=True)
        self.assertEqual(result["mods"][0]["status"], "SUPERSEDED")

    def test_close_refuses_a_folder_that_is_neither_a_workspace_nor_an_archive(self) -> None:
        from bridgeforge.workspace_tools import close_workspace

        with resolved_temp_dir() as root:
            (root / "Somewhere").mkdir()
            with self.assertRaises(ValueError):
                close_workspace(root / "Somewhere", "SUPERSEDED", "Owner: superseded.")
            self.assertFalse((root / "Somewhere" / "working").exists())


if __name__ == "__main__":
    unittest.main()


class StatusBehindTests(unittest.TestCase):
    def test_an_archive_note_short_of_live_validated_is_flagged_when_the_live_record_is_current(self) -> None:
        # Six archives made on 2026-10-04 as READY_FOR_LIVE_TEST passed their runs on 2026-10-05 and were never refreshed.
        import json

        from bridgeforge.live.live_trust import shipped_hash

        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "In operation"
            for base in (done / "Mod" / "Mod", queue / "Mod" / "working"):
                _write(base / "mod_info.json", '{"id": "m", "version": "1"}')
            _write(done / "Mod" / "ARCHIVE_NOTE.md", "# Mod 1: archive note\n\nRevival report status: **READY_FOR_LIVE_TEST** (archived 2026-10-04).\n")
            _write(done / "Quiet" / "Quiet" / "mod_info.json", '{"id": "q", "version": "1"}')
            _write(queue / "Quiet" / "working" / "mod_info.json", '{"id": "q", "version": "1"}')
            _write(done / "Quiet" / "ARCHIVE_NOTE.md", "# Quiet 1: archive note\n\nRevival report status: **READY_FOR_LIVE_TEST** (archived 2026-10-04).\n")
            run = {"test_id": "GRP-X", "date": "2026-10-05", "verdict": "PASS", "version": "1",
                   "shipped_sha256": shipped_hash(queue / "Mod" / "working")}
            _write(queue / "Mod" / "reports" / "live_runs.jsonl", json.dumps(run) + "\n")
            result = done_audit(done, queue, quiet=True)
            report = (done / "DONE_AUDIT.md").read_text(encoding="utf-8")
        by = {r["mod"]: r for r in result["mods"]}
        # the fixture has no zip, so PACKAGING outranks it in `status`; the field and the report line are what matter here
        self.assertIn("GRP-X", by["Mod"]["status_behind"])
        self.assertIsNone(by["Quiet"]["status_behind"])  # no live record: nothing to be behind
        self.assertIn("archive status behind the live record", report)


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
