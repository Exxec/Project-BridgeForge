"""94.G3 slice 1: the gene bank (docs/GENE_BANK_DESIGN.md). Synthetic fixtures only."""
from __future__ import annotations

import hashlib
import json
import shutil
import unittest
import zipfile

from bridgeforge.genome.bank import Bank, BankError, member_bytes, put, rebuild
from tests.bound_runs import write_core_build
from tests.support import resolved_temp_dir, write_text as _write
from tests.test_gene_shared_needs import _core as _styled_core
from tests.test_gene_shared_needs import _mod as _styled_mod

BUILD = "0.98.5a-RC7"


def _base(root):
    """A data root holding `In operation/Demo/working` (the styled mod of slice 20) and an RC7-reporting core."""
    base = root / "data"
    mod = _styled_mod(base / "In operation" / "Demo")
    (base / "In operation" / "Demo" / "mod").rename(base / "In operation" / "Demo" / "working")
    core = _styled_core(root)
    write_core_build(core, BUILD)
    return base, base / "In operation" / "Demo" / "working", core, mod


class BankTests(unittest.TestCase):
    def test_put_stores_the_manifest_its_member_and_need_bytes_and_a_clean_root(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            result = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            records = bank.records()
            problems = bank.verify()
            again = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
        self.assertEqual((result["stored"], result["build"], problems), (1, BUILD, []))
        (record,) = records.values()
        self.assertEqual(record["source"], {"mod_id": "demomod", "mod_version": "1.0", "folder": "working",
                                            "path": "In operation/Demo/working"})
        self.assertEqual(record["licence"], "UNRECORDED")  # the WP4 ledger's decision for a mod with no licence record
        self.assertIn("data/config/hull_styles.json#/FX_STYLE", record["donor"])  # slice 20's need is banked too
        self.assertEqual(again["root"], result["root"])  # putting the same thing again changes nothing

    def test_a_rebuild_on_another_machine_gives_the_same_root(self) -> None:
        # Two data roots at different absolute paths stand for White_Legion and Test1: records hold no machine paths.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            first = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)["root"]
            other = root / "elsewhere"
            shutil.copytree(base, other / "data")
            shutil.copytree(root / "Genes", other / "Genes")
            rebuilt = rebuild(core, bank=other / "Genes", quiet=True, base=other / "data")
        self.assertEqual((rebuilt["root"], rebuilt["problems"]), (first, []))

    def test_tampering_a_missing_need_and_a_stale_root_are_reported(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            blob = next(p for p in (root / "Genes" / "blobs").rglob("*") if p.is_file())
            blob.write_bytes(b"changed")
            record = next(iter(bank.records().values()))
            (root / "Genes" / "records" / f"{record['manifest']}.json").write_text(
                json.dumps({**record, "needs_genes": ["variant:gone_Var1"]}), encoding="utf-8")
            problems = bank.verify()
        self.assertTrue([p for p in problems if "does not hash to its name" in p])
        self.assertTrue([p for p in problems if "variant:gone_Var1 has no record" in p])
        self.assertTrue([p for p in problems if p.startswith("ROOT does not recompute")])

    def test_a_changed_source_supersedes_the_old_record_and_keeps_it(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            old = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            _write(working / "data" / "hulls" / "fx_ship.ship", json.dumps({"hullId": "fx_ship", "style": "FX_STYLE", "hitpoints": 9}))
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            records = Bank(root / "Genes").records()
        self.assertEqual(len(records), 2)
        superseded = [r for r in records.values() if r["superseded_by"]]
        self.assertEqual(len(superseded), 1)
        self.assertIn(superseded[0]["superseded_by"], records)
        self.assertNotEqual(old["root"], Bank(root / "Genes").root_hash())

    def test_a_source_that_changed_after_describe_is_refused(self) -> None:
        from bridgeforge.genome.bank import source_entry
        from bridgeforge.genome.gene import describe

        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            gene = describe(working, "hull:fx_ship", vanilla_core=core)
            _write(working / "data" / "hulls" / "fx_ship.ship", json.dumps({"hullId": "fx_ship", "style": "FX_STYLE", "changed": 1}))
            with self.assertRaisesRegex(BankError, "do not hash to the manifest's sha256"):
                Bank(root / "Genes").store(gene, working, source_entry(working, "working", base), BUILD, {})

    def test_one_manifest_from_two_sources_keeps_two_records(self) -> None:
        # Found banking the pilots: records were filed by manifest alone, so an unchanged gene in a second release would have
        # overwritten the first source's record.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            twin = base / "In operation" / "Demo" / "original"
            shutil.copytree(working, twin)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            put(twin, "hull:fx_ship", core, folder="original", bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            records = bank.records()
            manifests = [p for p in (root / "Genes" / "manifests").rglob("*.json")]
            problems = bank.verify()
        self.assertEqual((len(records), len(manifests), problems), (2, 1, []))
        self.assertEqual({r["source"]["folder"] for r in records.values()}, {"working", "original"})

    def test_a_source_outside_the_data_root_and_a_core_of_another_build_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            stray = root / "stray"
            shutil.copytree(working, stray)
            with self.assertRaisesRegex(BankError, "not under the data root"):
                put(stray, "hull:fx_ship", core, bank=root / "Genes", base=base)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            write_core_build(core, "0.98a-RC8")
            with self.assertRaisesRegex(BankError, "described against 0.98.5a-RC7"):
                rebuild(core, bank=root / "Genes", quiet=True, base=base)


class MemberBytesTests(unittest.TestCase):
    def test_each_member_kind_s_bytes_hash_as_its_member_does(self) -> None:
        from bridgeforge.genome.closure import value_sha256
        from bridgeforge.genome.gene import _file_member, _row_member

        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "data" / "hulls" / "a.ship", '{"hullId": "a"}  \r\n\r\n')  # CRLF and trailing space: normalised
            _write(mod / "data" / "weapons" / "weapon_data.csv", "name,id,range\nGun,gun_a,600\n")
            _write(mod / "data" / "config" / "settings.json", json.dumps({"fx": {"b": 2, "a": 1}}))
            (mod / "jars").mkdir(parents=True)
            with zipfile.ZipFile(mod / "jars" / "x.jar", "w") as jar:
                jar.writestr("a/B.class", b"\xca\xfe\xba\xbe-class")
            checks = [
                (member_bytes(mod, "file", "data/hulls/a.ship"), _file_member(mod, "data/hulls/a.ship")["sha256"]),
                (member_bytes(mod, "csv-row", "data/weapons/weapon_data.csv [gun_a]"),
                 _row_member(mod, "data/weapons/weapon_data.csv [gun_a]")["sha256"]),
                (member_bytes(mod, "json-entry", "data/config/settings.json#/fx"), value_sha256({"b": 2, "a": 1})),
                (member_bytes(mod, "jar-class", "jars/x.jar!a/B.class"), hashlib.sha256(b"\xca\xfe\xba\xbe-class").hexdigest()),
            ]
        for data, expected in checks:
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
