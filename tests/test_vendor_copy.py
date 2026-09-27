"""vendor-copy: copy one hullmod (its CSV row and script) from a provider into another mod (ROADMAP P14 item 4)."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.strip_plan import vendor_copy


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")



def _core(root: Path) -> Path:
    core = root / "core"
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\nArmor,heavyarmor\n")
    _write(core / "data" / "hulls" / "wing_data.csv", "id,variant\ntalon_wing,t\n")
    _write(core / "data" / "weapons" / "weapon_data.csv", "name,id\nLight MG,lightmg\nVanilla Beam,vbeam\nBig Cannon,bigcannon\n")
    _write(core / "data" / "weapons" / "lightmg.wpn", json.dumps({"id": "lightmg", "type": "BALLISTIC", "size": "SMALL"}))
    _write(core / "data" / "weapons" / "vbeam.wpn", json.dumps({"id": "vbeam", "type": "ENERGY", "size": "SMALL"}))
    _write(core / "data" / "weapons" / "bigcannon.wpn", json.dumps({"id": "bigcannon", "type": "BALLISTIC", "size": "LARGE"}))
    _write(core / "data" / "hulls" / "lasher.ship", json.dumps({
        "hullId": "lasher", "hullSize": "FRIGATE",
        "weaponSlots": [{"id": "WS001", "type": "ENERGY", "size": "SMALL"}],
    }))
    return core



def _provider_mod(root: Path, mod_id: str, hullmod_row: str, script_class: str | None = None, script_body: str = "") -> Path:
    provider = root / "provider"
    _write(provider / "mod_info.json", json.dumps({"id": mod_id, "name": mod_id}))
    _write(provider / "data" / "hullmods" / "hull_mods.csv", "name,id,script,desc\n" + hullmod_row)
    if script_class:
        script_path = provider / (script_class.replace(".", "/") + ".java")
        _write(script_path, script_body)
    return provider



class VendorCopyTests(unittest.TestCase):
    """ROADMAP P14 item 4's vendoring alternative: "copy the one missing piece... instead of
    reviving a heavy provider." Scoped to hullmods (a CSV row plus its declared script is a single,
    well-defined unit); a licence gate blocks a local-only source, matching item 7's own gate.
    """

    def test_dry_run_plans_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", "package data.hullmods;\nclass XRadar {}\n")
            target = root / "target"
            result = vendor_copy("hullmod", "x_radar", provider, target)
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["files"], ["data/hullmods/XRadar.java"])
        self.assertFalse((target / "data" / "hullmods" / "hull_mods.csv").exists())
        self.assertFalse((target / "data" / "hullmods" / "XRadar.java").exists())

    def test_apply_writes_the_csv_row_and_the_script(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", "package data.hullmods;\nclass XRadar {}\n")
            target = root / "target"
            result = vendor_copy("hullmod", "x_radar", provider, target, apply=True)
            self.assertEqual(result["status"], "APPLIED")
            csv_text = (target / "data" / "hullmods" / "hull_mods.csv").read_text(encoding="utf-8")
            self.assertIn("x_radar", csv_text)
            self.assertEqual((target / "data" / "hullmods" / "XRadar.java").read_text(encoding="utf-8"), "package data.hullmods;\nclass XRadar {}\n")

    def test_transitive_same_mod_script_dependency_is_also_copied(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(
                root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar",
                "package data.hullmods;\nimport data.scripts.plugins.XRadarPlugin;\nclass XRadar { XRadarPlugin p; }\n",
            )
            _write(provider / "data" / "scripts" / "plugins" / "XRadarPlugin.java", "package data.scripts.plugins;\nclass XRadarPlugin {}\n")
            target = root / "target"
            result = vendor_copy("hullmod", "x_radar", provider, target, apply=True)
            self.assertEqual(sorted(result["files"]), ["data/hullmods/XRadar.java", "data/scripts/plugins/XRadarPlugin.java"])
            self.assertTrue((target / "data" / "scripts" / "plugins" / "XRadarPlugin.java").is_file())

    def test_jar_only_script_is_reported_not_vendored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n")  # no loose script written
            target = root / "target"
            result = vendor_copy("hullmod", "x_radar", provider, target)
        self.assertEqual(result["status"], "PLANNED")
        self.assertEqual(result["files"], [])
        self.assertEqual(result["script_not_vendored"], "data.hullmods.XRadar")

    def test_id_not_found_in_source_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n")
            result = vendor_copy("hullmod", "does_not_exist", provider, root / "target")
        self.assertEqual(result["status"], "NOT_FOUND")

    def test_target_already_declaring_the_id_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", "x")
            target = root / "target"
            _write(target / "data" / "hullmods" / "hull_mods.csv", "name,id,script,desc\nOther,x_radar,data.hullmods.Other,d\n")
            result = vendor_copy("hullmod", "x_radar", provider, target)
        self.assertEqual(result["status"], "CONFLICT")

    def test_different_content_already_at_the_target_script_path_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", "package data.hullmods;\nclass XRadar { /* new */ }\n")
            target = root / "target"
            _write(target / "data" / "hullmods" / "XRadar.java", "package data.hullmods;\nclass XRadar { /* different, already here */ }\n")
            result = vendor_copy("hullmod", "x_radar", provider, target)
        self.assertEqual(result["status"], "CONFLICT")

    def test_identical_content_already_at_the_target_script_path_is_not_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = "package data.hullmods;\nclass XRadar {}\n"
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", body)
            target = root / "target"
            _write(target / "data" / "hullmods" / "XRadar.java", body)
            result = vendor_copy("hullmod", "x_radar", provider, target)
        self.assertEqual(result["status"], "PLANNED")

    def test_a_local_only_provider_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "no_licence_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", "x")
            policy = root / "policy.json"
            policy.write_text(json.dumps({"schema_version": 1, "mods": {"no_licence_mod": {"local_only": True, "reason": "no licence found"}}}), encoding="utf-8")
            result = vendor_copy("hullmod", "x_radar", provider, root / "target", policy_path=policy)
        self.assertEqual(result["status"], "REFUSED")
        self.assertIn("no licence found", result["reason"])

    def test_a_kind_other_than_hullmod_is_refused(self) -> None:
        result = vendor_copy("weapon", "x", Path("."), Path("."))
        self.assertEqual(result["status"], "REFUSED")

    def test_real_shields_formshield_is_refused_because_rebal_is_local_only(self) -> None:
        # Real corpus check: confirms the licence gate actually reads the real policy for the
        # exact mod/id this whole item's example was written from, not just a synthetic one.
        real_root = Path("In operation/Xenoargh-Rebal/working")
        if not real_root.is_dir():
            self.skipTest("real corpus not present")
        with tempfile.TemporaryDirectory() as directory:
            result = vendor_copy("hullmod", "shields_formshield", real_root, Path(directory) / "target")
        self.assertEqual(result["status"], "REFUSED")

    def test_cli_dry_run_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = _provider_mod(root, "provider_mod", "Radar,x_radar,data.hullmods.XRadar,desc\n", "data.hullmods.XRadar", "package data.hullmods;\nclass XRadar {}\n")
            target = root / "target"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["vendor-copy", "hullmod", "x_radar", str(provider), str(target), "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "PLANNED")
            self.assertFalse((target / "data" / "hullmods" / "hull_mods.csv").exists())

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["vendor-copy", "hullmod", "x_radar", str(provider), str(target), "--apply", "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["status"], "APPLIED")
            self.assertTrue((target / "data" / "hullmods" / "hull_mods.csv").exists())



if __name__ == "__main__":
    unittest.main()



if __name__ == "__main__":
    unittest.main()
