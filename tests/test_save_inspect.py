from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.save_inspect import (
    audit_scripts,
    diff_saves,
    growth_trend,
    inspect_save,
    save_provenance,
)
from tests.save_fixtures import write_descriptor, write_mod_class_jar, write_mod_info, write_text

SAVE_HEADER = '<?xml version="1.0" ?>\n<CampaignEngine z="1">\n'
SAVE_FOOTER = "</CampaignEngine>\n"


def _movement_xml(progress: float, loitering: str, waypoint: int) -> str:
    return (
        '<ExampleMovement z="891">\n'
        '<WAYPOINTS z="892">\n'
        '<ExampleMovementWaypoint z="893">\n'
        '<loc z="894">1.0|2.0</loc>\n'
        "<loiter>true</loiter>\n"
        "</ExampleMovementWaypoint>\n"
        "</WAYPOINTS>\n"
        "<burnLevel>3.0</burnLevel>\n"
        f"<loitering>{loitering}</loitering>\n"
        f"<progress>{progress}</progress>\n"
        f"<waypoint>{waypoint}</waypoint>\n"
        "</ExampleMovement>\n"
    )


class InspectTrackedClassTests(unittest.TestCase):
    def test_tracks_scalar_fields_of_tracked_class(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            write_text(save_dir / "campaign.xml", SAVE_HEADER + _movement_xml(0.5, "true", 3) + SAVE_FOOTER)

            result = inspect_save(save_dir, track_classes=["ExampleMovement"])

            self.assertEqual(len(result["tracked_objects"]), 1)
            obj = result["tracked_objects"][0]
            self.assertEqual(obj["class"], "ExampleMovement")
            self.assertEqual(obj["fields"]["progress"], 0.5)
            self.assertEqual(obj["fields"]["loitering"], True)
            self.assertEqual(obj["fields"]["waypoint"], 3)
            self.assertNotIn("WAYPOINTS", obj["fields"])
            self.assertNotIn("loiter", obj["fields"])

    def test_tracked_ids_report_field_and_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            xml = SAVE_HEADER + '<FMmbr z="2" sid="hull_a" id="c781"></FMmbr>\n' + SAVE_FOOTER
            write_text(save_dir / "campaign.xml", xml)

            result = inspect_save(save_dir, track_ids=["c781"])

            self.assertEqual(len(result["tracked_id_hits"]), 1)
            hit = result["tracked_id_hits"][0]
            self.assertEqual(hit["id"], "c781")
            self.assertIn("FMmbr", hit["path"])

    def test_known_list_heuristic_counts_children(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            xml = (
                SAVE_HEADER
                + '<knownFactions z="2">\n<one>a</one>\n<two>b</two>\n<three>c</three>\n</knownFactions>\n'
                + SAVE_FOOTER
            )
            write_text(save_dir / "campaign.xml", xml)

            result = inspect_save(save_dir)

            self.assertEqual(len(result["known_lists"]), 1)
            self.assertEqual(result["known_lists"][0]["size"], 3)
            self.assertEqual(result["known_lists"][0]["tag"], "knownFactions")

    def test_mod_object_counts_by_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_class_jar(mod_dir, ["data.scripts.samplemod.PluginA", "data.scripts.samplemod.PluginB"])
            save_dir = Path(directory) / "save"
            xml = (
                SAVE_HEADER
                + '<PluginA z="2"></PluginA>\n'
                + '<PluginA z="3"></PluginA>\n'
                + '<PluginB z="4"></PluginB>\n'
                + SAVE_FOOTER
            )
            write_text(save_dir / "campaign.xml", xml)

            result = inspect_save(save_dir, mod_dir=mod_dir)

            counts = result["mod_object_counts"]
            self.assertEqual(counts["by_namespace"]["data.scripts.samplemod"], 3)
            self.assertEqual(counts["total"], 3)


class DiffSavesTests(unittest.TestCase):
    def test_diff_reports_changed_added_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_a = Path(directory) / "save_a"
            save_b = Path(directory) / "save_b"
            write_text(save_a / "campaign.xml", SAVE_HEADER + _movement_xml(0.2, "false", 1) + SAVE_FOOTER)
            write_text(
                save_b / "campaign.xml",
                SAVE_HEADER
                + _movement_xml(0.9, "true", 5)
                + '<OtherThing z="999"></OtherThing>\n'
                + SAVE_FOOTER,
            )

            result = diff_saves(save_a, save_b, track_classes=["ExampleMovement"])

            self.assertEqual(len(result["changed_objects"]), 1)
            changed = result["changed_objects"][0]
            self.assertEqual(changed["fields"]["progress"], {"a": 0.2, "b": 0.9})
            self.assertEqual(changed["fields"]["loitering"], {"a": False, "b": True})
            self.assertEqual(changed["fields"]["waypoint"], {"a": 1, "b": 5})

    def test_diff_matches_by_path_not_z_across_independently_saved_files(self) -> None:
        # Real finding (validation against In operation/_rig/saves/
        # save_FourthAnderson_*): the same ExipiratedAvestaMovement singleton had z="889" in
        # campaign.xml.bak and z="891" in campaign.xml -- XStream's z is a per-file sequence
        # number, not a stable id. Matching on path (not z) is what lets this be seen as
        # "changed" instead of "removed + added".
        with tempfile.TemporaryDirectory() as directory:
            save_a = Path(directory) / "save_a"
            save_b = Path(directory) / "save_b"
            xml_a = SAVE_HEADER + '<Holder z="2">\n' + _movement_xml(0.2, "false", 1).replace('z="891"', 'z="889"') + "</Holder>\n" + SAVE_FOOTER
            xml_b = SAVE_HEADER + '<Holder z="2">\n' + _movement_xml(0.9, "true", 5) + "</Holder>\n" + SAVE_FOOTER
            write_text(save_a / "campaign.xml", xml_a)
            write_text(save_b / "campaign.xml", xml_b)

            result = diff_saves(save_a, save_b, track_classes=["ExampleMovement"])

            self.assertEqual(len(result["changed_objects"]), 1)
            self.assertEqual(result["added_objects"], [])
            self.assertEqual(result["removed_objects"], [])


class AuditScriptsTests(unittest.TestCase):
    def test_flags_duplicate_script_on_same_holder(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_class_jar(mod_dir, ["data.scripts.samplemod.NoFuelDriftScript"])
            save_dir = Path(directory) / "save"
            xml = (
                SAVE_HEADER
                + '<holderEntity z="2">\n'
                + '<scripts z="3">\n'
                + '<NoFuelDriftScript z="4"></NoFuelDriftScript>\n'
                + '<NoFuelDriftScript z="5"></NoFuelDriftScript>\n'
                + "</scripts>\n"
                + "</holderEntity>\n"
                + SAVE_FOOTER
            )
            write_text(save_dir / "campaign.xml", xml)

            result = audit_scripts(save_dir, mod_dir)

            self.assertEqual(result["status"], "DUPLICATES_FOUND")
            self.assertEqual(len(result["duplicates"]), 1)
            dup = result["duplicates"][0]
            self.assertEqual(dup["class"], "data.scripts.samplemod.NoFuelDriftScript")
            self.assertEqual(dup["count"], 2)
            self.assertIn("holderEntity", dup["holder"])

    def test_single_instance_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_class_jar(mod_dir, ["data.scripts.samplemod.NoFuelDriftScript"])
            save_dir = Path(directory) / "save"
            xml = (
                SAVE_HEADER
                + '<scripts z="3">\n<NoFuelDriftScript z="4"></NoFuelDriftScript>\n</scripts>\n'
                + SAVE_FOOTER
            )
            write_text(save_dir / "campaign.xml", xml)

            result = audit_scripts(save_dir, mod_dir)

            self.assertEqual(result["status"], "CLEAN")
            self.assertEqual(result["duplicates"], [])
            self.assertEqual(result["total_instances"], 1)


class GrowthTrendTests(unittest.TestCase):
    def test_warns_on_large_object_count_growth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_class_jar(mod_dir, ["data.scripts.samplemod.LeakyList"])

            save1 = Path(directory) / "save1"
            write_text(save1 / "campaign.xml", SAVE_HEADER + '<LeakyList z="2"></LeakyList>\n' + SAVE_FOOTER)

            save2 = Path(directory) / "save2"
            many = "".join(f'<LeakyList z="{n}"></LeakyList>\n' for n in range(2, 22))
            write_text(save2 / "campaign.xml", SAVE_HEADER + many + SAVE_FOOTER)

            result = growth_trend([save1, save2], mod_dir=mod_dir, growth_rate_warning=2.0)

            self.assertEqual(result["status"], "GROWTH_WARNING")
            self.assertTrue(any(w["axis"] == "mod_object_count" for w in result["warnings"]))
            self.assertEqual(result["points"][0]["mod_object_count"], 1)
            self.assertEqual(result["points"][1]["mod_object_count"], 20)

    def test_stable_counts_are_ok(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod")
            write_mod_class_jar(mod_dir, ["data.scripts.samplemod.Steady"])
            save1 = Path(directory) / "save1"
            save2 = Path(directory) / "save2"
            xml = SAVE_HEADER + '<Steady z="2"></Steady>\n' + SAVE_FOOTER
            write_text(save1 / "campaign.xml", xml)
            write_text(save2 / "campaign.xml", xml)

            result = growth_trend([save1, save2], mod_dir=mod_dir)

            self.assertEqual(result["status"], "OK")
            self.assertEqual(result["warnings"], [])


class SaveProvenanceTests(unittest.TestCase):
    def test_stale_build_warns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            write_descriptor(save_dir, [{"id": "samplemod", "name": "Sample [BF r2]", "version": "1.0"}])
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod", name="Sample [BF r5]", version="1.0")

            result = save_provenance(save_dir, mod_dirs=[mod_dir])

            self.assertEqual(result["status"], "STALE_BUILD")
            self.assertEqual(len(result["warnings"]), 1)
            self.assertEqual(result["warnings"][0]["saved_build"], 2)
            self.assertEqual(result["warnings"][0]["current_build"], 5)

    def test_current_build_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            write_descriptor(save_dir, [{"id": "samplemod", "name": "Sample [BF r5]", "version": "1.0"}])
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="samplemod", name="Sample [BF r5]", version="1.0")

            result = save_provenance(save_dir, mod_dirs=[mod_dir])

            self.assertEqual(result["status"], "CURRENT")
            self.assertEqual(result["warnings"], [])

    def test_unrelated_mod_dir_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            save_dir = Path(directory) / "save"
            write_descriptor(save_dir, [{"id": "samplemod", "version": "1.0"}])
            mod_dir = Path(directory) / "mod"
            write_mod_info(mod_dir, mod_id="othermod", version="1.0")

            result = save_provenance(save_dir, mod_dirs=[mod_dir])

            self.assertEqual(result["comparisons"], [])
            self.assertEqual(result["status"], "CURRENT")


if __name__ == "__main__":
    unittest.main()
