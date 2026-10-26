from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

import bridgeforge.finding_stats as fs
from bridgeforge.scan import scan_registry as reg
from bridgeforge.cli import main
from bridgeforge.finding_stats import finding_stats
from tests.support import resolved_temp_dir

MOD_INFO = '{"id": "%s", "name": "%s", "version": "1.0", "gameVersion": "0.98a-RC8"}'


def _workspace(queue: Path, name: str, extra_info: str | None = None) -> Path:
    workspace = queue / name
    (workspace / "working").mkdir(parents=True)
    (workspace / "working" / "mod_info.json").write_text(extra_info or MOD_INFO % (name.lower(), name), encoding="utf-8")
    (workspace / "working" / "data").mkdir()
    (workspace / "working" / "data" / "x.csv").write_text("id,name\na,A\n", encoding="utf-8")
    return workspace


def _scan(workspace: Path, folder: str = "scan-anything", *extra: str) -> tuple[int, str]:
    err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(err):
        code = main(["scan", str(workspace / "working"), "--output", str(workspace / "reports" / folder), *extra])
    return code, err.getvalue()


def _edit_keeping_mtime(path: Path, text: str) -> None:
    info = path.stat()
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))


class FingerprintTests(unittest.TestCase):
    def test_an_edit_that_keeps_the_file_time_changes_the_state(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            self.assertEqual(_scan(workspace, "owner-followup-scan-20261017")[0], 0)
            self.assertEqual(reg.assess(workspace)["state"], "CURRENT")
            _edit_keeping_mtime(workspace / "working" / "data" / "x.csv", "id,name\na,B\n")
            result = reg.assess(workspace)
        self.assertEqual(result["state"], "STALE")
        self.assertIn("inputs", result["detail"])

    def test_generated_reports_backups_and_new_report_times_do_not_make_a_scan_stale(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            _scan(workspace)
            (workspace / "reports" / "REVIVE.md").write_text("generated", encoding="utf-8")
            (workspace / "working" / "reports").mkdir()
            (workspace / "working" / "reports" / "baseline.json").write_text("{}", encoding="utf-8")
            (workspace / "working" / "data" / "x.csv.pre-bf-fix-a.bak").write_text("old", encoding="utf-8")
            _scan(workspace, "second")  # a second registration of identical content
            self.assertEqual(reg.assess(workspace)["state"], "CURRENT")

    def test_a_changed_jar_with_the_same_name_and_version_is_stale(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            jar = workspace / "working" / "jars" / "mod.jar"
            jar.parent.mkdir()
            jar.write_bytes(b"PK-one")
            _scan(workspace)
            self.assertEqual(reg.assess(workspace)["state"], "CURRENT")
            jar.write_bytes(b"PK-two")
            self.assertEqual(reg.assess(workspace)["state"], "STALE")

    def test_a_changed_dependency_provider_is_stale(self):
        info = '{"id": "m", "name": "M", "version": "1.0", "gameVersion": "0.98a-RC8", "dependencies": [{"id": "dep"}]}'
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod", info)
            provider = root / "providers" / "Dep"
            (provider / "data").mkdir(parents=True)
            (provider / "mod_info.json").write_text(MOD_INFO % ("dep", "Dep"), encoding="utf-8")
            (provider / "data" / "d.csv").write_text("id\n1\n", encoding="utf-8")
            self.assertEqual(_scan(workspace, "s", "--providers", str(root / "providers"))[0], 0)
            self.assertEqual(reg.assess(workspace)["state"], "CURRENT")
            (provider / "data" / "d.csv").write_text("id\n2\n", encoding="utf-8")
            result = reg.assess(workspace)
        self.assertEqual(result["state"], "STALE")
        self.assertIn("dependencies", result["detail"])

    def test_a_changed_check_or_option_or_target_changes_the_fingerprint(self):
        with resolved_temp_dir() as root:
            working = _workspace(root, "Mod") / "working"
            base = reg.fingerprint(working, {"target": "0.98.x/java17"})
            with mock.patch.object(reg, "scanner_identity", return_value="another-revision"):
                checks = reg.fingerprint(working, {"target": "0.98.x/java17"})
            options = reg.fingerprint(working, {"target": "0.98.x/java17", "removed_content": root / "catalogue.json"})
            target = reg.fingerprint(working, {"target": "0.98.x/java21"})
        self.assertEqual(reg._differing(base["parts"], checks["parts"]), ["scanner"])
        self.assertEqual(reg._differing(base["parts"], target["parts"]), ["target"])
        self.assertIn("options", reg._differing(base["parts"], options["parts"]))
        self.assertTrue(options["incomplete"])  # the named catalogue cannot be read
        self.assertNotEqual({base["digest"], checks["digest"], target["digest"]}, {base["digest"]})

    def test_an_unreadable_input_is_incomplete(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            _scan(workspace)
            real = reg._sha256

            def refuse(path):
                if Path(path).name == "x.csv":
                    raise PermissionError("locked")
                return real(path)

            with mock.patch.object(reg, "_sha256", side_effect=refuse):
                result = reg.assess(workspace)
        self.assertEqual(result["state"], "INCOMPLETE")
        self.assertIn("x.csv", result["detail"])


class RegistryTests(unittest.TestCase):
    def _registered(self, root: Path) -> Path:
        workspace = _workspace(root, "Mod")
        _scan(workspace, "wherever")
        return workspace

    def test_scan_is_found_through_the_registry_whatever_its_folder_is_called(self):
        with resolved_temp_dir() as root:
            workspace = self._registered(root)
            stats = finding_stats([workspace])
            result = reg.assess(workspace)
        self.assertEqual(result["state"], "CURRENT")
        self.assertEqual(stats["freshness"]["CURRENT"], 1)
        self.assertEqual(stats["mods"][0]["freshness"]["report"], "reports/wherever/bridgeforge.compat.json")

    def test_legacy_scan_is_unknown_and_a_new_file_time_does_not_bless_it(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            legacy = workspace / "reports" / "scan-2026-09-14" / "bridgeforge.compat.json"
            legacy.parent.mkdir(parents=True)
            legacy.write_text('{"findings": []}', encoding="utf-8")
            os.utime(legacy, (9_999_999_999, 9_999_999_999))
            result = reg.assess(workspace)
        self.assertEqual(result["state"], "UNKNOWN")

    def test_an_entry_without_a_fingerprint_is_unknown(self):
        with resolved_temp_dir() as root:
            workspace = self._registered(root)
            index = workspace / "reports" / reg.REGISTRY_NAME
            data = json.loads(index.read_text(encoding="utf-8"))
            data["entries"][0].pop("fingerprint")
            index.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(reg.assess(workspace)["state"], "UNKNOWN")

    def test_tampered_missing_relocated_or_escaping_reports_are_incomplete(self):
        cases = {}
        with resolved_temp_dir() as root:
            for label in ("tampered", "relocated", "escaping", "malformed"):
                workspace = _workspace(root, label)
                _scan(workspace, "out")
                report = workspace / "reports" / "out" / "bridgeforge.compat.json"
                index = workspace / "reports" / reg.REGISTRY_NAME
                if label == "tampered":
                    report.write_text('{"findings": []}', encoding="utf-8")
                elif label == "relocated":
                    report.parent.rename(workspace / "reports" / "moved")
                elif label == "escaping":
                    data = json.loads(index.read_text(encoding="utf-8"))
                    data["entries"][0]["report"] = "../../outside.json"
                    index.write_text(json.dumps(data), encoding="utf-8")
                else:
                    index.write_text("{not json", encoding="utf-8")
                cases[label] = reg.assess(workspace)["state"]
        self.assertEqual(cases, {"tampered": "INCOMPLETE", "relocated": "INCOMPLETE", "escaping": "INCOMPLETE", "malformed": "INCOMPLETE"})

    def test_an_interrupted_publication_leaves_no_entry(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            report = workspace / "reports" / "half" / "bridgeforge.compat.json"
            report.parent.mkdir(parents=True)
            report.write_text('{"findings": [', encoding="utf-8")  # cut short
            with self.assertRaises(reg.RegistryError):
                reg.register(workspace, report, workspace / "working", {})
            self.assertFalse((workspace / "reports" / reg.REGISTRY_NAME).exists())
            self.assertEqual(reg.assess(workspace)["state"], "NONE")

    def test_output_outside_the_workspace_is_not_registered(self):
        with resolved_temp_dir() as root:
            workspace = _workspace(root, "Mod")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = main(["scan", str(workspace / "working"), "--output", str(root / "elsewhere")])
            self.assertFalse((workspace / "reports" / reg.REGISTRY_NAME).exists())
        self.assertEqual(code, 0)
        self.assertIn("scan not registered", err.getvalue())


class FindingStatsFreshnessTests(unittest.TestCase):
    def _queue(self, root: Path) -> Path:
        queue = root / "q"
        for name in ("Current", "Changed", "Legacy"):
            _workspace(queue, name)
        _scan(queue / "Current", "a")
        _scan(queue / "Changed", "b")
        _edit_keeping_mtime(queue / "Changed" / "working" / "data" / "x.csv", "id,name\nz,Z\n")
        legacy = queue / "Legacy" / "reports" / "scan-1" / "bridgeforge.compat.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text('{"findings": []}', encoding="utf-8")
        return queue

    def test_report_counts_the_states(self):
        with resolved_temp_dir() as root:
            stats = finding_stats([self._queue(root)])
        self.assertEqual({k: v for k, v in stats["freshness"].items() if v}, {"CURRENT": 1, "STALE": 1, "UNKNOWN": 1})
        self.assertEqual(sorted(r["workspace"] for r in stats["not_current"]), ["Changed", "Legacy"])
        self.assertIn("### Not current (2)", fs.render(stats))

    def test_rescan_stale_scans_only_what_is_not_current_and_makes_it_current(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            with mock.patch.object(fs, "_scan_and_register", wraps=fs._scan_and_register) as scanned:
                stats = finding_stats([queue], rescan_stale=True)
            names = sorted(call.args[0].name for call in scanned.call_args_list)
            again = finding_stats([queue])
        self.assertEqual(names, ["Changed", "Legacy"])
        self.assertEqual({k: v for k, v in stats["freshness"].items() if v}, {"CURRENT": 3})
        self.assertEqual({k: v for k, v in again["freshness"].items() if v}, {"CURRENT": 3})
        self.assertTrue(all(r["freshness"]["rescanned"] for r in stats["mods"] if r["workspace"] != "Current"))

    def test_checkpoint_is_reused_only_for_the_same_content_and_filter(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            checkpoint = root / "out" / fs.CHECKPOINT_NAME
            finding_stats([queue], checkpoint=checkpoint)
            with mock.patch.object(fs, "_workspace_record", wraps=fs._workspace_record) as record:
                finding_stats([queue], checkpoint=checkpoint)
            same = record.call_count
            _edit_keeping_mtime(queue / "Current" / "working" / "data" / "x.csv", "id,name\nq,Q\n")
            (queue / "Legacy" / "working" / "reports").mkdir()
            (queue / "Legacy" / "working" / "reports" / "baseline.json").write_text('{"findings": []}', encoding="utf-8")
            with mock.patch.object(fs, "_workspace_record", wraps=fs._workspace_record) as record:
                finding_stats([queue], checkpoint=checkpoint)
            names = sorted(call.args[0].name for call in record.call_args_list)
        self.assertEqual(same, 0)
        self.assertEqual(names, ["Current", "Legacy"])  # changed content, changed baseline filter

    def test_cli_rescan_stale_writes_and_prints_progress(self):
        with resolved_temp_dir() as root:
            queue = self._queue(root)
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                self.assertEqual(main(["finding-stats", str(queue), "--rescan-stale", "--write", str(root / "out")]), 0)
            self.assertFalse((root / "out" / fs.CHECKPOINT_NAME).exists())
            text = (root / "out" / "FINDING_STATS.md").read_text(encoding="utf-8")
        self.assertIn("[3/3] Legacy:", err.getvalue())
        self.assertIn("CURRENT 3", text)


if __name__ == "__main__":
    unittest.main()
