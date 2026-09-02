import json
import io
import tempfile
import unittest
import warnings
import zipfile
import shutil
import subprocess
from contextlib import redirect_stderr
from unittest.mock import patch
from pathlib import Path

from bridgeforge import __version__, scanner
from bridgeforge.bytecode import inspect_bytecode, rewrite_class
from bridgeforge.bytecode_diff import diff_bytecode
from bridgeforge.bytecode_rules import apply_bytecode_class, apply_bytecode_jar, load_bytecode_rules, plan_bytecode
from bridgeforge.scanner import scan_mod
from bridgeforge.report import write_artifacts
from bridgeforge.migrate import apply_plan, build_plan, load_rules
from bridgeforge.models import TargetProfile
from bridgeforge.workspace import create_workspace, rollback, workspace_paths
from bridgeforge.build import compile_feedback, create_build_profile, package_compiled_jar, resolve_registered_dependency_jars, run_compile
from bridgeforge.library_registry import LibraryRegistryEntry, load_library_registry
from bridgeforge.review import create_review_bundle
from bridgeforge.validate import validate_workspace
from bridgeforge.save_risk import analyze_save_risk
from bridgeforge.pipeline import run_pipeline
from bridgeforge.packs import BRIDGEFORGE_VERSION, MigrationPack, compatible, discover_packs, resolve_pack_rule_paths
from bridgeforge.opportunities import analyze_opportunities
from bridgeforge.doctor import doctor
from bridgeforge.conflicts import detect_conflicts
from bridgeforge.provenance import write_provenance
from bridgeforge.corpus import compare_corpus
from bridgeforge.evaluation import evaluate_releases
from bridgeforge.runtime import create_runtime_profile, run_runtime_smoke
from bridgeforge.fixtures import discover_compatibility_fixtures, discover_corpus_baselines
from bridgeforge.interface import export_patch, inspect_workspace
from bridgeforge.corpus_audit import audit_directories
from bridgeforge.corpus_audit import write_corpus_audit
from bridgeforge.archive_intake import inspect_zip_archive, stage_zip_archive
from bridgeforge.library_api import inventory_library_api, match_library_imports
from bridgeforge.pack_candidate import create_migration_pack_candidate
from bridgeforge.cli import main



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
        later_pack = MigrationPack("later", "later", "test", "SCAFFOLDED", None, Path("."), min_bridgeforge_version="0.1.1")
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


