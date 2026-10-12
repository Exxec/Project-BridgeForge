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


class JarPacketsTests(JarPatchTests):
    """`jar-packets`: source lookup and the faithful check for jar-only packets."""

    def _packet(self, ws: Path, entry: str) -> None:
        import json
        packets = ws / "reports" / "escalations"
        packets.mkdir(parents=True)
        (packets / "hullmod-instance-state--1.json").write_text(json.dumps(
            {"id": "hullmod-instance-state--1", "finding": "hullmod-instance-state", "kind": "agent", "allowed_files": [entry]}), encoding="utf-8")

    def test_matching_source_is_faithful_and_copied_to_edit(self) -> None:
        from bridgeforge.jar_patch import prepare_jar_packets
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            self._packet(ws, "jars/mod.jar!data/hullmods/Gantry.class")
            row = prepare_jar_packets(ws)["packets"][0]
            copied = Path(row["edit"]).is_file()
        self.assertEqual(row["state"], "FAITHFUL", row)
        self.assertTrue(copied)
        self.assertIn("--install", row["next"])

    def test_a_source_that_is_not_what_shipped_differs(self) -> None:
        from bridgeforge.jar_patch import prepare_jar_packets
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            (ws / "working" / "src" / "data" / "hullmods" / "Gantry.java").write_text(PER_SHIP, encoding="utf-8")
            self._packet(ws, "jars/mod.jar!data/hullmods/Gantry.class")
            row = prepare_jar_packets(ws)["packets"][0]
        self.assertEqual(row["state"], "SOURCE_DIFFERS", row)

    def test_no_source_says_so(self) -> None:
        from bridgeforge.jar_patch import prepare_jar_packets
        with resolved_temp_dir() as root:
            ws = self._workspace(root)
            self._packet(ws, "jars/mod.jar!data/hullmods/Missing.class")
            row = prepare_jar_packets(ws)["packets"][0]
        self.assertEqual(row["state"], "NO_SOURCE")


class RelinkAndDecompilerTests(unittest.TestCase):
    def test_a_return_type_change_alone_is_a_relink(self) -> None:
        from bridgeforge.jar_patch import _only_return_type_relinks
        # Too Much Information (2026-09-30): RC8's TooltipMakerAPI.beginTable returns UIPanelAPI, the jar expects void.
        self.assertEqual(_only_return_type_relinks({"T.beginTable:(F)V": -2, "T.beginTable:(F)LUIPanelAPI;": 2}),
                         ["T.beginTable:(F)V -> LUIPanelAPI;"])
        self.assertEqual(_only_return_type_relinks({"T.a:(F)V": -1, "T.b:(F)V": 1}), [])
        self.assertEqual(_only_return_type_relinks({"T.a:(F)V": -1}), [])

    def test_decompiler_is_found_beside_the_queue(self) -> None:
        from bridgeforge.jar_patch import find_decompiler
        with resolved_temp_dir() as root:
            (root / "_tools").mkdir()
            (root / "_tools" / "vineflower-1.12.0.jar").write_bytes(b"")
            found = find_decompiler(root / "Mod")
        self.assertEqual(found.name, "vineflower-1.12.0.jar")


class NestCallTests(unittest.TestCase):
    def test_calls_inside_the_class_nest_are_separated(self) -> None:
        from bridgeforge.jar_patch import _in_nest
        # VayraGhostShip (2026-09-30): an old javac's access$000 bridge vs a Java 17 direct nestmate call.
        entry = "data/scripts/hullmods/VayraGhostShip.class"
        self.assertTrue(_in_nest("data/scripts/hullmods/VayraGhostShip$NanobotData.access$000:(I)V", entry))
        self.assertTrue(_in_nest("init:(Lcom/fs/starfarer/api/combat/ShipAPI;)V", entry))
        self.assertFalse(_in_nest("com/fs/starfarer/api/ui/TooltipMakerAPI.beginTable:(F)V", entry))
