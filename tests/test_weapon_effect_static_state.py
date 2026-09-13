"""Live run SK13-1: SEEKER's ART_thrusterRotation kept `static ShipAPI ship` in a per-weapon plugin."""

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import _parse_class_file, scan_mod


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class_with_field(this_name: str, interface: str, field_name: str, descriptor: str, access: int) -> bytes:
    """A minimal class file: one interface, one field, no methods."""
    pool = [
        _utf8(this_name), b"\x07" + struct.pack(">H", 1),          # 1, 2: this
        _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3),  # 3, 4: super
        _utf8(interface), b"\x07" + struct.pack(">H", 5),          # 5, 6: interface
        _utf8(field_name), _utf8(descriptor),                       # 7, 8: field
    ]
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    body += struct.pack(">HHH", 0x0021, 2, 4)                       # access, this, super
    body += struct.pack(">HH", 1, 6)                                # interfaces
    body += struct.pack(">HHHHH", 1, access, 7, 8, 0)               # one field, no attributes
    body += struct.pack(">HH", 0, 0)                                # no methods, no attributes
    return body


WEAPON_IFACE = "com/fs/starfarer/api/combat/EveryFrameWeaponEffectPlugin"
SHIP = "Lcom/fs/starfarer/api/combat/ShipAPI;"


def _mod_with_jar(root: Path, classes: dict[str, bytes]) -> Path:
    (root / "jars").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
    with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)
    return root


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "weapon-effect-static-combat-state"]


class ClassFileFieldParsingTests(unittest.TestCase):
    def test_parser_reports_interfaces_and_static_fields(self) -> None:
        info = _parse_class_file(_class_with_field("data/W", WEAPON_IFACE, "ship", SHIP, 0x0008 | 0x0002))
        self.assertIsNotNone(info)
        self.assertEqual(info.interfaces, [WEAPON_IFACE])
        self.assertEqual(info.super_class, "java/lang/Object")
        self.assertEqual(info.fields, [("ship", SHIP, True, False)])


class WeaponEffectStaticStateTests(unittest.TestCase):
    def test_static_ship_in_weapon_plugin_jar_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod_with_jar(Path(directory), {"data/scripts/weapons/W.class": _class_with_field("data/scripts/weapons/W", WEAPON_IFACE, "ship", SHIP, 0x0008 | 0x0002)})
            findings = _findings(root)
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].evidence, ["static:ship:ShipAPI"])
            self.assertEqual(findings[0].classification, "MANUAL")

    def test_instance_field_or_unrelated_class_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod_with_jar(Path(directory), {
                "data/A.class": _class_with_field("data/A", WEAPON_IFACE, "ship", SHIP, 0x0002),  # instance field
                "data/B.class": _class_with_field("data/B", "java/lang/Runnable", "ship", SHIP, 0x0008),  # not a weapon plugin
            })
            self.assertEqual(_findings(root), [])

    def test_source_static_ship_in_weapon_plugin_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            src = root / "src" / "data" / "W.java"
            src.parent.mkdir(parents=True)
            src.write_text(
                "public class W implements EveryFrameWeaponEffectPlugin {\n"
                "  private static ShipAPI ship;\n"
                "  // private static WeaponAPI commented;\n"
                "  private static final String ID = \"x\";\n"
                "}\n",
                encoding="utf-8",
            )
            evidence = [f.evidence for f in _findings(root)]
            self.assertEqual(evidence, [["static:ship:ShipAPI"]])


if __name__ == "__main__":
    unittest.main()
