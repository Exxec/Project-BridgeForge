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
from tests.test_gene_bank import SHIP, _base


def _copy(base: Path, name: str, mod_id: str | None, *, ship: dict | None = None) -> Path:
    """In operation/<name>/working: the Demo mod under another mod id (or none), its ship file optionally changed."""
    source = base / "In operation" / "Demo" / "working"
    working = base / "In operation" / name / "working"
    shutil.copytree(source, working)
    info = json.loads((working / "mod_info.json").read_text(encoding="utf-8"))
    if mod_id is None:
        info.pop("id")
    else:
        info["id"] = mod_id
    (working / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    if ship is not None:
        (working / SHIP).write_text(json.dumps(ship), encoding="utf-8")
    return working


def _corpus(root: Path, *copies: tuple[str, str | None, dict | None]):
    """(base, core, bank, plan file): Demo banked by a real put, then copies of it, then an alleles plan over In operation."""
    base, working, core, _ = _base(root)
    put(working, "hull:fx_ship", core, bank=root / "Genes", base=base)
    for name, mod_id, ship in copies:
        _copy(base, name, mod_id, ship=ship)
    result = plan(base / "In operation", bank=root / "Genes", base=base, quiet=True)
    plan_file = root / "plan.json"
    write_plan(result, plan_file)
    return base, core, root / "Genes", plan_file


class ScanTests(unittest.TestCase):
    def test_a_copy_under_another_mod_id_shares_its_members_and_an_edited_one_exactly_the_unchanged_one(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None),
                                                  ("Edited", "editedmod", {"hullId": "fx_ship", "style": "FX_STYLE", "hitpoints": 9}))
            before = _snapshot(bank)
            members = sorted(json.loads(p.read_text(encoding="utf-8"))["members"]
                             for p in (bank / "records").iterdir())[0]
            report = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True)
            after, problems = _snapshot(bank), Bank(bank).verify()
        self.assertEqual((before, problems), (after, []))  # nothing is put and the bank verifies
        rows = {row["mod_id"]: row for row in report["candidates"]}
        self.assertEqual(sorted(rows), ["copymod", "editedmod"])  # the banked mod's own copy is no candidate
        self.assertEqual(sorted(blob["path"] for blob in rows["copymod"]["shared"]), sorted(members))
        edited = [blob["path"] for blob in rows["editedmod"]["shared"]]
        self.assertEqual(sorted(edited), sorted(path for path in members if path != SHIP))
        self.assertTrue(all(h["mod_id"] == "demomod" for blob in rows["copymod"]["shared"] for h in blob["bank_holders"]))
        counts = report["counts"]
        self.assertEqual((counts["candidates"], counts["described"], counts["errors"], counts["candidates_sharing"]), (2, 2, 0, 2))
        self.assertEqual(counts["shared_blobs"], len(members))
        self.assertEqual(report["build"], "0.98.5a-RC7")

    def test_a_plan_with_only_the_banked_mod_finds_nothing(self) -> None:
        # The acceptance's "0 over Done/": no root defines a banked anchor under another mod id.
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root)
            report = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True)
        self.assertEqual((report["counts"]["candidates"], report["counts"]["shared_blobs"]), (0, 0))

    def test_a_root_without_a_mod_id_is_a_candidate(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Nameless", None, None))
            report = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True)
        self.assertEqual([row["mod_id"] for row in report["candidates"]], [None])
        self.assertTrue(report["candidates"][0]["shared"])

    def test_a_root_changed_or_gone_since_the_plan_is_an_error_and_a_resume_retries_only_it(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None), ("Gone", "gonemod", None))
            shutil.rmtree(base / "In operation" / "Gone")
            checkpoint = root / "scan.partial.jsonl"
            first = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True, checkpoint_path=checkpoint)
            with mock.patch("bridgeforge.genome.gene_set.walk", side_effect=AssertionError("described again")) as walk:
                second = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True, checkpoint_path=checkpoint)
            changed = _copy(base, "Gone", "gonemod")  # back, but not as planned
            (changed / "mod_info.json").write_text(json.dumps({"id": "gonemod", "version": "2.0"}), encoding="utf-8")
            third = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True)
        errors = {row["mod_id"]: row["error"] for row in first["candidates"]}
        self.assertEqual(errors["copymod"], None)
        self.assertIn("gone since the plan", errors["gonemod"])
        walk.assert_not_called()  # copymod came from the checkpoint; gonemod failed before describing
        self.assertEqual(second["counts"]["errors"], 1)
        self.assertIn("changed since the plan", {r["mod_id"]: r["error"] for r in third["candidates"]}["gonemod"])

    def test_a_describe_that_fails_or_refuses_is_counted_and_the_scan_goes_on(self) -> None:
        from bridgeforge.genome import gene_set

        real = gene_set.walk

        def walk(mod, anchor, core, **kwargs):
            if "Broken" in str(mod):
                raise RuntimeError("cannot parse")
            if "Refused" in str(mod):
                return {}, {anchor: "defines no such hull"}
            return real(mod, anchor, core, **kwargs)

        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Broken", "brokenmod", None), ("Refused", "refusedmod", None),
                                                  ("Copy", "copymod", None))
            with mock.patch("bridgeforge.genome.gene_set.walk", walk):
                report = ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True)
        rows = {row["mod_id"]: row for row in report["candidates"]}
        self.assertIn("RuntimeError: cannot parse", rows["brokenmod"]["error"])
        self.assertEqual(rows["refusedmod"]["refused"], "defines no such hull")
        self.assertTrue(rows["copymod"]["shared"])
        self.assertEqual((report["counts"]["errors"], report["counts"]["refused"], report["counts"]["described"]), (1, 1, 1))

    def test_a_core_of_another_build_is_refused(self) -> None:
        from tests.bound_runs import write_core_build

        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            write_core_build(core, "0.98.5a-RC9")
            with self.assertRaises(BankError) as refused:
                ls.lineage_scan(plan_file, core, bank=bank, base=base, quiet=True)
        self.assertIn("one bank holds one build", str(refused.exception))

    def test_something_that_is_not_a_plan_is_refused(self) -> None:
        from bridgeforge.genome.alleles import AllelesError

        with resolved_temp_dir() as root:
            (root / "x.json").write_text(json.dumps({"schema": "other"}), encoding="utf-8")
            with self.assertRaises(AllelesError):
                ls.load_plan(root / "x.json")
            with self.assertRaises(BankError):
                ls.load_plan(root / "missing.json")


class CompareTests(unittest.TestCase):
    """The exclusions of slice 3a, applied to a candidate's members: each is counted apart, never reported as shared."""

    def _compare(self, member_data: dict[str, bytes], holder_mod: str = "banked", *, donor_only: bytes | None = None,
                 vanilla: set[str] | None = None, candidate_mod: str = "other"):
        with resolved_temp_dir() as root:
            fake = FakeBank(root)
            fake.record(holder_mod, "hull:a_ship", members=member_data, donor={"d/x.json": donor_only} if donor_only else None)
            bank = fake.finish()
            _anchors, members, donor, _unreadable = ls.bank_side(bank)
            genes = {"hull:b_ship": {"members": [{"path": p, "sha256": hashlib.sha256(d).hexdigest()} for p, d in member_data.items()]
                                     + ([{"path": "c/donor.json", "sha256": hashlib.sha256(donor_only).hexdigest()}] if donor_only else [])}}
            excluded = {"donor_side": 0, "trivial_value": 0, "vanilla_file": 0, "same_mod": 0}
            shared = ls._compare(bank, genes, candidate_mod, members, donor, vanilla or set(), excluded)
        return shared, excluded

    def test_a_long_value_is_shared_and_names_the_bank_holder(self) -> None:
        shared, excluded = self._compare({"data/a.json": LONG_TEXT})
        self.assertEqual([(s["path"], s["bank_holders"][0]["mod_id"]) for s in shared], [("data/a.json", "banked")])
        self.assertEqual(sum(excluded.values()), 0)

    def test_trivial_vanilla_donor_only_and_same_mod_are_counted_apart(self) -> None:
        self.assertEqual(self._compare({"data/n.json": b"5"})[1]["trivial_value"], 1)
        digest = hashlib.sha256(LONG_TEXT).hexdigest()
        self.assertEqual(self._compare({"data/a.json": LONG_TEXT}, vanilla={digest})[1]["vanilla_file"], 1)
        shared, excluded = self._compare({}, donor_only=b"a sprite the bank only needs, byte for byte, as a donor")
        self.assertEqual((shared, excluded["donor_side"]), ([], 1))
        shared, excluded = self._compare({"data/a.json": LONG_TEXT}, holder_mod="other", candidate_mod="other")
        self.assertEqual((shared, excluded["same_mod"]), ([], 1))


class CliTests(unittest.TestCase):
    def test_the_command_writes_the_report_outside_the_bank_and_refuses_inside(self) -> None:
        with resolved_temp_dir() as root:
            base, core, bank, plan_file = _corpus(root, ("Copy", "copymod", None))
            args = SimpleNamespace(bank_command="lineage-scan", plan=plan_file, vanilla_core=core, bank=bank, quiet=True,
                                   out=root / "reports" / "scan.json")
            out = io.StringIO()
            with mock.patch("bridgeforge.paths.data_root", return_value=base), contextlib.redirect_stdout(out):
                code = run_bank_cli(args)
            written = json.loads((root / "reports" / "scan.json").read_text(encoding="utf-8"))
            self.assertFalse((root / "reports" / "scan.json.partial.jsonl").exists())
            args.out = bank / "scan.json"
            with mock.patch("bridgeforge.paths.data_root", return_value=base), contextlib.redirect_stderr(io.StringIO()) as err:
                refused = run_bank_cli(args)
            inside = (bank / "scan.json").exists()
        self.assertEqual((code, refused, inside), (0, 2, False))
        self.assertEqual(written["report"], "lineage-scan")
        self.assertIn("lineage-scan:", out.getvalue())
        self.assertIn("1 of 1 candidate(s)", out.getvalue())
        self.assertIn("bank", err.getvalue())


if __name__ == "__main__":
    unittest.main()
