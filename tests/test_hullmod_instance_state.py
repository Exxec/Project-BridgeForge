"""Live run SK13-1b: SEEKER's ART_organicHull kept per-ship state on the shared hull mod instance."""

import json
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
    def test_mutable_instance_field_in_jar_hullmod_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "jars").mkdir()
            (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
            with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
                archive.writestr("data/H.class", _class("data/H", HULLMOD, [("runOnce", "Z", 0x0002), ("ID", "Ljava/lang/String;", 0x0018)]))
                archive.writestr("data/Other.class", _class("data/Other", "java/lang/Object", [("runOnce", "Z", 0x0002)]))
            findings = _findings(root)
            self.assertEqual([f.evidence for f in findings], [["field:runOnce"]])
            self.assertEqual(findings[0].classification, "REVIEW")

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
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["field:healTime"]])


if __name__ == "__main__":
    unittest.main()
