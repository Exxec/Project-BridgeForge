"""94.G3 slice 3b: `gene bank lineage-scan`, lineage beyond the bank (docs/GENE_BANK_DESIGN.md). Synthetic banks and corpora."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.genome import lineage_scan as ls
from bridgeforge.genome.alleles import plan, write_plan
from bridgeforge.genome.bank import Bank, BankError, put, run_bank_cli
from tests.support import resolved_temp_dir
from tests.test_gene_bank_reports import LONG_TEXT, FakeBank, _snapshot
from tests.test_gene_bank import SHIP, _base, _refusing_walk


def _copy(base: Path, name: str, mod_id: str | None, *, ship: dict | None = None) -> Path:
    """In operation/<name>/working: the Demo mod under another mod id (or none), its ship file optionally changed."""
    source = base / "In operation" / "Demo" / "working"
    working = base / "In operation" / name / "working"
    shutil.copytree(source, working)
    info = json.loads((working / "mod_info.json").read_text(encoding="utf-8"))
    if mod_id is None:
        info.pop("id", None)
    else:
        info["id"] = mod_id
    (working / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    if ship is not None:
        (working / SHIP).write_text(json.dumps(ship), encoding="utf-8")
    return working


def _plan(root: Path, base: Path) -> Path:
    plan_file = root / "plan.json"
    write_plan(plan(base / "In operation", bank=root / "Genes", base=base, quiet=True), plan_file)
    return plan_file


def _corpus(root: Path, *copies: tuple[str, str | None, dict | None], anchors: tuple[str, ...] = ("hull:fx_ship",)):
    """(base, core, bank, plan file): Demo banked by a real put of `anchors`, then copies of it, then an alleles plan."""
    base, working, core, _ = _base(root)
    for anchor in anchors:
        put(working, anchor, core, bank=root / "Genes", base=base)
    for name, mod_id, ship in copies:
        _copy(base, name, mod_id, ship=ship)
    return base, core, root / "Genes", _plan(root, base)


def _scan(plan_file, core, bank, base, **kwargs):
    return ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True, **kwargs)


class ScanTests(unittest.TestCase):
    def test_a_copy_under_another_mod_id_shares_its_members_and_an_edited_one_exactly_the_unchanged_one(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None),
                                                  ("Edited", "editedmod", {"hullId": "fx_ship", "style": "FX_STYLE", "hitpoints": 9}))
            before = _snapshot(bank)
            members = sorted(json.loads(next((bank / "records").iterdir()).read_text(encoding="utf-8"))["members"])
            report = _scan(plan_file, core, bank, base)
            after, problems = _snapshot(bank), Bank(bank).verify()
        self.assertEqual((before, problems), (after, []))  # nothing is put and the bank verifies
        rows = {row["mod_id"]: row for row in report["candidates"]}
        self.assertEqual(sorted(rows), ["copymod", "editedmod"])  # the banked mod's own copy is no candidate
        self.assertEqual(sorted(blob["path"] for blob in rows["copymod"]["shared"]), members)
        self.assertEqual(sorted(blob["path"] for blob in rows["editedmod"]["shared"]), [p for p in members if p != SHIP])
        self.assertEqual({blob["gene"] for blob in rows["copymod"]["shared"]}, {"hull:fx_ship"})
        self.assertTrue(all(h["mod_id"] == "demomod" for blob in rows["copymod"]["shared"] for h in blob["bank_holders"]))
        counts = report["counts"]
        self.assertEqual((counts["candidate_roots"], counts["described"], counts["errors"], counts["roots_sharing"]), (2, 2, 0, 2))
        self.assertEqual((counts["shared_blobs"], counts["mod_ids_sharing"]), (len(members), 2))
        self.assertEqual(report["build"], "0.98.5a-RC7")

    def test_a_plan_with_only_the_banked_mod_finds_nothing(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root)
            report = _scan(plan_file, core, bank, base)
        self.assertEqual((report["counts"]["candidate_roots"], report["counts"]["shared_blobs"]), (0, 0))

    def test_id_less_roots_are_keyed_by_path_as_3a_keys_them(self) -> None:
        # Review: an id-less banked root was its own candidate, and three id-less roots counted as one mod.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            info = json.loads((working / "mod_info.json").read_text(encoding="utf-8"))
            info.pop("id")
            (working / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
            for name in ("A", "B", "C"):
                _copy(base, name, None)
            report = _scan(_plan(root, base), core, root / "Genes", base)
        self.assertEqual(sorted(row["path"] for row in report["candidates"]),
                         [f"In operation/{n}/working" for n in ("A", "B", "C")])  # not Demo, the banked id-less root
        self.assertEqual(report["counts"]["mod_ids_sharing"], 3)

    def test_a_root_with_several_banked_anchors_is_one_row_and_its_blobs_count_once(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None), anchors=("hull:fx_ship", "hull:fx_other"))
            report = _scan(plan_file, core, bank, base)
        self.assertEqual(len(report["candidates"]), 1)
        row = report["candidates"][0]
        self.assertEqual(sorted(row["anchors"]), ["hull:fx_other", "hull:fx_ship"])
        self.assertEqual({blob["gene"] for blob in row["shared"]}, {"hull:fx_other", "hull:fx_ship"})
        counts = report["counts"]
        self.assertEqual((counts["candidate_roots"], counts["candidate_anchors"], counts["roots_sharing"]), (1, 2, 1))
        self.assertEqual(counts["shared_blobs"], len({blob["sha256"] for blob in row["shared"]}))

    def test_an_anchor_an_earlier_walk_of_the_root_reached_is_not_walked_again(self) -> None:
        # Review: a root with several banked anchors was walked once per anchor.
        from bridgeforge.genome import gene_set

        real, walked = gene_set.walk, []

        def walk(mod, anchor, *args, **kwargs):  # the first walk reaches both anchors, as a closure through a need would
            walked.append(anchor)
            genes, refused = {}, {}
            for each in ("hull:fx_other", "hull:fx_ship"):
                found, why = real(mod, each, *args, **kwargs)
                genes.update(found)
                refused.update(why)
            return genes, refused

        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None), anchors=("hull:fx_ship", "hull:fx_other"))
            with mock.patch("bridgeforge.genome.gene_set.walk", walk):
                report = _scan(plan_file, core, bank, base)
        self.assertEqual(len(walked), 1)
        self.assertEqual({blob["gene"] for blob in report["candidates"][0]["shared"]}, {"hull:fx_other", "hull:fx_ship"})

    def test_a_refused_need_is_recorded(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            with _refusing_walk():
                report = _scan(plan_file, core, bank, base)
        row = report["candidates"][0]
        self.assertEqual(list(row["needs_refused"]), ["variant:gone_Var1"])
        self.assertEqual((report["counts"]["needs_refused"], report["counts"]["anchors_refused"]), (1, 0))

    def test_a_root_changed_or_gone_since_the_plan_is_an_error_and_a_resume_retries_only_it(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None), ("Gone", "gonemod", None))
            shutil.rmtree(base / "In operation" / "Gone")
            checkpoint = root / "scan.partial.jsonl"
            first = _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
            _copy(base, "Gone", "gonemod")  # back exactly as planned: the resume describes it, and only it
            from bridgeforge.genome import gene_set

            real, described = gene_set.walk, []

            def walk(mod, *args, **kwargs):
                described.append(Path(mod).parent.name)
                return real(mod, *args, **kwargs)

            with mock.patch("bridgeforge.genome.gene_set.walk", walk):
                second = _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
            fresh = _scan(plan_file, core, bank, base)
            changed = base / "In operation" / "Gone" / "working"  # then changed: no longer the plan's copy
            (changed / "mod_info.json").write_text(json.dumps({"id": "gonemod", "version": "2.0"}), encoding="utf-8")
            third = _scan(plan_file, core, bank, base)
        errors = {row["mod_id"]: row["error"] for row in first["candidates"]}
        self.assertEqual(errors["copymod"], None)
        self.assertIn("gone since the plan", errors["gonemod"])
        self.assertEqual(described, ["Gone"])  # copymod came from the checkpoint; the error was not kept, so it is retried
        self.assertEqual(second["counts"]["errors"], 0)
        # Review: the resumed report is the fresh one, row for row (shared and counted apart included), not 0 == 0.
        self.assertTrue({r["mod_id"]: r["shared"] for r in fresh["candidates"]}["copymod"])
        self.assertEqual(second, fresh)
        self.assertIn("changed since the plan", {r["mod_id"]: r["error"] for r in third["candidates"]}["gonemod"])

    def test_a_root_changed_after_its_row_was_saved_is_described_again_on_resume(self) -> None:
        # Review: the checkpoint key held the plan's mod_info hash, so a saved row was replayed for a root changed since.
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None), ("Gone", "gonemod", None))
            shutil.rmtree(base / "In operation" / "Gone")
            checkpoint = root / "scan.partial.jsonl"
            _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)  # copymod saved; the error keeps the checkpoint
            info = base / "In operation" / "Copy" / "working" / "mod_info.json"
            info.write_text(json.dumps({"id": "copymod", "version": "2.0"}), encoding="utf-8")
            resumed = _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
            fresh = _scan(plan_file, core, bank, base)
        self.assertIn("changed since the plan", {r["mod_id"]: r["error"] for r in resumed["candidates"]}["copymod"])
        self.assertEqual(resumed, fresh)

    def test_a_changed_core_data_folder_restarts_the_scan(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            checkpoint = root / "scan.partial.jsonl"
            _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
            (core / "data" / "extra.json").write_text("{}", encoding="utf-8")
            with mock.patch("bridgeforge.genome.gene_set.walk", side_effect=RuntimeError("described again")):
                again = _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
        self.assertIn("described again", again["candidates"][0]["error"])  # not resumed from the old core's rows

    def test_a_core_data_file_renamed_restarts_the_scan(self) -> None:
        # Review: the header digested the core's content hashes without their paths, so a rename (or removing one of two
        # files with the same content) resumed, though describe finds vanilla content by path.
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            checkpoint = root / "scan.partial.jsonl"
            _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
            moved = next(path for path in sorted((core / "data").rglob("*")) if path.is_file())
            moved.rename(moved.with_name("renamed-" + moved.name))
            with mock.patch("bridgeforge.genome.gene_set.walk", side_effect=RuntimeError("described again")):
                again = _scan(plan_file, core, bank, base, checkpoint_path=checkpoint)
        self.assertIn("described again", again["candidates"][0]["error"])

    def test_a_failing_describe_or_an_unreadable_mod_info_is_that_roots_error_only(self) -> None:
        from bridgeforge.genome import alleles, gene_set

        real = gene_set.walk

        def walk(mod, anchor, core, **kwargs):
            if "Broken" in str(mod):
                raise RuntimeError("cannot parse")
            if "Refused" in str(mod):
                return {}, {anchor: "defines no such hull"}
            return real(mod, anchor, core, **kwargs)

        real_sha = alleles._sha

        def sha(data):
            if b"lockedmod" in data:
                raise PermissionError("held open")
            return real_sha(data)

        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Broken", "brokenmod", None), ("Refused", "refusedmod", None),
                                                  ("Copy", "copymod", None), ("Locked", "lockedmod", None))
            with mock.patch("bridgeforge.genome.gene_set.walk", walk), mock.patch.object(alleles, "_sha", sha):
                report = _scan(plan_file, core, bank, base)
        rows = {row["mod_id"]: row for row in report["candidates"]}
        self.assertIn("RuntimeError: cannot parse", rows["brokenmod"]["error"])
        self.assertIn("PermissionError", rows["lockedmod"]["error"])
        self.assertEqual(rows["refusedmod"]["anchors_refused"], {"hull:fx_ship": "defines no such hull"})
        self.assertTrue(rows["copymod"]["shared"])
        counts = report["counts"]
        self.assertEqual((counts["errors"], counts["anchors_refused"], counts["described"]), (2, 1, 1))


class RefusalTests(unittest.TestCase):
    def test_a_core_of_another_build_is_refused(self) -> None:
        from tests.bound_runs import write_core_build

        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            write_core_build(core, "0.98.5a-RC9")
            with self.assertRaises(BankError) as refused:
                _scan(plan_file, core, bank, base)
        self.assertIn("one bank holds one build", str(refused.exception))

    def test_records_of_another_build_are_refused_even_without_sources(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            record = next((bank / "records").iterdir())
            data = json.loads(record.read_text(encoding="utf-8"))
            data["build"] = "0.98.5a-RC9"
            record.write_text(json.dumps(data), encoding="utf-8")
            (bank / "sources.json").write_text("[]", encoding="utf-8")
            with self.assertRaises(BankError) as refused:
                _scan(plan_file, core, bank, base)
        self.assertIn("described against 0.98.5a-RC9", str(refused.exception))

    def test_a_plan_older_than_the_bank_or_from_another_data_root_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            put(base / "In operation" / "Demo" / "working", "hull:fx_other", core, bank=bank, base=base)  # after the plan
            with self.assertRaises(BankError) as stale:
                _scan(plan_file, core, bank, base)
            with self.assertRaises(BankError) as elsewhere:
                _scan(_plan(root, base), core, bank, root / "another")
        self.assertIn("did not look for", str(stale.exception))
        self.assertIn("not under", str(elsewhere.exception))

    def test_something_that_is_not_a_plan_is_refused(self) -> None:
        from bridgeforge.genome.alleles import AllelesError

        with resolved_temp_dir() as root:
            (root / "x.json").write_text(json.dumps({"schema": "other"}), encoding="utf-8")
            with self.assertRaises(AllelesError):
                ls.load_plan(root / "x.json")
            with self.assertRaises(BankError):
                ls.load_plan(root / "missing.json")

    def test_a_plan_that_lists_no_anchors_is_refused(self) -> None:
        # Without its anchors, a plan cannot show it looked for every anchor the bank holds.
        with resolved_temp_dir() as root:
            _base_folder, _core, _bank, plan_file = _corpus(root)
            data = json.loads(plan_file.read_text(encoding="utf-8"))
            del data["anchors"]
            plan_file.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(BankError) as refused:
                ls.load_plan(plan_file)
        self.assertIn("lists no anchors", str(refused.exception))


class ClassifyTests(unittest.TestCase):
    """Each blob is counted in one bucket, in the documented order, never reported as shared."""

    def _classify(self, member_data: dict[str, bytes], holder_mod: str = "banked", *, donor_only: bytes | None = None,
                  vanilla: set[str] | None = None, candidate_mod: str = "other"):
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record(holder_mod, "hull:a_ship", members=member_data, donor={"d/x.json": donor_only} if donor_only else None)
            bank = fake.finish()
            _anchors, members, donor, _unreadable, _builds = ls.bank_side(bank)
            genes = {"hull:b_ship": {"members": [{"path": p, "sha256": hashlib.sha256(d).hexdigest()} for p, d in member_data.items()]
                                     + ([{"path": "c/donor.json", "sha256": hashlib.sha256(donor_only).hexdigest()}] if donor_only else [])}}
            return ls._classify(bank, genes, candidate_mod, members, donor, vanilla or set())

    def test_a_long_value_is_shared_and_names_the_bank_holder(self) -> None:
        shared, buckets = self._classify({"data/a.json": LONG_TEXT})
        self.assertEqual([(s["path"], s["gene"], s["bank_holders"][0]["mod_id"]) for s in shared], [("data/a.json", "hull:b_ship", "banked")])
        self.assertEqual(sum(len(v) for v in buckets.values()), 0)

    def test_each_bucket(self) -> None:
        self.assertEqual(len(self._classify({"data/n.json": b"5"})[1]["trivial_value"]), 1)
        digest = hashlib.sha256(LONG_TEXT).hexdigest()
        self.assertEqual(self._classify({"data/a.json": LONG_TEXT}, vanilla={digest})[1]["vanilla_file"], [digest])
        shared, buckets = self._classify({}, donor_only=b"a sprite the bank only needs, byte for byte, as a donor")
        self.assertEqual((shared, len(buckets["donor_side"])), ([], 1))
        shared, buckets = self._classify({"data/a.json": LONG_TEXT}, holder_mod="other", candidate_mod="other")
        self.assertEqual((shared, len(buckets["same_mod"])), ([], 1))

    def test_same_mod_comes_before_trivial_and_vanilla(self) -> None:
        # The candidate's own banked blob is an allele first, whatever its size (the documented order).
        shared, buckets = self._classify({"data/n.json": b"5"}, holder_mod="other", candidate_mod="other")
        self.assertEqual((len(buckets["same_mod"]), len(buckets["trivial_value"])), (1, 0))

    def test_trivial_comes_before_vanilla(self) -> None:
        _shared, buckets = self._classify({"data/n.json": b"5"}, vanilla={hashlib.sha256(b"5").hexdigest()})
        self.assertEqual((len(buckets["trivial_value"]), buckets["vanilla_file"]), (1, []))

    def test_a_blob_two_of_the_roots_genes_hold_is_classified_once(self) -> None:
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record("banked", "hull:a_ship", members={"data/a.json": LONG_TEXT, "data/n.json": b"5"})
            bank = fake.finish()
            _anchors, members, donor, _unreadable, _builds = ls.bank_side(bank)
            held = [{"path": p, "sha256": hashlib.sha256(d).hexdigest()} for p, d in (("data/a.json", LONG_TEXT), ("data/n.json", b"5"))]
            shared, buckets = ls._classify(bank, {"hull:b_ship": {"members": held}, "hull:c_ship": {"members": held}}, "other",
                                           members, donor, set())
        self.assertEqual(([s["gene"] for s in shared], len(buckets["trivial_value"])), (["hull:b_ship"], 1))

    def test_counts_are_of_distinct_blobs_across_rows(self) -> None:
        # A blob two candidate roots hold is one blob, shared or counted apart (the module docstring).
        row = {"path": "In operation/A/working", "mod_id": "a", "anchors": ["hull:a_ship"], "error": None, "anchors_refused": {},
               "needs_refused": {}, "shared": [{"sha256": "s1"}], "counted_apart": {"trivial_value": ["t1"], "same_mod": ["m1"]}}
        counts = ls._counts({"roots": [{}, {}], "summary": {}}, [row, dict(row, path="In operation/B/working", mod_id="b")], 0)
        self.assertEqual((counts["shared_blobs"], counts["excluded"]["trivial_value"], counts["excluded"]["same_mod"]), (1, 1, 1))
        self.assertEqual((counts["roots_sharing"], counts["mod_ids_sharing"]), (2, 2))


class CliTests(unittest.TestCase):
    def _args(self, plan_file, core, bank, out):
        return SimpleNamespace(bank_command="lineage-scan", plan=plan_file, vanilla_core=core, bank=bank, quiet=True, out=out)

    def test_the_command_writes_the_report_outside_the_bank(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            out = io.StringIO()
            with mock.patch("bridgeforge.paths.data_root", return_value=base), contextlib.redirect_stdout(out):
                code = run_bank_cli(self._args(plan_file, core, bank, root / "reports" / "scan.json"))
            written = json.loads((root / "reports" / "scan.json").read_text(encoding="utf-8"))
            leftover = (root / "reports" / "scan.json.partial.jsonl").exists()
        self.assertEqual((code, leftover), (0, False))
        self.assertEqual(written["report"], "lineage-scan")
        self.assertIn("in 1 of 1 candidate root(s)", out.getvalue())

    def test_an_out_inside_the_bank_is_refused_before_anything_is_written(self) -> None:
        # Review, HIGH: the checkpoint beside --out was written into the bank, and the refusal came after the whole scan.
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            before = _snapshot(bank)
            with mock.patch("bridgeforge.paths.data_root", return_value=base), \
                    mock.patch.object(ls, "lineage_scan", side_effect=AssertionError("scanned")), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                codes = [run_bank_cli(self._args(plan_file, core, bank, bank / "scan.json")),
                         run_bank_cli(self._args(plan_file, core, bank, bank / "blobs" / "scan.json"))]
            after, problems = _snapshot(bank), Bank(bank).verify()
        self.assertEqual((codes, before, problems), ([2, 2], after, []))
        self.assertIn("inside the bank", err.getvalue())

    def test_the_checkpoint_stays_while_errors_remain(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None), ("Gone", "gonemod", None))
            shutil.rmtree(base / "In operation" / "Gone")
            with mock.patch("bridgeforge.paths.data_root", return_value=base), contextlib.redirect_stdout(io.StringIO()):
                code = run_bank_cli(self._args(plan_file, core, bank, root / "reports" / "scan.json"))
            kept = (root / "reports" / "scan.json.partial.jsonl").is_file()
        self.assertEqual((code, kept), (1, True))


if __name__ == "__main__":
    unittest.main()
