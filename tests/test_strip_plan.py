from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.strip_plan import find_content_references, strip_plan, vendor_copy, weapon_substitute_candidates, write_expected_changes


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


class FindContentReferencesTests(unittest.TestCase):
    def test_finds_hullmod_field_and_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": ["gone_mod"]}))
            refs = find_content_references(root, "hullmod", "gone_mod")
        self.assertEqual(refs, [{"file": "data/variants/x.variant", "field": "hullMods"}])

    def test_finds_faction_known_hullmods(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "world" / "factions" / "x.faction", json.dumps({"id": "x", "knownHullMods": {"hullMods": ["gone_mod"]}}))
            refs = find_content_references(root, "hullmod", "gone_mod")
        self.assertEqual(refs, [{"file": "data/world/factions/x.faction", "field": "knownHullMods.hullMods"}])

    def test_finds_weapon_group_slot_and_hull(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "weaponGroups": [{"weapons": {"WS001": "gone_wpn"}}]}))
            refs = find_content_references(root, "weapon", "gone_wpn")
        self.assertEqual(refs, [{"file": "data/variants/x.variant", "field": "weaponGroups.weapons.WS001", "slot_id": "WS001", "hull_id": "lasher"}])

    def test_finds_hull_id_and_skin_base_hull_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "gone_hull"}))
            _write(root / "data" / "hulls" / "skins" / "x.skin", json.dumps({"skinHullId": "x_skin", "baseHullId": "gone_hull"}))
            refs = find_content_references(root, "hull", "gone_hull")
        self.assertEqual(len(refs), 2)
        self.assertIn({"file": "data/variants/x.variant", "field": "hullId"}, refs)
        self.assertIn({"file": "data/hulls/skins/x.skin", "field": "baseHullId"}, refs)

    def test_no_false_positive_for_an_unrelated_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": ["other_mod"]}))
            self.assertEqual(find_content_references(root, "hullmod", "gone_mod"), [])


class WeaponSubstituteCandidatesTests(unittest.TestCase):
    def test_matches_by_type_and_size_only_vanilla_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            candidates = weapon_substitute_candidates(core, "ENERGY", "SMALL")
        self.assertEqual(candidates, ["vbeam"])

    def test_a_larger_weapon_does_not_fit_a_smaller_slot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            candidates = weapon_substitute_candidates(core, "BALLISTIC", "SMALL")
        self.assertEqual(candidates, ["lightmg"])  # bigcannon (LARGE) excluded

    def test_excludes_the_missing_id_itself(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            candidates = weapon_substitute_candidates(core, "ENERGY", "SMALL", exclude_id="vbeam")
        self.assertEqual(candidates, [])

    def test_no_vanilla_core_returns_nothing(self) -> None:
        self.assertEqual(weapon_substitute_candidates(None, "ENERGY", "SMALL"), [])


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


class StripPlanTests(unittest.TestCase):
    """ROADMAP P14 item 4: the exact edit list for a STRIP_FROM_MOD recommendation, plus real
    vanilla weapon substitute candidates "of the same slot type and size" - never a second
    implementation of the scanner's own slot-fit logic, never an invented match.
    """

    def _addon(self, root: Path, *, hull_mods: list[str] | None = None, weapon_slot: dict[str, str] | None = None, dependencies: list[dict] | None = None) -> Path:
        mod = root / "mod"
        info = {"id": "addon", "name": "Addon", "gameVersion": "0.98a-RC8"}
        if dependencies:
            info["dependencies"] = dependencies
        _write(mod / "mod_info.json", json.dumps(info))
        variant = {"variantId": "x", "hullId": "lasher", "hullMods": hull_mods or [], "wings": []}
        if weapon_slot:
            variant["weaponGroups"] = [{"weapons": weapon_slot}]
        _write(mod / "data" / "variants" / "x.variant", json.dumps(variant))
        return mod

    def test_a_weapon_with_no_provider_proposes_a_real_vanilla_substitute(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            mod = self._addon(root, weapon_slot={"WS001": "missing_beam"})
            plan = strip_plan(mod, provider_roots=[root / "no-providers"], vanilla_core=core)
        self.assertEqual(plan["hard_id_count"], 1)
        entry = plan["entries"][0]
        self.assertEqual(entry["kind"], "weapon")
        self.assertEqual(entry["id"], "missing_beam")
        self.assertEqual(entry["action"], "substitute")
        self.assertEqual(entry["substitute_candidates"], [{"slot_type": "ENERGY", "slot_size": "SMALL", "candidates": ["vbeam"]}])
        self.assertEqual(entry["references"][0]["file"], "data/variants/x.variant")

    def test_a_hullmod_with_no_provider_proposes_strip_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            mod = self._addon(root, hull_mods=["missing_hullmod"])
            plan = strip_plan(mod, provider_roots=[root / "no-providers"], vanilla_core=core)
        self.assertEqual(plan["hard_id_count"], 1)
        entry = plan["entries"][0]
        self.assertEqual(entry["kind"], "hullmod")
        self.assertEqual(entry["action"], "strip")
        self.assertEqual(entry["substitute_candidates"], [])

    def test_a_live_provider_covering_the_id_means_zero_hard_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            provider = root / "providers" / "base"
            _write(provider / "mod_info.json", json.dumps({"id": "base", "name": "Base", "gameVersion": "0.98a-RC8"}))
            _write(provider / "data" / "hullmods" / "hull_mods.csv", "name,id\nX,shared_hullmod\n")
            mod = self._addon(root, hull_mods=["shared_hullmod"], dependencies=[{"id": "base"}])
            plan = strip_plan(mod, provider_roots=[root / "providers"], vanilla_core=core)
        self.assertEqual(plan["hard_id_count"], 0)
        self.assertEqual(plan["entries"], [])

    def test_write_expected_changes_produces_a_real_proposed_expect_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            mod = self._addon(root, hull_mods=["missing_hullmod"])
            plan = strip_plan(mod, provider_roots=[root / "no-providers"], vanilla_core=core)
            expected_path = root / "expected.json"
            written = write_expected_changes(plan, expected_path, mod_id="addon", build="r1")
            self.assertEqual(len(written), 1)
            self.assertEqual(written[0]["status"], "UPDATED")
            payload = json.loads(expected_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["mod_id"], "addon")
            change = payload["changes"][0]
            self.assertEqual(change["status"], "PROPOSED")
            self.assertEqual(change["match"], {"change": "removed", "kind": "hullmod", "id": "missing_hullmod"})

    def test_write_expected_changes_sanitizes_a_mod_id_with_underscores(self) -> None:
        # EXP-<MOD>-nnn only accepts alphanumeric MOD; a real mod_id like "xxx_ss_FX_mod_core"
        # would otherwise fail behavior_discovery's own id pattern with an opaque error.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            mod = self._addon(root, hull_mods=["missing_hullmod"])
            plan = strip_plan(mod, provider_roots=[root / "no-providers"], vanilla_core=core)
            expected_path = root / "expected.json"
            written = write_expected_changes(plan, expected_path, mod_id="xxx_ss_fx_mod", build="r1")
        self.assertEqual(written[0]["status"], "UPDATED")
        self.assertNotIn("_", written[0]["id"])

    def test_cli_reports_and_writes_expected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            mod = self._addon(root, hull_mods=["missing_hullmod"])
            expected_path = root / "expected.json"
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "strip-plan", str(mod), "--vanilla-core", str(core),
                    "--providers", str(root / "no-providers"),
                    "--write-expected", str(expected_path), "--build", "r1", "--json",
                ])
            self.assertEqual(exit_code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["hard_id_count"], 1)
            self.assertEqual(len(payload["written_expected_changes"]), 1)
            self.assertTrue(expected_path.is_file())

    def test_cli_requires_build_with_write_expected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = _core(root)
            mod = self._addon(root, hull_mods=["missing_hullmod"])
            exit_code = main(["strip-plan", str(mod), "--vanilla-core", str(core), "--write-expected", str(root / "e.json")])
            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
