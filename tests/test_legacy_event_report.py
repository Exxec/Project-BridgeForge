"""Live run EX-7b (EXI-EVENT-01): SectorAPI.reportEventStage is a no-op in 0.98a, so its delivery script never runs."""

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod

SECTOR_API = "com/fs/starfarer/api/campaign/SectorAPI"


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class(this_name: str, owner: str, method: str) -> bytes:
    pool = [
        _utf8(this_name), b"\x07" + struct.pack(">H", 1),
        _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3),
        _utf8(owner), b"\x07" + struct.pack(">H", 5),
        _utf8(method),
    ]
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    return body + struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">HHHH", 0, 0, 0, 0)


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "legacy-event-report-noop"]


class LegacyEventReportTests(unittest.TestCase):
    def _jar_mod(self, root: Path, classes: dict[str, bytes]) -> Path:
        (root / "jars").mkdir(parents=True)
        (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
        with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
            for name, data in classes.items():
                archive.writestr(name, data)
        return root

    def test_jar_call_on_sector_api_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._jar_mod(Path(directory), {"data/E.class": _class("data/E", SECTOR_API, "reportEventStage")})
            findings = _findings(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].classification, "MANUAL")

    def test_same_method_name_on_another_class_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self._jar_mod(Path(directory), {"data/E.class": _class("data/E", "data/MyBus", "reportEventStage")})
            self.assertEqual(_findings(root), [])

    def test_source_call_is_flagged_but_comment_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "E.java").write_text(
                "class E { void f() {\n"
                "  // Global.getSector().reportEventStage(this, \"old\", null);\n"
                "  Global.getSector().reportEventStage(this, \"caught\", player, priority, script);\n"
                "} }\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["line:3"]])


if __name__ == "__main__":
    unittest.main()
