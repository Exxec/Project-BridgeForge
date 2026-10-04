from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.cli import main
from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.scanner import _load_lenient_json_file, scan_mod
from tests.save_fixtures import _class_entry, _u2, _utf8_entry, build_class_file, write_jar


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


def _class_file_with_personality_call(this_class: str, personality: str) -> bytes:
    """A minimal class file whose constant pool carries setPersonality(...) plus a string literal."""
    pool: list[bytes] = []

    def add_utf8(text: str) -> int:
        pool.append(_utf8_entry(text))
        return len(pool)

    def add_class(name_index: int) -> int:
        pool.append(_class_entry(name_index))
        return len(pool)

    def add_string(utf8_index: int) -> int:
        pool.append(b"\x08" + _u2(utf8_index))
        return len(pool)

    this_idx = add_class(add_utf8(this_class))
    super_idx = add_class(add_utf8("java/lang/Object"))
    add_utf8("setPersonality")
    add_string(add_utf8(personality))

    constant_pool_count = len(pool) + 1
    data = b"\xca\xfe\xba\xbe" + _u2(0) + _u2(52) + _u2(constant_pool_count)
    data += b"".join(pool)
    data += _u2(0x0021)
    data += _u2(this_idx)
    data += _u2(super_idx)
    data += _u2(0) + _u2(0) + _u2(0) + _u2(0)
    return data


class WingDataMissingRoleDescTests(unittest.TestCase):
    """VAC-R002: RC8 cannot load wing_data.csv without 'role desc'; a blank value is accepted."""

    def _mod(self, root: Path, wing_data: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        _write(root / "data" / "hulls" / "wing_data.csv", wing_data)
        return root / "data" / "hulls" / "wing_data.csv"

    def test_apply_appends_a_blank_column_padding_short_rows_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(root, "id,variant,tags,op cost\nwing_a,a_Wing,,4\n#note,x\nwing_b,b_Wing\n")
            self.assertEqual(len(_findings(scan_mod(root), "wing-data-missing-role-desc-column")), 1)
            applied = apply_fix(compute_fix(root, "wing-data-missing-role-desc-column"))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            self.assertEqual(path.read_text(encoding="utf-8"), "id,variant,tags,op cost,role desc\nwing_a,a_Wing,,4,\n#note,x,,,\nwing_b,b_Wing,,,\n")
            self.assertEqual(_findings(scan_mod(root), "wing-data-missing-role-desc-column"), [])

    def test_comma_only_padding_rows_are_not_mistaken_for_multiline_fields(self) -> None:
        # Cobalt Arms pads wing_data.csv with rows of bare commas; the fixer wrongly refused it.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(root, "id,variant,role,,number\nwing_a,a,ASSAULT,,\n,,,,\n,,,,26\n")
            apply_fix(compute_fix(root, "wing-data-missing-role-desc-column"))
            self.assertEqual(path.read_text(encoding="utf-8"), "id,variant,role,,number,role desc\nwing_a,a,ASSAULT,,,\n,,,,,\n,,,,26,\n")

    def test_refuses_when_present_or_rows_span_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "id,role desc\nwing_a,x\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-data-missing-role-desc-column")
            self._mod(root, 'id,variant\nwing_a,"two\nlines"\n')
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-data-missing-role-desc-column")


class RulesFireBestPopulateOptionsFixerTests(unittest.TestCase):
    """VAC-DIALOG-01: FireBest PopulateOptions -> FireAll PopulateOptions, same column."""

    def _mod(self, root: Path, rules_csv: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        _write(root / "data" / "campaign" / "rules.csv", rules_csv)
        return root / "data" / "campaign" / "rules.csv"

    def test_apply_swaps_firebest_for_fireall_and_rescan_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(
                root,
                "id,trigger,command,conditions\n"
                "vac_after_bounty,BAR_EVENT,FireBest PopulateOptions,\n"
                "vac_leave,BAR_EVENT,FireAll PopulateOptions,\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "rules-firebest-populate-options")), 1)
            applied = apply_fix(compute_fix(root, "rules-firebest-populate-options"))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("FireAll PopulateOptions"), 2)
            self.assertNotIn("FireBest", text)
            self.assertEqual(_findings(scan_mod(root), "rules-firebest-populate-options"), [])

    def test_refuses_when_no_firebest_populate_options_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, "id,trigger,command\nvac_leave,BAR_EVENT,FireAll PopulateOptions\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "rules-firebest-populate-options")


class PersonalityIdUnknownFixerTests(unittest.TestCase):
    """SK13-1d: setPersonality("suicidal"/"cowardly"/"fearless") -> RC8's own valid ids."""

    def _mod(self, root: Path, source: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        path = root / "data" / "scripts" / "FixtureMission.java"
        _write(path, source)
        return path

    def test_apply_rewrites_each_legacy_id_to_its_rc8_replacement_and_rescan_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(
                root,
                "class FixtureMission {\n"
                "  void go(PersonAPI p) {\n"
                '    p.setPersonality("cowardly");\n'
                '    p.setPersonality("suicidal");\n'
                '    p.setPersonality("fearless");\n'
                "  }\n"
                "}\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "personality-id-unknown")), 1)
            applied = apply_fix(compute_fix(root, "personality-id-unknown"))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn('setPersonality("timid")', text)
            self.assertEqual(text.count('setPersonality("reckless")'), 2)
            self.assertNotIn("cowardly", text)
            self.assertNotIn("suicidal", text)
            self.assertNotIn("fearless", text)
            self.assertEqual(_findings(scan_mod(root), "personality-id-unknown"), [])

    def test_refuses_when_only_a_jar_bundled_source_has_the_legacy_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            class_file = _class_file_with_personality_call("FixtureScript", "suicidal")
            write_jar(root / "jars" / "fixture.jar", {"FixtureScript.class": class_file})
            self.assertEqual(len(_findings(scan_mod(root), "personality-id-unknown")), 1)
            with self.assertRaises(FixerError):
                compute_fix(root, "personality-id-unknown")

    def test_refuses_when_no_unknown_personality_id_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, 'class X { void go(PersonAPI p) { p.setPersonality("reckless"); } }\n')
            with self.assertRaises(FixerError):
                compute_fix(root, "personality-id-unknown")


class FactionTraitWeightLegacyPersonalityIdFixerTests(unittest.TestCase):
    """SK13-1d, reached through faction-level generation: cowardly/suicidal/fearless in a
    traits.<role> weight block -> RC8's own ids, merging suicidal+fearless's weights into reckless
    rather than leaving a silently-colliding duplicate JSON key."""

    def _mod(self, root: Path, faction_text: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        path = root / "data" / "world" / "factions" / "fixture.faction"
        _write(path, faction_text)
        return path

    def test_apply_renames_and_merges_and_rescan_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(
                root,
                '{"id":"fixture","traits":{"admiral":{},"captain":{\n'
                '\t"cowardly":1,\n\t"cautious":1,\n\t"steady":1,\n\t"aggressive":1,\n\t"suicidal":1,\n\t"fearless":1,\n'
                "}}}\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "faction-trait-weight-legacy-personality-id")), 1)
            applied = apply_fix(compute_fix(root, "faction-trait-weight-legacy-personality-id"))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn('"timid":1', text)
            self.assertIn('"reckless":2', text)
            self.assertNotIn("cowardly", text)
            self.assertNotIn("suicidal", text)
            self.assertNotIn("fearless", text)
            self.assertEqual(_findings(scan_mod(root), "faction-trait-weight-legacy-personality-id"), [])
            # everything else (admiral's empty block, key order, formatting) survives untouched
            data = _load_lenient_json_file(root / "data" / "world" / "factions" / "fixture.faction")
            self.assertEqual(data["traits"]["admiral"], {})

    def test_refuses_when_the_merge_target_already_has_its_own_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(
                root,
                '{"id":"fixture","traits":{"captain":{"cowardly":1,"timid":3,"cautious":1}}}\n',
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "faction-trait-weight-legacy-personality-id")

    def test_refuses_when_no_legacy_id_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, '{"id":"fixture","traits":{"captain":{"timid":1,"reckless":1}}}\n')
            with self.assertRaises(FixerError):
                compute_fix(root, "faction-trait-weight-legacy-personality-id")


class ShipRolesWingIdFixerTests(unittest.TestCase):
    """0.98a's shipRoles only resolves variant ids; a wing id there is fatal at load. The fixer
    renames each flagged key to the wing's own wing_data.csv 'variant' column value."""

    def _mod(self, root: Path, faction_text: str, wing_data_text: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        path = root / "data" / "world" / "factions" / "fixture.faction"
        _write(path, faction_text)
        _write(root / "data" / "hulls" / "wing_data.csv", wing_data_text)
        return path

    def test_apply_renames_to_the_variant_id_and_rescan_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(
                root,
                '{"id":"fixture","shipRoles":{"interceptor":{\n\t"fx_wing":10,\n\t"fallback":{"fighter":1}\n}}}\n',
                "id,variant,role\nfx_wing,fx_wing_standard,INTERCEPTOR\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "shiproles-wing-id")), 1)
            applied = apply_fix(compute_fix(root, "shiproles-wing-id"))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            text = path.read_text(encoding="utf-8")
            self.assertIn('"fx_wing_standard":10', text)
            self.assertNotIn("fx_wing\"", text)
            self.assertEqual(_findings(scan_mod(root), "shiproles-wing-id"), [])
            data = _load_lenient_json_file(root / "data" / "world" / "factions" / "fixture.faction")
            self.assertEqual(data["shipRoles"]["interceptor"]["fallback"], {"fighter": 1})

    def test_two_roles_sharing_the_same_wing_id_both_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(
                root,
                '{"id":"fixture","shipRoles":{"interceptor":{"fx_wing":10},"escortSmall":{"fx_wing":8}}}\n',
                "id,variant,role\nfx_wing,fx_wing_standard,INTERCEPTOR\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "shiproles-wing-id")), 2)
            apply_fix(compute_fix(root, "shiproles-wing-id"))
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count('"fx_wing_standard"'), 2)
            self.assertEqual(_findings(scan_mod(root), "shiproles-wing-id"), [])

    def test_refuses_when_the_wing_has_no_variant_column_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(
                root,
                '{"id":"fixture","shipRoles":{"interceptor":{"fx_wing":10}}}\n',
                "id,variant,role\nfx_wing,,INTERCEPTOR\n",
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "shiproles-wing-id")

    def test_refuses_when_no_wing_id_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(
                root,
                '{"id":"fixture","shipRoles":{"interceptor":{"fx_wing_standard":10}}}\n',
                "id,variant,role\nfx_wing,fx_wing_standard,INTERCEPTOR\n",
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "shiproles-wing-id")


class AssaultRoleIsValidTests(unittest.TestCase):
    """RC8's WingRole enum still has ASSAULT (javap, 2026-09-14); the old rewrite to FIGHTER is retired."""

    def test_assault_wings_raise_nothing_and_have_no_rewrite_fixer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "hulls" / "wing_data.csv", "id,role,role desc,op cost\nwing_a,ASSAULT,desc,4\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "wing-role-assault-removed"), [])
            self.assertEqual(_findings(result, "fighter-wing-role-invalid"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "wing-role-assault-removed")


class CarrierBaysProposalFixerTests(unittest.TestCase):
    """`fix <mod> --finding carrier-bays-proposal --hull ID=N` (roadmap P14 item 6)."""

    def _mod(self, root: Path, ship_data: str) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        path = root / "data" / "hulls" / "ship_data.csv"
        _write(path, ship_data)
        return path

    def test_pre08_hangar_schema_adds_column_blank_for_untouched_hulls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(
                root,
                "name,id,designation,system id,hangar,hints\nBig,big,Carrier,,6,\nSmall,small,Frigate,,,\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "carrier-bays-proposal")), 1)
            applied = apply_fix(compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=2"]}))
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "name,id,designation,system id,hangar,hints,fighter bays\nBig,big,Carrier,,6,,2\nSmall,small,Frigate,,,,\n",
            )
            # "big" is no longer proposed (it has a fighter bays value now); "small" has no evidence
            # of its own, so the check is fully quiet.
            self.assertEqual(_findings(scan_mod(root), "carrier-bays-proposal"), [])

    def test_existing_fighter_bays_column_is_overwritten_for_the_approved_hull_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(
                root,
                "name,id,designation,fighter bays,hints\nBig,big,Carrier,,\nSmall,small,Frigate,,\n",
            )
            apply_fix(compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=3"]}))
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                "name,id,designation,fighter bays,hints\nBig,big,Carrier,3,\nSmall,small,Frigate,,\n",
            )

    def test_multiple_hulls_in_one_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(
                root,
                "name,id,designation,hangar\nBig,big,Carrier,6\nMed,med,Cruiser,3\nSmall,small,Frigate,\n",
            )
            apply_fix(compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=4", "med=2"]}))
            text = path.read_text(encoding="utf-8")
            self.assertIn("Big,big,Carrier,6,4\n", text)
            self.assertIn("Med,med,Cruiser,3,2\n", text)
            self.assertIn("Small,small,Frigate,,\n", text)

    def test_only_the_approved_hull_stops_being_proposed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(
                root,
                "name,id,designation,hangar\nBig,big,Carrier,6\nMed,med,Cruiser,3\n",
            )
            self.assertEqual(len(_findings(scan_mod(root), "carrier-bays-proposal")), 1)
            apply_fix(compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=4"]}))
            remaining = _findings(scan_mod(root), "carrier-bays-proposal")
            self.assertEqual(len(remaining), 1)
            self.assertFalse([item for item in remaining[0].evidence if item.startswith("big:")])
            self.assertTrue([item for item in remaining[0].evidence if item.startswith("med:")])

    def test_refuses_unknown_hull_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {"hulls": ["ghost=2"]})

    def test_refuses_a_value_above_vanillas_own_maximum(self) -> None:
        # RC8's own ship_data.csv maximum is 6 (the Astral); see fixers._MAX_FIGHTER_BAYS.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=7"]})

    def test_refuses_a_negative_value(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=-1"]})

    def test_zero_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            apply_fix(compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=0"]}))
            self.assertIn("Big,big,Carrier,6,0\n", path.read_text(encoding="utf-8"))

    def test_requires_at_least_one_hull(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {})

    def test_malformed_hull_assignment_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {"hulls": ["big"]})  # no '='
            with self.assertRaises(FixerError):
                compute_fix(root, "carrier-bays-proposal", {"hulls": ["big=two"]})  # not an integer

    def test_cli_apply_and_resolved_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            exit_code = main(["fix", str(root), "--finding", "carrier-bays-proposal", "--hull", "big=4", "--apply", "--json"])
            self.assertEqual(exit_code, 0)  # the finding is fully resolved (one hull, now fixed)
            self.assertEqual(_findings(scan_mod(root), "carrier-bays-proposal"), [])

    def test_cli_dry_run_does_not_write(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(root, "name,id,designation,hangar\nBig,big,Carrier,6\n")
            original = path.read_text(encoding="utf-8")
            exit_code = main(["fix", str(root), "--finding", "carrier-bays-proposal", "--hull", "big=4"])
            self.assertEqual(exit_code, 0)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


class TargetInterfaceMethodMissingTests(unittest.TestCase):
    SYSTEM = "package data.shipsystems.scripts;\nimport com.fs.starfarer.api.plugins.ShipSystemStatsScript;\npublic class Old implements ShipSystemStatsScript {\n    public void apply() {}\n    public float getActiveOverride(com.fs.starfarer.api.combat.ShipAPI s) { return 2f; }\n}\n"
    HIT = "package data.scripts;\npublic class Hit implements OnHitEffectPlugin {\n    public void onHit(DamagingProjectileAPI projectile, CombatEntityAPI target, Vector2f point, boolean shieldHit, CombatEngineAPI engine) { engine.getTotalElapsedTime(false); }\n}\n"
    MOD = "package data.hullmods;\npublic class Tow implements HullModEffect {\n    public void init() {}\n}\n"

    def test_loose_scripts_gain_rc8_members_without_touching_bodies_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "shipsystems" / "scripts" / "Old.java", self.SYSTEM)
            _write(root / "data" / "scripts" / "Hit.java", self.HIT)
            _write(root / "data" / "hullmods" / "Tow.java", self.MOD)
            self.assertEqual(len(_findings(scan_mod(root), "target-interface-method-missing")), 8)
            apply_fix(compute_fix(root, "target-interface-method-missing"))
            system = (root / "data" / "shipsystems" / "scripts" / "Old.java").read_text(encoding="utf-8")
            self.assertIn("return 2f;", system)  # an existing override is kept
            self.assertEqual(system.count("getActiveOverride"), 1)
            self.assertIn("public int getUsesOverride(com.fs.starfarer.api.combat.ShipAPI ship) { return -1; }", system)
            self.assertIn("com.fs.starfarer.api.combat.listeners.ApplyDamageResultAPI damageResult, CombatEngineAPI engine)", (root / "data" / "scripts" / "Hit.java").read_text(encoding="utf-8"))
            tow = (root / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8")
            self.assertIn("showInRefitScreenModPickerFor", tow)
            self.assertIn("isSModEffectAPenalty() { return false; }", tow)
            self.assertEqual(_findings(scan_mod(root), "target-interface-method-missing"), [])

    def test_jar_sources_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "jars" / "src" / "data" / "scripts" / "Hit.java", self.HIT)
            with self.assertRaises(FixerError) as caught:
                compute_fix(root, "target-interface-method-missing")
            self.assertIn("jar sources need a rebuild", str(caught.exception))


class RemovedApiCallTests(unittest.TestCase):
    """removed-api-call: 0.6's getSector().createFleet(...) has no RC8 SectorAPI equivalent (javap,
    2026-09-14); the fixer ports call sites to bf.legacyfleets.LegacyFleets (RevenantLib) instead.
    RevenantLib 1.1.0+bf.1 folded in the standalone BF Legacy Fleets library (owner decision 2026-09-15),
    so the dependency this fixer adds is `revenantlib`, not the retired `bf_legacy_fleets`."""

    SPAWN_SRC = (
        "package data.scripts.world;\n"
        "public class Spawn extends BaseSpawnPoint {\n"
        "    protected CampaignFleetAPI spawnFleet() {\n"
        "        // getSector().createFleet(\"x\", \"y\") -- commented out, must stay untouched\n"
        "        CampaignFleetAPI fleet = getSector().createFleet(\"gekelonian\", type);\n"
        "        return fleet;\n"
        "    }\n"
        "}\n"
    )
    CONVOY_SRC = (
        "package data.scripts.world;\n"
        "public class Convoy extends BaseSpawnPoint {\n"
        "    protected CampaignFleetAPI spawnFleet() {\n"
        "        return Global.getSector().createFleet(\"gekelonian\", \"heavy\");\n"
        "    }\n"
        "}\n"
    )

    def _mod(self, root: Path, mod_info: str = '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}') -> None:
        _write(root / "mod_info.json", mod_info)
        _write(root / "data" / "scripts" / "world" / "Spawn.java", self.SPAWN_SRC)
        _write(root / "data" / "scripts" / "world" / "Convoy.java", self.CONVOY_SRC)

    def test_rewrites_both_receiver_forms_leaves_comments_alone_adds_dependency_once_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 1)

            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(
                changed,
                {"data/scripts/world/Spawn.java", "data/scripts/world/Convoy.java", "mod_info.json"},
            )
            applied = apply_fix(plan)
            self.assertTrue(all(Path(item["backup"]).is_file() for item in applied))

            spawn_lines = (root / "data" / "scripts" / "world" / "Spawn.java").read_text(encoding="utf-8").split("\n")
            # The commented-out call keeps its original (unqualified) receiver text untouched...
            self.assertIn('// getSector().createFleet("x", "y") -- commented out', spawn_lines[3])
            # ...while the real, active call is rewritten.
            self.assertNotIn("getSector().createFleet(", spawn_lines[4])
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("gekelonian", type);', spawn_lines[4])

            convoy_text = (root / "data" / "scripts" / "world" / "Convoy.java").read_text(encoding="utf-8")
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("gekelonian", "heavy");', convoy_text)
            self.assertNotIn("Global.getSector()", convoy_text)

            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])

    def test_existing_dependencies_array_gets_the_entry_prepended_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(
                root,
                '{\n\t"id":"fixture",\n\t"dependencies": [\n\t\t{"id": "lw_lazylib", "name": "LazyLib"}\n\t]\n}\n',
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(
                mod_info["dependencies"],
                [{"id": "revenantlib", "name": "RevenantLib"}, {"id": "lw_lazylib", "name": "LazyLib"}],
            )

    def test_dependency_already_present_is_not_duplicated_and_only_source_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, '{"id":"fixture","dependencies":[{"id":"revenantlib","name":"RevenantLib"}]}')
            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(changed, {"data/scripts/world/Spawn.java", "data/scripts/world/Convoy.java"})
            apply_fix(plan)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])

    def test_disabled_files_are_never_touched_or_counted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(root / "data" / "scripts" / "world" / "disabled_files" / "Old.java", self.SPAWN_SRC)
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_jar_sources_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(root / "jars" / "src" / "data" / "scripts" / "world" / "Spawn.java", self.SPAWN_SRC)
            with self.assertRaises(FixerError) as caught:
                compute_fix(root, "removed-api-call")
            self.assertIn("jar sources need a rebuild", str(caught.exception))

    def test_refuses_when_no_removed_call_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_refuses_when_dependencies_is_not_an_array(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root, '{"id":"fixture","dependencies":"oops"}')
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_global_getsectorapi_create_fleet_receiver_is_also_rewritten(self) -> None:
        # E6, 2026-09-14: javap confirms Global.getSectorAPI() returns SectorAPI too.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Spawn.java",
                'package data.scripts.world;\npublic class Spawn extends BaseSpawnPoint {\n'
                '    CampaignFleetAPI f() { return Global.getSectorAPI().createFleet("CAPSCO", type); }\n}\n',
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            text = (root / "data" / "scripts" / "world" / "Spawn.java").read_text(encoding="utf-8")
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("CAPSCO", type);', text)
            self.assertNotIn("getSectorAPI()", text)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])


class AddMessageRewriteTests(unittest.TestCase):
    """removed-api-call, E6 (2026-09-14): RC8's SectorAPI has no addMessage; the fixer inserts
    .getCampaignUI() before .addMessage(, keeping the original receiver, since CampaignUIAPI has it."""

    CONVOY_SRC = (
        "package data.scripts.world;\n"
        "public class Convoy extends BaseSpawnPoint {\n"
        "    protected CampaignFleetAPI spawnFleet() {\n"
        "        // Global.getSectorAPI().addMessage(\"x\") -- commented out, must stay untouched\n"
        "        Global.getSectorAPI().addMessage(\"A CAPSCO supply convoy is in-system\");\n"
        "        return null;\n"
        "    }\n"
        "    private Script createArrivedScript() {\n"
        "        return new Script() {\n"
        "            public void run() {\n"
        "                Global.getSectorAPI().addMessage(\"delivered\");\n"
        "            }\n"
        "        };\n"
        "    }\n"
        "    private void bare() {\n"
        "        getSector().addMessage(\"bare receiver\");\n"
        "    }\n"
        "}\n"
    )

    def _mod(self, root: Path) -> Path:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
        path = root / "data" / "scripts" / "world" / "Convoy.java"
        _write(path, self.CONVOY_SRC)
        return path

    def test_inserts_getcampaignui_before_addmessage_keeping_receiver_and_does_not_add_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            path = self._mod(root)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 1)

            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            # mod_info.json is untouched: no createFleet rewrite happened in this run, so no dependency is added.
            self.assertEqual(changed, {"data/scripts/world/Convoy.java"})
            apply_fix(plan)

            lines = path.read_text(encoding="utf-8").split("\n")
            # The commented-out call keeps its original text untouched...
            self.assertIn('// Global.getSectorAPI().addMessage("x") -- commented out', lines[3])
            # ...while the real calls are rewritten, receiver kept, .getCampaignUI() inserted before .addMessage(.
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("A CAPSCO supply convoy is in-system");', lines[4])
            text = path.read_text(encoding="utf-8")
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("delivered");', text)
            self.assertIn('getSector().getCampaignUI().addMessage("bare receiver");', text)

            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertNotIn("dependencies", mod_info)

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])

    def test_create_fleet_and_add_message_together_rewrite_both_and_add_dependency_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Convoy.java",
                "package data.scripts.world;\npublic class Convoy extends BaseSpawnPoint {\n"
                "    CampaignFleetAPI spawnFleet() {\n"
                '        CampaignFleetAPI fleet = getSector().createFleet("CAPSCO", "supplyConvoy");\n'
                '        Global.getSectorAPI().addMessage("under way");\n'
                "        return fleet;\n"
                "    }\n}\n",
            )
            plan = compute_fix(root, "removed-api-call")
            apply_fix(plan)
            text = (root / "data" / "scripts" / "world" / "Convoy.java").read_text(encoding="utf-8")
            self.assertIn('bf.legacyfleets.LegacyFleets.createFleet("CAPSCO", "supplyConvoy");', text)
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("under way");', text)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])


class CrewXPLevelRewriteTests(unittest.TestCase):
    """removed-api-call, owner decision 2026-09-15 ("crew quality no longer exists in RC8; crew counts
    are kept"): RC8's CargoAPI no longer nests CrewXPLevel, and its plain addCrew(int) drops the
    crew-quality level; the fixer drops the level and keeps the count. addCrew(CrewXPLevel.X, n) ->
    addCrew(n); a MissionDefinitionAPI.addToFleet trailing CrewXPLevel argument is dropped the same way;
    the now-unresolvable import is removed. No `bf.` call is introduced, so this rule never adds a
    dependency (createFleet/addPlanet/addOrbitalStation do; CrewXPLevel does not)."""

    def test_addcrew_leading_crewxplevel_argument_is_dropped_import_removed_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "scripts" / "world" / "Convoy.java"
            _write(
                path,
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "    void crew(CargoAPI cargo) { cargo.addCrew(CrewXPLevel.VETERAN, 5); }\n}\n",
            )
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 1)

            plan = compute_fix(root, "removed-api-call")
            # No `bf.` call is introduced, so no mod_info.json dependency change.
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(changed, {"data/scripts/world/Convoy.java"})
            apply_fix(plan)

            text = path.read_text(encoding="utf-8")
            self.assertNotIn("CrewXPLevel", text)
            self.assertIn("cargo.addCrew(5);", text)
            self.assertNotIn("dependencies", json.loads((root / "mod_info.json").read_text(encoding="utf-8")))

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])

    def test_addtofleet_trailing_crewxplevel_argument_is_dropped_both_overload_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "missions" / "m" / "MissionDefinition.java"
            _write(
                path,
                "package data.missions.m;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class MissionDefinition implements MissionDefinitionPlugin {\n"
                "    public void defineMission(MissionDefinitionAPI api) {\n"
                '        api.addToFleet(FleetSide.PLAYER, "hull_Standard", FleetMemberType.SHIP, "Name", true, CrewXPLevel.REGULAR);\n'
                '        api.addToFleet(FleetSide.PLAYER, "wing", FleetMemberType.FIGHTER_WING, true, CrewXPLevel.VETERAN);\n'
                "    }\n}\n",
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("CrewXPLevel", text)
            self.assertIn('api.addToFleet(FleetSide.PLAYER, "hull_Standard", FleetMemberType.SHIP, "Name", true);', text)
            self.assertIn('api.addToFleet(FleetSide.PLAYER, "wing", FleetMemberType.FIGHTER_WING, true);', text)
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])

    def test_addmessage_and_crewxplevel_in_the_same_file_are_both_rewritten_no_dependency_added(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "scripts" / "world" / "Convoy.java"
            _write(
                path,
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "    void spawn(CargoAPI cargo) {\n"
                "        cargo.addCrew(CrewXPLevel.VETERAN, 5);\n"
                '        Global.getSectorAPI().addMessage("heavy convoy returned");\n'
                "    }\n}\n",
            )
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 2)  # addMessage + CrewXPLevel

            apply_fix(compute_fix(root, "removed-api-call"))
            text = path.read_text(encoding="utf-8")
            self.assertIn('Global.getSectorAPI().getCampaignUI().addMessage("heavy convoy returned");', text)
            self.assertNotIn("CrewXPLevel", text)
            self.assertIn("cargo.addCrew(5);", text)
            self.assertNotIn("dependencies", json.loads((root / "mod_info.json").read_text(encoding="utf-8")))

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])


class CrewXPLevelTypeDeclarationRefusalTests(unittest.TestCase):
    """removed-api-call, CrewXPLevel rule: a file that declares a CrewXPLevel-typed variable or
    parameter is refused, not rewritten. Real case (AI-War, 2026-09-15):
    data/missions/aiw_midnight/MissionDefinition.java had a helper
    `addToFleetAndAddSkills(..., CrewXPLevel level, boolean isFlagship)` with a body line
    `if (level == null) level = CrewXPLevel.REGULAR;`. The call-site-only rewrite (which only
    touches `CrewXPLevel.X` member access, never a bare type name) would drop the argument at call
    sites while leaving the parameter's own (now-unresolvable) type and the default-value line
    untouched -- desyncing call-site argument counts from the helper's own signature. The owner's
    task A10 hand-ported this file; this rule refuses it instead of guessing."""

    _WRAPPER_SHAPE = (
        "package data.missions.m;\n"
        "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
        "public class MissionDefinition implements MissionDefinitionPlugin {\n"
        "    public void defineMission(MissionDefinitionAPI api) {\n"
        '        addToFleetAndAddSkills(api, FleetSide.PLAYER, "hull_Standard", "Name", CrewXPLevel.ELITE, true);\n'
        '        addToFleetAndAddSkills(api, FleetSide.PLAYER, "hull2_Standard", null, null, false);\n'
        "    }\n"
        "    protected void addToFleetAndAddSkills(MissionDefinitionAPI api, FleetSide fleetSide, String variantId, String name, CrewXPLevel level, boolean isFlagship) {\n"
        "        if (level == null) level = CrewXPLevel.REGULAR;\n"
        "        api.addToFleet(fleetSide, variantId, name, isFlagship);\n"
        "    }\n}\n"
    )

    def test_refused_when_it_is_the_only_removed_api_call_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "missions" / "m" / "MissionDefinition.java"
            _write(path, self._WRAPPER_SHAPE)
            before = path.read_bytes()

            self.assertEqual(len(_findings(scan_mod(root), "removed-api-call")), 1)
            with self.assertRaises(FixerError) as ctx:
                compute_fix(root, "removed-api-call")
            message = str(ctx.exception)
            self.assertIn("CrewXPLevel", message)
            self.assertIn("hand-port", message.lower())
            self.assertIn("MissionDefinition.java", message)
            self.assertEqual(path.read_bytes(), before)  # compute_fix never writes; still unchanged

    def test_a_plain_call_site_in_another_file_is_still_fixed(self) -> None:
        # The refusal is per-file: a second, unrelated loose script with a plain (non-wrapper)
        # CrewXPLevel call site still gets its mechanical rewrite.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            refused_path = root / "data" / "missions" / "m" / "MissionDefinition.java"
            _write(refused_path, self._WRAPPER_SHAPE)
            plain_path = root / "data" / "scripts" / "world" / "Convoy.java"
            _write(
                plain_path,
                "package data.scripts.world;\n"
                "import com.fs.starfarer.api.campaign.CargoAPI.CrewXPLevel;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "    void crew(CargoAPI cargo) { cargo.addCrew(CrewXPLevel.VETERAN, 5); }\n}\n",
            )
            refused_before = refused_path.read_bytes()

            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(changed, {"data/scripts/world/Convoy.java"})
            apply_fix(plan)

            self.assertEqual(refused_path.read_bytes(), refused_before)  # untouched
            plain_text = plain_path.read_text(encoding="utf-8")
            self.assertNotIn("CrewXPLevel", plain_text)
            self.assertIn("cargo.addCrew(5);", plain_text)

            after = scan_mod(root)
            remaining = _findings(after, "removed-api-call")
            self.assertEqual(len(remaining), 1)
            self.assertTrue(any("data/missions/m/MissionDefinition.java" in item for item in remaining[0].evidence))

    def test_dotted_type_qualifier_also_counts_as_a_declaration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "scripts" / "world" / "Convoy.java"
            _write(
                path,
                "package data.scripts.world;\n"
                "public class Convoy extends BaseSpawnPoint {\n"
                "    void crew(CargoAPI cargo, CargoAPI.CrewXPLevel x) { cargo.addCrew(CargoAPI.CrewXPLevel.VETERAN, 5); }\n}\n",
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")


class LegacyWorldRewriteTests(unittest.TestCase):
    """removed-api-call: the 0.6 7-argument LocationAPI.addPlanet(...) and the 6-argument
    LocationAPI.addOrbitalStation(...) both become a bf.legacyworld.LegacyWorld (RevenantLib) call, with
    the old receiver forwarded as the new static method's first argument. RC8's own 8-argument id-first
    addPlanet and MissionDefinitionAPI's unrelated 5/6-argument addPlanet must never be flagged (task
    instruction: count top-level arguments, be conservative)."""

    def test_seven_argument_addplanet_is_rewritten_receiver_becomes_first_argument(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "scripts" / "world" / "Gen.java"
            _write(
                path,
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "    public void generate(SectorAPI sector) {\n"
                '        SectorEntityToken anchor = system.addPlanet(lot, "Anchor", "lava", 0, 0, 1, 1);\n'
                "    }\n}\n",
            )
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "removed-api-call")), 1)

            plan = compute_fix(root, "removed-api-call")
            changed = {change.path.relative_to(root).as_posix() for change in plan.changes}
            self.assertEqual(changed, {"data/scripts/world/Gen.java", "mod_info.json"})
            apply_fix(plan)

            text = path.read_text(encoding="utf-8")
            self.assertIn(
                'bf.legacyworld.LegacyWorld.addPlanet(system, lot, "Anchor", "lava", 0, 0, 1, 1);', text
            )
            self.assertNotIn("system.addPlanet(", text)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])

            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "removed-api-call"), [])

    def test_six_argument_addorbitalstation_is_rewritten_and_adds_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            path = root / "data" / "scripts" / "world" / "Gen.java"
            _write(
                path,
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "    public void generate(SectorAPI sector) {\n"
                '        SectorEntityToken station = system.addOrbitalStation(anchor, 45, 13000, 365, "Depot", "faction");\n'
                "    }\n}\n",
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                'bf.legacyworld.LegacyWorld.addOrbitalStation(system, anchor, 45, 13000, 365, "Depot", "faction");',
                text,
            )
            self.assertNotIn("system.addOrbitalStation(", text)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])

    def test_rc8_eight_argument_id_first_addplanet_is_never_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Gen.java",
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "    public void generate(SectorAPI sector) {\n"
                '        PlanetAPI p = system.addPlanet("asharu", star, "Asharu", "desert", 55, 150, 2800, 100);\n'
                "    }\n}\n",
            )
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_missiondefinitionapi_addplanet_five_and_six_argument_forms_are_never_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "missions" / "m" / "MissionDefinition.java",
                "package data.missions.m;\n"
                "public class MissionDefinition implements MissionDefinitionPlugin {\n"
                "    public void defineMission(MissionDefinitionAPI api) {\n"
                '        api.addPlanet(minX + width * 0.2f, minY + height * 0.2f, 300f, "cryovolcanic", 300f);\n'
                '        api.addPlanet(minX, minY, 300f, "cryovolcanic", 300f, true);\n'
                "    }\n}\n",
            )
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")

    def test_addplanet_and_addorbitalstation_together_add_the_dependency_only_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Gen.java",
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "    public void generate(SectorAPI sector) {\n"
                '        SectorEntityToken a = system.addPlanet(lot, "Anchor", "lava", 0, 0, 1, 1);\n'
                '        SectorEntityToken s = system.addOrbitalStation(a, 45, 13000, 365, "Depot", "faction");\n'
                "    }\n}\n",
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])

    def test_fixed_output_is_not_re_flagged_by_a_second_scan_no_self_matching_loop(self) -> None:
        # bf.legacyworld.LegacyWorld.addOrbitalStation(...) itself has the shape `LegacyWorld.
        # addOrbitalStation(` - without an explicit guard the scanner's own receiver.addOrbitalStation(
        # pattern would re-match its own fixer's output forever.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "data" / "scripts" / "world" / "Gen.java",
                "package data.scripts.world;\n"
                "public class Gen implements SectorGeneratorPlugin {\n"
                "    public void generate(SectorAPI sector) {\n"
                '        SectorEntityToken a = system.addPlanet(lot, "Anchor", "lava", 0, 0, 1, 1);\n'
                '        SectorEntityToken s = system.addOrbitalStation(a, 45, 13000, 365, "Depot", "faction");\n'
                "    }\n}\n",
            )
            apply_fix(compute_fix(root, "removed-api-call"))
            self.assertEqual(_findings(scan_mod(root), "removed-api-call"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "removed-api-call")


class ModInfoGameVersionInexactTests(unittest.TestCase):
    def _mod(self, root: Path) -> None:
        _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.97a"}')

    def test_requires_target_game_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root)
            with self.assertRaises(FixerError):
                compute_fix(root, "mod-info-game-version-inexact")

    def test_dry_run_byte_identical_then_apply_and_rescan(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root)
            path = root / "mod_info.json"
            before = path.read_bytes()
            plan = compute_fix(root, "mod-info-game-version-inexact", {"target_game_version": "0.98a"})
            self.assertEqual(path.read_bytes(), before)
            scan_mod(root, vanilla_core=None)
            applied = apply_fix(plan)
            self.assertTrue(Path(applied[0]["backup"]).is_file())
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["gameVersion"], "0.98a")
            self.assertEqual(data["id"], "fixture")


class CsvSpaceBeforeQuoteTests(unittest.TestCase):
    def test_a_space_before_an_opening_quote_is_dropped_when_that_fits_the_header(self) -> None:
        # SWP Triumphant's descriptions.csv (2026-10-01): `SHIP, "...` split a multi-line description at its commas.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "data" / "strings" / "descriptions.csv"
            _write(path, 'id,type,text1,text2\nx,SHIP, "One, two, five\nthree, four",\n')
            apply_fix(compute_fix(root, "csv-row-extra-columns", {}))
            rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"))))
        self.assertEqual(rows[1], ["x", "SHIP", "One, two, five\nthree, four", ""])


class CsvRowExtraColumnsTests(unittest.TestCase):
    def test_drops_trailing_empty_extras_and_rescans_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture"}')
            _write(
                root / "data" / "strings" / "descriptions.csv",
                "id,text\nrow1,hello,,\nrow2,world\n",
            )
            path = root / "data" / "strings" / "descriptions.csv"
            before = path.read_bytes()
            plan = compute_fix(root, "csv-row-extra-columns")
            self.assertEqual(path.read_bytes(), before)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "csv-row-extra-columns")), 1)
            apply_fix(plan)
            self.assertEqual(path.read_text(encoding="utf-8"), "id,text\nrow1,hello\nrow2,world\n")
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "csv-row-extra-columns"), [])

    def test_refuses_when_extra_field_non_empty(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(
                root / "data" / "strings" / "descriptions.csv",
                "id,text\nrow1,hello,unexpected\n",
            )
            with self.assertRaises(FixerError):
                compute_fix(root, "csv-row-extra-columns")


class CsvMissingDesignTypeColumnTests(unittest.TestCase):
    def _mod(self, root: Path) -> None:
        _write(
            root / "data" / "hulls" / "ship_data.csv",
            "id,name,hints\nff_cruiser,Cruiser,\nvanilla_hull,Vanilla,\n",
        )

    def test_requires_all_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root)
            with self.assertRaises(FixerError):
                compute_fix(root, "csv-missing-design-type-column")

    def test_apply_adds_column_and_settings_color_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root)
            options = {"design_type": "FF", "id_prefixes": ["ff_"], "design_color": "10,20,30"}
            plan = compute_fix(root, "csv-missing-design-type-column", options)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "csv-missing-design-type-column")), 1)
            apply_fix(plan)
            ship_data = (root / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
            lines = ship_data.splitlines()
            self.assertEqual(lines[0], "id,name,hints,tech/manufacturer")
            self.assertEqual(lines[1], "ff_cruiser,Cruiser,,FF")
            self.assertEqual(lines[2], "vanilla_hull,Vanilla,,")
            settings = json.loads((root / "data" / "config" / "settings.json").read_text(encoding="utf-8"))
            self.assertEqual(settings["designTypeColors"]["FF"], [10, 20, 30, 255])
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "csv-missing-design-type-column"), [])

    def test_existing_settings_designtypecolors_key_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod(root)
            _write(root / "data" / "config" / "settings.json", '{"designTypeColors":{"Other":[1,2,3,255]}}')
            options = {"design_type": "FF", "id_prefixes": ["ff_"], "design_color": "10,20,30"}
            plan = compute_fix(root, "csv-missing-design-type-column", options)
            # Only the CSV file should be part of the plan; settings.json already has the key.
            self.assertEqual(len(plan.changes), 1)
            self.assertTrue(str(plan.changes[0].path).endswith("ship_data.csv"))


class UnattendedInputFixerTests(unittest.TestCase):
    """Owner ruling 2026-09-30: two input fixers run unattended with defaults that invent nothing."""

    def test_nearest_vanilla_gen_row(self) -> None:
        from bridgeforge.fixers import nearest_vanilla_gen_row
        planets = {"barren", "water", "lava", "gas_giant", "frozen", "star_yellow", "star_red_dwarf"}
        self.assertEqual(nearest_vanilla_gen_row("waterworld", "", planets, False), "water")
        self.assertEqual(nearest_vanilla_gen_row("em_gas_giant", "", planets, False), "gas_giant")
        self.assertEqual(nearest_vanilla_gen_row("batavia_shipyards", "Shipyards", planets, False), "barren")
        self.assertEqual(nearest_vanilla_gen_row("my_sun", "Red Sun", planets, True), "star_red_dwarf")

    def test_blank_design_type_column_needs_no_design_type_or_colour(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id\nOne,ff_one\n")
            plan = compute_fix(root, "csv-missing-design-type-column", {"blank_design_type": True})
            apply_fix(plan)
            written = (root / "data" / "hulls" / "ship_data.csv").read_text(encoding="utf-8")
        self.assertEqual(written, "name,id,tech/manufacturer\nOne,ff_one,\n")
        self.assertEqual(len(plan.changes), 1)  # no settings.json colour


class ProcgenRowMissingTests(unittest.TestCase):
    def _vanilla(self, vanilla: Path) -> None:
        _write(
            vanilla / "data" / "campaign" / "procgen" / "planet_gen_data.csv",
            "id,age,frequency\nbarren,ANY,10\n",
        )
        _write(
            vanilla / "data" / "campaign" / "procgen" / "star_gen_data.csv",
            "id,freqYOUNG,freqAVERAGE,freqOLD\nstar_yellow,5,5,5\n",
        )

    def test_requires_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(FixerError):
                compute_fix(root, "procgen-planet-row-missing")

    def test_apply_clones_and_zeroes_planet_frequency_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            self._vanilla(vanilla)
            _write(root / "data" / "config" / "planets.json", '{"custom_planet":{"isStar":false,"name":"Custom"}}')
            _write(root / "src" / "S.java", 'class S { void g() { api.addPlanet("x", "custom_planet"); } }')
            before_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(len(_findings(before_scan, "procgen-planet-row-missing")), 1)
            options = {"vanilla_core": vanilla, "type_id": "custom_planet", "from_vanilla_id": "barren"}
            plan = compute_fix(root, "procgen-planet-row-missing", options)
            apply_fix(plan)
            written = (root / "data" / "campaign" / "procgen" / "planet_gen_data.csv").read_text(encoding="utf-8")
            self.assertEqual(written, "id,age,frequency\ncustom_planet,ANY,0\n")
            after_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(after_scan, "procgen-planet-row-missing"), [])

    def test_apply_clones_and_zeroes_star_frequencies(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            self._vanilla(vanilla)
            _write(root / "data" / "config" / "planets.json", '{"custom_star":{"isStar":true,"name":"Custom Star"}}')
            _write(root / "src" / "S.java", 'class S { void g() { api.addStar("custom_star"); } }')
            options = {"vanilla_core": vanilla, "type_id": "custom_star", "from_vanilla_id": "star_yellow"}
            plan = compute_fix(root, "procgen-star-row-missing", options)
            apply_fix(plan)
            written = (root / "data" / "campaign" / "procgen" / "star_gen_data.csv").read_text(encoding="utf-8")
            self.assertEqual(written, "id,freqYOUNG,freqAVERAGE,freqOLD\ncustom_star,0,0,0\n")


class FactionKnownListsMissingTests(unittest.TestCase):
    def test_requires_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(FixerError):
                compute_fix(root, "faction-known-lists-missing")

    def test_apply_derives_known_lists_from_variants_and_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            faction_path = root / "data" / "world" / "factions" / "newfac.faction"
            _write(
                faction_path,
                '{"id":"newfac","displayName":"New Faction",'
                '"shipRoles":{"role1":{"variant1":1}}}',
            )
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            _write(root / "data" / "variants" / "variant1.variant", '{"hullId":"hull1","weaponGroups":[{"weapons":{"WP0":"weapon1"}}],"wings":["wing1_wing"]}')
            _write(root / "data" / "hulls" / "ship_data.csv", "id,name\nhull1,Hull One\n")
            _write(root / "data" / "weapons" / "weapon_data.csv", "id,name\nweapon1,Weapon One\n")
            _write(root / "data" / "hulls" / "wing_data.csv", "id,role,role desc,op cost\nwing1_wing,FIGHTER,desc,4\n")

            before_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(len(_findings(before_scan, "faction-known-lists-missing")), 1)

            options = {"faction_file": faction_path, "vanilla_core": vanilla}
            plan = compute_fix(root, "faction-known-lists-missing", options)
            apply_fix(plan)
            data = json.loads(faction_path.read_text(encoding="utf-8"))
            self.assertEqual(data["knownShips"]["hulls"], ["hull1"])
            self.assertEqual(data["knownWeapons"]["weapons"], ["weapon1"])
            self.assertEqual(data["knownFighters"]["fighters"], ["wing1_wing"])
            self.assertNotIn("knownHullMods", data)
            after_scan = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(after_scan, "faction-known-lists-missing"), [])

    def test_a_0_6_faction_derives_lists_from_fleet_compositions(self) -> None:
        # Antediluvians' wayfarer.faction (2026-09-30): no shipRoles; fleets name a variant and a wing directly.
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            faction_path = root / "data" / "world" / "factions" / "oldfac.faction"
            _write(faction_path, '{id:"oldfac","fleetCompositions":{"f":{"displayName":"F","ships":{"variant1":[1, 1],"wing1_wing":[6, 6],},},},}')
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            _write(root / "data" / "variants" / "variant1.variant", '{"hullId":"hull1","weaponGroups":[{"weapons":{"WP0":"weapon1"}}]}')
            _write(root / "data" / "hulls" / "ship_data.csv", "id,name\nhull1,Hull One\n")
            _write(root / "data" / "weapons" / "weapon_data.csv", "id,name\nweapon1,Weapon One\n")
            _write(root / "data" / "hulls" / "wing_data.csv", "id,role,role desc,op cost\nwing1_wing,FIGHTER,desc,4\n")
            apply_fix(compute_fix(root, "faction-known-lists-missing", {"faction_file": faction_path, "vanilla_core": vanilla}))
            data = _load_lenient_json_file(faction_path)
            self.assertEqual(data["knownShips"]["hulls"], ["hull1"])
            self.assertEqual(data["knownFighters"]["fighters"], ["wing1_wing"])
            self.assertEqual(_findings(scan_mod(root, vanilla_core=vanilla), "faction-known-lists-missing"), [])

    def test_a_faction_nothing_reads_is_a_safe_note(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "data" / "world" / "factions" / "hvb_hostile.faction", '{"id":"hvb_hostile","displayName":"hostile"}')
            _write(vanilla / "data" / "world" / "factions" / "pirates.faction", '{"id":"pirates"}')
            found = _findings(scan_mod(root, vanilla_core=vanilla), "faction-known-lists-missing")
        self.assertEqual([f.classification for f in found], ["SAFE"])
        self.assertIn("nothing-reads-lists", found[0].evidence)

    def test_refuses_on_unresolved_id(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            faction_path = root / "data" / "world" / "factions" / "newfac.faction"
            _write(faction_path, '{"id":"newfac","shipRoles":{"role1":{"variant_missing":1}}}')
            options = {"faction_file": faction_path, "vanilla_core": vanilla}
            with self.assertRaises(FixerError):
                compute_fix(root, "faction-known-lists-missing", options)


class ModInfoTriageBannerTests(unittest.TestCase):
    def test_apply_removes_leading_banner_and_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"(BROEKN MAYBE) Fixture Mod"}')
            path = root / "mod_info.json"
            before = path.read_bytes()
            plan = compute_fix(root, "mod-info-triage-banner")
            self.assertEqual(path.read_bytes(), before)
            before_scan = scan_mod(root)
            self.assertEqual(len(_findings(before_scan, "mod-info-triage-banner")), 1)
            apply_fix(plan)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["name"], "Fixture Mod")
            after_scan = scan_mod(root)
            self.assertEqual(_findings(after_scan, "mod-info-triage-banner"), [])

    def test_refuses_when_no_leading_banner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Clean Mod Name"}')
            with self.assertRaises(FixerError):
                compute_fix(root, "mod-info-triage-banner")


class RevenantlibFoldConflictFixerTests(unittest.TestCase):
    """revenantlib-fold-conflict (roadmap P14 item 10, the fold-in workflow's fixer): a mod that still
    declares an original id RevenantLib has folded in, alongside revenantlib itself, double-registers
    the same ids and classes. This fixer drops the redundant original entry/entries and leaves
    revenantlib's own entry alone. `bridgeforge.substitutes.load_successors` is patched (not the real
    dependency_successors.json) so this stays independent of whatever real folds exist when it runs.
    """

    FOLDED = [
        {"match": "oldlib", "kind": "folded-into-revenantlib", "successor": "s", "action": "a", "evidence": "e"},
        {"match": "anotherlib", "kind": "folded-into-revenantlib", "successor": "s", "action": "a", "evidence": "e"},
    ]

    def _patch(self):
        return mock.patch("bridgeforge.substitutes.load_successors", return_value=self.FOLDED)

    def test_removes_the_redundant_original_entry_leaves_revenantlib_then_rescan_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", json.dumps({
                "id": "dependent", "name": "Dependent", "gameVersion": "0.98a",
                "dependencies": [{"id": "revenantlib", "name": "RevenantLib"}, {"id": "oldlib", "name": "OldLib"}],
            }))
            with self._patch():
                self.assertEqual(len(_findings(scan_mod(root), "revenantlib-fold-conflict")), 1)
                plan = compute_fix(root, "revenantlib-fold-conflict")
                applied = apply_fix(plan)
                self.assertTrue(Path(applied[0]["backup"]).is_file())
                self.assertTrue(Path(applied[0]["backup"]).name.endswith(".pre-bf-fix-revenantlib-fold-conflict.bak"))
                mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
                self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])
                self.assertEqual(_findings(scan_mod(root), "revenantlib-fold-conflict"), [])

    def test_multiple_conflicting_entries_are_all_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", json.dumps({
                "id": "dependent",
                "dependencies": [
                    {"id": "oldlib", "name": "OldLib"},
                    {"id": "revenantlib", "name": "RevenantLib"},
                    {"id": "anotherlib", "name": "AnotherLib"},
                ],
            }))
            with self._patch():
                apply_fix(compute_fix(root, "revenantlib-fold-conflict"))
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])

    def test_bare_string_dependency_entries_are_removed_too(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", json.dumps({"id": "dependent", "dependencies": ["revenantlib", "oldlib"]}))
            with self._patch():
                apply_fix(compute_fix(root, "revenantlib-fold-conflict"))
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], ["revenantlib"])

    def test_comments_and_other_keys_are_left_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            text = (
                "{\n"
                "\t# a leading comment\n"
                '\t"id":"dependent",\n'
                '\t"name":"Dependent",\n'
                '\t"dependencies":[\n'
                '\t\t{"id":"revenantlib","name":"RevenantLib"},\n'
                '\t\t{"id":"oldlib","name":"OldLib"}\n'
                "\t]\n"
                "}\n"
            )
            _write(root / "mod_info.json", text)
            with self._patch():
                apply_fix(compute_fix(root, "revenantlib-fold-conflict"))
            new_text = (root / "mod_info.json").read_text(encoding="utf-8")
            self.assertIn("# a leading comment", new_text)
            self.assertIn('"name":"Dependent"', new_text)
            self.assertNotIn("oldlib", new_text)
            self.assertIn('"id":"revenantlib"', new_text)

    def test_refuses_when_no_conflict_finding_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", json.dumps({"id": "dependent", "dependencies": [{"id": "revenantlib", "name": "RevenantLib"}]}))
            with self._patch():
                with self.assertRaises(FixerError):
                    compute_fix(root, "revenantlib-fold-conflict")

    def test_cli_fix_apply_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", json.dumps({
                "id": "dependent",
                "dependencies": [{"id": "revenantlib", "name": "RevenantLib"}, {"id": "oldlib", "name": "OldLib"}],
            }))
            with self._patch():
                exit_code = main(["fix", str(root), "--finding", "revenantlib-fold-conflict", "--apply", "--json"])
            self.assertEqual(exit_code, 0)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "revenantlib", "name": "RevenantLib"}])


class RefuseShadowedEditTests(unittest.TestCase):
    """ROADMAP P14 item 14: a fixer must refuse to edit a loose script one of this mod's own jars
    already shadows - editing it has no effect (the game loads the jar's class), confirmed live on
    Thule-Legacy 2026-09-20: a task converted six setPersonality() calls with a full evidence trail
    and changed nothing in-game, because ThuleLegacy.jar shipped that exact class.
    """

    MOD = "package data.hullmods;\npublic class Tow implements HullModEffect {\n    public void init() {}\n}\n"

    def test_refuses_when_the_mods_own_jar_shadows_the_edited_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "hullmods" / "Tow.java", self.MOD)
            write_jar(root / "jars" / "fixture.jar", {"data/hullmods/Tow.class": build_class_file("data/hullmods/Tow")})
            self.assertEqual(len(_findings(scan_mod(root), "target-interface-method-missing")), 2)
            with self.assertRaises(FixerError) as ctx:
                compute_fix(root, "target-interface-method-missing")
            self.assertIn("shadowed", str(ctx.exception))
            self.assertIn("data.hullmods.Tow", str(ctx.exception))
            # Refused before any write - the loose source is untouched.
            self.assertEqual((root / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8"), self.MOD)

    def test_allow_shadowed_edit_overrides_the_refusal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "hullmods" / "Tow.java", self.MOD)
            write_jar(root / "jars" / "fixture.jar", {"data/hullmods/Tow.class": build_class_file("data/hullmods/Tow")})
            plan = compute_fix(root, "target-interface-method-missing", {"allow_shadowed_edit": True})
            apply_fix(plan)
            self.assertIn("showInRefitScreenModPickerFor", (root / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8"))

    def test_no_jar_present_is_not_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "hullmods" / "Tow.java", self.MOD)
            plan = compute_fix(root, "target-interface-method-missing")
            apply_fix(plan)
            self.assertIn("showInRefitScreenModPickerFor", (root / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8"))

    def test_cli_surfaces_the_refusal_and_the_override_flag_clears_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            _write(root / "data" / "hullmods" / "Tow.java", self.MOD)
            write_jar(root / "jars" / "fixture.jar", {"data/hullmods/Tow.class": build_class_file("data/hullmods/Tow")})
            exit_code = main(["fix", str(root), "--finding", "target-interface-method-missing", "--apply"])
            self.assertEqual(exit_code, 2)
            exit_code = main(["fix", str(root), "--finding", "target-interface-method-missing", "--apply", "--allow-shadowed-edit"])
            self.assertEqual(exit_code, 0)


class RefuseCrossModShadowedEditTests(unittest.TestCase):
    """ROADMAP P14 item 12/14: the same refusal for a loose script shadowed by a *declared
    dependency's* jar - all mod jars share one classloader, so the rule is identical to item 14's
    own-jar case. Real shape confirmed on Maelstrom Interstellar Imperium Unofficial Expansion
    (escalation E8): its Titan scripts duplicated classes the base mod's own II.jar already supplied.
    """

    MOD = "package data.hullmods;\npublic class Tow implements HullModEffect {\n    public void init() {}\n}\n"

    def _provider(self, root: Path) -> Path:
        provider = root / "providers" / "basemod"
        _write(provider / "mod_info.json", '{"id":"basemod","name":"Base Mod"}')
        write_jar(provider / "jars" / "base.jar", {"data/hullmods/Tow.class": build_class_file("data/hullmods/Tow")})
        return provider

    def test_refuses_when_a_declared_dependencys_jar_shadows_the_edited_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._provider(root)
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a","dependencies":[{"id":"basemod"}]}')
            _write(mod / "data" / "hullmods" / "Tow.java", self.MOD)
            with self.assertRaises(FixerError) as ctx:
                compute_fix(mod, "target-interface-method-missing", {"provider_roots": [root / "providers"]})
            self.assertIn("Base Mod", str(ctx.exception))
            self.assertIn("data.hullmods.Tow", str(ctx.exception))
            self.assertEqual((mod / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8"), self.MOD)

    def test_allow_shadowed_edit_overrides_the_cross_mod_refusal_too(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._provider(root)
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a","dependencies":[{"id":"basemod"}]}')
            _write(mod / "data" / "hullmods" / "Tow.java", self.MOD)
            plan = compute_fix(mod, "target-interface-method-missing", {"allow_shadowed_edit": True, "provider_roots": [root / "providers"]})
            apply_fix(plan)
            self.assertIn("showInRefitScreenModPickerFor", (mod / "data" / "hullmods" / "Tow.java").read_text(encoding="utf-8"))

    def test_cli_wires_the_providers_flag_through(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._provider(root)
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a","dependencies":[{"id":"basemod"}]}')
            _write(mod / "data" / "hullmods" / "Tow.java", self.MOD)
            exit_code = main(["fix", str(mod), "--finding", "target-interface-method-missing", "--apply", "--providers", str(root / "providers")])
            self.assertEqual(exit_code, 2)
            exit_code = main(["fix", str(mod), "--finding", "target-interface-method-missing", "--apply", "--allow-shadowed-edit", "--providers", str(root / "providers")])
            self.assertEqual(exit_code, 0)


class UndeclaredLibraryDependencyFixerTests(unittest.TestCase):
    """undeclared-library-dependency (roadmap P14 item 16): a mod that reaches a known library's
    package without declaring it in mod_info.json - hand-applied three times this session
    (EZFaction, Maelstrom, Leon-Heavy-Industries) before this fixer existed.
    """

    def _mod_with_graphicslib_import(self, root: Path, mod_info: dict | None = None) -> None:
        _write(root / "mod_info.json", json.dumps(mod_info or {"id": "flowergod"}))
        _write(
            root / "src" / "FlowerGodPlugin.java",
            "package fg;\nimport org.dark.shaders.light.LightAPI;\nclass FlowerGodPlugin { LightAPI l; }",
        )

    def test_declares_the_missing_library_with_the_real_corrected_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod_with_graphicslib_import(root)
            self.assertEqual(len(_findings(scan_mod(root), "undeclared-library-dependency")), 1)
            plan = compute_fix(root, "undeclared-library-dependency")
            applied = apply_fix(plan)
            self.assertTrue(Path(applied[0]["backup"]).name.endswith(".pre-bf-fix-undeclared-library-dependency.bak"))
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            # The real, corrected id (mixed-case, matching GraphicsLib's own mod_info.json) - not
            # the lowercase "shaderlib" the table had before this session's casing fix.
            self.assertEqual(mod_info["dependencies"], [{"id": "shaderLib", "name": "GraphicsLib"}])
            self.assertEqual(_findings(scan_mod(root), "undeclared-library-dependency"), [])

    def test_already_declared_with_the_bare_string_shape_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod_with_graphicslib_import(root, {"id": "flowergod", "dependencies": ["shaderLib"]})
            self.assertEqual(_findings(scan_mod(root), "undeclared-library-dependency"), [])
            with self.assertRaises(FixerError):
                compute_fix(root, "undeclared-library-dependency")

    def test_no_finding_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _write(root / "mod_info.json", json.dumps({"id": "clean"}))
            with self.assertRaises(FixerError):
                compute_fix(root, "undeclared-library-dependency")

    def test_cli_fix_apply_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            self._mod_with_graphicslib_import(root)
            exit_code = main(["fix", str(root), "--finding", "undeclared-library-dependency", "--apply", "--json"])
            self.assertEqual(exit_code, 0)
            mod_info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(mod_info["dependencies"], [{"id": "shaderLib", "name": "GraphicsLib"}])


class UnsupportedFindingTests(unittest.TestCase):
    def test_unsupported_finding_lists_supported_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            with self.assertRaises(FixerError) as ctx:
                compute_fix(root, "not-a-real-finding")
            self.assertIn("wing-data-missing-role-desc-column", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


class CsvFullwidthNumberFixerTests(unittest.TestCase):
    def test_rewrites_reported_cells_and_keeps_prose_and_quoting(self) -> None:
        from bridgeforge.fixers import apply_fix, compute_fix
        from bridgeforge.scanner import scan_mod

        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            (mod / "data" / "hulls").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "x"}', encoding="utf-8")
            csv_path = mod / "data" / "hulls" / "ship_data.csv"
            csv_path.write_bytes(b"\xef\xbb\xbf" + 'name,id,hitpoints,max speed,designation\r\nA,fx_a,１５００,"0。5",护卫舰，快速\r\nB,fx_b,1500,50,"3，000 tons"\r\n'.encode("utf-8"))
            apply_fix(compute_fix(mod, "csv-fullwidth-number"))
            after = csv_path.read_bytes()
            remaining = [f for f in scan_mod(mod).findings if f.id == "csv-fullwidth-number"]
            with self.assertRaises(FixerError):
                compute_fix(mod, "csv-fullwidth-number")  # nothing left to do
        self.assertEqual(after, b"\xef\xbb\xbf" + 'name,id,hitpoints,max speed,designation\r\nA,fx_a,1500,"0.5",护卫舰，快速\r\nB,fx_b,1500,50,"3，000 tons"\r\n'.encode("utf-8"))
        self.assertEqual(remaining, [])


class ShipDataFighterBaysColumnFixerTests(unittest.TestCase):
    def test_adds_a_blank_column_and_refuses_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            (mod / "data/hulls").mkdir(parents=True)
            (mod / "data/hulls/ship_data.csv").write_bytes(b"name,id,hitpoints\r\nA,old_a,1500\r\n\r\nB,old_b,900\r\n")  # bytes: write_text would double \r on Windows
            apply_fix(compute_fix(mod, "ship-data-missing-fighter-bays-column"))
            after = (mod / "data/hulls/ship_data.csv").read_bytes().decode("utf-8")
            remaining = _findings(scan_mod(mod), "ship-data-missing-fighter-bays-column")
            with self.assertRaises(FixerError):
                compute_fix(mod, "ship-data-missing-fighter-bays-column")
        self.assertEqual(after, "name,id,hitpoints,fighter bays\r\nA,old_a,1500,\r\n\r\nB,old_b,900,\r\n")
        self.assertEqual(remaining, [])


class CustomUiButtonPressedFixerTests(unittest.TestCase):
    def test_adds_a_no_op_to_each_block_that_lacks_it(self) -> None:
        source = (
            "package data.scripts;\n"
            "import com.fs.starfarer.api.campaign.CustomUIPanelPlugin;\n"
            "public class Panel implements CustomUIPanelPlugin {\n"
            "    public void render(float alpha) {}\n"
            "    Object other = new CustomUIPanelPlugin() {\n"
            "        public void buttonPressed(Object id) { }\n"
            "    };\n"
            "    Object third = new CustomUIPanelPlugin() {\n"
            "        public void advance(float amount) { if (amount > 0) { } }\n"
            "    };\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            _write(mod / "data/scripts/Panel.java", source)
            _write(mod / "src/x/Jar.java", "class Jar implements CustomUIPanelPlugin { }\n")
            apply_fix(compute_fix(mod, "missing-custom-ui-button-pressed-callback"))
            after = (mod / "data/scripts/Panel.java").read_text(encoding="utf-8")
            loose_left = [f for f in _findings(scan_mod(mod), "missing-custom-ui-button-pressed-callback") if f.file.startswith("data/")]
            _write(mod / "data/scripts/Broken.java", "class Broken implements CustomUIPanelPlugin {\n  void f() {\n")
            with self.assertRaises(FixerError):
                compute_fix(mod, "missing-custom-ui-button-pressed-callback")
        # Only the third block: the scanner's brace walk counts the outer class as covered by the
        # buttonPressed its nested anonymous class declares, and the fixer follows the scanner.
        self.assertEqual(after.count("public void buttonPressed(Object buttonId) {}"), 1)
        self.assertIn("        public void buttonPressed(Object buttonId) {}\n    };\n}", after)
        self.assertIn("public void buttonPressed(Object id) { }", after)                 # the existing one is untouched
        self.assertEqual(loose_left, [])


class SuppliedFindingsTests(unittest.TestCase):
    """A caller that already scanned (revive) passes its findings, so the fixer doesn't rescan."""

    def test_supplied_findings_give_the_same_edit_without_a_scan(self) -> None:
        from dataclasses import asdict

        source = ("package data.scripts;\nimport com.fs.starfarer.api.campaign.CustomUIPanelPlugin;\n"
                  "public class Panel implements CustomUIPanelPlugin {\n    public void render(float alpha) {}\n}\n")
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            _write(mod / "data/scripts/Panel.java", source)
            findings = scan_mod(mod).findings
            scanned = compute_fix(mod, "missing-custom-ui-button-pressed-callback")
            with mock.patch("bridgeforge.scanner.scan_mod", side_effect=AssertionError("rescanned")):
                as_objects = compute_fix(mod, "missing-custom-ui-button-pressed-callback", {"scan_findings": findings})
                as_dicts = compute_fix(mod, "missing-custom-ui-button-pressed-callback", {"scan_findings": [asdict(f) for f in findings]})
                with self.assertRaises(FixerError):  # the caller's scan has none: nothing to fix, no fallback scan
                    compute_fix(mod, "missing-custom-ui-button-pressed-callback", {"scan_findings": []})
        self.assertEqual([c.after for c in as_objects.changes], [c.after for c in scanned.changes])
        self.assertEqual([c.after for c in as_dicts.changes], [c.after for c in scanned.changes])


class ShippableWorkFileFixerTests(unittest.TestCase):
    """P15 item 14: move editor/work files out of the shipped tree, keeping any the mod names."""

    def test_moves_unreferenced_work_files_to_scratch_and_keeps_referenced_ones(self) -> None:
        import zipfile

        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "Mod"
            mod = workspace / "working"
            _write(mod / "mod_info.json", '{"id": "x", "jars": ["jars/x.jar"]}')
            (mod / "graphics/ships").mkdir(parents=True)
            (mod / "graphics/ships/hull.psd").write_bytes(b"8BPS\x00\x01binary")
            _write(mod / "data/config/notes.old", "old notes")
            _write(mod / "data/config/settings.json", '{"intro": "graphics/ships/intro.log"}')
            _write(mod / "graphics/ships/intro.log", "the settings file names me")
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars/x.jar", "w") as jar:
                jar.writestr("data/Plugin.class", b"\xca\xfe\xba\xbe loads sounds/pack.zip")
            (mod / "sounds").mkdir()
            (mod / "sounds/pack.zip").write_bytes(b"PK\x05\x06" + b"\x00" * 18)
            # An IDE file naming a work file is not a runtime reference (Jackundor's .idea, 2026-09-27).
            _write(mod / ".idea/libraries/data.xml", '<root url="jar://$PROJECT_DIR$/graphics/ships/hull.psd" />')
            # Nor is a root readme (Hiver Swarm's README named its .rar, ROADMAP 34.18).
            _write(mod / "README.txt", "Unpack hull.psd and notes.old if you like.")
            self.assertTrue(_findings(scan_mod(mod), "shippable-work-file"))
            plan = compute_fix(mod, "shippable-work-file")
            applied = apply_fix(plan)
            moved = workspace / "scratch" / "work-files"
            psd = (moved / "graphics/ships/hull.psd").read_bytes()
            old_moved = (moved / "data/config/notes.old").is_file()
            kept = [(mod / p).is_file() for p in ("graphics/ships/intro.log", "sounds/pack.zip")]
            gone = [(mod / p).exists() for p in ("graphics/ships/hull.psd", "data/config/notes.old")]
            backups = [entry["backup"] for entry in applied if entry.get("removed")]
            remaining = _findings(scan_mod(mod), "shippable-work-file")
            with self.assertRaises(FixerError):
                compute_fix(mod, "shippable-work-file")  # only referenced files left
        self.assertEqual(psd, b"8BPS\x00\x01binary")
        self.assertTrue(old_moved)
        self.assertEqual(kept, [True, True])
        self.assertEqual(gone, [False, False])
        self.assertEqual(backups, [None, None])  # the moved copy is the backup
        self.assertEqual(sorted(remaining[0].evidence), ["graphics/ships/intro.log", "sounds/pack.zip"])

    def test_refuses_to_overwrite_an_earlier_move_and_shows_binary_moves_briefly(self) -> None:
        from bridgeforge.fixers import unified_diff_for_change

        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory) / "loose"
            _write(mod / "mod_info.json", '{"id": "x"}')
            (mod / "graphics").mkdir()
            (mod / "graphics/a.psd").write_bytes(b"8BPS\x00" * 100)
            plan = compute_fix(mod, "shippable-work-file")
            diffs = [unified_diff_for_change(change) for change in plan.changes]
            (Path(directory) / "loose.work-files" / "graphics").mkdir(parents=True)
            (Path(directory) / "loose.work-files" / "graphics" / "a.psd").write_bytes(b"earlier")
            with self.assertRaises(FixerError):
                compute_fix(mod, "shippable-work-file")
        self.assertIn("new binary file (500 bytes)", diffs[0])
        self.assertIn("removed (500 bytes)", diffs[1])


class DataFileNotUtf8FixerTests(unittest.TestCase):
    """P15 item 15: only isolated CP-1252 punctuation is re-encoded; anything else needs a person."""

    def test_reencodes_cp1252_punctuation_and_keeps_existing_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            (mod / "data/strings").mkdir(parents=True)
            path = mod / "data/strings/descriptions.csv"
            path.write_bytes(b'id,text\r\na,"it\x92s \x93fine\x94 \x96 caf\xc3\xa9"\r\n')  # CP-1252 quotes + real UTF-8
            self.assertTrue(_findings(scan_mod(mod), "data-file-not-utf8"))
            apply_fix(compute_fix(mod, "data-file-not-utf8"))
            after = path.read_bytes()
            remaining = _findings(scan_mod(mod), "data-file-not-utf8")
        self.assertEqual(after.decode("utf-8"), 'id,text\r\na,"it’s “fine” – café"\r\n')
        self.assertEqual(remaining, [])

    def test_partial_refusal_is_kept_as_a_pending_item(self) -> None:
        # ROADMAP P15 20.5: one file converts, another is refused; revive used to drop the refused list.
        from bridgeforge.revive import _try_fixers

        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            (mod / "data/strings").mkdir(parents=True)
            (mod / "data/strings/descriptions.csv").write_bytes(b'id,text\r\na,"it\x92s"\r\n')
            (mod / "data/strings/tips.csv").write_bytes(b'id,text\r\nb,"caf\xe9 d\xe9j\xe0"\r\n')
            findings = [{"id": f.id, "classification": f.classification, "file": f.file, "evidence": f.evidence}
                        for f in _findings(scan_mod(mod), "data-file-not-utf8")]
            applied, pending = _try_fixers(mod, findings, target="0.98a-RC8", vanilla_core=None, approved={"data-file-not-utf8"}, apply=True)
        self.assertEqual([item["files"] for item in applied], [["data/strings/descriptions.csv"]])
        refused = [item for item in pending if item["state"] == "FIXER_REFUSED"]
        self.assertEqual(len(refused), 1)
        self.assertIn("data/strings/tips.csv", refused[0]["reason"])

    def test_named_encodings_are_recorded_and_reapplied_by_revive(self) -> None:
        # ROADMAP P15 20.4: a person's fix --encoding decision survives a fresh copy from original/.
        from bridgeforge.cli import main
        from bridgeforge.revive import _try_fixers

        with tempfile.TemporaryDirectory() as directory:
            working = Path(directory) / "ws" / "working"
            _write(working / "mod_info.json", '{"id": "x"}')
            (working / "data/strings").mkdir(parents=True)
            raw = 'id,text\r\na,"日本"\r\n'.encode("shift_jis")
            (working / "data/strings/tips.csv").write_bytes(raw)
            main(["fix", str(working), "--finding", "data-file-not-utf8", "--encoding", "data/strings/tips.csv=shift_jis", "--apply"])
            recorded = json.loads((working.parent / "NAMED_ENCODINGS.json").read_text(encoding="utf-8"))
            (working / "data/strings/tips.csv").write_bytes(raw)  # a fresh copy from original/
            findings = [{"id": f.id, "classification": f.classification, "file": f.file, "evidence": f.evidence}
                        for f in _findings(scan_mod(working), "data-file-not-utf8")]
            applied, _pending = _try_fixers(working, findings, target="0.98a-RC8", vanilla_core=None, approved={"data-file-not-utf8"}, apply=True)
            text = (working / "data/strings/tips.csv").read_bytes().decode("utf-8")
        self.assertEqual(recorded, {"data/strings/tips.csv": "shift_jis"})
        self.assertEqual([item["files"] for item in applied], [["data/strings/tips.csv"]])
        self.assertIn("日本", text)

    def test_refuses_mac_roman_shift_jis_and_accented_letters(self) -> None:
        cases = {
            "mac_roman.csv": b"id,text\na,the station\xd5s hull\n",  # Mac Roman 0xD5 = right quote
            "shift_jis.csv": b"id,text\na,the ship\x81fs hull\n",    # Shift-JIS 0x81 0x66
            "letters.csv": b"id,text\na,Myst\xe9re\n",               # CP-1252 e-acute or Mac Roman E-grave
        }
        for name, raw in cases.items():
            with self.subTest(name), tempfile.TemporaryDirectory() as directory:
                mod = Path(directory)
                _write(mod / "mod_info.json", '{"id": "x"}')
                (mod / "data/strings").mkdir(parents=True)
                (mod / "data/strings" / name).write_bytes(raw)
                with self.assertRaises(FixerError) as caught:
                    compute_fix(mod, "data-file-not-utf8")
                self.assertIn(name, str(caught.exception))

    def test_a_mixed_mod_fixes_what_it_can_and_leaves_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            (mod / "data/strings").mkdir(parents=True)
            (mod / "data/strings/a.csv").write_bytes(b"id,t\na,it\x92s\n")
            (mod / "data/strings/b.csv").write_bytes(b"id,t\na,Myst\xe9re\n")
            plan = compute_fix(mod, "data-file-not-utf8")
        self.assertEqual([c.path.name for c in plan.changes], ["a.csv"])


class DataFileNamedEncodingTests(unittest.TestCase):
    """A person names a refused file's encoding with `fix --encoding FILE=ENC` (2026-09-27 survey)."""

    def test_mac_roman_and_shift_jis_named_by_a_person(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = Path(directory)
            _write(mod / "mod_info.json", '{"id": "x"}')
            (mod / "data/strings").mkdir(parents=True)
            (mod / "data/strings/mac.csv").write_bytes(b"id,t\na,it\xd5s Myst\x8fre\n")
            (mod / "data/strings/sjis.csv").write_bytes(b"id,t\na,the ship\x81fs hull \xc3\xa9\n")
            code = main(["fix", str(mod), "--finding", "data-file-not-utf8", "--apply",
                         "--encoding", "data/strings/mac.csv=mac_roman", "--encoding", "data/strings/sjis.csv=shift_jis"])
            mac = (mod / "data/strings/mac.csv").read_bytes().decode("utf-8")
            sjis = (mod / "data/strings/sjis.csv").read_bytes().decode("utf-8")
            with self.assertRaises(FixerError):
                compute_fix(mod, "data-file-not-utf8", {"encodings": {"data/strings/mac.csv": "ebcdic"}})
            with self.assertRaises(FixerError):  # nothing left to re-encode in a named file
                compute_fix(mod, "data-file-not-utf8", {"encodings": {"data/strings/mac.csv": "cp1252"}})
        self.assertEqual(code, 0)
        self.assertEqual(mac, "id,t\na,it’s Mystère\n")
        self.assertEqual(sjis, "id,t\na,the ship’s hull é\n")


class HullModInstanceStateFixerTests(unittest.TestCase):
    # ROADMAP 34.1 (2026-10-04): the per-ship State port done by hand for SEEKER and Sylphon, as a fixer.
    SOURCE = (
        "package data.hullmods;\n\n"
        "import com.fs.starfarer.api.combat.BaseHullMod;\n"
        "import com.fs.starfarer.api.combat.ShipAPI;\n\n"
        "public class Fixture extends BaseHullMod {\n"
        "    private static final float DELAY = 2f;\n"
        "    private float timer = 0f;\n\n"
        "    public void advanceInCombat(ShipAPI ship, float amount) {\n"
        "        this.timer += amount;\n"
        "        if (timer > DELAY) { reset(ship); }\n"
        "    }\n\n"
        "    private void reset(ShipAPI s) {\n"
        "        timer = 0f;\n"
        "    }\n"
        "}\n"
    )

    def _mod(self, root: Path, source: str) -> Path:
        (root / "mod_info.json").write_text('{"id":"fixture","name":"F","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
        path = root / "data" / "hullmods" / "Fixture.java"
        path.parent.mkdir(parents=True)
        path.write_text(source, encoding="utf-8")
        return path

    def test_moves_fields_into_per_ship_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(root, self.SOURCE)
            self.assertEqual(len(_findings(scan_mod(root), "hullmod-instance-state")), 1)
            apply_fix(compute_fix(root, "hullmod-instance-state"))
            text = path.read_text(encoding="utf-8")
            self.assertEqual(_findings(scan_mod(root), "hullmod-instance-state"), [])
        self.assertIn("private static class State {\n        float timer = 0f;\n    }", text)
        self.assertIn('ship.getCustomData().get("Fixture_bfState")', text)
        self.assertIn("if (ship == null) return new State();", text)
        self.assertEqual(text.count("State bfState = bfState("), 2)
        self.assertIn("bfState.timer += amount;", text)
        self.assertIn("State bfState = bfState(s);\n        bfState.timer = 0f;", text)
        self.assertIn("private static final float DELAY = 2f;", text)

    def test_refuses_a_method_without_a_ship(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, self.SOURCE.replace("private void reset(ShipAPI s) {", "private void reset() {").replace("reset(ship)", "reset()"))
            with self.assertRaises(FixerError):
                compute_fix(root, "hullmod-instance-state")


class PortHullModStateCommandTests(unittest.TestCase):
    def test_writes_the_port_and_refuses_overwriting_the_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Fixture.java"
            source.write_text(HullModInstanceStateFixerTests.SOURCE, encoding="utf-8")
            out = Path(directory) / "out" / "Fixture.java"
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                code = main(["port-hullmod-state", str(source), "--field", "timer", "--out", str(out)])
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                same = main(["port-hullmod-state", str(source), "--field", "timer", "--out", str(source)])
            ported = out.read_text(encoding="utf-8")
        self.assertEqual(code, 0)
        self.assertEqual(same, 2)
        self.assertIn("bfState.timer += amount;", ported)


class NexerelinCorvusModeImportTests(unittest.TestCase):
    # ROADMAP 34.13 (2026-10-04): Hiver Swarm's plugin failed to compile without Nexerelin.
    def _mod(self, root: Path, dependencies: str = "[]") -> Path:
        (root / "mod_info.json").write_text('{"id":"fixture","dependencies":' + dependencies + '}', encoding="utf-8")
        path = root / "data" / "scripts" / "Plugin.java"
        path.parent.mkdir(parents=True)
        path.write_text(
            "package data.scripts;\n\nimport com.fs.starfarer.api.BaseModPlugin;\nimport exerelin.campaign.SectorManager;\n\n"
            "public class Plugin extends BaseModPlugin {\n    public void onNewGame() {\n"
            "        if (SectorManager.getManager().getCorvusMode()) { }\n    }\n}\n", encoding="utf-8")
        return path

    def test_reads_sector_memory_instead_of_importing_nexerelin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._mod(root)
            self.assertEqual(len(_findings(scan_mod(root), "nexerelin-corvus-mode-import")), 1)
            apply_fix(compute_fix(root, "nexerelin-corvus-mode-import"))
            text = path.read_text(encoding="utf-8")
            self.assertEqual(_findings(scan_mod(root), "nexerelin-corvus-mode-import"), [])
        self.assertNotIn("exerelin", text)
        self.assertIn('if ((!Global.getSector().getMemoryWithoutUpdate().getBoolean("$nex_randomSector"))) { }', text)
        self.assertIn("import com.fs.starfarer.api.Global;", text)

    def test_not_flagged_when_a_jar_class_shadows_the_loose_file(self) -> None:
        # Kadur Remnant ships its plugin both loose and in KadurRemnant.jar; the jar class wins (2026-10-04).
        import zipfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root)
            (root / "mod_info.json").write_text('{"id":"fixture","dependencies":[],"jars":["jars/m.jar"]}', encoding="utf-8")
            (root / "jars").mkdir()
            with zipfile.ZipFile(root / "jars" / "m.jar", "w") as jar:
                jar.writestr("data/scripts/Plugin.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x3d")
            self.assertEqual(_findings(scan_mod(root), "nexerelin-corvus-mode-import"), [])

    def test_not_flagged_when_the_mod_requires_nexerelin(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._mod(root, '[{"id":"nexerelin"}]')
            self.assertEqual(_findings(scan_mod(root), "nexerelin-corvus-mode-import"), [])


class SpawnedShipCaptainFixerTests(unittest.TestCase):
    # ROADMAP 34.14 (2026-10-04): Traverser's turrets, done by hand, as a fixer; the captain overload is guarded.
    def test_gives_a_spawned_ship_a_captain_and_the_rescan_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            path = root / "data" / "shipsystems" / "Deploy.java"
            path.parent.mkdir(parents=True)
            path.write_text(
                "package data.shipsystems;\n\npublic class Deploy {\n    void go(CombatFleetManagerAPI m, Vector2f at) {\n"
                '        m.spawnShipOrWing("fx_turret", at, (float) Math.random() * 360f);\n'
                '        m.spawnShipOrWing("fx_wing", at, 0f);\n    }\n}\n', encoding="utf-8")
            self.assertEqual(len(_findings(scan_mod(root), "spawned-ship-captain-personality-risk")), 1)
            apply_fix(compute_fix(root, "spawned-ship-captain-personality-risk"))
            text = path.read_text(encoding="utf-8")
            self.assertEqual(_findings(scan_mod(root), "spawned-ship-captain-personality-risk"), [])
        self.assertIn('m.spawnShipOrWing("fx_turret", at, (float) Math.random() * 360f, 0f, bfSpawnCaptain());', text)
        self.assertIn('m.spawnShipOrWing("fx_wing", at, 0f);', text)
        self.assertIn("Personalities.STEADY", text)
        self.assertTrue(text.rstrip().endswith("}"))


class JsonMissingCommaTests(unittest.TestCase):
    # ROADMAP 34.16 (2026-10-04): Hiigaran's polaris.json; org.json rejects a missing separator.
    def test_adds_the_comma_and_the_file_then_parses(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            path = root / "data" / "campaign" / "econ" / "x.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b'{\r\n\t"conditions":[\r\n\t\t"a",\r\n\t\t#"b",\r\n\t\t"c"\r\n\t\t"d",\r\n\t],\r\n}\r\n')
            found = _findings(scan_mod(root), "json-missing-comma")
            apply_fix(compute_fix(root, "json-missing-comma"))
            data = path.read_bytes()
            after = scan_mod(root)
        self.assertEqual(found[0].evidence, ["line:5"])
        self.assertIn(b'\t\t"c",\r\n\t\t"d"', data)
        self.assertEqual(_findings(after, "json-missing-comma"), [])
        self.assertEqual(_findings(after, "unverified-json-syntax"), [])

    def test_other_syntax_errors_stay_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text('{"id":"fixture"}', encoding="utf-8")
            (root / "data").mkdir()
            (root / "data" / "y.json").write_text('{"a": [1, 2}', encoding="utf-8")
            result = scan_mod(root)
        self.assertEqual(_findings(result, "json-missing-comma"), [])
        self.assertTrue(_findings(result, "unverified-json-syntax"))


class BuiltinWingIsHullmodTests(unittest.TestCase):
    # 2026-10-04: The Nomads' nom_komodo_p.ship listed the vanilla hull mod advancedcore under builtInWings.
    def test_renames_the_key_when_every_entry_is_a_hull_mod(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core"
            _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\nAdvanced Targeting Core,advancedcore\n")
            _write(core / "data" / "hulls" / "wing_data.csv", "id,variant\ntalon_wing,talon_wing\n")
            _write(core / "data" / "weapons" / "weapon_data.csv", "name,id\nLight Machine Gun,lightmg\n")
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture"}')
            ship = mod / "data" / "hulls" / "fx_p.ship"
            _write(ship, '{\n  "hullId": "fx_p",\n  "builtInWings": [\n    "advancedcore"\n  ]\n}\n')
            _write(mod / "data" / "hulls" / "fx_q.ship", '{"hullId": "fx_q", "builtInMods": ["x"], "builtInWings": ["advancedcore"]}')
            found = _findings(scan_mod(mod, vanilla_core=core), "builtin-wing-is-hullmod")
            content = _findings(scan_mod(mod, vanilla_core=core), "content-reference-unresolved")
            apply_fix(compute_fix(mod, "builtin-wing-is-hullmod", {"vanilla_core": core}))
            text = ship.read_text(encoding="utf-8")
            after = [f.file for f in _findings(scan_mod(mod, vanilla_core=core), "builtin-wing-is-hullmod")]
        self.assertEqual(sorted(f.file for f in found), ["data/hulls/fx_p.ship", "data/hulls/fx_q.ship"])
        self.assertFalse(any("wing:advancedcore" in str(f.evidence) for f in content))
        self.assertIn('"builtInMods": [\n    "advancedcore"', text)
        self.assertEqual(after, ["data/hulls/fx_q.ship"])  # it already has builtInMods: left to a person


class WingOpCostFixerTests(unittest.TestCase):
    # ROADMAP 34.22 (2026-10-04): the owner's ruling for 36 wings in 7 mods, as an approval-gated fixer.
    def _core(self, root: Path) -> Path:
        core = root / "core"
        _write(core / "data" / "hulls" / "wing_data.csv", "id,variant,role,fleet pts,num,op cost\n"
               "talon_wing,talon,INTERCEPTOR,3,4,2\nbroadsword_wing,bs,FIGHTER,6,3,8\n")
        return core

    def test_legacy_layout_gets_the_column_and_only_fittable_wings_get_a_cost(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = self._core(root)
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id":"fixture"}')
            path = mod / "data" / "hulls" / "wing_data.csv"
            _write(path, "id,variant,fleet pts,num,role\nfx_fighter_wing,fx,6,3,FIGHTER\nfx_spare_wing,fx2,3,4,INTERCEPTOR\n")
            _write(mod / "data" / "variants" / "fx_carrier.variant", '{"variantId": "fx_carrier", "wings": ["fx_fighter_wing"]}')
            findings = [SimpleNamespace(id="wing-op-cost-blank", file="data/hulls/wing_data.csv", evidence=[f"wing:{w}"])
                        for w in ("fx_fighter_wing", "fx_spare_wing")]
            apply_fix(compute_fix(mod, "wing-op-cost-blank", {"vanilla_core": core, "scan_findings": findings}))
            text = path.read_text(encoding="utf-8")
            with self.assertRaises(FixerError):
                compute_fix(mod, "wing-op-cost-blank", {"scan_findings": findings})  # no vanilla core: refused
        self.assertEqual(text, "id,variant,fleet pts,num,role,op cost\nfx_fighter_wing,fx,6,3,FIGHTER,8\nfx_spare_wing,fx2,3,4,INTERCEPTOR,\n")
