from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod


class RevivalLessonsScannerTests(unittest.TestCase):
    def test_csv_spill_is_not_treated_as_structurally_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "descriptions.csv").write_text(
                "id,type,text1\nship,SHIP,expected,spilled\n",
                encoding="utf-8",
            )
            finding = next(item for item in scan_mod(root).findings if item.id == "csv-row-extra-columns")
            self.assertEqual(finding.classification, "MANUAL")
            self.assertEqual(finding.file, "data/descriptions.csv")
            self.assertEqual(finding.evidence[:3], ["line:2", "header-columns:3", "row-columns:4"])

    def test_local_weapon_spec_missing_from_local_registry_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            weapons = root / "data" / "weapons"
            weapons.mkdir(parents=True)
            (weapons / "weapon_data.csv").write_text(
                "name,id\nRegistered,fixture_registered\n",
                encoding="utf-8",
            )
            (weapons / "fixture_registered.wpn").write_text("{}", encoding="utf-8")
            (weapons / "fixture_orphan.wpn").write_text("{}", encoding="utf-8")

            result = scan_mod(root)
            findings = [item for item in result.findings if item.id == "local-weapon-spec-unregistered"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertEqual(findings[0].file, "data/weapons/fixture_orphan.wpn")
            self.assertEqual(
                result.migration_context["content_graph"]["locally_registered_weapons"],
                ["fixture_registered"],
            )

    def test_variant_id_in_weapon_slot_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = root / "data" / "variants"
            variants.mkdir(parents=True)
            (variants / "fixture_child.variant").write_text("{}", encoding="utf-8")
            (variants / "fixture_parent.variant").write_text(
                '{"weaponGroups":[{"weapons":{"MODULE1":"fixture_child"}}],'
                '"modules":[{"MODULE2":"fixture_child"}]}',
                encoding="utf-8",
            )

            result = scan_mod(root)
            findings = [item for item in result.findings if item.id == "variant-id-in-weapon-slot"]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertEqual(
                findings[0].evidence,
                ["group:0", "slot:MODULE1", "variant:fixture_child"],
            )

    def test_known_target_interface_expansions_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "src"
            sources.mkdir()
            (sources / "OldOnHit.java").write_text(
                "class OldOnHit implements OnHitEffectPlugin { "
                "public void onHit(DamagingProjectileAPI p, CombatEntityAPI t, Vector2f v, "
                "boolean shield, CombatEngineAPI engine) {} }",
                encoding="utf-8",
            )
            (sources / "OldAutofire.java").write_text(
                "class OldAutofire implements AutofireAIPlugin {}",
                encoding="utf-8",
            )
            (sources / "OldSystem.java").write_text(
                "class OldSystem implements ShipSystemStatsScript { "
                "public float getRegenOverride(ShipAPI ship) { return -1f; } }",
                encoding="utf-8",
            )
            (sources / "OldHullMod.java").write_text(
                "class OldHullMod implements HullModEffect {}",
                encoding="utf-8",
            )

            missing = {
                tuple(item.evidence)
                for item in scan_mod(root).findings
                if item.id == "target-interface-method-missing"
            }
            self.assertIn(
                ("OnHitEffectPlugin", "void onHit(..., ApplyDamageResultAPI, CombatEngineAPI)"),
                missing,
            )
            self.assertIn(("AutofireAIPlugin", "MissileAPI getTargetMissile()"), missing)
            self.assertIn(("ShipSystemStatsScript", "float getActiveOverride(ShipAPI)"), missing)
            self.assertNotIn(("ShipSystemStatsScript", "float getRegenOverride(ShipAPI)"), missing)
            self.assertIn(("HullModEffect", "boolean showInRefitScreenModPickerFor(ShipAPI)"), missing)

    def test_current_on_hit_signature_satisfies_target_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root / "src"
            sources.mkdir()
            (sources / "CurrentOnHit.java").write_text(
                "class CurrentOnHit implements OnHitEffectPlugin { "
                "public void onHit(DamagingProjectileAPI p, CombatEntityAPI t, Vector2f v, "
                "boolean shield, ApplyDamageResultAPI result, CombatEngineAPI engine) {} }",
                encoding="utf-8",
            )
            missing = [
                item
                for item in scan_mod(root).findings
                if item.id == "target-interface-method-missing"
                and item.evidence[0] == "OnHitEffectPlugin"
            ]
            self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
