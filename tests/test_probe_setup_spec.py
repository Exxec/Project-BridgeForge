import tempfile
import unittest
from pathlib import Path

from bridgeforge.probe_config import ProbeConfigError, build_probe_config, parse_setups, validate_setup_spec


class SetupSpecValidationTests(unittest.TestCase):
    def test_rep_with_level_name_ok(self) -> None:
        self.assertEqual(validate_setup_spec("rep:exipirated=FRIENDLY"), "rep:exipirated=FRIENDLY")

    def test_rep_is_case_insensitive_for_level_name(self) -> None:
        self.assertEqual(validate_setup_spec("rep:exipirated=friendly"), "rep:exipirated=friendly")

    def test_rep_with_numeric_value_ok(self) -> None:
        self.assertEqual(validate_setup_spec("rep:exipirated=0.5"), "rep:exipirated=0.5")

    def test_rep_with_bad_value_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            validate_setup_spec("rep:exipirated=NOT_A_LEVEL")

    def test_rep_missing_equals_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            validate_setup_spec("rep:exipirated")

    def test_credits_ok(self) -> None:
        self.assertEqual(validate_setup_spec("credits:5000"), "credits:5000")

    def test_credits_negative_ok(self) -> None:
        self.assertEqual(validate_setup_spec("credits:-100"), "credits:-100")

    def test_credits_non_numeric_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            validate_setup_spec("credits:lots")

    def test_ship_without_count_ok(self) -> None:
        self.assertEqual(validate_setup_spec("ship:ART_dimention_manipulator"), "ship:ART_dimention_manipulator")

    def test_ship_with_count_ok(self) -> None:
        self.assertEqual(validate_setup_spec("ship:ART_dimention_manipulator:3"), "ship:ART_dimention_manipulator:3")

    def test_ship_missing_id_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            validate_setup_spec("ship:")

    def test_spawn_fleet_ok(self) -> None:
        self.assertEqual(validate_setup_spec("spawn-fleet:pirates:120"), "spawn-fleet:pirates:120")

    def test_spawn_fleet_missing_points_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            validate_setup_spec("spawn-fleet:pirates")

    def test_jump_ok(self) -> None:
        self.assertEqual(validate_setup_spec("jump:Corvus"), "jump:Corvus")

    def test_jump_with_spaces_ok(self) -> None:
        self.assertEqual(validate_setup_spec("jump:Op Center"), "jump:Op Center")

    def test_unrecognized_kind_raises(self) -> None:
        with self.assertRaises(ProbeConfigError):
            validate_setup_spec("teleport:Corvus")

    def test_parse_setups_validates_every_entry(self) -> None:
        specs = ["rep:exipirated=FRIENDLY", "credits:5000"]
        self.assertEqual(parse_setups(specs), specs)

    def test_parse_setups_raises_on_first_bad_entry(self) -> None:
        with self.assertRaises(ProbeConfigError):
            parse_setups(["credits:5000", "credits:notanumber"])

    def test_parse_setups_none_returns_empty(self) -> None:
        self.assertEqual(parse_setups(None), [])


class BuildProbeConfigSetupsTests(unittest.TestCase):
    def _make_fixture_mod(self, root: Path) -> Path:
        mod = root / "fixture_mod"
        (mod / "data" / "hulls").mkdir(parents=True)
        (mod / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
        (mod / "data" / "hulls" / "ship_data.csv").write_text("id,hints\n", encoding="utf-8")
        return mod

    def test_build_probe_config_includes_validated_setups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = self._make_fixture_mod(Path(directory))
            config = build_probe_config(mod, setups=["rep:exipirated=FRIENDLY", "credits:5000"])
            self.assertEqual(config["setups"], ["rep:exipirated=FRIENDLY", "credits:5000"])

    def test_build_probe_config_rejects_bad_setup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = self._make_fixture_mod(Path(directory))
            with self.assertRaises(ProbeConfigError):
                build_probe_config(mod, setups=["rep:exipirated=NOT_A_LEVEL"])


if __name__ == "__main__":
    unittest.main()
