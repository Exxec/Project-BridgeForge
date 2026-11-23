"""94.G3 slice 1: the gene bank (docs/GENE_BANK_DESIGN.md). Synthetic fixtures only."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.genome.bank import Bank, BankError, member_bytes, put, rebuild, run_bank_cli
from tests.bound_runs import write_core_build
from tests.support import resolved_temp_dir, write_text as _write
from tests.test_gene_shared_needs import _core as _styled_core
from tests.test_gene_shared_needs import _mod as _styled_mod

BUILD = "0.98.5a-RC7"
SHIP = "data/hulls/fx_ship.ship"
GONE = "variant:gone_Var1"


def _base(root):
    """A data root holding `In operation/Demo/working` (the styled mod of slice 20) and an RC7-reporting core."""
    base = root / "data"
    mod = _styled_mod(base / "In operation" / "Demo")
    (base / "In operation" / "Demo" / "mod").rename(base / "In operation" / "Demo" / "working")
    core = _styled_core(root)
    write_core_build(core, BUILD)
    return base, base / "In operation" / "Demo" / "working", core, mod


def _ship(working, hitpoints):
    _write(working / SHIP, json.dumps({"hullId": "fx_ship", "style": "FX_STYLE", "hitpoints": hitpoints}))


def _refusing_walk():
    """The real walk, plus a needed gene describe refuses with a message naming the mod and the core by absolute path, as
    gene.py's and faction.py's refusals do."""
    from bridgeforge.genome import gene_set

    real = gene_set.walk

    def walk(mod, anchor, core, **kwargs):
        genes, refused = real(mod, anchor, core, **kwargs)
        gene = genes[anchor]
        needs = {**gene["needs"], "genes": sorted([*(gene["needs"].get("genes") or []), GONE])}
        reason = f"{GONE}: {Path(mod).resolve()} defines no such variant ({(Path(core).resolve() / 'data').as_posix()})"
        return {**genes, anchor: {**gene, "needs": needs}}, {**refused, GONE: reason}

    return mock.patch("bridgeforge.genome.gene_set.walk", walk)


def _seed(bank, other):
    """A bank folder on `other` holding only `bank`'s sources.json: what Test1 starts a rebuild from."""
    (other / "Genes").mkdir(parents=True)
    shutil.copyfile(bank / "sources.json", other / "Genes" / "sources.json")
    return other / "Genes"


class BankTests(unittest.TestCase):
    def test_put_stores_the_manifest_its_member_and_need_bytes_and_a_clean_root(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            result = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            records, current, problems = bank.records(), bank.current_ids(), bank.verify()
            again = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            checkpoint_left = (root / "Genes" / "put.partial.jsonl").exists()
        self.assertEqual((result["stored"], result["build"], problems, set(records), checkpoint_left),
                         (1, BUILD, [], current, False))
        (record,) = records.values()
        self.assertEqual(record["source"], {"mod_id": "demomod", "mod_version": "1.0", "folder": "working",
                                            "path": "In operation/Demo/working"})
        self.assertEqual(record["licence"], "UNRECORDED")  # the WP4 ledger's decision for a mod with no licence record
        self.assertIn("data/config/hull_styles.json#/FX_STYLE", record["donor"])  # slice 20's need is banked too
        self.assertNotIn("superseded_by", record)  # history is entries.json's to say, not a field the ROOT would cover
        self.assertEqual((again["root"], again["retired"]), (result["root"], []))  # the same put again changes nothing

    def test_a_rebuild_into_an_empty_folder_elsewhere_gives_the_same_root_and_reasons_hold_no_paths(self) -> None:
        # The other data root, core and bank stand for Test1: only sources.json goes across, as in the acceptance run.
        with resolved_temp_dir() as root, _refusing_walk():
            base, working, core, _ = _base(root)
            first = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)["root"]
            other = root / "elsewhere"
            shutil.copytree(base, other / "data")
            shutil.copytree(core, other / "core")
            seeded = _seed(root / "Genes", other)
            rebuilt = rebuild(other / "core", bank=seeded, quiet=True, base=other / "data")
            (record,) = Bank(seeded).records().values()
        self.assertEqual((rebuilt["root"], rebuilt["problems"]), (first, []))
        self.assertEqual(record["needs_refused"], {GONE: f"{GONE}: <source> defines no such variant (<core>/data)"})

    def test_history_is_kept_and_a_rebuild_in_place_matches_a_fresh_one(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            first = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            _ship(working, 9)
            second = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            in_place = rebuild(core, bank=root / "Genes", quiet=True, base=base)
            kept = len(Bank(root / "Genes").records())
            fresh = rebuild(core, bank=_seed(root / "Genes", root / "fresh"), quiet=True, base=base)
            fresh_records = len(Bank(root / "fresh" / "Genes").records())
        self.assertEqual(len(second["retired"]), 1)
        self.assertNotEqual(first["root"], second["root"])
        self.assertEqual((in_place["root"], in_place["problems"]), (second["root"], []))
        self.assertEqual((fresh["root"], fresh["problems"]), (second["root"], []))
        self.assertEqual((kept, fresh_records), (2, 1))  # history stays in the bank and outside the ROOT

    def test_a_source_changed_and_changed_back_has_its_first_record_current_again(self) -> None:
        # Review 2026-11-23: A, then B, then A again left A superseded by B and B by A: no current record, and verify quiet.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            original = (working / SHIP).read_bytes()
            first = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            _ship(working, 9)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            (working / SHIP).write_bytes(original)
            again = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            current, problems = bank.current_ids(), bank.verify()
        self.assertEqual((again["root"], len(current), problems), (first["root"], 1, []))

    def test_tampering_a_missing_need_a_missing_entry_and_a_stale_root_are_reported(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            blob = next(p for p in (root / "Genes" / "blobs").rglob("*") if p.is_file())
            blob.write_bytes(b"changed")
            ((rid, record),) = bank.records().items()
            (root / "Genes" / "records" / f"{rid}.json").write_text(json.dumps({**record, "needs_genes": [GONE]}), encoding="utf-8")
            (root / "Genes" / "records" / "broken.json").write_text("{", encoding="utf-8")
            problems = bank.verify()
            (root / "Genes" / "entries.json").write_text("[]", encoding="utf-8")
            unlisted = bank.verify()
        self.assertTrue([p for p in problems if "does not hash to its name" in p])
        self.assertTrue([p for p in problems if f"needed gene {GONE} has no current record" in p])
        self.assertTrue([p for p in problems if p.startswith("ROOT does not recompute")])
        self.assertIn("records/broken.json is unreadable", problems)
        self.assertTrue([p for p in unlisted if "has no entries row" in p])

    def test_a_source_that_changed_after_describe_is_refused(self) -> None:
        from bridgeforge.genome.bank import source_entry
        from bridgeforge.genome.gene import describe

        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            gene = describe(working, "hull:fx_ship", vanilla_core=core)
            _write(working / SHIP, json.dumps({"hullId": "fx_ship", "style": "FX_STYLE", "changed": 1}))
            with self.assertRaisesRegex(BankError, "do not hash to the manifest's sha256"):
                Bank(root / "Genes").store(gene, working, source_entry(working, "working", base), BUILD, {})

    def test_one_manifest_from_two_sources_keeps_two_records(self) -> None:
        # Found banking the pilots: records were filed by manifest alone, so an unchanged gene in a second release would have
        # overwritten the first source's record.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            twin = base / "In operation" / "Twin"
            shutil.copytree(working, twin)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            put(twin, "hull:fx_ship", core, folder="original", bank=root / "Genes", base=base)
            bank = Bank(root / "Genes")
            records, current = bank.records(), bank.current_ids()
            manifests = [p for p in (root / "Genes" / "manifests").rglob("*.json")]
            problems = bank.verify()
        self.assertEqual((len(records), len(current), len(manifests), problems), (2, 2, 1, []))
        self.assertEqual({r["source"]["folder"] for r in records.values()}, {"working", "original"})

    def test_a_source_outside_the_data_root_a_workspace_as_original_and_a_core_of_another_build_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            stray = root / "stray"
            shutil.copytree(working, stray)
            with self.assertRaisesRegex(BankError, "not under the data root"):
                put(stray, "hull:fx_ship", core, bank=root / "Genes", base=base)
            with self.assertRaisesRegex(BankError, "is a workspace: its working/ copy is not the original"):
                put(working.parent, "hull:fx_ship", core, folder="original", bank=root / "Genes", base=base)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            write_core_build(core, "0.98a-RC8")
            with self.assertRaisesRegex(BankError, "described against 0.98.5a-RC7"):
                rebuild(core, bank=root / "Genes", quiet=True, base=base)


class BankFolderTests(unittest.TestCase):
    """Review 2026-11-23 (CRITICAL): `rebuild --bank <data root>` deleted In operation/, Done/ and bridgeforge-state/."""

    def test_a_folder_holding_anything_else_is_refused_and_nothing_is_deleted(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            _write(root / "Genes" / "keep.txt", "mine")
            with self.assertRaisesRegex(BankError, "holds keep.txt, which no bank holds"):
                rebuild(core, bank=root / "Genes", quiet=True, base=base)
            shutil.copyfile(root / "Genes" / "sources.json", base / "sources.json")
            with self.assertRaisesRegex(BankError, "which no bank holds"):
                rebuild(core, bank=base, quiet=True, base=base)
            with self.assertRaisesRegex(BankError, "which no bank holds"):
                put(working, "hull:fx_ship", core, bank=base, base=base)
            with self.assertRaisesRegex(BankError, "sits inside the source"):
                put(working, "hull:fx_ship", core, bank=working / "Genes", base=base)
            survived = ((root / "Genes" / "keep.txt").is_file(), (working / SHIP).is_file())
        self.assertEqual(survived, (True, True))

    def test_the_bank_module_deletes_no_tree(self) -> None:
        import inspect

        from bridgeforge.genome import bank

        self.assertNotIn("rmtree", inspect.getsource(bank))

    def test_a_missing_source_is_refused_before_anything_is_written(self) -> None:
        # Review 2026-11-23: a workspace archived out of In operation/ made the old rebuild fail after it had wiped the bank.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            stored = put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            shutil.move(str(working.parent), str(root / "archived"))
            with self.assertRaisesRegex(BankError, "1 source\\(s\\) are not on this machine: In operation/Demo/working"):
                rebuild(core, bank=root / "Genes", quiet=True, base=base)
            bank = Bank(root / "Genes")
            after = (bank.root_hash(), len(bank.records()), bank.verify())
        self.assertEqual(after, (stored["root"], 1, []))


class BankCliTests(unittest.TestCase):
    def _run(self, **fields) -> tuple[int, str, str]:
        args = SimpleNamespace(**{"kind": None, "anchor": None, "build": None, "licence": None, "history": False, **fields})
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_bank_cli(args)
        return code, out.getvalue(), err.getvalue()

    def test_list_shows_current_records_and_history_on_request_and_errors_exit_two(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            _ship(working, 9)
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            current = self._run(bank_command="list", bank=root / "Genes")
            history = self._run(bank_command="list", bank=root / "Genes", history=True)
            verified = self._run(bank_command="verify", bank=root / "Genes")
            (root / "Genes" / "entries.json").write_text("{", encoding="utf-8")
            broken = self._run(bank_command="verify", bank=root / "Genes")
            no_sources = self._run(bank_command="rebuild", bank=root / "empty", vanilla_core=core, quiet=True)
        self.assertEqual((current[0], len(current[1].splitlines()), current[1].count("history")), (0, 1, 0))
        self.assertEqual((len(history[1].splitlines()), history[1].count(" history")), (2, 1))
        self.assertEqual(verified[0], 0)
        self.assertIn("1 current record(s) of 2, 0 problem(s)", verified[1])
        self.assertEqual((broken[0], no_sources[0]), (2, 2))
        self.assertIn("sources.json is missing", no_sources[2])


class MemberBytesTests(unittest.TestCase):
    def test_each_member_kind_s_bytes_hash_as_its_member_does(self) -> None:
        from bridgeforge.genome.closure import _settings, value_sha256
        from bridgeforge.genome.gene import _file_member, _row_member

        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "data" / "hulls" / "a.ship", '{"hullId": "a"}  \r\n\r\n')  # CRLF and trailing space: normalised
            _write(mod / "data" / "weapons" / "weapon_data.csv", "name,id,range\nGun,gun_a,600\n")
            (mod / "data" / "config").mkdir(parents=True)
            # A stray Latin-1 byte: describe reads settings with errors="replace", and the bank must hash what it hashed.
            (mod / "data" / "config" / "settings.json").write_bytes(b'{"fx": {"b": "caf\xe9", "a": 1}}')
            (mod / "jars").mkdir(parents=True)
            with zipfile.ZipFile(mod / "jars" / "x.jar", "w") as jar:
                jar.writestr("a/B.class", b"\xca\xfe\xba\xbe-class")
            checks = [
                (member_bytes(mod, "file", "data/hulls/a.ship"), _file_member(mod, "data/hulls/a.ship")["sha256"]),
                (member_bytes(mod, "csv-row", "data/weapons/weapon_data.csv [gun_a]"),
                 _row_member(mod, "data/weapons/weapon_data.csv [gun_a]")["sha256"]),
                (member_bytes(mod, "json-entry", "data/config/settings.json#/fx"), value_sha256(_settings(mod)["fx"])),
                (member_bytes(mod, "jar-class", "jars/x.jar!a/B.class"), hashlib.sha256(b"\xca\xfe\xba\xbe-class").hexdigest()),
            ]
        for data, expected in checks:
            self.assertEqual(hashlib.sha256(data).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
