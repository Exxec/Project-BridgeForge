"""`patch-jar-class`: recompile a few edited classes and swap them into a jar (2026-09-30)."""
from __future__ import annotations

import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.jar_patch import patch_jar_classes
from tests.support import resolved_temp_dir

ORIGINAL = (
    "package data.hullmods;\n"
    "public class Gantry {\n"
    "    private float check = 0f;\n"
    "    public Object anchor(java.util.Map<String, Object> m) { return m.get(\"a\").toString(); }\n"
    "    public float tick() { check += 1f; return check; }\n"
    "}\n"
)
GUARDED = ORIGINAL.replace('return m.get("a").toString();', 'Object a = m.get("a"); return a == null ? null : a.toString();')
PER_SHIP = ORIGINAL.replace("    private float check = 0f;\n", "").replace("check += 1f; return check;", "return 1f;")


class JarPatchTests(unittest.TestCase):
    """Real javac; skipped cleanly when no JDK is on PATH."""

    def setUp(self) -> None:
        javac = shutil.which("javac")
        if javac is None:
            self.skipTest("no javac on PATH")
        self.javac = javac

    def _workspace(self, root: Path) -> Path:
        ws = root / "In operation" / "Mod"
        (ws / "working" / "jars").mkdir(parents=True)
        (ws / "working" / "mod_info.json").write_text('{"id":"mod","name":"Mod","version":"1","gameVersion":"0.98a-RC8","jars":["jars/mod.jar"]}', encoding="utf-8")
        src = root / "orig" / "data" / "hullmods"
        src.mkdir(parents=True)
        (src / "Gantry.java").write_text(ORIGINAL, encoding="utf-8")
        classes = root / "orig-classes"
        done = subprocess.run([self.javac, "--release", "17", "-d", str(classes), str(src / "Gantry.java")], capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0, done.stderr)
        with zipfile.ZipFile(ws / "working" / "jars" / "mod.jar", "w") as archive:
            archive.write(classes / "data" / "hullmods" / "Gantry.class", "data/hullmods/Gantry.class")
            archive.writestr("README.txt", "kept")
        (ws / "working" / "src" / "data" / "hullmods").mkdir(parents=True)
        (ws / "working" / "src" / "data" / "hullmods" / "Gantry.java").write_text(ORIGINAL, encoding="utf-8")
        return ws

    def test_a_null_guard_passes_and_installs_with_backups(self) -> None:
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            edited = root / "edit" / "Gantry.java"
            edited.parent.mkdir()
            edited.write_text(GUARDED, encoding="utf-8")
            result = patch_jar_classes(ws, "jars/mod.jar", [edited], source_root="src", install=True)
            jar_names = zipfile.ZipFile(ws / "working" / "jars" / "mod.jar").namelist()
            source_now = (ws / "working" / "src" / "data" / "hullmods" / "Gantry.java").read_text(encoding="utf-8")
            backup = Path(result["backup_jar"]).is_file()
        self.assertEqual(result["status"], "PASS", result)
        entry = result["classes"][0]
        self.assertEqual(entry["calls_changed"], {})
        self.assertEqual(entry["null_checks"][1] - entry["null_checks"][0], 1)
        self.assertTrue(result["installed"] and backup)
        self.assertIn("README.txt", jar_names)  # other entries kept
        self.assertIn("a == null", source_now)  # the edited source copied into the source tree

    def test_a_removed_field_is_refused_unless_allowed(self) -> None:
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            edited = root / "edit" / "Gantry.java"
            edited.parent.mkdir()
            edited.write_text(PER_SHIP, encoding="utf-8")
            refused = patch_jar_classes(ws, "jars/mod.jar", [edited], install=True)
            allowed = patch_jar_classes(ws, "jars/mod.jar", [edited], allow_removed=["check"])
        self.assertEqual(refused["status"], "REFUSED")
        self.assertFalse(refused["installed"])
        self.assertEqual(allowed["status"], "PASS", allowed)


if __name__ == "__main__":
    unittest.main()
