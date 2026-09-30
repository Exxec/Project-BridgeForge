"""The campaign lookup guard fixer (2026-09-30): hard-coded-campaign-system-reference / -entity-reference."""
from __future__ import annotations

import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, compute_fix
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

GEN = """package data.scripts.world;

import com.fs.starfarer.api.campaign.*;

public class Gen {
    public void generate(SectorAPI sector) {
        StarSystemAPI system = sector.getStarSystem("Arcadia");
        SectorEntityToken nomios = system.getEntityById("nomios");
        nomios.getName();
    }
}
"""
IN_LOOP = """package data.scripts.world;

import com.fs.starfarer.api.campaign.*;

public class Gen {
    public void generate(SectorAPI sector) {
        for (int i = 0; i < 2; i++) {
            StarSystemAPI system = sector.getStarSystem("Arcadia");
            system.getName();
        }
    }
}
"""


def _mod(root: Path, source: str) -> Path:
    (root / "data" / "scripts" / "world").mkdir(parents=True)
    (root / "data" / "scripts" / "world" / "Gen.java").write_bytes(source.encode())
    (root / "mod_info.json").write_text('{"id":"m","name":"m","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    return root


class CampaignLookupGuardTests(unittest.TestCase):
    def test_guards_a_declaration_in_a_void_method_and_the_finding_turns_safe(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, GEN)
            for finding_id in ("hard-coded-campaign-system-reference", "hard-coded-campaign-entity-reference"):
                plan = compute_fix(root, finding_id, {})
                for change in plan.changes:
                    change.path.write_bytes(change.after)
            text = (root / "data" / "scripts" / "world" / "Gen.java").read_text(encoding="utf-8")
            after = {f.id: f.classification for f in scan_mod(root).findings if f.id.startswith("hard-coded-campaign-")}
        self.assertIn('if (system == null) { // BridgeForge', text)
        self.assertIn('if (nomios == null) {', text)
        self.assertLess(text.index("system == null"), text.index('getEntityById("nomios")'))
        self.assertEqual(after, {"hard-coded-campaign-system-reference": "SAFE", "hard-coded-campaign-entity-reference": "SAFE"})

    def test_a_lookup_inside_a_loop_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, IN_LOOP)
            with self.assertRaises(FixerError):
                compute_fix(root, "hard-coded-campaign-system-reference", {})


if __name__ == "__main__":
    unittest.main()
