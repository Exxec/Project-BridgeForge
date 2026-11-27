"""`done-audit` (owner request 2026-10-04): stale archives and crash-class findings in Done/."""
from __future__ import annotations

import unittest

from bridgeforge.done_audit import done_audit
from tests.support import resolved_temp_dir
from tests.support import write_text as _write


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

    def test_all_findings_lists_every_finding_and_the_run_names_its_code(self) -> None:
        """ROADMAP-3 98.19 review: findings-diff over done-audit compared only crash-class, MANUAL and UNKNOWN findings, and two
        runs could not be told apart. --all-findings lists every finding (accepted ones marked); the result and the checkpoint
        header name the checkout and its HEAD, so a resumed run under other code starts over."""
        import json
        from unittest import mock

        from bridgeforge import done_audit as audit

        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "queue"
            _write(done / "Mod" / "Mod" / "mod_info.json", '{"id": "m", "version": "1",}')  # a trailing comma: a REVIEW finding
            _write(done / "Mod" / "Mod" / "data" / "plugins" / "P.java",
                   "package data.plugins;\npublic class P {\n    void s(String n) { Global.getSector().getStarSystem(n).getPlanets(); }\n}\n")
            plain = done_audit(done, queue, quiet=True)
            every = done_audit(done, queue, quiet=True, all_findings=True)
            # an interrupted run under other code: its checkpoint is not reused
            stale = {"done": str(done.resolve()), "queue": str(queue.resolve()), "vanilla_core": None, "all_findings": True,
                     "code": {"checkout": "elsewhere", "head": "0" * 40}}
            cached = {"mod": "Mod", "status": "CLEAN", "stale": None, "findings": [], "all_findings": []}
            (done / audit.CHECKPOINT).write_text(json.dumps(stale) + "\n" + json.dumps({"key": "Mod", "value": cached}) + "\n",
                                                 encoding="utf-8")
            resumed = done_audit(done, queue, quiet=True, all_findings=True)
        record = every["mods"][0]
        kept = {h["id"] for h in record["findings"]}
        listed = {h["id"] for h in record["all_findings"]}
        self.assertNotIn("all_findings", plain["mods"][0])
        self.assertTrue(kept < listed, (kept, listed))  # every kept finding is listed, and more besides
        self.assertTrue(all("accepted" in h for h in record["all_findings"]))
        self.assertEqual((plain["all_findings"], every["all_findings"]), (False, True))
        self.assertEqual(set(every["code"]), {"checkout", "head"})
        self.assertNotEqual(resumed["mods"][0]["all_findings"], [])  # the other code's cached record was not reused
        with mock.patch("subprocess.run", side_effect=OSError("no git")):  # code_identity imports subprocess when called
            self.assertIsNone(audit.code_identity()["head"])

    def test_an_accepted_finding_is_listed_and_marked(self) -> None:
        from bridgeforge.baseline import accept_findings, finding_dict_baseline_key

        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "queue"
            mod = done / "Mod" / "Mod"
            _write(mod / "mod_info.json", '{"id": "m", "version": "1"}')
            _write(mod / "data" / "plugins" / "P.java",
                   "package data.plugins;\npublic class P {\n    void s(String n) { Global.getSector().getStarSystem(n).getPlanets(); }\n}\n")
            first = done_audit(done, queue, quiet=True)["mods"][0]["findings"][0]
            accept_findings(mod, [finding_dict_baseline_key(first)], reason="test")
            record = done_audit(done, queue, quiet=True, all_findings=True)["mods"][0]
        self.assertNotIn(first["id"], [h["id"] for h in record["findings"]])
        listed = [h for h in record["all_findings"] if h["id"] == first["id"]]
        self.assertEqual([h["accepted"] for h in listed], [True])

    def test_an_interrupted_run_resumed_under_other_code_starts_over(self) -> None:
        # Review, 2026-11-27: the checkpoint did not record the code, so a run resumed with the other checkout reused records.
        from unittest import mock

        from bridgeforge import done_audit as audit

        with resolved_temp_dir() as root:
            done, queue = root / "Done", root / "queue"
            for name in ("A", "B"):
                _write(done / name / name / "mod_info.json", f'{{"id": "{name.lower()}", "version": "1"}}')
            calls: list[str] = []
            real = audit.audit_one

            def counting(folder, *args, **kwargs):
                calls.append(folder.name)
                if interrupt and len(calls) == 2:
                    raise KeyboardInterrupt
                return real(folder, *args, **kwargs)

            interrupt = True
            with mock.patch.object(audit, "audit_one", counting), \
                    mock.patch.object(audit, "code_identity", return_value={"checkout": "main", "head": "a" * 40}):
                with self.assertRaises(KeyboardInterrupt):
                    done_audit(done, queue, quiet=True, all_findings=True)
                self.assertTrue((done / audit.CHECKPOINT).is_file())
            calls.clear()
            interrupt = False
            with mock.patch.object(audit, "audit_one", counting), \
                    mock.patch.object(audit, "code_identity", return_value={"checkout": "branch", "head": "b" * 40}):
                done_audit(done, queue, quiet=True, all_findings=True)
        self.assertEqual(calls, ["A", "B"])  # A was audited again: its record came from the other code

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
