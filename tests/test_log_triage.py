import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.log_triage import class_owner_index, triage_log
from bridgeforge.cli import main


def _write_mod(mods_dir: Path, mod_id: str, name: str, jar_name: str, class_entries: list[str]) -> None:
    mod_dir = mods_dir / mod_id
    mod_dir.mkdir(parents=True, exist_ok=True)
    (mod_dir / "mod_info.json").write_text(
        json.dumps({"id": mod_id, "name": name, "version": "1.0", "jars": [jar_name]}),
        encoding="utf-8",
    )
    with zipfile.ZipFile(mod_dir / jar_name, "w") as archive:
        for entry in class_entries:
            archive.writestr(entry, b"")


class LogTriageTests(unittest.TestCase):
    def test_classifies_fatal_mod_error_and_known_noise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        "100 [Thread-2] ERROR com.fs.starfarer.loading.ShipHullSpreadsheetLoader  - Ship hull spec [flare] not found in ship_data.csv",
                        "200 [Thread-2] WARN  lunalib.lunaSettings.LunaSettings  - LunaSettings: Value enableFullExplosionEffects of type String not found in JSONObject (ModID: shaderLib)",
                        "300 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - java.lang.RuntimeException: Spec of class [com.fs.starfarer.api.impl.campaign.procgen.PlanetGenDataSpec] with id [exigency_planetoid] not found",
                        "java.lang.RuntimeException: Spec of class [com.fs.starfarer.api.impl.campaign.procgen.PlanetGenDataSpec] with id [exigency_planetoid] not found",
                        "\tat com.fs.starfarer.loading.SpecStore.o00000(Unknown Source)",
                        "\tat data.scripts.world.exigency.Tasserus.generate(Tasserus.java:250)",
                        "400 [Thread-8] INFO  sound.O  - Creating streaming player for music with id [miscallenous_main_menu.ogg]",
                        "500 [Thread-8] INFO  sound.H  - Playing music with id [miscallenous_main_menu.ogg]",
                        "600 [Thread-2] WARN  com.fs.starfarer.loading.WeaponSpreadsheetLoader  - Weapon [lightmortar_fighter] from weapon_data.csv not found in store",
                    ]
                ),
                encoding="utf-8",
            )
            result = triage_log(log)
            self.assertEqual(result["counts"]["FATAL"], 1)
            self.assertEqual(result["counts"]["KNOWN-NOISE"], 2)
            self.assertEqual(result["counts"]["OTHER"], 1)
            self.assertEqual(result["fatal"][0]["matched_rule"], "Spec not found")
            self.assertIn("Tasserus.generate", result["fatal"][0]["top_mod_frame"])
            self.assertTrue(result["milestones"]["main_menu_reached"])

    def test_mod_error_classification_uses_stack_frame_mod_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        "10 [Thread-2] WARN  some.Logger  - Something odd happened in a script",
                        "\tat data.scripts.plugins.myMod_Plugin.advance(myMod_Plugin.java:10)",
                        "20 [Thread-2] INFO  x  - unrelated",
                    ]
                ),
                encoding="utf-8",
            )
            result = triage_log(log, mod_prefixes=["myMod_"])
            self.assertEqual(result["counts"]["MOD-ERROR"], 1)
            self.assertIn("myMod_Plugin", result["mod_errors"][0]["top_mod_frame"])

    def test_whole_word_error_level_avoids_substring_false_positives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        "10 [Thread-2] INFO  com.fs.starfarer.loading.SpecStore  - Loaded spec with id [Ferror_|_star, planet, moon, nebula, constellation]",
                        "20 [Thread-2] INFO  com.fs.starfarer.campaign.rules.Rules  - Loading rule: anhCantinaAskTerroristA",
                    ]
                ),
                encoding="utf-8",
            )
            result = triage_log(log)
            self.assertEqual(result["counts"]["FATAL"], 0)
            self.assertEqual(result["counts"]["MOD-ERROR"], 0)
            self.assertEqual(result["counts"]["OTHER"], 0)

    def test_detects_spec_store_ship_system_shadowing_symptom(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("10 [Thread-2] WARN  com.fs.starfarer.loading.SpecStore  - Ship system [temporalshell] from ship_systems.csv not found in store\n", encoding="utf-8")
            result = triage_log(log)
            self.assertEqual(len(result["vanilla_shadowing_symptoms"]), 1)
            self.assertEqual(result["vanilla_shadowing_symptoms"][0]["ship_system"], "temporalshell")

    def test_campaign_load_uses_real_load_line_not_save_menu_or_mission_preloads(self) -> None:
        # Lines copied from a real RC8 log: the Load menu reads every save's descriptor, and startup
        # preloads every mission's variants; neither is a load. Only "Loading ...saves/..." is.
        lines = [
            r"9639 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Reading save data from [..\saves\save_A_1\descriptor.xml]",
            r"9692 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Reading save data from [..\saves\save_B_2\descriptor.xml]",
            r"5229 [Thread-2] INFO  com.fs.starfarer.loading.B  - Loading saved variants for mission ambush",
            r"31689 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading ..\saves/save_A_1...",
            r"31693 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading stage 2",
        ]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            milestones = triage_log(log)["milestones"]
            self.assertEqual(milestones["campaign_loads"], [r"..\saves/save_A_1"])
            self.assertEqual(milestones["mission_variant_preloads"], ["ambush"])

    def test_campaign_load_with_absolute_path_containing_spaces(self) -> None:
        lines = [
            r"19567 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading C:\Users\me\Documents\Project BridgeForge\In operation\rig\starsector-core\..\saves\save_Four_55...",
            r"20295 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Finished loading",
            r"20296 [Thread-2] INFO  com.fs.starfarer.campaign.save.CampaignGameManager  - Loading stage 2",
        ]
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "starsector.log"
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            loads = triage_log(log)["milestones"]["campaign_loads"]
            self.assertEqual(loads, [r"C:\Users\me\Documents\Project BridgeForge\In operation\rig\starsector-core\..\saves\save_Four_55"])

    def test_missing_log_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            triage_log(Path("does-not-exist.log"))

    def test_sk13_npe_through_ai_tweaks_with_seeker_in_stack_is_attributed(self) -> None:
        # Realistic SK-13 shape: an NPE inside vanilla Person.getPersonality is reached through AI
        # Tweaks code with SEEKER further down the stack. AI Tweaks ran closest to the throw, so it
        # is the suspect; SEEKER is merely involved.
        with tempfile.TemporaryDirectory() as directory:
            mods_dir = Path(directory) / "mods"
            _write_mod(mods_dir, "ai_tweaks", "AI Tweaks", "ai_tweaks.jar", ["aitweaks/ai/PersonAI.class"])
            _write_mod(mods_dir, "seeker", "SEEKER", "seeker.jar", ["seeker/plugins/SeekerCampaignPlugin.class"])
            (mods_dir / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["ai_tweaks", "seeker"]}), encoding="utf-8")

            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        "50 [Thread-2] ERROR com.fs.starfarer.campaign.CampaignEngine  - java.lang.NullPointerException",
                        "java.lang.NullPointerException",
                        "\tat com.fs.starfarer.campaign.Person.getPersonality(Person.java:42)",
                        "\tat aitweaks.ai.PersonAI.assignPersonality(PersonAI.java:88)",
                        "\tat seeker.plugins.SeekerCampaignPlugin.advance(SeekerCampaignPlugin.java:120)",
                        "\tat com.fs.starfarer.campaign.CampaignEngine.advance(CampaignEngine.java:500)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = triage_log(log, mods_dir=mods_dir)
            attributed = result["fatal"] + result["mod_errors"] + result["other"]
            self.assertEqual(len(attributed), 1)
            entry = attributed[0]
            self.assertEqual(entry["suspect"], "ai_tweaks")
            self.assertIn("seeker", entry["involved"])
            self.assertIn("ai_tweaks", entry["involved"])
            self.assertIn("PersonAI.assignPersonality", entry["top_mod_frame"])
            self.assertEqual(result["attribution"]["counts_by_suspect"], {"ai_tweaks": 1})

    def test_attribution_works_on_a_foreign_modpack_mods_dir(self) -> None:
        # mods_dir need not be the rig's own -- a foreign modpack's mods dir (different mod ids,
        # no enabled_mods.json at all) must still attribute correctly.
        with tempfile.TemporaryDirectory() as directory:
            mods_dir = Path(directory) / "someone_elses_modpack" / "mods"
            _write_mod(mods_dir, "foreign_mod", "Foreign Mod", "foreign.jar", ["foreignpkg/plugins/Plugin.class"])

            log = Path(directory) / "starsector.log"
            log.write_text(
                "\n".join(
                    [
                        "10 [Thread-2] ERROR some.Logger  - java.lang.RuntimeException: boom",
                        "\tat foreignpkg.plugins.Plugin.advance(Plugin.java:5)",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = triage_log(log, mods_dir=mods_dir)
            other = result["other"]
            self.assertEqual(len(other), 1)
            self.assertEqual(other[0]["suspect"], "foreign_mod")

    def test_class_owner_index_maps_package_and_respects_enabled_mods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mods_dir = Path(directory) / "mods"
            _write_mod(mods_dir, "enabled_mod", "Enabled Mod", "enabled.jar", ["enabledpkg/Thing.class"])
            _write_mod(mods_dir, "disabled_mod", "Disabled Mod", "disabled.jar", ["disabledpkg/Thing.class"])
            (mods_dir / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["enabled_mod"]}), encoding="utf-8")

            index = class_owner_index(mods_dir)
            self.assertEqual(index.get("enabledpkg.Thing"), "enabled_mod")
            self.assertEqual(index.get("enabledpkg"), "enabled_mod")
            self.assertNotIn("disabledpkg.Thing", index)

            index_all = class_owner_index(mods_dir, enabled_only=False)
            self.assertEqual(index_all.get("disabledpkg.Thing"), "disabled_mod")

    def test_cli_json_output_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "clean.log"
            log.write_text("10 [Thread-2] INFO  x  - Playing music with id [miscallenous_main_menu.ogg]\n", encoding="utf-8")
            self.assertEqual(main(["log-triage", str(log), "--json"]), 0)
            fatal_log = Path(directory) / "fatal.log"
            fatal_log.write_text("10 [Thread-2] ERROR x  - java.lang.NoClassDefFoundError: Foo\n", encoding="utf-8")
            self.assertEqual(main(["log-triage", str(fatal_log)]), 1)
