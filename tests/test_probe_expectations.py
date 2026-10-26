"""Probe 0.3.2 inputs: bounty ids from MagicLib's file and entity expectations from the workspace (2026-10-22)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.probe.probe_config import build_probe_config
from bridgeforge.probe.probe_expectations import MAX_BOUNTIES, bounty_ids, entity_checks, expectations_path
from bridgeforge.probe.probe_group import merge_configs
from tests.support import resolved_temp_dir


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _workspace(root: Path, mod_id: str) -> Path:
    working = root / mod_id / "working"
    _write(working / "mod_info.json", json.dumps({"id": mod_id, "name": mod_id, "version": "1"}))
    return working


class ProbeExpectationsTests(unittest.TestCase):
    def test_bounty_ids_come_from_magiclib_file_with_comments_and_are_capped(self) -> None:
        with resolved_temp_dir() as root:
            working = _workspace(root, "seven_nexus")
            _write(working / "data" / "config" / "modFiles" / "magicBounty_data.json",
                   '{\n  # EPTA\n  "Masamune": {"fleet_faction": "pirates",},\n  "Artifact 667": {"fleet_faction": "narcepolis"},\n}\n')
            self.assertEqual(bounty_ids(working), ["Artifact 667", "Masamune"])
            many = "{" + ",".join(f'"b{i:02d}": {{}}' for i in range(MAX_BOUNTIES + 5)) + "}"
            _write(working / "data" / "config" / "modFiles" / "magicBounty_data.json", many)
            self.assertEqual(len(bounty_ids(working)), MAX_BOUNTIES)
            self.assertEqual(bounty_ids(_workspace(root, "none")), [])

    def test_entity_checks_are_read_beside_working_and_validated(self) -> None:
        with resolved_temp_dir() as root:
            working = _workspace(root, "zorg")
            self.assertEqual(entity_checks(working), [])
            self.assertEqual(expectations_path(working), root / "zorg" / "PROBE_EXPECTATIONS.json")
            checks = [{"entity": "zorg_planet_001", "expect": {"discoverable": False, "market_size": 7}},
                      {"custom_entity_spec": "proelefsi_cap", "expect": {"sprite": "graphics/x.png", "sprite_height": 50}}]
            _write(root / "zorg" / "PROBE_EXPECTATIONS.json", json.dumps({"entity_checks": checks}))
            self.assertEqual(entity_checks(working), checks)
            for bad in ({"entity_checks": [{"entity": "p", "expect": {"discoverible": False}}]},
                        {"entity_checks": [{"custom_entity_spec": "s", "expect": {"discoverable": False}}]},
                        {"entity_checks": [{"entity": "p", "expect": {}}]}, {"checks": []}):
                _write(root / "zorg" / "PROBE_EXPECTATIONS.json", json.dumps(bad))
                with self.assertRaises(ValueError):
                    entity_checks(working)

    def test_config_carries_both_and_a_group_merge_keeps_them(self) -> None:
        with resolved_temp_dir() as root:
            epta = _workspace(root, "seven_nexus")
            _write(epta / "data" / "config" / "modFiles" / "magicBounty_data.json", '{"Artifact 667": {}}')
            zorg = _workspace(root, "zorg")
            _write(root / "zorg" / "PROBE_EXPECTATIONS.json",
                   json.dumps({"entity_checks": [{"entity": "zorg_planet_001", "expect": {"discoverable": False}}]}))
            a, b = build_probe_config(epta), build_probe_config(zorg)
            self.assertEqual((a["bounty_checks"], a["entity_checks"]), ({"seven_nexus": ["Artifact 667"]}, []))
            self.assertEqual((b["bounty_checks"], len(b["entity_checks"])), ({}, 1))
            merged = merge_configs([a, b, b])
            self.assertEqual(merged["bounty_checks"], {"seven_nexus": ["Artifact 667"]})
            self.assertEqual(merged["entity_checks"], b["entity_checks"])


if __name__ == "__main__":
    unittest.main()
