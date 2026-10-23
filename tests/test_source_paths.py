
"""ROADMAP-3 83 B0: moving a source must never remove it from an audit."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import Mock, patch

from bridgeforge.atlas import atlas
from bridgeforge import checks_index
from bridgeforge import cli_commands
from bridgeforge import scan_registry
from bridgeforge import source_paths
from bridgeforge.merge_train import test_modules_for
from tests import test_bug_class_registry as bug_audit
from tests import test_hull_id_resolution_audit as hull_audit
from tests import test_safeio_ratchet as safeio_audit
from tests import test_skin_chain_resolution_audit as skin_audit
from tests import test_probe_contract as probe_contract
from tests.support import resolved_temp_dir

ROOT = Path(__file__).resolve().parent.parent


class SourcePathsTests(unittest.TestCase):
    def test_inventory_includes_duplicate_leaves_and_excludes_caches(self):
        with resolved_temp_dir() as root:
            for name in ("a.py", "pkg/a.py", "pkg/deep/__init__.py", "__pycache__/hidden.py", "pkg/__pycache__/hidden.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            (root / "directory.py").mkdir()
            self.assertEqual([p.relative_to(root).as_posix() for p in source_paths.python_sources(root)],
                             ["a.py", "pkg/a.py", "pkg/deep/__init__.py"])

    def test_every_audit_discovers_the_entire_python_inventory_before_exemptions(self):
        package = ROOT / "bridgeforge"
        expected = {p for p in package.rglob("*.py") if p.is_file() and "__pycache__" not in p.relative_to(package).parts}
        consumers = (
            (safeio_audit, safeio_audit.counts),
            (hull_audit, hull_audit.hull_id_builders),
            (checks_index, checks_index.gather),
            (scan_registry, scan_registry.scanner_identity),
            (source_paths, atlas._extractor_digest),
            (source_paths, skin_audit._scanner_source),
            (source_paths, bug_audit.BugClassRegistryTests("test_every_listed_check_id_exists_somewhere_in_the_codebase").test_every_listed_check_id_exists_somewhere_in_the_codebase),
        )
        original = source_paths.python_sources
        for module, run in consumers:
            visited = []
            def inventory(root):
                paths = original(root)
                if Path(root) == package:
                    visited.append(set(paths))
                return paths
            with self.subTest(consumer=run.__qualname__), patch.object(module, "python_sources", side_effect=inventory), patch.object(scan_registry, "_SCANNER_CACHE", {}):
                run()
                self.assertTrue(visited, "consumer bypassed the source inventory")
                for found in visited:
                    self.assertEqual(found, expected)

    def test_ratchet_keeps_nested_names_distinct_and_exempts_only_root_safeio(self):
        with resolved_temp_dir() as root:
            for name in ("same.py", "pkg/same.py", "safeio.py", "pkg/safeio.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("x.write_text('x')\n", encoding="utf-8")
            with patch.object(safeio_audit, "PACKAGE", root):
                self.assertEqual(set(safeio_audit.counts()), {"same.py", "pkg/same.py", "pkg/safeio.py"})

    def test_hull_audit_sees_nested_builders_with_distinct_paths(self):
        with resolved_temp_dir() as root:
            for name in ("same.py", "pkg/same.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("def f(root):\n    return _ship_file_index(root)\n", encoding="utf-8")
            with patch.object(hull_audit, "PACKAGE", root):
                self.assertEqual(hull_audit.hull_id_builders(), {("same.py", "f"): False, ("pkg/same.py", "f"): False})

    def test_families_include_renamed_leaves_in_future_packages(self):
        with resolved_temp_dir() as root:
            for name in ("atlas.py", "atlas_data.py", "atlas/reader.py", "scan/checks.py", "other.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            self.assertEqual({p.relative_to(root).as_posix() for p in source_paths.family_sources(root, "atlas")},
                             {"atlas.py", "atlas_data.py", "atlas/reader.py"})

    def test_checks_index_reads_nested_sources_and_tests_without_leaf_collisions(self):
        with resolved_temp_dir() as root:
            for name, text in (
                ("bridgeforge/a/same.py", 'def f(r):\n    r.add(id="nested-alpha", severity="low", classification="SAFE")\n'),
                ("bridgeforge/b/same.py", 'def f(r):\n    r.add(id="nested-beta", severity="low", classification="SAFE")\n'),
                ("tests/a/test_same.py", 'ID = "nested-alpha"\n'),
                ("tests/b/test_same.py", 'ID = "nested-beta"\n'),
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            result = checks_index.gather(root)
            self.assertEqual(result.checks["nested-alpha"].where, {"a/same.py:f"})
            self.assertEqual(result.checks["nested-beta"].where, {"b/same.py:f"})
            self.assertEqual(result.tests["nested-alpha"], ["a.test_same"])
            self.assertEqual(result.tests["nested-beta"], ["b.test_same"])

    def test_fingerprints_notice_nested_code_and_rules_but_ignore_caches(self):
        with resolved_temp_dir() as root:
            path = root / "pkg" / "nested.py"
            path.parent.mkdir()
            path.write_text("x = 1\n", encoding="utf-8")
            def identity():
                with patch.object(scan_registry, "__file__", str(root / "scan_registry.py")), patch.object(scan_registry, "_SCANNER_CACHE", {}):
                    return scan_registry.scanner_identity()
            first = identity()
            path.write_text("x = 2\n", encoding="utf-8")
            second = identity()
            self.assertNotEqual(first, second)
            rule = path.with_suffix(".json")
            rule.write_text("{}", encoding="utf-8")
            third = identity()
            self.assertNotEqual(second, third)
            cache = root / "__pycache__"
            cache.mkdir()
            (cache / "ignored.py").write_text("ignored", encoding="utf-8")
            (cache / "ignored.json").write_text("{}", encoding="utf-8")
            self.assertEqual(third, identity())
            path.rename(root / "nested.py")
            self.assertNotEqual(third, identity())

    def test_atlas_identity_includes_renamed_nested_extractor(self):
        with resolved_temp_dir() as root:
            package = root / "atlas"
            package.mkdir()
            path = package / "reader.py"
            path.write_text("x = 1\n", encoding="utf-8")
            with patch.object(atlas, "__file__", str(root / "atlas" / "atlas.py")):
                before = atlas._extractor_digest()
                path.write_text("x = 2\n", encoding="utf-8")
                self.assertNotEqual(before, atlas._extractor_digest())

    def test_probe_reader_sees_nested_java_sources(self):
        with resolved_temp_dir() as root:
            nested = root / "nested"
            nested.mkdir()
            (nested / "Reader.java").write_text('root.optString("nested_key");', encoding="utf-8")
            with patch.object(probe_contract, "PROBE", root):
                self.assertEqual(probe_contract.java_read_keys(), {"nested_key"})

    def test_nested_module_mapping_supports_flat_and_nested_tests_and_windows_paths(self):
        with resolved_temp_dir() as root:
            for name in ("test_reader.py", "pkg/test_reader_extra.py", "pkg/test_other.py", "__pycache__/test_reader_bad.py"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            paths = ["bridgeforge/pkg/reader.py", "bridgeforge\\pkg\\reader.py", "docs/reader.py"]
            self.assertEqual(test_modules_for(paths, root), ["tests.pkg.test_reader_extra", "tests.test_reader"])

    def test_prepush_powershell_mapping_matches_python_mapping(self):
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            self.assertIn("-Recurse", (ROOT / "tools/prepush-check.ps1").read_text(encoding="utf-8"))
            return
        with resolved_temp_dir() as root:
            for name in ("test_reader.py", "pkg/test_reader_extra.py", "__pycache__/test_reader_bad.py"):
                path = root / "tests" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            script = (ROOT / "tools/prepush-check.ps1").read_text(encoding="utf-8")
            selector = script[script.index("$modules=@($crossCutting)"):script.index("# Git runs hooks")]
            setup = "$root='" + str(root).replace("'", "''") + "'\n$crossCutting=@()\n"
            setup += "function git { if($args -contains 'diff'){'bridgeforge/pkg/reader.py'}; $global:LASTEXITCODE=0 }\n"
            result = subprocess.run([shell, "-NoProfile", "-Command", setup + selector + "\nConvertTo-Json -InputObject @($modules) -Compress"],
                                    capture_output=True, text=True, timeout=30, check=True)
            self.assertEqual(set(json.loads(result.stdout)), set(test_modules_for(["bridgeforge/pkg/reader.py"], root / "tests")))

    def test_command_registry_accepts_dotted_module_paths(self):
        module = Mock()
        with patch.object(cli_commands, "COMMAND_MODULES", {"research.cli": ("research",)}), patch.object(cli_commands.importlib, "import_module", return_value=module) as load:
            cli_commands.register_all("subcommands")
            self.assertIs(cli_commands.handler_for("research"), module.run_cli)
            self.assertEqual(load.call_args_list, [unittest.mock.call("bridgeforge.research.cli")] * 2)
            module.add_parser.assert_called_once_with("subcommands")
