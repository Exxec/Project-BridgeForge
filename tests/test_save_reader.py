from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.save_reader import (
    PeekableElements,
    SaveReadError,
    campaign_xml_path,
    descriptor_xml_path,
    iter_elements,
    parse_build_tag,
    parse_descriptor,
    read_scalar_record,
    resolve_save_dir,
)
from tests.save_fixtures import write_descriptor, write_text


class ResolveSaveTests(unittest.TestCase):
    def test_resolve_save_dir_accepts_dir_or_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            # resolve(): CI temp dirs arrive as 8.3 short paths (RUNNER~1) while the code resolves them.
            save_dir = Path(directory).resolve() / "save_Foo_1"
            write_text(save_dir / "campaign.xml", "<CampaignEngine z=\"1\"></CampaignEngine>\n")
            self.assertEqual(resolve_save_dir(save_dir), save_dir)
            self.assertEqual(resolve_save_dir(save_dir / "campaign.xml"), save_dir)

    def test_missing_save_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SaveReadError):
                resolve_save_dir(Path(directory) / "does_not_exist")

    def test_campaign_and_descriptor_paths_require_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            save_dir.mkdir()
            with self.assertRaises(SaveReadError):
                campaign_xml_path(save_dir)
            with self.assertRaises(SaveReadError):
                descriptor_xml_path(save_dir)


class BuildTagParseTests(unittest.TestCase):
    def test_name_suffix_only(self) -> None:
        result = parse_build_tag("Exigency [BF r3]", "0.7.2")
        self.assertEqual(result, {"name_build": 3, "version_build": None, "build": 3, "tagged": True})

    def test_version_suffix_only(self) -> None:
        result = parse_build_tag("Exigency", "0.7.2+bf.5")
        self.assertEqual(result["version_build"], 5)
        self.assertEqual(result["build"], 5)

    def test_both_suffixes_take_the_higher(self) -> None:
        result = parse_build_tag("Exigency [BF r2]", "0.7.2+bf.4")
        self.assertEqual(result["build"], 4)

    def test_no_suffix_is_untagged(self) -> None:
        result = parse_build_tag("Exigency", "0.7.2")
        self.assertEqual(result, {"name_build": None, "version_build": None, "build": None, "tagged": False})


class ParseDescriptorTests(unittest.TestCase):
    def test_mod_list_with_versions_and_enabled_subset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save_FourthAnderson_1"
            write_descriptor(
                save_dir,
                [
                    {"id": "exigency", "name": "Exigency [BF r3]", "version": "0.7.2", "game_version": "0.98a-RC8"},
                    {"id": "lw_lazylib", "name": "LazyLib", "version": "3.0.0", "game_version": "0.98a-RC5"},
                ],
                character_name="Fourth Anderson",
            )
            result = parse_descriptor(save_dir)

            self.assertEqual(result["character_name"], "Fourth Anderson")
            self.assertEqual(len(result["all_mods_ever_enabled"]), 2)
            self.assertEqual(len(result["enabled_mods"]), 2)
            exigency = next(m for m in result["enabled_mods"] if m["id"] == "exigency")
            self.assertEqual(exigency["version"], "0.7.2")
            self.assertEqual(exigency["game_version"], "0.98a-RC8")
            self.assertEqual(exigency["build_tag"]["build"], 3)
            lazylib = next(m for m in result["enabled_mods"] if m["id"] == "lw_lazylib")
            self.assertFalse(lazylib["build_tag"]["tagged"])

    def test_enabled_mods_is_the_ref_resolved_subset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            write_descriptor(save_dir, [{"id": "onlymod", "version": "1.0"}])
            result = parse_descriptor(save_dir)
            self.assertEqual([m["id"] for m in result["enabled_mods"]], ["onlymod"])
            self.assertEqual([m["id"] for m in result["all_mods_ever_enabled"]], ["onlymod"])


CAMPAIGN_SNIPPET = (
    '<?xml version="1.0" ?>\n'
    '<CampaignEngine z="1">\n'
    '<SampleMovement z="2">\n'
    '<WAYPOINTS z="3">\n'
    '<SampleWaypoint z="4">\n'
    '<loc z="5">1.0|2.0</loc>\n'
    '<loiter>true</loiter>\n'
    '</SampleWaypoint>\n'
    '</WAYPOINTS>\n'
    '<progress>0.5</progress>\n'
    '<loitering>false</loitering>\n'
    '<entity cl="CCEnt" ref="99"></entity>\n'
    '</SampleMovement>\n'
    '<Sibling z="6"></Sibling>\n'
    '</CampaignEngine>\n'
)


class IterElementsTests(unittest.TestCase):
    def test_leaf_and_structural_elements_and_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory) / "campaign.xml"
            write_text(campaign, CAMPAIGN_SNIPPET)
            elements = list(iter_elements(campaign))

        by_tag = {el.tag: el for el in elements if el.tag in ("progress", "loitering", "loc", "entity")}
        self.assertEqual(by_tag["progress"].text, "0.5")
        self.assertEqual(by_tag["progress"].path, ("CampaignEngine", "SampleMovement", "progress"))
        self.assertEqual(by_tag["loitering"].text, "false")
        self.assertEqual(by_tag["loc"].text, "1.0|2.0")
        self.assertEqual(
            by_tag["loc"].path,
            ("CampaignEngine", "SampleMovement", "WAYPOINTS", "SampleWaypoint", "loc"),
        )
        # `<entity cl="..." ref="99"></entity>` is an open+immediate-close leaf (empty text),
        # confirmed as this project's real shape for an XStream ref-attribute leaf.
        self.assertEqual(by_tag["entity"].text, "")
        self.assertEqual(by_tag["entity"].attrs["ref"], "99")

        sibling = next(el for el in elements if el.tag == "Sibling")
        self.assertEqual(sibling.path, ("CampaignEngine", "Sibling"))


class ScalarRecordTests(unittest.TestCase):
    def test_reads_only_immediate_children_and_stops_at_scope_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            campaign = Path(directory) / "campaign.xml"
            write_text(campaign, CAMPAIGN_SNIPPET)
            stream = PeekableElements(iter_elements(campaign))
            start = next(stream)  # CampaignEngine
            self.assertEqual(start.tag, "CampaignEngine")
            movement = next(stream)  # SampleMovement
            self.assertEqual(movement.tag, "SampleMovement")
            record = read_scalar_record(stream, len(movement.path))

            self.assertEqual(record["progress"], 0.5)
            self.assertEqual(record["loitering"], False)
            self.assertEqual(record["entity@ref"], "99")
            self.assertNotIn("WAYPOINTS", record)
            self.assertNotIn("loiter", record)  # nested inside WAYPOINTS, not an immediate child

            # The iterator should have stopped exactly at Sibling, still available to the caller.
            nxt = stream.peek()
            self.assertEqual(nxt.tag, "Sibling")
            stream.close()


if __name__ == "__main__":
    unittest.main()
