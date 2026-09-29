"""Checks from the 2026-09-28 live runs: skill-unregistered, csv-slash-quote-escape."""
from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.fixers import apply_fix, compute_fix
from bridgeforge.scanner import scan_mod


def _mod(root: Path) -> Path:
    mod = root / "mod"
    mod.mkdir()
    (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "M", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    return mod


def _core(root: Path) -> Path:
    """A minimal RC8-like core: safety_procedures ships a .skill file but is commented out of skill_data.csv."""
    skills = root / "core" / "data" / "characters" / "skills"
    skills.mkdir(parents=True)
    (skills / "skill_data.csv").write_text("id,name\ncontainment_procedures,Containment\n#safety_procedures,Safety\n", encoding="utf-8")
    (skills / "safety_procedures.skill").write_text("{}", encoding="utf-8")
    (skills / "containment_procedures.skill").write_text("{}", encoding="utf-8")
    return root / "core"


def _ids(result, finding_id):
    return [f for f in result.findings if f.id == finding_id]


class SkillUnregisteredTests(unittest.TestCase):
    def test_setting_a_commented_out_skill_is_flagged_and_its_successor_is_not(self) -> None:
        # FlowerGod FG_PersonBountyEvent (FG-SOLO2-20260928): setSkillLevel("safety_procedures", 3) was a Fatal.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, core = _mod(root), _core(root)
            source = mod / "data" / "scripts" / "Bounty.java"
            source.parent.mkdir(parents=True)
            source.write_text('class B { void f(P p) { p.getStats().setSkillLevel("safety_procedures", 3f); } }\n', encoding="utf-8")
            bad = _ids(scan_mod(mod, vanilla_core=core), "skill-unregistered")
            source.write_text('class B { void f(P p) { p.getStats().setSkillLevel("containment_procedures", 1f);'
                              ' float x = p.getStats().getSkillLevel("safety_procedures"); } }\n', encoding="utf-8")
            fixed = _ids(scan_mod(mod, vanilla_core=core), "skill-unregistered")
        self.assertEqual(len(bad), 1)
        self.assertIn("safety_procedures", bad[0].evidence[0])
        self.assertEqual(fixed, [])


class CsvSlashQuoteEscapeTests(unittest.TestCase):
    def test_slash_quotes_are_found_and_fixed_to_doubled_quotes(self) -> None:
        # SEEKER 0.6.6 special_items.csv: /"brute force/" split the row; the probe read a fragment as item "0".
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            path = mod / "data" / "campaign" / "special_items.csv"
            path.parent.mkdir(parents=True)
            path.write_text('name,id,desc\nCaps,skr_caps,"used a /"brute force/" approach.\n\nMore text.",x\n', encoding="utf-8")
            before = _ids(scan_mod(mod), "csv-slash-quote-escape")
            apply_fix(compute_fix(mod, "csv-slash-quote-escape"))
            text = path.read_text(encoding="utf-8")
            after = _ids(scan_mod(mod), "csv-slash-quote-escape")
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(before), 1)
        self.assertEqual(after, [])
        self.assertEqual([r["id"] for r in rows], ["skr_caps"])
        self.assertIn('a "brute force" approach', rows[0]["desc"])


if __name__ == "__main__":
    unittest.main()
