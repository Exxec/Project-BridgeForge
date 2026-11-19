"""94.G1: gene manifests (gene.json schema 2) and their content-hash identity."""
from __future__ import annotations

import io
import json
import shutil
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge.cli import main
from bridgeforge.genome.gene import GENE_SCHEMA_VERSION, REQUIRED_KEYS, GeneError, describe, identity, validate
from tests.support import resolved_temp_dir
from tests.test_vendor_plan import _rebal, _vanilla


class GeneManifestTests(unittest.TestCase):
    def test_a_hull_mod_gene_lists_its_closure_with_hashes_and_validates(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_rebal(root), "hullmod:shields_formshield", vanilla_core=_vanilla(root))
        self.assertEqual(validate(gene), [])
        self.assertEqual((gene["schema_version"], gene["kind"], gene["anchors"]), (GENE_SCHEMA_VERSION, "hullmod", ["hullmod:shields_formshield"]))
        paths = {(m["what"], m["path"]) for m in gene["members"]}
        self.assertIn(("csv-row", "data/hullmods/hull_mods.csv [shields_formshield]"), paths)
        self.assertIn(("file", "data/hullmods/FormShield.java"), paths)
        self.assertIn(("file", "graphics/fx/formshield_glow.png"), paths)
        self.assertTrue(all(len(m["sha256"]) == 64 for m in gene["members"]))
        self.assertEqual(gene["provenance"]["mod_id"], "@_ss_rebal_@")
        self.assertEqual(gene["phenotype_obligations"], ["the hull mod applies to a ship and shows its effect"])
        self.assertIn("data/scripts/plugins/FormShieldPlugin.java", {s["path"] for s in gene["unknowns"]["suspects"]})
        self.assertEqual(gene["collected_from"], ["vendor-plan"])
        self.assertEqual(sorted(gene), sorted(REQUIRED_KEYS))

    def test_the_same_feature_in_another_mod_and_line_ending_is_the_same_allele(self) -> None:
        with resolved_temp_dir() as root:
            first = describe(_rebal(root / "a"), "weapon:rebal_rail")
            copy = root / "b" / "Copied-Elsewhere"
            shutil.copytree(root / "a" / "Xenoargh-Rebal", copy)
            working = copy / "working"
            (working / "mod_info.json").write_text(json.dumps({"id": "other_mod", "name": "Other"}), encoding="utf-8")
            for path in working.rglob("*.java"):  # the other line ending, whichever the fixture was written with
                data = path.read_bytes()
                path.write_bytes(data.replace(b"\r\n", b"\n") if b"\r\n" in data else data.replace(b"\n", b"\r\n"))
            second = describe(copy, "weapon:rebal_rail")
            (working / "data/weapons/proj/rebal_rail_shot.proj").write_text('{"id": "rebal_rail_shot", "sprite": "graphics/missiles/rail_shot.png", "speed": 9}', encoding="utf-8")
            changed = describe(copy, "weapon:rebal_rail")
        self.assertEqual(first["identity"], second["identity"])
        self.assertNotEqual(first["provenance"], second["provenance"])  # provenance is recorded but is not identity
        self.assertNotEqual(changed["identity"], first["identity"])

    def test_a_bad_anchor_or_an_id_the_mod_lacks_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            mod = _rebal(root)
            for anchor, message in (("faction:x", "kind one of"), ("weapon", "kind one of"), ("weapon:nope", "not defined")):
                with self.subTest(anchor=anchor), self.assertRaisesRegex(GeneError, message):
                    describe(mod, anchor)

    def test_validate_catches_a_tampered_manifest(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_rebal(root), "weapon:rebal_rail")
        tampered = json.loads(json.dumps(gene))
        tampered["members"][0]["sha256"] = "0" * 64
        self.assertIn("identity does not match the members", validate(tampered))
        self.assertEqual(validate({**gene, "schema_version": 1})[0][:9], "schema is")  # schema 1 is withdrawn
        self.assertIn("missing licence", validate({k: v for k, v in gene.items() if k != "licence"}))
        self.assertEqual(validate([]), ["a manifest is a JSON object"])
        self.assertEqual(identity(gene["kind"], list(reversed(gene["members"]))), gene["identity"])  # order does not matter

    def test_describing_twice_gives_the_same_manifest(self) -> None:
        with resolved_temp_dir() as root:
            mod = _rebal(root)
            self.assertEqual(describe(mod, "hullmod:shields_formshield"), describe(mod, "hullmod:shields_formshield"))

    def test_a_csv_row_is_its_trimmed_named_cells(self) -> None:
        """BOM, cell padding and cells past the header leave the identity alone; a changed value does not."""
        with resolved_temp_dir() as root:
            mod = _rebal(root)
            table = mod / "working" / "data/weapons/weapon_data.csv"
            first = describe(mod, "weapon:rebal_rail")
            table.write_bytes(b"\xef\xbb\xbfname,id\r\n\"Rail \", rebal_rail ,extra cell\r\n")
            padded = describe(mod, "weapon:rebal_rail")
            table.write_text("name,id\nRail Gun,rebal_rail\n", encoding="utf-8")
            renamed = describe(mod, "weapon:rebal_rail")
        self.assertEqual(padded["identity"], first["identity"])
        self.assertNotEqual(renamed["identity"], first["identity"])

    def test_a_text_file_ignores_bom_trailing_space_and_blank_end_lines(self) -> None:
        with resolved_temp_dir() as root:
            mod = _rebal(root)
            source = mod / "working" / "data/scripts/weapons/RailOnHit.java"
            first = describe(mod, "weapon:rebal_rail")
            source.write_bytes(b"\xef\xbb\xbfpackage data.scripts.weapons;   \rpublic class RailOnHit {}\t\n\n\n")
            same = describe(mod, "weapon:rebal_rail")
            source.write_text("package data.scripts.weapons;\npublic class RailOnHit { int x; }\n", encoding="utf-8")
            changed = describe(mod, "weapon:rebal_rail")
        self.assertEqual(same["identity"], first["identity"])
        self.assertNotEqual(changed["identity"], first["identity"])

    def test_a_jar_class_member_is_named_by_its_jar_path_and_a_junction_is_not_followed(self) -> None:
        from tests.support import javac_path, link_dir

        javac = javac_path()
        if javac is None:
            self.skipTest("no JDK")
        import subprocess
        import zipfile

        with resolved_temp_dir() as root:
            mod = _rebal(root)
            working = mod / "working"
            (working / "data/scripts/weapons/RailOnHit.java").unlink()  # compiled only, as many mods ship it
            src = root / "src" / "data" / "scripts" / "weapons" / "RailOnHit.java"
            src.parent.mkdir(parents=True)
            src.write_text("package data.scripts.weapons;\npublic class RailOnHit {}\n", encoding="utf-8")
            subprocess.run([javac, "-encoding", "UTF-8", "-proc:none", "-d", str(root / "classes"), str(src)], check=True, capture_output=True)
            (working / "jars").mkdir()
            with zipfile.ZipFile(working / "jars" / "rebal.jar", "w") as jar:
                jar.write(root / "classes" / "data/scripts/weapons/RailOnHit.class", "data/scripts/weapons/RailOnHit.class")
            outside = root / "outside"
            (outside).mkdir()
            # A valid copy reachable only through the link: "aaa_link/" sorts first, so following the link would pick it.
            (outside / "rebal.jar").write_bytes((working / "jars" / "rebal.jar").read_bytes())
            link_dir(outside, working / "aaa_link")
            gene = describe(mod, "weapon:rebal_rail")
        jar_members = [m for m in gene["members"] if m["what"] == "jar-class"]
        self.assertEqual([m["path"] for m in jar_members], ["jars/rebal.jar!data/scripts/weapons/RailOnHit.class"])
        self.assertEqual(validate(gene), [])

    def test_validate_reports_malformed_shapes_without_raising(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_rebal(root), "weapon:rebal_rail")
        cases = {"members": None, "needs": [], "unknowns": {"missing": []}, "licence": {}, "build": "x", "anchors": ["hull:x"],
                 "schema_version": True, "identity": 5}
        for key, value in cases.items():
            with self.subTest(key=key):
                self.assertNotEqual(validate({**gene, key: value}), [])
        twice = {**gene, "members": gene["members"] + gene["members"][:1]}
        self.assertIn("a member is listed twice", validate(twice))
        self.assertNotEqual(validate({**gene, "members": [{"what": "file", "path": 5, "sha256": "0" * 64}]}), [])

    def test_schema_2_elements_derived_from_and_licence_shapes(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_rebal(root), "weapon:rebal_rail")
        self.assertIsNone(gene["derived_from"])
        self.assertEqual(gene["licence"]["local_only_members"], [])
        good = {**gene, "registrations": [{"locus": "data/scripts/Plugin.java#onApplicationLoad", "statement": "x", "extra": 1}],
                "conditions": [{"kind": "mod-enabled", "subject": "nexerelin"}], "persistent_state": [{"name": "a.B", "via": "xstream"}],
                "derived_from": {"identity": "a" * 64, "by": "relink", "from_build": None}}
        self.assertEqual(validate(good), [])
        bad = {"registrations": [{"locus": "x"}], "conditions": [{"kind": "", "subject": "s"}], "persistent_state": ["a.B"],
               "derived_from": {"identity": "a" * 64, "by": "relink"},
               "licence": {**gene["licence"], "decision": "RELEASABLE", "local_only_members": [gene["members"][0]["path"]]}}
        for key, value in bad.items():
            with self.subTest(key=key):
                self.assertEqual(len(validate({**gene, key: value})), 1, validate({**gene, key: value}))

    def test_a_member_under_a_local_only_path_makes_the_gene_local_only(self) -> None:
        import json as _json
        with resolved_temp_dir() as root:
            mod = _rebal(root)
            policy = root / "policy" / "release_policy.json"
            policy.parent.mkdir()
            policy.write_text(_json.dumps({"schema_version": 1, "default": {"local_only": False}, "mods": {"@_ss_rebal_@": {
                "local_only": False, "reason": "MIT", "paths": [
                    {"prefix": "graphics/fx", "local_only": True, "reason": "glow sprite by another author"}]}}}), encoding="utf-8")
            gene = describe(mod, "hullmod:shields_formshield", vanilla_core=_vanilla(root), policy_path=policy)
            other = describe(mod, "weapon:rebal_rail", policy_path=policy)
        self.assertEqual(validate(gene), [])
        self.assertEqual((gene["licence"]["decision"], gene["licence"]["mod_decision"]), ("LOCAL_ONLY", "RELEASABLE"))
        self.assertEqual(gene["licence"]["local_only_members"], ["graphics/fx/formshield_glow.png"])
        self.assertEqual((other["licence"]["decision"], other["licence"]["local_only_members"]), ("RELEASABLE", []))

    def test_the_cli_writes_the_manifest(self) -> None:
        with resolved_temp_dir() as root:
            mod = _rebal(root)
            out = root / "rail.gene.json"
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as err:
                code = main(["gene", "describe", str(mod), "weapon:rebal_rail", "--write", str(out)])
            gene = json.loads(out.read_text(encoding="utf-8"))
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as bad:
                refused = main(["gene", "describe", str(mod), "weapon:nope"])
        self.assertEqual(code, 0)
        self.assertEqual(validate(gene), [])
        self.assertIn(gene["identity"][:16], err.getvalue())
        self.assertEqual(refused, 2)
        self.assertIn("not defined", bad.getvalue())


if __name__ == "__main__":
    unittest.main()
