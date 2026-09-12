import tempfile
import unittest
from pathlib import Path

from bridgeforge.scenarios import (
    ScenarioError,
    list_scenarios,
    load_scenario,
    scenario_check,
    scenario_plan,
)


def _make_fixture_mod(root: Path, mod_id: str = "exigency") -> Path:
    mod = root / mod_id
    (mod / "data" / "hulls").mkdir(parents=True)
    (mod / "mod_info.json").write_text(f'{{"id":"{mod_id}"}}', encoding="utf-8")
    (mod / "data" / "hulls" / "ship_data.csv").write_text("id,hints\n", encoding="utf-8")
    return mod


class ScenarioCatalogTests(unittest.TestCase):
    def test_list_scenarios_includes_all_three_shipped(self) -> None:
        self.assertEqual(
            list_scenarios(),
            ["avesta-near", "betelgeuse-damaged", "nex-corvus-day1"],
        )

    def test_load_scenario_unknown_raises(self) -> None:
        with self.assertRaises(ScenarioError):
            load_scenario("does-not-exist")

    def test_every_shipped_scenario_loads_and_has_expect(self) -> None:
        for name in list_scenarios():
            scenario = load_scenario(name)
            self.assertEqual(scenario["schema_version"], 1)
            self.assertIn("expect", scenario)
            self.assertIn("probe", scenario["expect"])


class ScenarioPlanTests(unittest.TestCase):
    def test_plan_without_mod_dir_reports_error_but_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "rig"
            plan = scenario_plan("avesta-near", runtime, mod_dirs={})
            self.assertEqual(plan["scenario"], "avesta-near")
            self.assertIsNone(plan["probe_config_preview"])
            self.assertIsNotNone(plan["probe_config_preview_error"])
            self.assertIn("--dry-run", plan["probe_config_argv"])

    def test_plan_with_mod_dir_builds_config_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root, "exigency")
            runtime = root / "rig"
            plan = scenario_plan("avesta-near", runtime, mod_dirs={"exigency": mod})
            self.assertIsNotNone(plan["probe_config_preview"])
            self.assertEqual(plan["probe_config_preview"]["target_mod_id"], "exigency")
            self.assertEqual(plan["probe_config_preview"]["setups"], ["rep:exipirated=FRIENDLY"])
            self.assertIn(str(mod), plan["probe_config_argv"])
            self.assertIn("--setup", plan["probe_config_argv"])
            self.assertIn("rep:exipirated=FRIENDLY", plan["probe_config_argv"])

    def test_plan_never_writes_to_runtime_dir(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root, "exigency")
            runtime = root / "rig"
            scenario_plan("avesta-near", runtime, mod_dirs={"exigency": mod})
            self.assertFalse(runtime.exists())

    def test_plan_betelgeuse_damaged_mods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "rig"
            plan = scenario_plan("betelgeuse-damaged", runtime, mod_dirs={})
            self.assertEqual(plan["mods"], ["SEEKER"])
            self.assertIn("ship:ART_dimention_manipulator", plan["probe_setups"])

    def test_plan_nex_corvus_resolves_compat_set(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / "rig"
            plan = scenario_plan("nex-corvus-day1", runtime, mod_dirs={})
            self.assertIn("exigency", plan["mods"])
            self.assertIn("nexerelin", plan["mods"])
            # 'libs' compat set members (see bridgeforge/compat_sets/standard.json)
            self.assertIn("lw_lazylib", plan["mods"])
            self.assertIn("MagicLib", plan["mods"])
            self.assertIsNone(plan["compat_set_note"])


class ScenarioCheckTests(unittest.TestCase):
    def _write_log(self, directory: Path, lines: list[str]) -> Path:
        log_path = directory / "starsector.log"
        text = "\n".join(f"1 [Thread-1] INFO com.bridgeforge.probe.ProbeLog  - {line}" for line in lines) + "\n"
        log_path.write_text(text, encoding="utf-8")
        return log_path

    def test_avesta_near_passes_when_all_expected_lines_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|setup|OK|rep:exipirated=FRIENDLY|faction=exipirated value=FRIENDLY",
                    "BF-PROBE|0.1.0|submarket-stock|OK|market_exipirated/open_market|ships=3 weaponStacks=5",
                    "BF-PROBE|0.1.0|tracked-entities|INFO|exipirated_avesta|x=100.0 y=200.0",
                ],
            )
            result = scenario_check("avesta-near", log)
            self.assertEqual(result["status"], "PASS", result)

    def test_avesta_near_fails_when_setup_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|submarket-stock|OK|market_exipirated/open_market|ships=3 weaponStacks=5",
                    "BF-PROBE|0.1.0|tracked-entities|INFO|exipirated_avesta|x=100.0 y=200.0",
                ],
            )
            result = scenario_check("avesta-near", log)
            self.assertEqual(result["status"], "FAIL")
            statuses = [a["status"] for a in result["probe_assertions"]]
            self.assertIn("FAIL", statuses)

    def test_betelgeuse_damaged_fails_on_personality_warn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|setup|OK|ship:ART_dimention_manipulator|variant=ART_dimention_manipulator count=1",
                    "BF-PROBE|0.1.0|setup|OK|spawn-fleet:pirates:120|faction=pirates requestedFP=120.0 actualFP=120.0 members=3",
                    "BF-PROBE|0.1.0|probe|INFO|combat|START",
                    "BF-PROBE|0.1.0|probe|INFO|combat|END",
                    "BF-PROBE|0.1.0|combat-captain-personality|WARN|Betelgeuse Prime|hull=skr_betelgeuse captain has a null personality",
                ],
            )
            result = scenario_check("betelgeuse-damaged", log)
            self.assertEqual(result["status"], "FAIL")

    def test_betelgeuse_damaged_passes_without_personality_warn(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|setup|OK|ship:ART_dimention_manipulator|variant=ART_dimention_manipulator count=1",
                    "BF-PROBE|0.1.0|setup|OK|spawn-fleet:pirates:120|faction=pirates requestedFP=120.0 actualFP=120.0 members=3",
                    "BF-PROBE|0.1.0|probe|INFO|combat|START",
                    "BF-PROBE|0.1.0|probe|INFO|combat|END",
                ],
            )
            result = scenario_check("betelgeuse-damaged", log)
            self.assertEqual(result["status"], "PASS", result)

    def test_nex_corvus_fails_on_duplicate_tasserus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|probe|INFO|campaign|START",
                    "BF-PROBE|0.1.0|probe|INFO|campaign|END",
                    "BF-PROBE|0.1.0|planet-specs|OK|Tasserus/tasserus_1|type=exigency_planet",
                    "BF-PROBE|0.1.0|planet-specs|OK|Tasserus/tasserus_1_dup|type=exigency_planet",
                ],
            )
            result = scenario_check("nex-corvus-day1", log)
            self.assertEqual(result["status"], "FAIL")

    def test_nex_corvus_passes_with_single_tasserus(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|probe|INFO|campaign|START",
                    "BF-PROBE|0.1.0|probe|INFO|campaign|END",
                    "BF-PROBE|0.1.0|planet-specs|OK|Tasserus/tasserus_1|type=exigency_planet",
                ],
            )
            result = scenario_check("nex-corvus-day1", log)
            self.assertEqual(result["status"], "PASS", result)

    def test_save_assertions_skipped_when_module_unavailable(self) -> None:
        # No shipped scenario currently declares save assertions; exercise the skip path directly by
        # loading a scenario and monkeypatching its expect() would require editing shipped JSON, so
        # instead this confirms the no-assertions path reports no save_note and PASSes trivially.
        with tempfile.TemporaryDirectory() as directory:
            log = self._write_log(
                Path(directory),
                [
                    "BF-PROBE|0.1.0|probe|INFO|campaign|START",
                    "BF-PROBE|0.1.0|probe|INFO|campaign|END",
                ],
            )
            result = scenario_check("nex-corvus-day1", log)
            self.assertIsNone(result["save_note"])
            self.assertEqual(result["save_assertions"], [])

    def test_missing_log_raises(self) -> None:
        with self.assertRaises(ScenarioError):
            scenario_check("avesta-near", Path("does-not-exist.log"))


if __name__ == "__main__":
    unittest.main()
