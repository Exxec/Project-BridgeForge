import json
import tempfile
import unittest
from pathlib import Path

try:
    import _winapi
except ImportError:  # pragma: no cover - non-Windows
    _winapi = None

from bridgeforge.cli import main
from bridgeforge.probe_config import ProbeConfigError, build_probe_config, write_probe_config


def _make_fixture_mod(root: Path) -> Path:
    mod = root / "fixture_mod"
    (mod / "data" / "hulls").mkdir(parents=True)
    (mod / "data" / "variants").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id":"fixture_mod"}', encoding="utf-8")
    (mod / "data" / "hulls" / "ship_data.csv").write_text(
        "id,hints\n"
        "fx_hull1,\n"
        "fx_hull2,\n"
        "fx_module1,MODULE\n"
        "fx_fighter1,FIGHTER\n",
        encoding="utf-8",
    )
    (mod / "data" / "variants" / "fx_hull1_Standard.variant").write_text(
        '{"hullId":"fx_hull1","id":"fx_hull1_Standard"}', encoding="utf-8"
    )
    # fx_hull2 deliberately has no variant, to exercise hulls_skipped_no_variant.
    return mod


def _make_rig(root: Path) -> Path | None:
    if _winapi is None:
        return None
    core_real = root / "core_real"
    core_real.mkdir()
    rig = root / "rig"
    rig.mkdir()
    try:
        _winapi.CreateJunction(str(core_real), str(rig / "starsector-core"))
    except OSError:
        return None
    return rig


class ProbeConfigBuildTests(unittest.TestCase):
    def test_build_probe_config_excludes_modules_and_fighters(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _make_fixture_mod(Path(directory))
            config = build_probe_config(mod, track_entities=["exipirated_avesta"])
            self.assertEqual(config["target_mod_id"], "fixture_mod")
            self.assertEqual(config["hulls"], ["fx_hull1"])
            self.assertEqual(config["variants"], {"fx_hull1": "fx_hull1_Standard"})
            self.assertEqual(config["hulls_skipped_no_variant"], ["fx_hull2"])
            self.assertEqual(config["track_entities"], ["exipirated_avesta"])

    def test_missing_mod_id_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "bad_mod"
            mod.mkdir()
            (mod / "mod_info.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ProbeConfigError):
                build_probe_config(mod)


class ProbeConfigRigTests(unittest.TestCase):
    def test_refuses_non_junction_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            runtime = root / "not_a_rig"
            (runtime / "starsector-core").mkdir(parents=True)
            with self.assertRaises(ProbeConfigError):
                write_probe_config(mod, runtime)

    def test_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Directory junctions are not supported in this environment.")
            result = write_probe_config(mod, rig, dry_run=True)
            self.assertFalse(result["written"])
            self.assertFalse((rig / "saves" / "common" / "bf_probe_config.data").exists())

    def test_writes_config_and_marker_into_rig_common(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Directory junctions are not supported in this environment.")
            result = write_probe_config(mod, rig, track_entities=["exipirated_avesta"], combat_seconds=30.0)
            self.assertTrue(result["written"])
            config_path = rig / "saves" / "common" / "bf_probe_config.data"
            marker_path = rig / "saves" / "common" / "bf_probe_rig.data"
            self.assertTrue(config_path.is_file())
            self.assertTrue(marker_path.is_file())
            written = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(written["target_mod_id"], "fixture_mod")
            self.assertEqual(written["combat_seconds"], 30.0)

    def test_cli_probe_config_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _make_fixture_mod(root)
            rig = _make_rig(root)
            if rig is None:
                self.skipTest("Directory junctions are not supported in this environment.")
            rc = main(["probe-config", str(mod), "--runtime", str(rig), "--dry-run", "--json"])
            self.assertEqual(rc, 0)
            self.assertFalse((rig / "saves" / "common" / "bf_probe_config.data").exists())


if __name__ == "__main__":
    unittest.main()
