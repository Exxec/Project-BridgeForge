import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts


class ScannerTests(unittest.TestCase):
    def test_scans_metadata_bytecode_and_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "legacy", "gameVersion": "0.95.1a", "dependencies": ["MagicLib"]}), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "Example.java").write_text("import sun.misc.Unsafe;", encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "broken.json").write_text("{", encoding="utf-8")
            with zipfile.ZipFile(root / "LazyLib.jar", "w") as archive:
                archive.writestr("Example.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            result = scan_mod(root)
            self.assertEqual(result.estimated_starsector, "0.95.1a")
            self.assertEqual(result.estimated_java, "8")
            self.assertTrue(any(f.id == "bundled-lazylib" for f in result.findings))
            self.assertTrue(any(f.id == "internal-jvm-api" for f in result.findings))
            self.assertTrue(any(f.id == "invalid-json" for f in result.findings))

    def test_refuses_artifacts_inside_original_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = scan_mod(root)
            with self.assertRaises(ValueError):
                write_artifacts(result, root / "artifacts")
