"""Live bug BF-DRIFT-01: SEEKER's jar lives in jar/ (singular), which copy_drift never compared."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.copy_drift import _collect, compare_copies


def _mod(root: Path, jar_bytes: bytes) -> Path:
    (root / "jar").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jar/FX.jar"]}), encoding="utf-8")
    (root / "jar" / "FX.jar").write_bytes(jar_bytes)
    (root / "jar" / "FX.jar.pre-fix.bak").write_bytes(b"old")  # backups stay excluded
    return root


class DeclaredJarDriftTests(unittest.TestCase):
    def test_declared_jar_outside_jars_dir_is_collected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            files = _collect(_mod(Path(directory), b"PK-new"))
            self.assertIn("jar/FX.jar", files)
            self.assertNotIn("jar/FX.jar.pre-fix.bak", files)

    def test_changed_declared_jar_is_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            working = _mod(Path(directory) / "working", b"PK-patched")
            rig = _mod(Path(directory) / "rig", b"PK-stale")
            result = compare_copies(working, rig)
            self.assertEqual(result["status"], "DRIFT")
            self.assertIn("jar/FX.jar", [entry["path"] for entry in result["different"]])


if __name__ == "__main__":
    unittest.main()
