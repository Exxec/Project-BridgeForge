"""PRB-2 (2026-09-13): save-content reported 50+ false "missing" ids on a healthy Exigency save."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.save_content_compat import check_save_content
from bridgeforge.save_reader import campaign_xml_path

SAVE_XML = """<CampaignEngine>
  <factionManager><relations><e><st>fx_hegemony</st><st>fx_pirates</st></e></relations></factionManager>
  <markets><Market><knownFighters><st>fx_bomber_wing</st><st>fx_gone_wing</st></knownFighters></Market></markets>
  <scripts><FleetManager><memory><st>fx_runtime_market</st></memory></FleetManager></scripts>
</CampaignEngine>
"""


def _mod(root: Path) -> Path:
    (root / "data" / "hulls").mkdir(parents=True)
    (root / "data" / "world" / "factions").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
    (root / "data" / "hulls" / "wing_data.csv").write_text("id,variant\nfx_bomber_wing,fx_bomber_Standard\n", encoding="utf-8")
    (root / "data" / "world" / "factions" / "fx.faction").write_text('{"id":"fx"}', encoding="utf-8")
    return root


def _save(root: Path) -> Path:
    save = root / "save_Test_1"
    save.mkdir()
    (save / "campaign.xml").write_text(SAVE_XML, encoding="utf-8")
    return save


class SaveContentFalsePositiveTests(unittest.TestCase):
    def test_skin_hull_ids_back_known_ships_and_generated_market_variants(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root / "mod")
            skins = mod / "data" / "hulls" / "skins"
            skins.mkdir()
            skin = skins / "skin-file-name.skin"
            skin.write_text(
                '{"baseHullId":"hound","skinHullId":"fx_hound","builtInMods":[livinghull]}',
                encoding="utf-8",
            )
            save = _save(root)
            (save / "campaign.xml").write_text(
                '<CampaignEngine><knownShips><st>fx_hound</st></knownShips>'
                '<market><FMmbr sid="fx_hound_Hull"/></market></CampaignEngine>',
                encoding="utf-8",
            )
            result = check_save_content(save, mod)
            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["missing"], [])
            self.assertEqual(
                {entry["id"]: entry["category"] for entry in result["present"]["ids"]},
                {"fx_hound": "hull", "fx_hound_Hull": "generated_variant"},
            )
            skin.unlink()
            self.assertEqual(
                {entry["id"] for entry in check_save_content(save, mod)["missing"]},
                {"fx_hound", "fx_hound_Hull"},
            )

    def test_generated_market_variant_uses_its_existing_base_hull(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root / "mod")
            (mod / "data" / "hulls" / "fx_frigate.ship").write_text('{"hullId":"fx_frigate"}', encoding="utf-8")
            save = _save(root)
            (save / "campaign.xml").write_text(
                '<CampaignEngine><market><FMmbr sid="fx_frigate_Hull"/></market></CampaignEngine>',
                encoding="utf-8",
            )
            result = check_save_content(save, mod)
            self.assertEqual(result["status"], "LOADS")
            self.assertEqual(result["missing"], [])
            self.assertEqual(result["present"]["ids"][0]["category"], "generated_variant")
            (mod / "data" / "hulls" / "fx_frigate.ship").unlink()
            self.assertEqual(check_save_content(save, mod)["status"], "WILL_FAIL")

    def test_only_a_genuinely_missing_wing_in_a_known_list_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = check_save_content(_save(root), _mod(root / "mod"))
            self.assertEqual([entry["id"] for entry in result["missing"]], ["fx_gone_wing"])
            self.assertEqual(result["status"], "WILL_FAIL")
            present = {entry["id"]: entry["category"] for entry in result["present"]["ids"]}
            self.assertEqual(present.get("fx_bomber_wing"), "wing")  # wing ids come from wing_data.csv
            unattributed = [entry["id"] for entry in result["unattributed_prefix_matches"]]
            self.assertEqual(unattributed, ["fx_runtime_market"])  # reported, not a load failure
            all_reported = [e["id"] for e in result["missing"]] + unattributed
            self.assertNotIn("fx_hegemony", all_reported)  # faction relation keys are skipped entirely

    def test_runtime_and_relation_strings_alone_do_not_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save = _save(root)
            (save / "campaign.xml").write_text(SAVE_XML.replace("<st>fx_gone_wing</st>", ""), encoding="utf-8")
            self.assertEqual(check_save_content(save, _mod(root / "mod"))["status"], "LOADS")


class CampaignXmlPathTests(unittest.TestCase):
    def test_explicit_bak_file_is_used_as_given(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save = _save(Path(directory).resolve())
            (save / "campaign.xml.bak").write_text("<CampaignEngine/>", encoding="utf-8")
            self.assertEqual(campaign_xml_path(save / "campaign.xml.bak"), save / "campaign.xml.bak")
            self.assertEqual(campaign_xml_path(save), save / "campaign.xml")
            self.assertEqual(campaign_xml_path(save / "descriptor.xml" if (save / "descriptor.xml").exists() else save), save / "campaign.xml")


if __name__ == "__main__":
    unittest.main()
