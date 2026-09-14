"""dependency-substitutes: replacing a missing or discontinued dependency (2026-09-14)."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.substitutes import Provider, dependency_substitutes, provider_for, rank, strategy


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _core(root: Path) -> Path:
    core = root / "core"
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\nArmor,heavyarmor\n")
    _write(core / "data" / "hulls" / "wing_data.csv", "id,variant\ntalon_wing,t\n")
    _write(core / "data" / "hulls" / "lasher.ship", json.dumps({"hullId": "lasher", "hullSize": "FRIGATE"}))
    _write(core / "data" / "weapons" / "weapon_data.csv", "name,id\nLight MG,lightmg\n")
    return core


def _addon(root: Path) -> Path:
    """A Communist-Clouds-like add-on: builds another mod's hull mod in and fields its wing."""
    mod = root / "addon"
    _write(mod / "mod_info.json", json.dumps({"id": "addon", "name": "Addon", "version": "1", "gameVersion": "0.98a-RC8", "dependencies": [{"id": "oldsector"}]}))
    _write(mod / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": ["old_red_army"], "wings": ["old_yak_wing"]}))
    return mod


def _provider(root: Path, name: str, game_version: str, hullmods: str, wings: str) -> Path:
    mod = root / "mods" / name
    _write(mod / "mod_info.json", json.dumps({"id": name, "name": name, "version": "1", "gameVersion": game_version}))
    _write(mod / "data" / "hullmods" / "hull_mods.csv", "name,id\n" + hullmods)
    _write(mod / "data" / "hulls" / "wing_data.csv", "id,variant\n" + wings)
    return mod


class SubstituteTests(unittest.TestCase):
    def test_exact_provider_for_0_98a_means_swap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "newsector", "0.98a-RC8", "Red,old_red_army\n", "old_yak_wing,v\n")
            _provider(root, "halfsector", "0.98a", "Red,old_red_army\n", "")
            report = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none")
        self.assertEqual(report["needed"], {"hullmod": ["old_red_army"], "wing": ["old_yak_wing"]})
        self.assertEqual(report["declared_dependencies_missing"], ["oldsector"])
        self.assertEqual([(c["mod_id"], c["verdict"]) for c in report["candidates"]], [("newsector", "EXACT"), ("halfsector", "PARTIAL")])
        self.assertEqual(report["strategy"], "SWAP")

    def test_a_full_provider_for_an_old_game_version_is_only_partial(self) -> None:
        provider = Provider("oldsector", "Old", "p", "0.9.1a")
        provider.provides["hullmod"] = {"old_red_army"}
        ranked = rank({"hullmod": {"old_red_army"}, "weapon": set(), "wing": set(), "hull": set(), "class": set()}, [provider])
        self.assertEqual(ranked[0]["verdict"], "PARTIAL")
        self.assertFalse(ranked[0]["targets_0.98a"])

    def test_nothing_visible_with_a_small_footprint_is_a_strip_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mods").mkdir()
            report = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none")
        self.assertEqual(report["candidates"], [])
        self.assertEqual(report["strategy"], "STRIP_FROM_MOD")  # 2 ids in 2 places

    def test_nothing_visible_with_a_large_footprint_escalates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mods").mkdir()
            mod = _addon(root)
            _write(mod / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": ["old_a", "old_b", "old_c"], "wings": ["old_yak_wing", "old_mig_wing"]}))
            report = dependency_substitutes(mod, [root / "mods"], vanilla_core=_core(root), ops=root / "none")
        self.assertEqual(report["strategy"], "ESCALATE")
        self.assertIn("No visible mod provides", report["reason"])

    def test_an_outdated_full_provider_means_revive_it_then_stripping_covers_small_gaps(self) -> None:
        # FX Example: FX Core (0.91a, a workspace here) provides all three classes.
        needed = {"class": {"data.scripts.fx_Particle", "data.scripts.fx_Trail", "data.scripts.fx_SharedLib"}}
        chosen = [{"name": "FX Core", "game_version": "0.91a", "targets_0.98a": False, "workspace": {"workspace": "Xenoargh-FX-Core", "manual_findings": 10}}]
        course, reason = strategy(needed, {"data.scripts.fx_Particle": 1}, chosen, set())
        self.assertEqual(course, "REVIVE_DEPENDENCY")
        self.assertIn("workspace Xenoargh-FX-Core: 10 MANUAL", reason)
        course, _reason = strategy({"weapon": {"thruster_fighter_sm"}}, {"thruster_fighter_sm": 1}, [], {"weapon:thruster_fighter_sm"})
        self.assertEqual(course, "STRIP_FROM_MOD")

    def test_an_id_only_a_large_workspace_has_is_stripped_not_revived(self) -> None:
        # Explorer Society: EZ Damage is current, but shields_formshield exists only in Rebal (84 MANUAL).
        needed = {"class": {"data.scripts.EZ_Damage"}, "hullmod": {"shields_formshield"}}
        chosen = [
            {"name": "EZ Damage", "game_version": "0.98a-RC8", "targets_0.98a": True, "covers": ["class:data.scripts.EZ_Damage"]},
            {"name": "Rebal", "game_version": "0.9a", "targets_0.98a": False, "covers": ["hullmod:shields_formshield"], "workspace": {"workspace": "Xenoargh-Rebal", "manual_findings": 84}},
        ]
        course, reason = strategy(needed, {"shields_formshield": 2}, chosen, set())
        self.assertEqual(course, "STRIP_FROM_MOD")
        self.assertIn("declare EZ Damage", reason)
        self.assertIn("hullmod:shields_formshield (only in Rebal", reason)

    def test_several_providers_together_can_cover_a_mod(self) -> None:
        # Rebal-like: one id from each of two current mods.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "redsector", "0.98a", "Red,old_red_army\n", "")
            _provider(root, "yaksector", "0.98a", "", "old_yak_wing,v\n")
            report = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none")
        self.assertEqual(sorted(item["mod_id"] for item in report["provider_set"]), ["redsector", "yaksector"])
        self.assertEqual(report["uncovered"], [])
        self.assertEqual(report["strategy"], "SWAP")

    def test_a_total_conversion_is_only_a_provider_when_declared(self) -> None:
        # Vacuum (a total conversion) defines thruster_fighter_sm, but Explorer Society can't run beside it.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tc = _provider(root, "vacuum", "0.98a-RC8", "Red,old_red_army\n", "old_yak_wing,v\n")
            info = json.loads((tc / "mod_info.json").read_text(encoding="utf-8"))
            info["totalConversion"] = True
            (tc / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            addon = _addon(root)
            report = dependency_substitutes(addon, [root / "mods"], vanilla_core=_core(root), ops=root / "none")
            self.assertEqual(report["provider_set"], [])
            self.assertEqual(report["total_conversions_excluded"], ["vacuum"])
            info = json.loads((addon / "mod_info.json").read_text(encoding="utf-8"))
            info["dependencies"] = [{"id": "vacuum"}]
            (addon / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            report = dependency_substitutes(addon, [root / "mods"], vanilla_core=_core(root), ops=root / "none")
        self.assertEqual(report["strategy"], "SWAP")

    def test_provider_lists_jar_classes_as_dotted_names(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "fxcore"
            _write(mod / "mod_info.json", json.dumps({"id": "fxcore", "name": "FX Core", "gameVersion": "0.91a"}))
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "core.jar", "w") as archive:
                archive.writestr("data/scripts/fx_Particle.class", b"\xca\xfe\xba\xbe")
            provider = provider_for(mod)
        self.assertIn("data.scripts.fx_Particle", provider.provides["class"])


if __name__ == "__main__":
    unittest.main()
