"""94.G2 (P2, 2026-11-19): a gene names the class the game loads, not a build source under src/."""
from __future__ import annotations

import hashlib
import json
import unittest
import zipfile
from pathlib import Path

from bridgeforge.genome.gene import describe, validate
from tests.support import resolved_temp_dir, write_text as _write

SCRIPT = "package data.hullmods;\npublic class marker_mod { }\n"
CLASS_BYTES = b"\xca\xfe\xba\xbe compiled marker_mod"


def _mod(root: Path, *, jar: bool, source_at: str) -> Path:
    mod = root / "mod"
    info = {"id": "markermod", "name": "Marker Mod", "version": "1.0"}
    if jar:
        info["jars"] = ["jars/marker.jar"]
        (mod / "jars").mkdir(parents=True)
        with zipfile.ZipFile(mod / "jars" / "marker.jar", "w") as archive:
            archive.writestr("data/hullmods/marker_mod.class", CLASS_BYTES)
    _write(mod / "mod_info.json", json.dumps(info))
    _write(mod / "data" / "hullmods" / "hull_mods.csv", "name,id,script\nMarker,marker_mod,data.hullmods.marker_mod\n")
    _write(mod / source_at, SCRIPT)
    return mod


class LoadedClassTests(unittest.TestCase):
    def test_a_jar_class_beats_its_build_source(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, jar=True, source_at="src/data/hullmods/marker_mod.java"), "hullmod:marker_mod")
        self.assertEqual(validate(gene), [])
        classes = [m for m in gene["members"] if m["what"] == "jar-class"]
        self.assertEqual([m["path"] for m in classes], ["jars/marker.jar!data/hullmods/marker_mod.class"])
        self.assertEqual(classes[0]["sha256"], hashlib.sha256(CLASS_BYTES).hexdigest())
        self.assertIn("src/data/hullmods/marker_mod.java is not a member", classes[0]["reason"])
        self.assertFalse(any(m["path"].startswith("src/") for m in gene["members"]))

    def test_a_jar_class_beats_a_loose_script_of_the_same_name(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, jar=True, source_at="data/hullmods/marker_mod.java"), "hullmod:marker_mod")
        self.assertEqual([m["what"] for m in gene["members"] if "marker_mod" in m["path"] and m["what"] != "csv-row"], ["jar-class"])

    def test_a_loose_script_at_its_package_path_is_the_member(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, jar=False, source_at="data/hullmods/marker_mod.java"), "hullmod:marker_mod")
        self.assertIn(("file", "data/hullmods/marker_mod.java"), {(m["what"], m["path"]) for m in gene["members"]})

    def test_a_source_only_under_src_with_no_jar_is_missing_not_a_member(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, jar=False, source_at="src/data/hullmods/marker_mod.java"), "hullmod:marker_mod")
        self.assertFalse(any(m["path"].startswith("src/") for m in gene["members"]))
        self.assertTrue(any("src/data/hullmods/marker_mod.java" in m and "never loads it" in m for m in gene["unknowns"]["missing"]))


if __name__ == "__main__":
    unittest.main()
