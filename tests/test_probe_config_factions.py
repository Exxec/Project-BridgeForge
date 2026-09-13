"""Live run EX-7: the probe never checked Exigency's market-less faction, so 0 fleets went unreported."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.probe_config import build_probe_config


def _mod(root: Path) -> Path:
    (root / "mod_info.json").write_text(json.dumps({"id": "fixture_mod"}), encoding="utf-8")
    factions = root / "data" / "world" / "factions"
    factions.mkdir(parents=True)
    # Starsector's lenient JSON: '#' comments and trailing commas (Exigency's files have both).
    (factions / "exigency.faction").write_text('{\n\t"id":"exigency", # corp\n\t"color":[0,0,200,255],\n}\n', encoding="utf-8")
    (factions / "contact.faction").write_text('{"id":"mysterious_contact"}', encoding="utf-8")
    (factions / "broken.faction").write_text("{not json", encoding="utf-8")
    (factions / "factions.csv").write_text("faction\ndata/world/factions/exigency.faction\n", encoding="utf-8")
    return root


class ProbeConfigFactionTests(unittest.TestCase):
    def test_config_lists_the_mods_own_faction_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = build_probe_config(_mod(Path(directory)))
        self.assertEqual(config["factions"], ["exigency", "mysterious_contact"])

    def test_mod_without_factions_gets_an_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fixture_mod"}), encoding="utf-8")
            self.assertEqual(build_probe_config(root)["factions"], [])


if __name__ == "__main__":
    unittest.main()
