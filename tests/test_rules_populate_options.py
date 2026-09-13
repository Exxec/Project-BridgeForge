"""Live report VAC-DIALOG-01: Vacuum's bounty board left the player stuck in the station dialog."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod


def _mod(root: Path, rules_text: str) -> Path:
    (root / "data" / "campaign").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
    (root / "data" / "campaign" / "rules.csv").write_text(rules_text, encoding="utf-8")
    return root


HEADER = "id,trigger,conditions,script,text,options,notes\n"


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "rules-firebest-populate-options"]


class RulesFireBestPopulateOptionsTests(unittest.TestCase):
    def test_firebest_populate_options_is_flagged_with_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rules = HEADER + 'fxTakeBounty,DialogOptionSelected,$option == fxTakeBounty,"FxTakeBounty\nFireBest PopulateOptions",,,\n'
            findings = _findings(_mod(Path(directory), rules))
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].evidence, ["line:3"])
            self.assertEqual(findings[0].classification, "MANUAL")

    def test_fireall_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            rules = HEADER + 'fxTakeBounty,DialogOptionSelected,$option == fxTakeBounty,"FxTakeBounty\nFireAll PopulateOptions",,,\n'
            self.assertEqual(_findings(_mod(Path(directory), rules)), [])


if __name__ == "__main__":
    unittest.main()
