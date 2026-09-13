from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.save_content_compat import check_save_content, removal_safety
from tests.save_fixtures import write_mod_data, write_mod_info, write_text

SAVE_HEADER = '<?xml version="1.0" ?>\n<CampaignEngine z="1">\n'
SAVE_FOOTER = "</CampaignEngine>\n"


class CheckSaveContentTests(unittest.TestCase):
    def test_present_ids_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",), hullmods=("samplemod_hullmod",))
            save_dir = Path(directory) / "save"
            xml = (
                SAVE_HEADER
                + "<st>samplemod_hull</st>\n"
                + "<st>samplemod_hullmod</st>\n"
                + SAVE_FOOTER
            )
            write_text(save_dir / "campaign.xml", xml)

            result = check_save_content(save_dir, mod_dir)

            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["present"]["count"], 2)
            categories = {entry["category"] for entry in result["present"]["ids"]}
            self.assertEqual(categories, {"hull", "hullmod"})
            self.assertEqual(result["missing"], [])

    def test_missing_id_by_prefix_is_will_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",))
            save_dir = Path(directory) / "save"
            # samplemod_removedhull shares the mod's "samplemod_" prefix but the build no
            # longer has that hull -- the id-level analogue of a removed class. It sits in a
            # knownShips list, where a save stores real data ids (a prefix match elsewhere is only
            # reported as unattributed; see test_save_content_false_positives.py).
            xml = SAVE_HEADER + "<knownShips><st>samplemod_removedhull</st></knownShips>\n" + SAVE_FOOTER
            write_text(save_dir / "campaign.xml", xml)

            result = check_save_content(save_dir, mod_dir)

            self.assertEqual(result["status"], "WILL_FAIL")
            self.assertEqual(result["missing"][0]["id"], "samplemod_removedhull")

    def test_fleet_member_sid_is_a_variant_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, variants=("samplemod_hull_Standard",))
            save_dir = Path(directory) / "save"
            xml = SAVE_HEADER + '<FMmbr z="2" sid="samplemod_hull_Standard" sN="Ship"></FMmbr>\n' + SAVE_FOOTER
            write_text(save_dir / "campaign.xml", xml)

            result = check_save_content(save_dir, mod_dir)

            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["present"]["ids"][0]["category"], "variant")

    def test_vanilla_ids_never_reported_as_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",))
            vanilla_dir = Path(directory) / "vanilla"
            write_mod_data(vanilla_dir, hulls=("vanilla_hull",))
            save_dir = Path(directory) / "save"
            xml = SAVE_HEADER + "<st>vanilla_hull</st>\n" + SAVE_FOOTER
            write_text(save_dir / "campaign.xml", xml)

            result = check_save_content(save_dir, mod_dir, vanilla_core=vanilla_dir)

            self.assertEqual(result["status"], "UNKNOWN")
            self.assertEqual(result["present"]["count"], 0)
            self.assertEqual(result["missing"], [])

    def test_no_candidate_ids_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",))
            save_dir = Path(directory) / "save"
            write_text(save_dir / "campaign.xml", SAVE_HEADER + "<unrelated>text</unrelated>\n" + SAVE_FOOTER)

            result = check_save_content(save_dir, mod_dir)

            self.assertEqual(result["status"], "UNKNOWN")


class RemovalSafetyTests(unittest.TestCase):
    def test_safe_to_remove_when_nothing_depends_on_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",))
            save_dir = Path(directory) / "save"
            write_text(save_dir / "campaign.xml", SAVE_HEADER + "<unrelated>text</unrelated>\n" + SAVE_FOOTER)

            result = removal_safety(save_dir, mod_dir)

            self.assertEqual(result["status"], "SAFE_TO_REMOVE")
            self.assertEqual(result["reasons"], [])
            self.assertTrue(result["internal_only"])

    def test_unsafe_when_content_id_still_referenced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_data(mod_dir, hulls=("samplemod_hull",))
            save_dir = Path(directory) / "save"
            write_text(save_dir / "campaign.xml", SAVE_HEADER + "<st>samplemod_hull</st>\n" + SAVE_FOOTER)

            result = removal_safety(save_dir, mod_dir)

            self.assertEqual(result["status"], "UNSAFE")
            self.assertTrue(any("content id" in reason for reason in result["reasons"]))

    def test_unsafe_when_memory_key_carries_mod_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            save_dir = Path(directory) / "save"
            xml = SAVE_HEADER + "<key>$samplemod_didThing</key>\n" + SAVE_FOOTER
            write_text(save_dir / "campaign.xml", xml)

            result = removal_safety(save_dir, mod_dir)

            self.assertEqual(result["status"], "UNSAFE")
            self.assertEqual(len(result["memory_keys"]), 1)
            self.assertTrue(any("memory key" in reason for reason in result["reasons"]))


if __name__ == "__main__":
    unittest.main()
