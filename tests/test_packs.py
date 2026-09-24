import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge import __version__
from bridgeforge.migrate import load_rules
from bridgeforge.packs import BRIDGEFORGE_VERSION, MigrationPack, compatible, discover_packs, resolve_pack_rule_paths
from bridgeforge.pack_candidate import create_migration_pack_candidate



class PacksTests(unittest.TestCase):
    def test_pack_candidate_is_non_loadable_evidence_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.json"
            create_migration_pack_candidate("org.magiclib", "magic-render-example", "Old.render", "MagicRender.battlespace", output)
            candidate = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(candidate["mode"], "RESEARCH_CANDIDATE_NOT_A_MIGRATION_PACK")
            self.assertEqual(candidate["automatic_modification"], "FORBIDDEN_UNTIL_EVIDENCE_COMPLETE")
            self.assertEqual(len(candidate["evidence_required"]), 7)
            with self.assertRaises(ValueError):
                create_migration_pack_candidate("org.magiclib", "magic-render-example", "Old.render", "MagicRender.battlespace", output)

    def test_bundled_pack_registry_is_unique_and_conservative(self) -> None:
        packs = discover_packs()
        self.assertGreaterEqual(len(packs), 8)
        self.assertEqual(len({pack.id for pack in packs}), len(packs))
        self.assertTrue(all(pack.status == "SCAFFOLDED" for pack in packs))
        self.assertEqual(resolve_pack_rule_paths(["java"]), [])


    def test_pack_version_compatibility_is_enforced(self) -> None:
        self.assertEqual(BRIDGEFORGE_VERSION, __version__)
        alpha_pack = MigrationPack("alpha", "alpha", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.1.0a1")
        final_pack = MigrationPack("final", "final", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.1.0")
        later_pack = MigrationPack("later", "later", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.2.1")
        self.assertTrue(compatible(alpha_pack))
        self.assertTrue(compatible(final_pack))
        self.assertFalse(compatible(later_pack))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "future"
            pack.mkdir()
            (pack / "pack.json").write_text(json.dumps({"schema_version": 1, "id": "future", "name": "future", "scope": "test", "status": "SCAFFOLDED", "min_bridgeforge_version": "2.0.0"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_pack_rule_paths(["future"], root)


    def test_library_migration_rules_require_verified_evidence_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            base = {"id": "library-rule", "classification": "REVIEW", "confidence": "HIGH", "description": "fixture", "file": "mod_info.json", "json_key": "gameVersion", "value_from_target": "starsector"}
            path.write_text(json.dumps({"pack": {"schema_version": 1, "id": "magiclib"}, "rules": [base]}), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_rules([path])
            base["evidence"] = {field: "verified" for field in ("provenance", "before_fixture", "after_fixture", "compile_validation", "idempotence", "conflict_review", "save_risk_assessment")}
            path.write_text(json.dumps({"pack": {"schema_version": 1, "id": "magiclib"}, "rules": [base]}), encoding="utf-8")
            self.assertEqual(load_rules([path])[0].id, "library-rule")


