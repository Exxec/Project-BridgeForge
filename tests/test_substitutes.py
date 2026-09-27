"""dependency-substitutes: replacing a missing or discontinued dependency (2026-09-14)."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.substitutes import Provider, dependency_substitutes, provider_for, rank, required_from_scan, strategy
import io
import shutil
from contextlib import redirect_stdout

from bridgeforge.cli import main
from bridgeforge.substitutes import (
    Provider,
    dependency_graph,
    dependency_substitutes,
    load_provider_index,
    provider_for,
    provider_index,
    rank,
    revival_licence,
    save_provider_index,
    strategy,
)


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


class ProviderIndexTests(unittest.TestCase):
    """ROADMAP P14 items 2-3: the provider index as an artefact, and the queue-wide dependency graph."""

    def test_index_round_trip_keeps_ids_and_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "oldsector", "0.9a", "Red,old_red_army\n", "old_yak_wing,v\n")
            info = root / "mods" / "oldsector" / "mod_info.json"
            info.write_text(json.dumps({"id": "oldsector", "name": "Old Sector", "gameVersion": "0.9a", "version": {"major": 1, "minor": 2, "patch": 3}}), encoding="utf-8")
            summary = save_provider_index(provider_index([root / "mods"]), root / "state" / "index.json", [root / "mods"])
            loaded = load_provider_index(root / "state" / "index.json")
        self.assertEqual(summary["providers"], 1)
        self.assertEqual((loaded[0].mod_id, loaded[0].version, loaded[0].game_version), ("oldsector", "1.2.3", "0.9a"))
        self.assertEqual(loaded[0].provides["hullmod"], {"old_red_army"})

    def test_an_indexed_provider_still_counts_after_its_folder_is_gone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "newsector", "0.98a-RC8", "Red,old_red_army\n", "old_yak_wing,v\n")
            save_provider_index(provider_index([root / "mods"]), root / "index.json", [root / "mods"])
            shutil.rmtree(root / "mods" / "newsector")
            without = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none")
            with_index = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none", index_path=root / "index.json")
            bad = root / "bad.json"
            bad.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_provider_index(bad)
        self.assertEqual(without["strategy"], "STRIP_FROM_MOD")
        self.assertEqual(with_index["strategy"], "SWAP")

    def _queue(self, root: Path) -> Path:
        queue = root / "In operation"
        for name, hullmod in (("AddonA", "old_red_army"), ("AddonB", "old_red_army"), ("AddonC", "rare_mod")):
            working = queue / name / "working"
            _write(working / "mod_info.json", json.dumps({"id": name.lower(), "name": name, "gameVersion": "0.98a-RC8"}))
            _write(working / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": [hullmod]}))
        _provider(root, "oldsector", "0.9a", "Red,old_red_army\n", "")
        _provider(root, "raresector", "0.9a", "Rare,rare_mod\n", "")
        return queue

    def test_graph_orders_revivals_by_how_many_queued_mods_they_unblock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            graph = dependency_graph(self._queue(root), [root / "mods"], vanilla_core=_core(root))
        self.assertEqual(graph["queued_mods"], 3)
        self.assertEqual([(e["mod_id"], e["unblocks"]) for e in graph["revival_order"]],
                         [("oldsector", ["AddonA", "AddonB"]), ("raresector", ["AddonC"])])
        self.assertEqual(graph["unprovided"], [])

    def test_graph_cli(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = self._queue(root)
            out = io.StringIO()
            with redirect_stdout(out):
                code = main(["dependency-graph", "--queue", str(queue), "--providers", str(root / "mods"), "--vanilla-core", str(_core(root))])
        self.assertEqual(code, 0)
        self.assertIn("1. revive oldsector (0.9a, not a workspace here", out.getvalue())
        self.assertIn("unblocks 2: AddonA, AddonB", out.getvalue())


class DependencyEvidenceOnBoardTests(unittest.TestCase):
    """Owner decision 2026-09-25: the graph (A) and per-mod results (C) are recorded evidence board reads."""

    def test_graph_write_records_queue_and_per_mod_evidence_and_board_shows_both(self) -> None:
        import os
        from datetime import datetime, timezone

        from bridgeforge.project_board import project_board, render_board
        from bridgeforge.substitutes import write_dependency_graph

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = ProviderIndexTests()._queue(root)
            now = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
            graph = dependency_graph(queue, [root / "mods"], vanilla_core=_core(root), write_reports=True, now=now)
            written = write_dependency_graph(graph, queue, now=now)
            recorded = json.loads((queue / "AddonA" / "reports" / "dependencies.json").read_text(encoding="utf-8"))
            markdown = (queue / "DEPENDENCY_GRAPH.md").read_text(encoding="utf-8")
            board = project_board(root)
            rendered = render_board(board)
            # A later scan makes AddonA's recorded dependencies stale.
            scan = queue / "AddonA" / "reports" / "scan-2" / "bridgeforge.compat.json"
            scan.parent.mkdir(parents=True)
            scan.write_text("{}", encoding="utf-8")
            later = (queue / "AddonA" / "reports" / "dependencies.json").stat().st_mtime + 10
            os.utime(scan, (later, later))
            stale = next(row for row in project_board(root)["mods"] if row["folder"] == "AddonA")
        self.assertEqual([Path(path).name for path in written], ["DEPENDENCY_GRAPH.json", "DEPENDENCY_GRAPH.md"])
        self.assertEqual((recorded["generated_at"], recorded["strategy"]), ("2026-09-25T12:00:00+00:00", "STRIP_FROM_MOD"))
        self.assertIn("| 1 | oldsector | 0.9a | 2: AddonA, AddonB |", markdown)
        row = next(row for row in board["mods"] if row["folder"] == "AddonA")
        self.assertEqual(row["dependencies"], {"strategy": "STRIP_FROM_MOD", "needs_revival_of": ["oldsector"], "unprovided": 0, "recorded": "2026-09-25"})
        self.assertIn("STRIP_FROM_MOD: revive oldsector (as of 2026-09-25)", rendered)
        self.assertIn("## Revival order (dependency-graph, as of 2026-09-25)", rendered)
        self.assertIn("1. oldsector: unblocks 2 (AddonA, AddonB)", rendered)
        self.assertNotIn("root-stray", json.dumps(board["layout_findings"]))  # the graph files are expected at the queue root
        self.assertIn("rescanned since dependencies.json was recorded; rerun dependency-substitutes --write", stale["warnings"])

    def test_per_mod_write_needs_the_convention_layout(self) -> None:
        from bridgeforge.substitutes import write_dependency_report

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                write_dependency_report({"strategy": "SWAP"}, root / "not-working")
            path = write_dependency_report({"strategy": "SWAP"}, root / "Mod" / "working")
            self.assertEqual(path, (root / "Mod" / "reports" / "dependencies.json").resolve())


class RevivalLicenceTests(unittest.TestCase):
    """ROADMAP P14 item 9: a dependency we would revive carries its release_policy.json decision."""

    def _policy(self, root: Path, mods: dict) -> Path:
        path = root / "policy.json"
        path.write_text(json.dumps({"schema_version": 1, "mods": mods, "default": {"local_only": False, "reason": None}}), encoding="utf-8")
        return path

    def test_decisions_by_id_or_name_and_unrecorded_is_not_releasable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            policy = self._policy(Path(directory), {"oldsector": {"local_only": True, "reason": "no licence"}, "Open Lib": {"local_only": False, "reason": "MIT"}})
            self.assertEqual(revival_licence("OLDSECTOR", None, policy), {"decision": "LOCAL_ONLY", "reason": "no licence"})
            self.assertEqual(revival_licence("openlib", "Open Lib", policy), {"decision": "RELEASABLE", "reason": "MIT"})
            self.assertEqual(revival_licence("unknown", "Unknown", policy)["decision"], "UNRECORDED")

    def test_revive_candidates_carry_their_licence_and_notes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "oldsector", "0.9a", "Red,old_red_army\n", "old_yak_wing,v\n")
            local = self._policy(root, {"oldsector": {"local_only": True, "reason": "author unreachable"}})
            report = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none", policy_path=local)
            self.assertEqual(report["provider_set"][0]["licence"], {"decision": "LOCAL_ONLY", "reason": "author unreachable"})
            self.assertEqual(len(report["licence_notes"]), 1)
            self.assertIn("cannot be published", report["licence_notes"][0])
            unrecorded = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none", policy_path=self._policy(root, {}))
            self.assertIn("no licence decision", unrecorded["licence_notes"][0])
            releasable = self._policy(root, {"oldsector": {"local_only": False, "reason": "permission on file"}})
            clean = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none", policy_path=releasable)
            self.assertEqual(clean["licence_notes"], [])

    def test_current_providers_need_no_licence_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _provider(root, "newsector", "0.98a-RC8", "Red,old_red_army\n", "old_yak_wing,v\n")
            report = dependency_substitutes(_addon(root), [root / "mods"], vanilla_core=_core(root), ops=root / "none")
        self.assertNotIn("licence", report["provider_set"][0])
        self.assertEqual(report["licence_notes"], [])


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


class RequiredFromScanTruncationTests(unittest.TestCase):
    """`content-reference-unresolved`/`source-import-unresolved`'s own evidence lines are capped
    (25/20 ids) for human readability, which used to be the only thing `required_from_scan` read -
    a mod with more ids than that would silently understate what dependency-substitutes/the strip
    planner see as needed. Fixed by preferring the full, untruncated data both checks now also
    store in `migration_context`.
    """

    def test_more_than_25_unresolved_content_ids_are_all_returned(self) -> None:
        from bridgeforge.scanner import scan_mod
        from bridgeforge.models import TargetProfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core"
            _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\nArmor,heavyarmor\n")
            _write(core / "data" / "hulls" / "wing_data.csv", "id,variant\ntalon_wing,t\n")
            _write(core / "data" / "hulls" / "lasher.ship", json.dumps({"hullId": "lasher", "hullSize": "FRIGATE"}))
            _write(core / "data" / "weapons" / "weapon_data.csv", "name,id\nLight MG,lightmg\n")
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "many", "name": "Many", "gameVersion": "0.98a-RC8"}))
            for i in range(30):
                _write(mod / "data" / "variants" / f"v{i}.variant", json.dumps({"variantId": f"v{i}", "hullId": "lasher", "hullMods": [f"missing_{i}"], "wings": []}))
            result = scan_mod(mod, TargetProfile(), core)
            needed, files = required_from_scan(result)
        self.assertEqual(len(needed["hullmod"]), 30)
        self.assertEqual(files["missing_15"], 1)

    def test_more_than_20_unresolved_imports_are_all_returned(self) -> None:
        from bridgeforge.scanner import scan_mod
        from bridgeforge.models import TargetProfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "many", "name": "Many"}))
            for i in range(25):
                _write(mod / "src" / f"Uses{i}.java", f"package data.scripts;\nimport data.scripts.other.Foreign{i};\nclass Uses{i} {{ Foreign{i} f; }}\n")
            result = scan_mod(mod, TargetProfile())
            needed, _files = required_from_scan(result)
        self.assertEqual(len(needed["class"]), 25)


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

    def test_include_intake_widens_the_dependent_side_to_report_less_mods(self) -> None:
        """ROADMAP P14 item 8 triage pass: the Ironclads intake queue's own cross-dependencies are
        exactly the unblocking signal this command exists to surface, and it has no reports yet."""
        from bridgeforge.dependency_graph import build_dependency_graph
        from bridgeforge.substitutes import update_provider_index

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "In operation" / "IntakeAddon"
            working = base / "working"
            _write(working / "mod_info.json", json.dumps({"id": "intakeaddon", "name": "IntakeAddon"}))
            _write(working / "data" / "variants" / "x.variant", json.dumps({"variantId": "x", "hullId": "lasher", "hullMods": ["missing_thing"], "wings": []}))
            # No reports/REVIVAL_REPORT.md - this is exactly the intake-queue shape.

            provider_root = root / "elsewhere"
            _provider(provider_root, "coverer", "0.98a-RC8", "X,missing_thing\n", "")
            cache_dir = root / "cache"
            update_provider_index([provider_root / "mods"], cache_dir)
            import shutil
            shutil.rmtree(provider_root)

            default_scope = build_dependency_graph(root, vanilla_core=_core(root), provider_index_dir=cache_dir)
            self.assertEqual(default_scope["ranked_providers"], [])

            widened = build_dependency_graph(root, vanilla_core=_core(root), provider_index_dir=cache_dir, require_report=False)
        self.assertEqual(len(widened["ranked_providers"]), 1)
        self.assertEqual(widened["ranked_providers"][0]["unblocks"], ["IntakeAddon"])

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


class WorkspaceStatusTests(unittest.TestCase):
    """A provider workspace's status is its report's final completion status, wherever the report sits."""

    def _state(self, report_path: str, text: str):
        from bridgeforge.substitutes import _workspace_state

        with tempfile.TemporaryDirectory() as directory:
            ops = Path(directory)
            _write(ops / "RevenantLib/working/mod_info.json", '{"id": "revenantlib"}')
            _write(ops / "RevenantLib" / report_path, text)
            return _workspace_state(ops, "revenantlib")

    def test_top_level_reports_folder_is_read_first(self) -> None:
        # RevenantLib's layout since 2026-09-25: reports/REVIVAL_REPORT.md beside PROVENANCE.md.
        self.assertEqual(self._state("reports/REVIVAL_REPORT.md", "## Status\n\n**READY_WITH_REVIEW_ITEMS**\n")["status"], "READY_WITH_REVIEW_ITEMS")
        self.assertEqual(self._state("working/reports/REVIVAL_REPORT.md", "READY\n")["status"], "READY")

    def test_a_trailing_note_is_not_a_status(self) -> None:
        # Before 2026-09-25 the last line was taken verbatim: RevenantLib's "status" was a sentence about FX Example.
        state = self._state("reports/REVIVAL_REPORT.md", "**READY_WITH_REVIEW_ITEMS** - notes\n\nFX Example still compile-checks PASS.\n")
        self.assertIsNone(state["status"])
