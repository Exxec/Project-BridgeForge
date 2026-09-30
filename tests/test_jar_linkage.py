"""jar-linkage-unresolved: a mod jar's calls into game classes checked against RC8's core jars (2026-09-30)."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir


def _compile(javac: str, root: Path, sources: dict[str, str], classpath: Path | None = None) -> Path:
    src, out = root / "src", root / "classes"
    for name, text in sources.items():
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_text(text, encoding="utf-8")
    command = [javac, "--release", "17", "-d", str(out)] + (["-cp", str(classpath)] if classpath else []) + [str(src / n) for n in sources]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return out


def _jar(classes: Path, jar: Path) -> None:
    jar.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jar, "w") as archive:
        for path in classes.rglob("*.class"):
            archive.write(path, path.relative_to(classes).as_posix())


OLD_API = {"com/fs/starfarer/api/ui/Tip.java": "package com.fs.starfarer.api.ui; public interface Tip { void table(float w); int rows(); }"}
NEW_API = {"com/fs/starfarer/api/ui/Tip.java": "package com.fs.starfarer.api.ui; public interface Tip { Object table(float w); int rows(); }"}
MOD = {"data/hullmods/Info.java": "package data.hullmods; import com.fs.starfarer.api.ui.Tip;\n"
                                  "public class Info { void draw(Tip t) { t.table(1f); t.rows(); t.toString(); } }"}


class JarLinkageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

    def test_a_call_whose_rc8_return_type_changed_is_reported_as_a_relink(self) -> None:
        with resolved_temp_dir() as root:
            old_api = _compile(self.javac, root / "old", OLD_API)
            _jar(_compile(self.javac, root / "new", NEW_API), root / "starsector-core" / "starfarer.api.jar")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", MOD, classpath=old_api), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "starsector-core").findings if f.id == "jar-linkage-unresolved"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].file, "jars/m.jar!data/hullmods/Info.class")
        self.assertEqual(len(found[0].evidence), 1)  # rows() and Object.toString() resolve
        self.assertIn("Tip.table(F)V (RC8: (F)Ljava/lang/Object;)", found[0].evidence[0])
        self.assertIn("return type", found[0].explanation)


if __name__ == "__main__":
    unittest.main()
