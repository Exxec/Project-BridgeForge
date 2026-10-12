"""Live run SK13-1b: SEEKER's ART_organicHull kept per-ship state on the shared hull mod instance."""

import json
import shutil
import subprocess
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class(this_name: str, super_name: str, fields: list[tuple[str, str, int]]) -> bytes:
    pool = [_utf8(this_name), b"\x07" + struct.pack(">H", 1), _utf8(super_name), b"\x07" + struct.pack(">H", 3)]
    field_entries = b""
    for name, descriptor, access in fields:
        pool.append(_utf8(name))
        name_index = len(pool)
        pool.append(_utf8(descriptor))
        field_entries += struct.pack(">HHHH", access, name_index, len(pool), 0)
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    body += struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">H", 0)
    body += struct.pack(">H", len(fields)) + field_entries + struct.pack(">HH", 0, 0)
    return body


HULLMOD = "com/fs/starfarer/api/combat/BaseHullMod"


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "hullmod-instance-state"]


class HullmodInstanceStateTests(unittest.TestCase):
    def test_declared_field_with_no_writing_method_is_not_flagged(self) -> None:
        # No method body writes runOnce, so nothing can leak between ships (constructor-only rule, 2026-09-27).
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jars").mkdir()
            (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
            with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
                archive.writestr("data/H.class", _class("data/H", HULLMOD, [("runOnce", "Z", 0x0002), ("ID", "Ljava/lang/String;", 0x0018)]))
            self.assertEqual(_findings(root), [])

    @unittest.skipUnless(shutil.which("javac"), "needs javac")
    def test_only_fields_written_outside_constructors_are_flagged(self) -> None:
        # RogueSynth (2026-09-27): RS_BaseVariantHullmod's 11 fields were set only in constructors; a real
        # per-ship timer is written in advanceInCombat, and a subclass writing an inherited field counts too.
        sources = {
            "com/fs/starfarer/api/combat/BaseHullMod.java": "package com.fs.starfarer.api.combat; public class BaseHullMod { public void advanceInCombat(Object ship, float amount) {} }",
            "data/Configured.java": "package data; public class Configured extends com.fs.starfarer.api.combat.BaseHullMod { protected String flavourText; protected int rarity; public Configured() { flavourText = \"x\"; rarity = 2; } }",
            "data/Timed.java": "package data; public class Timed extends com.fs.starfarer.api.combat.BaseHullMod { private float timer; public void advanceInCombat(Object ship, float amount) { timer += amount; } }",
            "data/Base.java": "package data; public class Base extends com.fs.starfarer.api.combat.BaseHullMod { protected boolean runOnce; }",
            "data/Child.java": "package data; public class Child extends Base { public void advanceInCombat(Object ship, float amount) { runOnce = true; } }",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            src, out = root / "src-build", root / "classes"
            for relative, text in sources.items():
                (src / relative).parent.mkdir(parents=True, exist_ok=True)
                (src / relative).write_text(text, encoding="utf-8")
            out.mkdir()
            subprocess.run(["javac", "-d", str(out), *[str(src / r) for r in sources]], check=True, capture_output=True)
            (root / "jars").mkdir()
            (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
            with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
                for name in ("Configured", "Timed", "Base", "Child"):
                    archive.write(out / "data" / f"{name}.class", f"data/{name}.class")
            shutil.rmtree(src)
            flagged = {f.file.split("!")[1]: f.evidence for f in _findings(root)}
        self.assertEqual(flagged, {"data/Timed.class": ["field:timer"], "data/Base.class": ["field:runOnce"]})

    def test_source_hullmod_fields_but_not_locals(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            src = root / "src" / "H.java"
            src.parent.mkdir(parents=True)
            src.write_text(
                "public class H extends BaseHullMod {\n"
                "    private float healTime = 0f;\n"
                "    private static final String ID = \"x\";\n"
                "    private float RANGE_BONUS = 5f;\n"                         # constant by convention
                "    private Map<ShipAPI, Float> perShip = new HashMap<>();\n"  # per-ship keyed cache
                "    public static float SHARED = 0f;\n"
                "    public void advanceInCombat(ShipAPI ship, float amount) {\n"
                "        float local = 1f;\n"
                "        healTime += amount;\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["field:healTime"]])

    def test_only_written_value_fields_count_but_arrays_and_public_fields_stay(self) -> None:
        # 2026-09-30: a private float set only at its declaration is a constant (Tahlan's runOnce, commented-out
        # code in AI War); an array changes through its contents (KT_Biter's skull[0]); a public field can be
        # written from another class (More Planetary Conditions' hybridMult).
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            src = root / "src" / "H.java"
            src.parent.mkdir(parents=True)
            src.write_text(
                "public class H extends BaseHullMod {\n"
                "    private float alpha = 0.5f;\n"
                "    private Seg[] skull = new Seg[1];\n"
                "    public float hybridMult = 0f;\n"
                "    public void advanceInCombat(ShipAPI ship, float amount) {\n"
                "        ship.setExtraAlphaMult(alpha);\n"
                "        Seg.setup(skull, ship);\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["field:hybridMult", "field:skull"]])


if __name__ == "__main__":
    unittest.main()
