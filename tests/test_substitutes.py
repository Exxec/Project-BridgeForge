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


class LicenceAwareRevivalTests(unittest.TestCase):
    """ROADMAP P14 item 7/9: before recommending REVIVE_DEPENDENCY, check `release_policy.json` so
    a revived library that can't be redistributed is flagged right where the recommendation is
    made, not discovered later at `release` time.
    """

    def _policy(self, root: Path, mod_id: str, local_only: bool, reason: str = "") -> Path:
        path = root / "policy.json"
        path.write_text(json.dumps({"schema_version": 1, "mods": {mod_id: {"local_only": local_only, "reason": reason}}}), encoding="utf-8")
        return path

    def test_a_local_only_provider_is_flagged_in_the_revive_recommendation(self) -> None:
        from bridgeforge.substitutes import strategy

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = self._policy(root, "fxcore", True, "Xenoargh: no licence text, author unresponsive.")
            needed = {"class": {"data.scripts.fx_Particle"}}
            chosen = [{"mod_id": "fxcore", "name": "FX Core", "game_version": "0.91a", "targets_0.98a": False, "workspace": {"workspace": "Xenoargh-FX-Core", "manual_findings": 10}}]
            course, reason = strategy(needed, {"data.scripts.fx_Particle": 1}, chosen, set(), policy)
        self.assertEqual(course, "REVIVE_DEPENDENCY")
        self.assertIn("licence: local-only", reason)
        self.assertIn("Xenoargh: no licence text", reason)

    def test_a_redistributable_provider_gets_no_licence_note(self) -> None:
        from bridgeforge.substitutes import strategy

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = self._policy(root, "fxcore", False)
            needed = {"class": {"data.scripts.fx_Particle"}}
            chosen = [{"mod_id": "fxcore", "name": "FX Core", "game_version": "0.91a", "targets_0.98a": False, "workspace": {"workspace": "Xenoargh-FX-Core", "manual_findings": 10}}]
            course, reason = strategy(needed, {"data.scripts.fx_Particle": 1}, chosen, set(), policy)
        self.assertEqual(course, "REVIVE_DEPENDENCY")
        self.assertNotIn("licence", reason)

    def test_an_unlisted_mod_defaults_to_no_note(self) -> None:
        from bridgeforge.substitutes import strategy

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            policy = self._policy(root, "some-other-mod", True)
            needed = {"class": {"data.scripts.fx_Particle"}}
            chosen = [{"mod_id": "fxcore", "name": "FX Core", "game_version": "0.91a", "targets_0.98a": False, "workspace": {"workspace": "Xenoargh-FX-Core", "manual_findings": 10}}]
            course, reason = strategy(needed, {"data.scripts.fx_Particle": 1}, chosen, set(), policy)
        self.assertEqual(course, "REVIVE_DEPENDENCY")
        self.assertNotIn("licence", reason)

    def test_real_bundled_policy_flags_a_known_local_only_mod(self) -> None:
        from bridgeforge.substitutes import _licence_note

        note = _licence_note("xxx_ss_FX_mod_core", None)
        self.assertIn("licence: local-only", note)
        self.assertIn("Xenoargh", note)

    def test_dependency_substitutes_threads_the_custom_policy_path_through(self) -> None:
        # A workspace-backed revivable provider needs a real scan report on disk to compute
        # manual_findings (see _workspace_state); construct that real layout so this exercises
        # dependency_substitutes end to end, not just strategy() directly.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "oldsector_provider", "0.9.1a", "Red,old_red_army\n", "old_yak_wing,v\n")
            info_path = root / "mods" / "oldsector_provider" / "mod_info.json"
            info = json.loads(info_path.read_text(encoding="utf-8"))
            info["id"] = "oldsector"
            info_path.write_text(json.dumps(info), encoding="utf-8")

            ops = root / "ops"
            base = ops / "OldSector"
            _write(base / "working" / "mod_info.json", json.dumps({"id": "oldsector", "name": "OldSector"}))
            scan_dir = base / "reports" / "scan-1"
            _write(scan_dir / "bridgeforge.compat.json", json.dumps({"findings": [{"classification": "REVIEW"}]}))

            policy = self._policy(root, "oldsector", True, "No redistribution licence found.")
            report = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=ops, policy_path=policy)
        self.assertEqual(report["strategy"], "REVIVE_DEPENDENCY")
        self.assertIn("licence: local-only", report["reason"])


class ProviderIndexCacheTests(unittest.TestCase):
    """ROADMAP P14 item 6/2: a persistent corpus artefact, so a provider lookup is instant and
    still works for a mod that isn't currently installed/visible anywhere live.
    """

    def test_round_trips_through_the_cache_including_version_fields(self) -> None:
        from bridgeforge.substitutes import load_provider_index, update_provider_index

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "newsector", "0.98a-RC8", "Red,old_red_army\n", "old_yak_wing,v\n")
            mod_info = root / "mods" / "newsector" / "mod_info.json"
            info = json.loads(mod_info.read_text(encoding="utf-8"))
            info["version"] = "1.2.3+bf.4"
            mod_info.write_text(json.dumps(info), encoding="utf-8")
            cache_dir = root / "cache"

            summary = update_provider_index([root / "mods"], cache_dir)
            self.assertEqual(summary["provider_count"], 1)
            self.assertEqual(summary["mod_ids"], ["newsector"])
            self.assertTrue((cache_dir / "newsector.json").is_file())

            loaded = load_provider_index(cache_dir)
        self.assertEqual(len(loaded), 1)
        provider = loaded[0]
        self.assertEqual(provider.mod_id, "newsector")
        self.assertEqual(provider.version, "1.2.3+bf.4")
        self.assertEqual(provider.game_version, "0.98a-RC8")
        self.assertEqual(provider.provides["hullmod"], {"old_red_army"})
        self.assertEqual(provider.provides["wing"], {"old_yak_wing"})

    def test_loaded_cache_works_when_the_provider_folder_no_longer_exists(self) -> None:
        from bridgeforge.substitutes import load_provider_index, update_provider_index
        import shutil

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "gone", "0.98a-RC8", "Red,old_red_army\n", "")
            cache_dir = root / "cache"
            update_provider_index([root / "mods"], cache_dir)
            shutil.rmtree(root / "mods")  # the provider is no longer visible anywhere live

            loaded = load_provider_index(cache_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].provides["hullmod"], {"old_red_army"})

    def test_load_from_an_empty_or_missing_directory_returns_nothing(self) -> None:
        from bridgeforge.substitutes import load_provider_index

        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(load_provider_index(Path(directory) / "does-not-exist"), [])

    def test_a_second_update_overwrites_a_changed_providers_cache_entry(self) -> None:
        from bridgeforge.substitutes import load_provider_index, update_provider_index

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "growing", "0.98a-RC8", "Red,old_red_army\n", "")
            cache_dir = root / "cache"
            update_provider_index([root / "mods"], cache_dir)

            hull_csv = root / "mods" / "growing" / "data" / "hullmods" / "hull_mods.csv"
            hull_csv.write_text(hull_csv.read_text(encoding="utf-8") + "Blue,new_blue_mod\n", encoding="utf-8")
            update_provider_index([root / "mods"], cache_dir)

            loaded = load_provider_index(cache_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].provides["hullmod"], {"old_red_army", "new_blue_mod"})


class DependencyGraphTests(unittest.TestCase):
    """ROADMAP P14 item 6/3: which mods with revival work recorded need which missing content,
    and which unrevived provider (from the cache) would unblock the most of them.
    """

    def _revival_mod(self, root: Path, folder: str, needs_hullmod: str) -> Path:
        base = root / "In operation" / folder
        working = base / "working"
        _write(working / "mod_info.json", json.dumps({"id": folder.lower(), "name": folder}))
        _write(working / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": [needs_hullmod], "wings": []}))
        (base / "reports").mkdir()
        (base / "reports" / "REVIVAL_REPORT.md").write_text("IN_PROGRESS\n", encoding="utf-8")
        return working

    def test_an_uninstalled_cached_provider_is_credited_and_ranked(self) -> None:
        from bridgeforge.dependency_graph import build_dependency_graph
        from bridgeforge.substitutes import update_provider_index

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._revival_mod(root, "ModA", "missing_thing")
            self._revival_mod(root, "ModB", "missing_thing")
            self._revival_mod(root, "ModC", "some_other_thing")

            # The provider that covers "missing_thing" is indexed once, then removed - matching
            # an Ironclads-queue mod that was scanned once but isn't installed in the live rig.
            provider_root = root / "elsewhere"
            _provider(provider_root, "coverer", "0.98a-RC8", "X,missing_thing\n", "")
            cache_dir = root / "cache"
            update_provider_index([provider_root / "mods"], cache_dir)
            import shutil
            shutil.rmtree(provider_root)

            result = build_dependency_graph(root, vanilla_core=_core(root), provider_index_dir=cache_dir)
        self.assertEqual(result["mod_count"], 3)
        self.assertEqual(len(result["ranked_providers"]), 1)
        top = result["ranked_providers"][0]
        self.assertEqual(top["provider_mod_id"], "coverer")
        self.assertEqual(top["unblocks_count"], 2)
        self.assertEqual(top["unblocks"], ["ModA", "ModB"])
        self.assertEqual(top["covers"]["hullmod"], ["missing_thing"])
        self.assertIn("ModA", result["unresolved_by_mod"])
        self.assertNotIn("ModC", result["unresolved_by_mod"])  # its need has no cached coverer at all

    def test_a_need_with_no_cached_coverage_anywhere_is_not_a_ranked_blocker(self) -> None:
        from bridgeforge.dependency_graph import build_dependency_graph

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._revival_mod(root, "ModA", "truly_nowhere")
            result = build_dependency_graph(root, vanilla_core=_core(root), provider_index_dir=root / "empty-cache")
        self.assertEqual(result["ranked_providers"], [])
        self.assertEqual(result["unresolved_by_mod"], {})

    def test_cli_provider_index_update_and_dependency_graph(self) -> None:
        import contextlib
        import io

        from bridgeforge.cli import main

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._revival_mod(root, "ModA", "missing_thing")
            provider_root = root / "elsewhere" / "mods"
            _provider(root / "elsewhere", "coverer", "0.98a-RC8", "X,missing_thing\n", "")
            cache_dir = root / "cache"

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main(["provider-index-update", "--providers", str(provider_root), "--output", str(cache_dir), "--json"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(out.getvalue())["provider_count"], 1)

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exit_code = main([
                    "dependency-graph", "--repo-root", str(root), "--vanilla-core", str(_core(root)),
                    "--provider-index", str(cache_dir), "--json",
                ])
            self.assertEqual(exit_code, 0)
            payload = json.loads(out.getvalue())
            self.assertEqual(payload["ranked_providers"][0]["provider_mod_id"], "coverer")


if __name__ == "__main__":
    unittest.main()
