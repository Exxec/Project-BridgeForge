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

    def test_a_crlf_file_with_a_doc_comment_gets_one_guard_after_the_declaration(self) -> None:
        # Scy Nation's SCY_outposts (2026-09-30): CRLF and a class doc comment put the guard inside the comment, five times.
        source = GEN.replace("public class Gen {", "/**\n * @author someone\n */\npublic class Gen {").replace("\n", "\r\n")
        with resolved_temp_dir() as root:
            _mod(root, source)
            path = root / "data" / "scripts" / "world" / "Gen.java"
            for _ in range(2):  # revive runs a fixer once per round
                try:
                    plan = compute_fix(root, "hard-coded-campaign-system-reference", {})
                except FixerError:
                    break
                for change in plan.changes:
                    change.path.write_bytes(change.after)
            lines = path.read_bytes().decode().split("\r\n")
        at = next(i for i, line in enumerate(lines) if 'getStarSystem("Arcadia")' in line)
        self.assertIn("if (system == null) { // BridgeForge", lines[at + 1])
        self.assertEqual(sum("if (system == null)" in line for line in lines), 1)

    def test_a_jar_source_is_left_for_patch_jar_class(self) -> None:
        with resolved_temp_dir() as root:
            (root / "src" / "data" / "scripts" / "world").mkdir(parents=True)
            (root / "src" / "data" / "scripts" / "world" / "Gen.java").write_bytes(GEN.encode())
            (root / "mod_info.json").write_text('{"id":"m","name":"m","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
            with self.assertRaises(FixerError):
                compute_fix(root, "hard-coded-campaign-system-reference", {})

    def test_a_lookup_inside_a_loop_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root, IN_LOOP)
            with self.assertRaises(FixerError):
                compute_fix(root, "hard-coded-campaign-system-reference", {})


if __name__ == "__main__":
    unittest.main()
