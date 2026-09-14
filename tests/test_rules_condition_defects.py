"""Flu-X rules.csv (found 2026-09-13): two greetings with merged condition lines, one testing the wrong faction.

"$faction.id == infected$faction.hostileToPlayer" never matches, so the rule never fires;
"greetinginfectedTOffWeaker" tested "$faction.id == templars" (copied from another mod).
"""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod

RULES = (
    "id,trigger,conditions,script,text,options,notes\n"
    "# comment row,,,,,,\n"
    'greetFine,OpenCommLink,"$faction.id == infected\n$faction.friendlyToPlayer",,"""Hello""",,\n'
    'greetMerged,OpenCommLink,"$faction.id == infected$faction.hostileToPlayer\n$relativeStrength < 0",,"""Die""",,\n'
    'greetWrongFaction,OpenCommLink,"$faction.id == templars\n!$player.transponderOn",,"""Who?""",,\n'
    'greetVanillaFaction,OpenCommLink,"$faction.id == hegemony",,"""Hi""",,\n'
)


def _findings(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


class RulesConditionDefectTests(unittest.TestCase):
    def _mod(self, root: Path) -> Path:
        mod = root / "mod"
        (mod / "data" / "campaign").mkdir(parents=True)
        (mod / "data" / "world" / "factions").mkdir(parents=True)
        (mod / "mod_info.json").write_text(json.dumps({"id": "fx", "name": "fx", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
        (mod / "data" / "campaign" / "rules.csv").write_text(RULES, encoding="utf-8")
        (mod / "data" / "world" / "factions" / "infected.faction").write_text(json.dumps({"id": "infected"}), encoding="utf-8")
        return mod

    def test_merged_condition_lines_are_reported_without_vanilla(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = scan_mod(self._mod(Path(directory)), TargetProfile())
        merged = _findings(result, "rules-condition-merged-lines")
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0].evidence), 1)
        self.assertIn("rule:greetMerged", merged[0].evidence[0])
        self.assertEqual(_findings(result, "rules-condition-unknown-faction"), [])  # needs vanilla ids

    def test_faction_neither_vanilla_nor_mod_defines_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core" / "data" / "world" / "factions"
            core.mkdir(parents=True)
            (core / "hegemony.faction").write_text(json.dumps({"id": "hegemony"}), encoding="utf-8")
            result = scan_mod(self._mod(root), TargetProfile(), root / "core")
        unknown = _findings(result, "rules-condition-unknown-faction")
        self.assertEqual(len(unknown), 1)
        self.assertEqual(unknown[0].evidence, ["rule:greetWrongFaction -> templars"])


if __name__ == "__main__":
    unittest.main()
