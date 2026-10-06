import unittest

from bridgeforge.save_format_survey import survey_save, survey_saves
from tests.support import resolved_temp_dir

_CAMPAIGN = """<CampaignEngine>
<fleetStuff>
<fleet cl="Flt" z="10">
<name>Secret Player Name</name>
<cargo z="11" uS="true" mC="100.0" sU="5.0" mF="50.0" mP="20.0" fT="false">
<s z="12">
<CIStack z="13" s="777.0" t="RESOURCES">
<d cl="st">supplies</d>
</CIStack>
<CIStack z="14" s="12.0" t="RESOURCES">
<d cl="st">fuel</d>
</CIStack>
</s>
<c z="15">
<value>123456.0</value>
</c>
</cargo>
</fleet>
<fleet cl="Flt" z="20">
<cargo z="21" mC="1.0"></cargo>
</fleet>
</fleetStuff>
<playerFleet ref="10"></playerFleet>
</CampaignEngine>
"""

_DESCRIPTOR = """<SaveGameData>
<gameVersion>0.98a-RC8</gameVersion>
<characterName>Secret Player Name</characterName>
</SaveGameData>
"""


def _make_save(root, name="save_Test_1", campaign=_CAMPAIGN):
    save = root / name
    save.mkdir()
    (save / "campaign.xml").write_text(campaign, encoding="utf-8")
    (save / "descriptor.xml").write_text(_DESCRIPTOR, encoding="utf-8")
    return save


class SaveFormatSurveyTests(unittest.TestCase):
    def test_reports_cargo_structure_credits_presence_and_never_values_or_names(self) -> None:
        with resolved_temp_dir() as root:
            result = survey_save(_make_save(root))
        cargo = result["cargo"]
        self.assertEqual(cargo["attribute_names"], ["fT", "mC", "mF", "mP", "sU", "uS", "z"])
        self.assertEqual(cargo["stack_types"], {"RESOURCES": 2})
        self.assertTrue(cargo["credits_value_present"])
        text = repr(result)
        for secret in ("Secret Player Name", "123456", "777", "supplies"):
            self.assertNotIn(secret, text)

    def test_only_the_player_fleet_is_surveyed(self) -> None:
        with resolved_temp_dir() as root:
            result = survey_save(_make_save(root))
        self.assertEqual(result["player_fleet"]["tag"], "fleet")
        self.assertEqual(len(result["cargo"]["attribute_names"]), 7)

    def test_a_save_without_a_player_fleet_reference_is_noted_not_guessed(self) -> None:
        with resolved_temp_dir() as root:
            result = survey_save(_make_save(root, campaign="<CampaignEngine>\n</CampaignEngine>\n"))
        self.assertIsNone(result["cargo"])
        self.assertIn("no playerFleet reference found", result["notes"])

    def test_comparison_lists_attributes_shared_by_every_save_and_survives_a_bad_save(self) -> None:
        with resolved_temp_dir() as root:
            good = _make_save(root, "save_A_1")
            good_two = _make_save(root, "save_B_2")
            summary = survey_saves([good, good_two, root / "missing"])
        self.assertEqual(summary["saves_surveyed"], 3)
        self.assertEqual(summary["saves_with_player_cargo"], 2)
        self.assertEqual(summary["game_versions"], {"0.98a-RC8": 2})
        self.assertTrue(summary["credits_value_present_in_every_save"])
        self.assertEqual(summary["surveys"][2]["status"], "ERROR")


if __name__ == "__main__":
    unittest.main()
