import tempfile
import time
import unittest
from pathlib import Path

from bridgeforge.copy_drift import compare_copies
from bridgeforge.cli import main


def _make_mod(root: Path, mod_id: str = "fixture") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "mod_info.json").write_text('{"id":"%s"}' % mod_id, encoding="utf-8")
    (root / "data" / "scripts").mkdir(parents=True)
    (root / "data" / "scripts" / "Plugin.java").write_text("class Plugin {}", encoding="utf-8")
    (root / "jars").mkdir()
    (root / "jars" / "mod.jar").write_bytes(b"jar-bytes")
    return root


class CopyDriftTests(unittest.TestCase):
    def test_identical_copies_report_no_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            working = _make_mod(root / "working" / "MyMod")
            deployed = _make_mod(root / "deployed" / "mods" / "MyMod")
            result = compare_copies(working.parent, deployed.parent)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["drift_count"], 0)

    def test_detects_missing_different_and_extra(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            working = _make_mod(root / "working" / "MyMod")
            deployed = _make_mod(root / "deployed" / "MyMod")
            # missing in deployed
            (working / "data" / "scripts" / "Extra.java").write_text("class Extra {}", encoding="utf-8")
            # different content, working newer
            time.sleep(0.02)
            (working / "jars" / "mod.jar").write_bytes(b"jar-bytes-updated")
            # extra in deployed only
            (deployed / "data" / "scripts" / "OnlyDeployed.java").write_text("class OnlyDeployed {}", encoding="utf-8")
            result = compare_copies(working, deployed)
            self.assertEqual(result["status"], "DRIFT")
            self.assertIn("data/scripts/Extra.java", result["missing_in_deployed"])
            self.assertIn("data/scripts/OnlyDeployed.java", result["extra_in_deployed"])
            different = {item["path"]: item["newer_side"] for item in result["different"]}
            self.assertEqual(different["jars/mod.jar"], "working")

    def test_ignores_backup_and_report_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            working = _make_mod(root / "working" / "MyMod")
            deployed = _make_mod(root / "deployed" / "MyMod")
            (working / "jars" / "mod.jar.pre-fix.bak").write_bytes(b"old")
            (working / "jars" / "mod.jar.orig-backup").write_bytes(b"old2")
            (working / "reports").mkdir()
            (working / "reports" / "notes.txt").write_text("n", encoding="utf-8")
            (working / "src.zip").write_bytes(b"z")
            result = compare_copies(working, deployed)
            self.assertEqual(result["status"], "PASS")

    def test_missing_mod_info_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "working").mkdir()
            (root / "deployed").mkdir()
            with self.assertRaises(ValueError):
                compare_copies(root / "working", root / "deployed")

    def test_cli_exit_code_reflects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            working = _make_mod(root / "working" / "MyMod")
            deployed = _make_mod(root / "deployed" / "MyMod")
            self.assertEqual(main(["copy-drift", str(working), str(deployed)]), 0)
            (working / "data" / "scripts" / "Extra.java").write_text("class Extra {}", encoding="utf-8")
            self.assertEqual(main(["copy-drift", str(working), str(deployed), "--json"]), 1)
