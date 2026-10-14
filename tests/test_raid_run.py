"""ROADMAP item 73 G6: the raid scenario mod's source, install, config and log reading (the game itself is not run here)."""
from __future__ import annotations

import json
import unittest

from bridgeforge.raid_run import (
    RAID_CLASSES, RAID_MOD_ID, RAID_SOURCE, check_raid_log, install_raid_mod, nexerelin_jar, parse_raid_log, raid_config,
)
from tests.support import resolved_temp_dir

START = "12 [main] INFO  data.scripts.bfraid.BfRaidScript  - BF-RAID|raid-start|attacker=hegemony|from=chicomoztoc|target=exi_avesta|targetFaction=exipirated|fp=120.0|ended=false"
END = "99 [main] INFO  data.scripts.bfraid.BfRaidScript  - BF-RAID|raid-end|outcome=SUCCESS|days=31.5"


def _rig(base, enabled):
    rig = base / "rig"
    (rig / "mods").mkdir(parents=True)
    (rig / "starsector-core").mkdir()
    (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": enabled}), encoding="utf-8")
    return rig


class RaidSourceTests(unittest.TestCase):
    def test_the_mod_depends_on_nexerelin_and_ships_inert(self) -> None:
        info = json.loads((RAID_SOURCE / "mod_info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["id"], RAID_MOD_ID)
        self.assertIn("nexerelin", [d["id"] for d in info["dependencies"]])
        config = (RAID_SOURCE / "data" / "config" / "bf_raid.json").read_text(encoding="utf-8")
        self.assertIn('"targetMarket":""', config)

    def test_every_script_class_has_its_source_and_only_the_raid_script_uses_nexerelin(self) -> None:
        root = RAID_SOURCE / "data" / "scripts" / "bfraid"
        for name in RAID_CLASSES:
            self.assertTrue((root / (name.rsplit(".", 1)[1] + ".java")).is_file(), name)
        users = [p.name for p in root.glob("*.java") if "exerelin." in p.read_text(encoding="utf-8")]
        self.assertEqual(users, ["BfRaidScript.java"])


class RaidLogTests(unittest.TestCase):
    def test_a_started_and_ended_raid_is_observed(self) -> None:
        verdict, reason = check_raid_log(parse_raid_log(f"noise\n{START}\n{END}\n"))
        self.assertEqual(verdict, "RAID_OBSERVED")
        self.assertIn("exi_avesta", reason)
        self.assertIn("SUCCESS", reason)

    def test_a_start_with_no_end_is_only_started(self) -> None:
        self.assertEqual(check_raid_log(parse_raid_log(START))[0], "RAID_STARTED")
        timeout = "BF-RAID|raid-timeout|days=120.0|outcome=null"
        self.assertEqual(check_raid_log(parse_raid_log(f"{START}\n{timeout}"))[0], "RAID_STARTED")

    def test_idle_error_and_empty_logs_never_count_as_a_raid(self) -> None:
        verdict, reason = check_raid_log(parse_raid_log("BF-RAID|idle|no targetMarket in data/config/bf_raid.json"))
        self.assertEqual(verdict, "RAID_NOT_STARTED")
        self.assertIn("targetMarket", reason)
        verdict, reason = check_raid_log(parse_raid_log("BF-RAID|error|target market not found: zzz"))
        self.assertEqual((verdict, "not found" in reason), ("RAID_NOT_STARTED", True))
        self.assertEqual(check_raid_log([])[0], "RAID_NOT_STARTED")


class RaidInstallTests(unittest.TestCase):
    def test_config_needs_a_target_and_a_source(self) -> None:
        with self.assertRaises(ValueError):
            raid_config("")
        with self.assertRaises(ValueError):
            raid_config("m1")
        self.assertEqual(raid_config("m1", attacker_faction="hegemony")["targetMarket"], "m1")

    def test_install_copies_the_mod_writes_the_config_and_enables_it(self) -> None:
        with resolved_temp_dir() as base:
            rig = _rig(base, ["nexerelin"])
            target = install_raid_mod(rig, "exi_avesta", attacker_faction="hegemony", fleet_points=200)
            written = json.loads((target / "data" / "config" / "bf_raid.json").read_text(encoding="utf-8"))
            self.assertEqual((written["targetMarket"], written["attackerFaction"], written["fleetPoints"]), ("exi_avesta", "hegemony", 200))
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            self.assertEqual(enabled, ["nexerelin", RAID_MOD_ID])
            install_raid_mod(rig, "exi_avesta", attacker_faction="hegemony")  # reinstall does not duplicate
            self.assertEqual(json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"].count(RAID_MOD_ID), 1)

    def test_install_refuses_without_nexerelin_or_a_rig(self) -> None:
        with resolved_temp_dir() as base:
            with self.assertRaises(ValueError):
                install_raid_mod(base, "m1", attacker_faction="hegemony")
            with self.assertRaises(ValueError):
                install_raid_mod(_rig(base, ["other"]), "m1", attacker_faction="hegemony")

    def test_nexerelin_jar_is_found_under_a_mods_folder(self) -> None:
        with resolved_temp_dir() as base:
            self.assertIsNone(nexerelin_jar(base))
            jar = base / "Nexerelin-0.12.2d" / "jars" / "ExerelinCore.jar"
            jar.parent.mkdir(parents=True)
            jar.write_bytes(b"")
            self.assertEqual(nexerelin_jar(base), jar)


if __name__ == "__main__":
    unittest.main()
