"""Offline save fingerprint (ROADMAP-3 item 79.2): hash parity with the probe's Java, the canonical text, compare and refusals."""
from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path

from bridgeforge import cli
from bridgeforge.save_fingerprint import SECTIONS
from bridgeforge.save_fingerprint_offline import (FingerprintError, compare_fingerprints, compare_with_file, fnv64, hundredths,
                                                  offline_fingerprint)
from tests.support import resolved_temp_dir

DESCRIPTOR = '<?xml version="1.0" ?>\n<SaveGameData z="1">\n<characterName>T</characterName>\n<gameVersion>0.98a-RC8</gameVersion>\n</SaveGameData>\n'
ECONOMY = '<economy z="10">\n<econ z="11">\n<markets z="12">\n<Market ref="20"></Market>\n</markets>\n</econ>\n</economy>\n'
MARKET = """<planet>
<market cl="Market" z="20">
<id>alpha_market</id>
<size>{size}</size>
<factionId>hegemony</factionId>
<submarkets z="21">
<Submarket z="22" s="open_market"></Submarket>
<Submarket z="23" s="black_market"></Submarket>
</submarkets>
<industries z="24">
<Spaceport z="25" id="spaceport"></Spaceport>
<Mining z="26" id="mining"></Mining>
</industries>
<conditions z="27">
<MCon z="28" i="ore_sparse" u="1" s="true"></MCon>
<MCon z="29" i="arid" u="2" s="true"></MCon>
</conditions>
</market>
</planet>
<market cl="PCMarket" z="900"><id>market_pcm</id><isPlanetConditionMarketOnly>true</isPlanetConditionMarketOnly></market>
"""
PLAYER = """<Flt z="500">
<fD z="501">
<cargo z="502" uS="true" mC="80.0" sU="80.0" mF="35.0" mP="60.0" fT="false">
<s z="503">
<CIStack z="504" rS="false" s="50.0" mS="1.0" cSPU="0.0" t="RESOURCES">
<d cl="st">crew</d>
</CIStack>
<CIStack z="505" rS="false" s="55.5" mS="1.0" cSPU="1.0" t="RESOURCES">
<d cl="st">supplies</d>
</CIStack>
<CIStack z="506" rS="false" s="25.0" mS="1.0" cSPU="0.0" t="RESOURCES">
<d cl="st">fuel</d>
</CIStack>
</s>
</cargo>
</fD>
</Flt>
<playerFleet ref="500"></playerFleet>
"""
# Expected canonical text, written out by hand from FingerprintSections.java.
MARKETS_TEXT = "alpha_market;faction=hegemony;size=5;cond=arid,ore_sparse;ind=mining,spaceport;sub=black_market,open_market"
CARGO_TEXT = "mC=8000;mF=3500;mP=6000;spaceUsed=8000;fuel=2500;crew=50;supplies=5550"


def _save(root: Path, name: str = "save_T_1", size: int = 5, with_player: bool = True) -> Path:
    save = root / name
    save.mkdir(parents=True)
    (save / "descriptor.xml").write_text(DESCRIPTOR, encoding="utf-8")
    body = ECONOMY + MARKET.format(size=size) + (PLAYER if with_player else "")
    (save / "campaign.xml").write_text('<?xml version="1.0" ?>\n<CampaignEngine z="1">\n' + body + "</CampaignEngine>\n", encoding="utf-8")
    return save


class HashParityTests(unittest.TestCase):
    def test_fnv64_matches_the_probes_java_on_fixed_strings(self) -> None:
        # Expected values printed by FingerprintSections.fnv64's body compiled and run with the rig JDK (jdk-25.0.4.1+1).
        expected = {
            "": "cbf29ce484222325",
            "a": "089be207b544f1e4",
            "abc": "cec64e155111225d",
            "ancyra_market;faction=hegemony;size=5;cond=arid,hot;ind=a,b;sub=open_market": "0e1ffd0d0f7a590c",
            "café\n中文 \U0001F680": "b5b2ab4e8797580a",
        }
        for text, digest in expected.items():
            self.assertEqual(fnv64(text), digest, text)

    def test_hundredths_matches_java_math_round_of_a_float(self) -> None:
        # Java: Math.round(v * 100f) printed by the same JDK run.
        for value, java in ((0.7, "70"), (1.005, "101"), (2.675, "268"), (617.61957, "61762"), (0.285, "29"),
                            (1234.565, "123456"), (0.125, "13"), (-0.005, "0")):
            self.assertEqual(hundredths(value), java, value)


class OfflineFingerprintTests(unittest.TestCase):
    def test_markets_and_cargo_match_the_hand_written_canonical_text(self) -> None:
        with resolved_temp_dir() as root:
            result = offline_fingerprint(_save(root))
        self.assertEqual(result["sections"]["markets"]["fnv"], fnv64(MARKETS_TEXT))
        self.assertEqual(result["sections"]["markets"]["count"], 1, "the condition-only PCMarket is not in the economy list")
        self.assertEqual(result["sections"]["cargo"]["fnv"], fnv64(CARGO_TEXT))

    def test_other_sections_are_explicitly_not_comparable_with_a_reason(self) -> None:
        with resolved_temp_dir() as root:
            result = offline_fingerprint(_save(root))
        self.assertEqual(list(result["sections"]), list(SECTIONS))
        for name in ("systems", "rings", "fleets", "player", "mod", "totals"):
            row = result["sections"][name]
            self.assertFalse(row["comparable"])
            self.assertTrue(row["reason"])
            self.assertNotIn("fnv", row)

    def test_missing_player_fleet_makes_cargo_not_comparable(self) -> None:
        with resolved_temp_dir() as root:
            result = offline_fingerprint(_save(root, with_player=False))
        self.assertFalse(result["sections"]["cargo"]["comparable"])

    def test_compare_two_saves_names_the_changed_section(self) -> None:
        with resolved_temp_dir() as root:
            before, after = offline_fingerprint(_save(root, "a")), offline_fingerprint(_save(root, "b", size=6))
        compared = compare_fingerprints(before, after)
        self.assertEqual((compared["markets"], compared["cargo"], compared["systems"]), ("differ", "equal", "not-comparable"))

    def test_compare_with_a_probe_log_uses_the_after_digests(self) -> None:
        with resolved_temp_dir() as root:
            result = offline_fingerprint(_save(root))
            line = "BF-PROBE|0.2.28|fingerprint|INFO|phase=after|section={};count=1;len=1;fnv={}"
            log = root / "probe.log"
            log.write_text("\n".join([line.format("markets", fnv64(MARKETS_TEXT)), line.format("cargo", "0" * 16),
                                      line.format("systems", "1" * 16)]), encoding="utf-8")
            compared = compare_with_file(result, log)
            (root / "off.json").write_text(json.dumps(result), encoding="utf-8")
            same = compare_with_file(result, root / "off.json")
            (root / "bad.txt").write_text("nothing here", encoding="utf-8")
            with self.assertRaises(FingerprintError):
                compare_with_file(result, root / "bad.txt")
        self.assertEqual((compared["markets"], compared["cargo"], compared["systems"]), ("equal", "differ", "not-comparable"))
        self.assertEqual((same["markets"], same["cargo"], same["totals"]), ("equal", "equal", "not-comparable"))

    def test_refuses_folders_that_are_not_saves(self) -> None:
        with resolved_temp_dir() as root:
            (root / "empty").mkdir()
            with self.assertRaises(FingerprintError):
                offline_fingerprint(root / "empty")
            fake = _save(root, "fake")
            (fake / "campaign.xml").write_text("<html>not a save</html>", encoding="utf-8")
            with self.assertRaises(FingerprintError):
                offline_fingerprint(fake)

    def test_cli_json_and_compare_exit_code(self) -> None:
        with resolved_temp_dir() as root:
            a, b = _save(root, "a"), _save(root, "b", size=6)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["save-fingerprint", str(a), "--json"]), 0)
            (root / "a.json").write_text(out.getvalue(), encoding="utf-8")
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                code = cli.main(["save-fingerprint", str(b), "--compare", str(root / "a.json")])
        self.assertEqual(code, 1)
        self.assertIn("markets  differ", text.getvalue())
        self.assertIn("cargo    equal", text.getvalue())


if __name__ == "__main__":
    unittest.main()
