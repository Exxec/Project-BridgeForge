"""mod_info.json `replace`-array hygiene, settings.json breadth, and byte-identical vanilla copies.

RC8's ModManager reads `replace` into ModSpec.getFullOverrides() but silently drops any entry
ending in settings.json (bytecode-verified, 2026-09-22), so that file always merges and can never
be made authoritative however it is declared. Both facts are invisible to a mod author.

`vanilla-file-identical-copy` came out of executing ESCALATIONS E14 stage 0: Rebal shipped 14
hullmod scripts that were byte-identical to vanilla's, so they looked like overrides and changed
nothing. That also exposed a real defect in vanilla-script-shadow-repointable, which was telling
the mod to *repoint* those 14 when the right advice is to drop them - pinned here.
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod

VANILLA_SETTINGS = {"xpGainMult": 1, "maxShipsInFleet": 30, "playerMaxLevel": 15, "untouched": "keep",
                    "plugins": {"vanillaPlugin": "com.fs.Vanilla"}, "ruleCommandPackages": ["com.fs.rulecmd"]}


def _fixture(base: Path, *, replace: list[str] | None = None, settings: dict | None = None,
             ship_bytes: bytes | None = None, vanilla_bytes: bytes = b"VANILLA\n") -> tuple[Path, Path]:
    mod, core = base / "mod", base / "core"
    (mod / "data" / "hulls").mkdir(parents=True, exist_ok=True)
    (mod / "data" / "config").mkdir(parents=True, exist_ok=True)
    (core / "data" / "hulls").mkdir(parents=True, exist_ok=True)
    (core / "data" / "config").mkdir(parents=True, exist_ok=True)
    info: dict = {"id": "m", "name": "M", "version": "1", "gameVersion": "0.98a-RC8"}
    if replace is not None:
        info["replace"] = replace
    (mod / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    (core / "data" / "hulls" / "thing.ship").write_bytes(vanilla_bytes)
    if ship_bytes is not None:
        (mod / "data" / "hulls" / "thing.ship").write_bytes(ship_bytes)
    (core / "data" / "config" / "settings.json").write_text(json.dumps(VANILLA_SETTINGS), encoding="utf-8")
    if settings is not None:
        (mod / "data" / "config" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    return mod, core


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


class ReplaceArrayTests(unittest.TestCase):
    def test_a_settings_json_replace_entry_is_flagged_as_ignored_by_the_game(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), replace=["data\\config\\settings.json"], settings={"xpGainMult": 4})
            result = scan_mod(mod, TargetProfile(), core)
        findings = _ids(result, "replace-entry-ignored")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].evidence, ["data/config/settings.json"])

    def test_a_replace_entry_for_a_file_the_mod_does_not_ship_is_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), replace=["data/hulls/gone.ship"])
            result = scan_mod(mod, TargetProfile(), core)
        findings = _ids(result, "replace-entry-stale")
        self.assertEqual(len(findings), 1)
        self.assertIn("data/hulls/gone.ship", findings[0].evidence)

    def test_a_replace_entry_the_mod_actually_ships_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), replace=["data/hulls/thing.ship"], ship_bytes=b"MODDED\n")
            result = scan_mod(mod, TargetProfile(), core)
        self.assertEqual(_ids(result, "replace-entry-stale"), [])
        self.assertEqual(_ids(result, "replace-entry-ignored"), [])

    def test_no_replace_array_at_all_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory))
            result = scan_mod(mod, TargetProfile(), core)
        self.assertEqual(_ids(result, "replace-entry-stale"), [])
        self.assertEqual(_ids(result, "replace-entry-ignored"), [])


class SettingsBreadthTests(unittest.TestCase):
    def test_overridden_vanilla_settings_keys_are_reported_with_the_blast_radius(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), settings={"xpGainMult": 4, "maxShipsInFleet": 90, "modOnly": 1})
            result = scan_mod(mod, TargetProfile(), core)
        findings = _ids(result, "settings-json-override-accepted")  # 2 values: within the owner's limit of 25
        self.assertEqual(len(findings), 1)
        self.assertIn("overridden:2", findings[0].evidence)
        self.assertIn("xpGainMult", findings[0].evidence)
        self.assertNotIn("modOnly", findings[0].evidence)  # mod-only keys override nothing

    def test_entries_only_added_inside_vanilla_objects_are_not_overrides(self) -> None:
        # SEEKER/Exigency/Flu-X add plugins/graphics entries and ran normally (live, 2026-09-24):
        # settings.json merges objects key by key. A changed nested value or a list still counts.
        with tempfile.TemporaryDirectory() as directory:
            added = dict(VANILLA_SETTINGS, plugins={**VANILLA_SETTINGS["plugins"], "myPlugin": "data.scripts.My"})
            mod, core = _fixture(Path(directory), settings=added)
            found = scan_mod(mod, TargetProfile(), core)
            quiet = _ids(found, "settings-json-override-breadth") + _ids(found, "settings-json-override-accepted")
        with tempfile.TemporaryDirectory() as directory:
            changed = dict(VANILLA_SETTINGS, plugins={**VANILLA_SETTINGS["plugins"], "vanillaPlugin": "data.scripts.Other"},
                           ruleCommandPackages=["data.campaign.rulecmd"])
            mod, core = _fixture(Path(directory), settings=changed)
            loud = _ids(scan_mod(mod, TargetProfile(), core), "settings-json-override-accepted")
        self.assertEqual(quiet, [])
        self.assertIn("overridden:2", loud[0].evidence)
        self.assertIn("plugins.vanillaPlugin", loud[0].evidence)
        self.assertIn("ruleCommandPackages", loud[0].evidence)

    def test_owner_limit_baseline_and_a_changed_baseline(self) -> None:
        # Owner's held rule (ROADMAP 19, 2026-09-27): up to 25 values accepted and recorded; more, or a change, is REVIEW.
        import shutil

        from bridgeforge.revive import _scan
        from bridgeforge.scanner import SETTINGS_BASELINE_FILE

        many = {f"k{i}": i + 1 for i in range(26)}
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), settings=dict(VANILLA_SETTINGS, **many))
            (core / "data" / "config" / "settings.json").write_text(json.dumps(dict(VANILLA_SETTINGS, **{k: 0 for k in many})), encoding="utf-8")
            over = _ids(scan_mod(mod, TargetProfile(), core), "settings-json-override-breadth")
        self.assertEqual(len(over), 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod, core = _fixture(root / "fixture", settings={"xpGainMult": 4})
            working = root / "ws" / "working"
            shutil.copytree(mod, working)
            _scan(working, core)
            baseline = json.loads((working.parent / SETTINGS_BASELINE_FILE).read_text(encoding="utf-8"))
            (working / "data" / "config" / "settings.json").write_text(json.dumps({"xpGainMult": 4, "maxShipsInFleet": 90}), encoding="utf-8")
            changed = _ids(scan_mod(working, TargetProfile(), core), "settings-json-override-breadth")
        self.assertEqual(baseline["keys"], ["xpGainMult"])
        self.assertEqual(len(changed), 1)
        self.assertIn("maxShipsInFleet", changed[0].explanation)

    def test_settings_matching_vanilla_exactly_is_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), settings=dict(VANILLA_SETTINGS))
            result = scan_mod(mod, TargetProfile(), core)
        self.assertEqual(_ids(result, "settings-json-override-breadth"), [])


class IdenticalVanillaCopyTests(unittest.TestCase):
    def test_a_byte_identical_copy_of_a_vanilla_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), ship_bytes=b"VANILLA\n")
            result = scan_mod(mod, TargetProfile(), core)
        findings = _ids(result, "vanilla-file-identical-copy")
        self.assertEqual(len(findings), 1)
        self.assertIn("count:1", findings[0].evidence)
        self.assertIn("data/hulls/thing.ship", findings[0].evidence)
        # It is not also reported as a shadow: it overrides vanilla with vanilla.
        self.assertEqual(_ids(result, "vanilla-path-shadowing"), [])

    def test_a_genuinely_different_file_is_a_shadow_not_an_identical_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod, core = _fixture(Path(directory), ship_bytes=b"MODDED\n")
            result = scan_mod(mod, TargetProfile(), core)
        self.assertEqual(_ids(result, "vanilla-file-identical-copy"), [])
        self.assertEqual(len(_ids(result, "vanilla-path-shadowing")), 1)

    def test_an_identical_script_is_not_advised_to_be_repointed(self) -> None:
        """Regression (E14 stage 0): the repointable check told Rebal to rename and repoint 14
        byte-identical no-op copies. The right advice is to drop them, not repoint them."""
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            mod, core = base / "mod", base / "core"
            (mod / "data" / "hullmods").mkdir(parents=True)
            (core / "data" / "hullmods").mkdir(parents=True)
            (mod / "mod_info.json").write_text(
                json.dumps({"id": "m", "name": "M", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8"
            )
            source = "package data.hullmods;\npublic class BlastDoors {}\n"
            (mod / "data" / "hullmods" / "BlastDoors.java").write_text(source, encoding="utf-8")
            (core / "data" / "hullmods" / "BlastDoors.java").write_text(source, encoding="utf-8")
            with (mod / "data" / "hullmods" / "hull_mods.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["name", "id", "script"])
                writer.writerow(["Blast Doors", "blast_doors", "data.hullmods.BlastDoors"])
            result = scan_mod(mod, TargetProfile(), core)
        self.assertEqual(_ids(result, "vanilla-script-shadow-repointable"), [])
        self.assertEqual(len(_ids(result, "vanilla-file-identical-copy")), 1)


if __name__ == "__main__":
    unittest.main()
