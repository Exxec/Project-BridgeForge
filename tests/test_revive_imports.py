"""Import resolution from the provider index inside revive's packets (ROADMAP item 73 B7)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.escalation.escalation import list_packets, load_packet
from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.revive import build_packets, import_resolution, render_packet, revive
from bridgeforge.substitutes import Provider
from tests.support import resolved_temp_dir


def _provider(mod_id: str, classes: set, version: str = "1.0") -> Provider:
    provider = Provider(mod_id, mod_id.title(), f"/x/{mod_id}", "0.98a", version=version)
    provider.provides["class"] |= classes
    return provider


def _import_finding(*imports: str) -> dict:
    return {"id": "source-import-unresolved", "file": None, "classification": "REVIEW", "severity": "high", "confidence": "HIGH",
            "explanation": "x", "evidence": list(imports)}


def _w(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ImportResolutionTests(unittest.TestCase):
    def test_one_provider_resolves_with_a_fix_option_carrying_id_and_version(self) -> None:
        found = import_resolution([_import_finding("data.scripts.Foo")],
                                  [_provider("fooprov", {"data.scripts.Foo"}, "2.1"), _provider("other", {"data.scripts.Bar"})])
        self.assertEqual(len(found["fix_options"]), 1)
        option = found["fix_options"][0]
        self.assertEqual(option["fixer"], "undeclared-library-dependency")
        self.assertEqual(option["options"]["declare_providers"], [{"id": "fooprov", "name": "Fooprov"}])
        self.assertEqual((option["provider_version"], option["covers"]), ("2.1", ["data.scripts.Foo"]))

    def test_two_providers_give_no_option_and_both_are_named(self) -> None:
        found = import_resolution([_import_finding("data.scripts.Foo")], [_provider("a", {"data.scripts.Foo"}), _provider("b", {"data.scripts.Foo"})])
        self.assertEqual(found["fix_options"], [])
        self.assertIn("a, b", found["imports"][0]["note"])

    def test_no_provider_says_so_or_cites_the_drift_catalogue_and_same_package_leads(self) -> None:
        providers = [_provider("near", {"data.scripts.Other"})]
        plain = import_resolution([_import_finding("data.scripts.Foo")], providers)
        self.assertEqual(plain["imports"][0]["note"], "not provided by any indexed mod")
        self.assertEqual(plain["imports"][0]["same_package_leads"], ["near"])
        catalogue = {"removed_classes": [{"class": "data.scripts.Foo", "same_name_elsewhere": ["data.scripts.x.Foo"]}]}
        cited = import_resolution([_import_finding("data.scripts.Foo", "... 3 more")], providers, catalogue)
        self.assertIn("API drift catalogue", cited["imports"][0]["note"])
        self.assertEqual(cited["unexamined"], 3)

    def test_packet_carries_the_resolution_and_renders_it(self) -> None:
        finding = _import_finding("data.scripts.Foo")
        with resolved_temp_dir() as root:
            packets = build_packets(root, [finding], [], vanilla_core=None,
                                    imports_for=lambda group: import_resolution(group, [_provider("fooprov", {"data.scripts.Foo"})]))
            plain = build_packets(root, [finding], [], vanilla_core=None)
        text = render_packet(packets[0])
        self.assertIn("Declare `fooprov`", text)
        self.assertIn("--declare-provider", text)
        self.assertNotIn("import_resolution", plain[0])

    def test_the_fixer_declares_the_approved_provider_idempotently(self) -> None:
        with resolved_temp_dir() as root:
            _w(root / "mod_info.json", '{"id": "m", "name": "M", "version": "1", "gameVersion": "0.98a"}')
            options = {"declare_providers": [{"id": "fooprov", "name": "Foo Provider"}]}
            apply_fix(compute_fix(root, "undeclared-library-dependency", options))
            info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
            with self.assertRaises(FixerError):
                compute_fix(root, "undeclared-library-dependency", options)
        self.assertEqual(info["dependencies"], [{"id": "fooprov", "name": "Foo Provider"}])

    def test_revive_attaches_the_resolution_from_the_queue(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            workspace = queue / "Needy"
            _w(workspace / "working" / "mod_info.json", '{"id": "needy", "name": "Needy", "version": "1", "gameVersion": "0.98a"}')
            _w(workspace / "working" / "data" / "scripts" / "Use.java", "package data.scripts;\nimport data.scripts.Foo;\npublic class Use { Foo f; }\n")
            _w(queue / "Prov" / "working" / "mod_info.json", '{"id": "fooprov", "name": "Foo Provider", "version": "2.1", "gameVersion": "0.98a"}')
            _w(queue / "Prov" / "working" / "data" / "scripts" / "Foo.java", "package data.scripts;\npublic class Foo {}\n")
            revive(workspace)
            ids = [p["id"] for p in list_packets(workspace) if p["id"].startswith("source-import-unresolved")]
            packet = load_packet(workspace, ids[0])
        self.assertEqual(packet["import_resolution"]["fix_options"][0]["options"]["declare_providers"][0]["id"], "fooprov")


if __name__ == "__main__":
    unittest.main()
