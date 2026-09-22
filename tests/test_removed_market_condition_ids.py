"""Real case, 2026-09-22: Thule-Legacy's TLHeimdallSystem.java references Conditions.MILITARY_BASE
and Conditions.ORBITAL_STATION - both removed when RC8's colony overhaul turned them into
buildable Industries instead (MILITARYBASE/ORBITALSTATION), a different API (addIndustry, not
addCondition). Found auditing ROADMAP P14 item 41; also live in Tore-Up-Plenty's own scripts.
"""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _mod(root: Path) -> Path:
    mod = root / "mod"
    (mod / "data" / "scripts" / "world").mkdir(parents=True)
    (mod / "mod_info.json").write_text(json.dumps({"id": "tl", "name": "TL", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    return mod


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


class RemovedMarketConditionIdTests(unittest.TestCase):
    def test_removed_condition_ids_are_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts" / "world" / "Gen.java").write_text(
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.impl.campaign.ids.Conditions;\n"
                "public class Gen {\n"
                "    void go() {\n"
                "        String[] a = {Conditions.MILITARY_BASE, Conditions.ORBITAL_STATION, Conditions.SPACEPORT};\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        findings = _ids(result, "removed-market-condition-id")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].evidence, ["condition:MILITARY_BASE", "condition:ORBITAL_STATION"])

    def test_only_still_valid_conditions_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts" / "world" / "Gen.java").write_text(
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.impl.campaign.ids.Conditions;\n"
                "public class Gen {\n"
                "    void go() {\n"
                "        String[] a = {Conditions.SPACEPORT, Conditions.POPULATION_3};\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "removed-market-condition-id"), [])

    def test_a_commented_out_reference_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            (mod / "data" / "scripts" / "world" / "Gen.java").write_text(
                "package data.scripts.world;\n"
                "public class Gen {\n"
                "    void go() {\n"
                "        // Conditions.MILITARY_BASE,\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            result = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(result, "removed-market-condition-id"), [])


if __name__ == "__main__":
    unittest.main()
