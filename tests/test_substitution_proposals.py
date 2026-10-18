"""Substitution proposals and the content-reference-substitute fixer (ROADMAP item 73 C3)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.substitution_proposals import propose, render_lines
from tests.support import resolved_temp_dir

VARIANT = '{\n\t"variantId": "wolf_Test",\n\t"hullId": "wolf",\n\t"weaponGroups": [{"weapons": {"WS0001": "old_laser", "WS0002": "keep_me"}}],\n\t"old_laser": 1\n}\n'


def _csv(path: Path, header: str, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")


def _core(root: Path, weapons: list[str], hullmods: list[str] | None = None) -> Path:
    _csv(root / "data" / "weapons" / "weapon_data.csv", "name,id,type", weapons)
    _csv(root / "data" / "hullmods" / "hull_mods.csv", "name,id,desc", hullmods or [])
    return root


def _mod(root: Path, dependencies: list[str] | None = None) -> Path:
    (root / "data" / "variants").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "m", "name": "M", "version": "1", "gameVersion": "0.98a-RC8",
                                                    "dependencies": [{"id": d} for d in dependencies or []]}), encoding="utf-8")
    (root / "data" / "variants" / "wolf_Test.variant").write_bytes(b"\xef\xbb\xbf" + VARIANT.replace("\n", "\r\n").encode("utf-8"))
    return root


UNRESOLVED = {"weapon": {"old_laser": ["data/variants/wolf_Test.variant"]}}


class ProposalSourceTests(unittest.TestCase):
    def test_rename_between_the_reference_install_and_rc8(self) -> None:
        with resolved_temp_dir() as base:
            working = _mod(base / "ws" / "working")
            reference = _core(base / "ref", ["Pulse Laser,old_laser,ENERGY"])
            rc8 = _core(base / "rc8", ["Pulse Laser,new_laser,ENERGY", "Heavy Mauler,other,BALLISTIC"])
            result = propose(working, rc8, reference_core=reference, unresolved=UNRESOLVED)
        item = result["proposals"][0]
        self.assertEqual((item["kind"], item["id"], item["replacement"], item["source"], item["approved"]), ("weapon", "old_laser", "new_laser", "rename", False))
        self.assertIn("pulse laser", item["evidence"])
        self.assertEqual(item["files"], ["data/variants/wolf_Test.variant"])
        self.assertEqual(len(item["file_sha256"]["data/variants/wolf_Test.variant"]), 64)
        self.assertIn("old_laser", "\n".join(render_lines(result)))

    def test_a_shared_name_word_is_not_a_proposal(self) -> None:
        with resolved_temp_dir() as base:
            working = _mod(base / "ws" / "working")
            reference = _core(base / "ref", ["Pulse Laser,old_laser,ENERGY"])
            rc8 = _core(base / "rc8", ["Heavy Laser,other_laser,ENERGY"])
            result = propose(working, rc8, reference_core=reference, unresolved=UNRESOLVED)
        self.assertEqual((result["proposals"], result["unproposed"]), ([], ["weapon:old_laser"]))

    def test_provider_rename_from_a_declared_dependency_only(self) -> None:
        with resolved_temp_dir() as base:
            queue = base / "queue"
            working = _mod(queue / "ws" / "working", dependencies=["acme"])
            (queue / "Acme").mkdir(parents=True)
            (queue / "Acme" / "mod_info.json").write_text(json.dumps({"id": "acme", "name": "Acme", "version": "2", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
            _csv(queue / "Acme" / "data" / "weapons" / "weapon_data.csv", "name,id,type", ["Blaster,old_laser2,ENERGY"])
            rc8 = _core(base / "rc8", [])
            declared = propose(working, rc8, provider_roots=[queue], unresolved=UNRESOLVED)
            (working / "mod_info.json").write_text(json.dumps({"id": "m", "name": "M", "version": "1"}), encoding="utf-8")
            undeclared = propose(working, rc8, provider_roots=[queue], unresolved=UNRESOLVED)
        item = declared["proposals"][0]
        self.assertEqual((item["source"], item["replacement"], item["provider"]), ("provider-rename", "old_laser2", "acme"))
        self.assertEqual(undeclared["proposals"], [])

    def test_catalogue_needs_exactly_one_same_name_lead(self) -> None:
        with resolved_temp_dir() as base:
            working = _mod(base / "ws" / "working")
            rc8 = _core(base / "rc8", [])
            one = {"removed": {"weapon": [{"id": "old_laser", "name": "Pulse Laser", "same_name_in_rc8": ["new_laser"]}]}}
            two = {"removed": {"weapon": [{"id": "old_laser", "same_name_in_rc8": ["a", "b"]}]}}
            found = propose(working, rc8, catalogue=one, unresolved=UNRESOLVED)
            ambiguous = propose(working, rc8, catalogue=two, unresolved=UNRESOLVED)
        self.assertEqual((found["proposals"][0]["source"], found["proposals"][0]["replacement"]), ("catalogue", "new_laser"))
        self.assertEqual(ambiguous["proposals"], [])

    def test_order_is_rename_then_catalogue_with_the_other_kept_as_an_alternative(self) -> None:
        with resolved_temp_dir() as base:
            working = _mod(base / "ws" / "working")
            reference = _core(base / "ref", ["Pulse Laser,old_laser,ENERGY"])
            rc8 = _core(base / "rc8", ["Pulse Laser,new_laser,ENERGY"])
            catalogue = {"removed": {"weapon": [{"id": "old_laser", "same_name_in_rc8": ["different_laser"]}]}}
            item = propose(working, rc8, reference_core=reference, catalogue=catalogue, unresolved=UNRESOLVED)["proposals"][0]
        self.assertEqual((item["source"], item["replacement"]), ("rename", "new_laser"))
        self.assertEqual([(a["source"], a["replacement"]) for a in item["alternatives"]], [("catalogue", "different_laser")])


class SubstituteFixerTests(unittest.TestCase):
    def _setup(self, base: Path, **kwargs):
        working = _mod(base / "ws" / "working", dependencies=kwargs.get("dependencies"))
        reference = _core(base / "ref", ["Pulse Laser,old_laser,ENERGY"])
        rc8 = _core(base / "rc8", ["Pulse Laser,new_laser,ENERGY"])
        proposals = propose(working, rc8, reference_core=reference, unresolved=UNRESOLVED)["proposals"]
        return working, rc8, proposals

    def test_rewrites_only_the_id_value_and_keeps_bom_line_endings_and_keys(self) -> None:
        with resolved_temp_dir() as base:
            working, rc8, proposals = self._setup(base)
            proposals[0]["approved"] = True
            before = (working / "data" / "variants" / "wolf_Test.variant").read_bytes()
            plan = compute_fix(working, "content-reference-substitute", {"substitutions": proposals, "vanilla_core": rc8})
            apply_fix(plan)
            after = (working / "data" / "variants" / "wolf_Test.variant").read_bytes()
        self.assertEqual(after, before.replace(b'"WS0001": "old_laser"', b'"WS0001": "new_laser"'))
        self.assertIn(b'"old_laser": 1', after)  # a key of the same name is not a reference
        self.assertTrue(after.startswith(b"\xef\xbb\xbf") and b"\r\n" in after)

    def test_unapproved_entries_do_nothing(self) -> None:
        with resolved_temp_dir() as base:
            working, rc8, proposals = self._setup(base)
            with self.assertRaises(FixerError) as caught:
                compute_fix(working, "content-reference-substitute", {"substitutions": proposals, "vanilla_core": rc8})
        self.assertIn("no approved substitution", str(caught.exception))

    def test_a_stale_approval_and_an_unknown_replacement_are_refused(self) -> None:
        with resolved_temp_dir() as base:
            working, rc8, proposals = self._setup(base)
            proposals[0]["approved"] = True
            with self.assertRaises(FixerError) as no_core:
                compute_fix(working, "content-reference-substitute", {"substitutions": proposals})
            wrong = [{**proposals[0], "replacement": "not_in_rc8"}]
            with self.assertRaises(FixerError) as unknown:
                compute_fix(working, "content-reference-substitute", {"substitutions": wrong, "vanilla_core": rc8})
            path = working / "data" / "variants" / "wolf_Test.variant"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaises(FixerError) as stale:
                compute_fix(working, "content-reference-substitute", {"substitutions": proposals, "vanilla_core": rc8})
        self.assertIn("pass the vanilla core", str(no_core.exception))
        self.assertIn("does not define", str(unknown.exception))
        self.assertIn("stale approval", str(stale.exception))

    def test_a_provider_replacement_needs_the_dependency_declared(self) -> None:
        with resolved_temp_dir() as base:
            working, rc8, proposals = self._setup(base)
            entry = {**proposals[0], "source": "provider-rename", "provider": "acme", "replacement": "acme_laser", "approved": True}
            with self.assertRaises(FixerError) as refused:
                compute_fix(working, "content-reference-substitute", {"substitutions": [entry]})
            (working / "mod_info.json").write_text(json.dumps({"id": "m", "dependencies": [{"id": "acme"}]}), encoding="utf-8")
            plan = compute_fix(working, "content-reference-substitute", {"substitutions": [entry]})
        self.assertIn("not a declared dependency", str(refused.exception))
        self.assertIn(b'"WS0001": "acme_laser"', plan.changes[0].after)

    def test_a_file_outside_the_mod_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            working, rc8, proposals = self._setup(base)
            entry = {**proposals[0], "approved": True, "files": ["../../ref/data/weapons/weapon_data.csv"]}
            with self.assertRaises(FixerError) as refused:
                compute_fix(working, "content-reference-substitute", {"substitutions": [entry], "vanilla_core": rc8})
        self.assertIn("outside the mod or missing", str(refused.exception))

    def test_the_tier_and_the_fix_command_are_registered(self) -> None:
        from bridgeforge.automation import tier_for
        from bridgeforge.fixers import SUPPORTED_FINDINGS

        self.assertIn("content-reference-substitute", SUPPORTED_FINDINGS)
        self.assertEqual(tier_for("content-reference-substitute"), "input")


class PacketIntegrationTests(unittest.TestCase):
    def test_a_missing_content_packet_lists_the_proposals(self) -> None:
        from bridgeforge.revive import _render_options

        result = {"proposals": [{"kind": "weapon", "id": "old_laser", "replacement": "new_laser", "source": "rename", "evidence": "same name",
                                 "alternatives": []}], "unproposed": ["hull:gone"]}
        text = "\n".join(_render_options({"proposals": result, "notes": []}))
        self.assertIn("`weapon:old_laser` -> `new_laser` (rename): same name", text)
        self.assertIn("no replacement found for: hull:gone", text)


if __name__ == "__main__":
    unittest.main()
