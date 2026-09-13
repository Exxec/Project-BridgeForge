"""Live run EX-7 (EXI-FLEET-01): Exigency built fleets from a bare createMarket() source, so every fleet was empty."""

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod

FACTORY = "com/fs/starfarer/api/impl/campaign/fleets/FleetFactoryV3"


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class(this_name: str, *, calls_factory: bool, strings: tuple[str, ...] = ()) -> bytes:
    pool = [_utf8(this_name), b"\x07" + struct.pack(">H", 1), _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3)]
    if calls_factory:
        pool += [_utf8(FACTORY), b"\x07" + struct.pack(">H", len(pool) + 1), _utf8("createMarket"), _utf8("createFleet")]
    for value in strings:
        pool.append(_utf8(value))
        pool.append(b"\x08" + struct.pack(">H", len(pool)))
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    return body + struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">HHHH", 0, 0, 0, 0)


def _mod(root: Path, classes: dict[str, bytes]) -> Path:
    (root / "jars").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
    with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)
    return root


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "fleet-source-bare-market"]


class BareMarketFleetSourceTests(unittest.TestCase):
    def test_bare_market_fleet_manager_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory), {"data/M.class": _class("data/M", calls_factory=True)})
            findings = _findings(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].evidence, ["jars/fx.jar!data/M.class"])
        self.assertEqual(findings[0].classification, "REVIEW")

    def test_mod_that_sets_the_fleet_size_multiplier_is_clean(self) -> None:
        # Exigency r2: the shared FleetParams adapter gives bare markets vanilla's fallback multiplier.
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory), {
                "data/M.class": _class("data/M", calls_factory=True),
                "data/Compat.class": _class("data/Compat", calls_factory=False, strings=("combat_fleet_size_mult",)),
            })
            self.assertEqual(_findings(root), [])

    def test_fix_only_in_source_does_not_clear_an_unrebuilt_jar(self) -> None:
        # Found sweeping Exigency: the adapter source was fixed before EXI.jar was patched, and the
        # first version of this check wrongly reported the mod clean. The game runs the jar.
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory), {"data/M.class": _class("data/M", calls_factory=True)})
            (root / "src").mkdir()
            (root / "src" / "Compat.java").write_text(
                "class Compat { void f(MarketAPI m) { m.getStats().getDynamic().getMod(Stats.COMBAT_FLEET_SIZE_MULT).modifyFlat(\"x\", 1f); } }\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["jars/fx.jar!data/M.class"]])

    def test_source_bare_market_is_flagged_and_comments_do_not_count_as_mitigation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "M.java").write_text(
                "class M { void f() {\n"
                "  MarketAPI m = Global.getFactory().createMarket(\"a\", \"b\", 4);\n"
                "  // TODO COMBAT_FLEET_SIZE_MULT\n"
                "  CampaignFleetAPI fleet = FleetFactoryV3.createFleet(params);\n"
                "} }\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["src/M.java"]])


if __name__ == "__main__":
    unittest.main()
