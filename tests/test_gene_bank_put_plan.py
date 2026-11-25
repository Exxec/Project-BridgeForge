"""94.G3 slice 2b: refusal rows, the `archive` folder kind and `gene bank put-plan` (docs/GENE_BANK_DESIGN.md). Synthetic
fixtures only."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.genome.alleles import AllelesError, plan
from bridgeforge.genome.bank import Bank, BankError, has_machine_path, put, rebuild, run_bank_cli, scrub_paths
from bridgeforge.genome.bank_plan import plan_items, put_plan, run_put_plan_cli
from tests.bound_runs import write_core_build
from tests.support import resolved_temp_dir, write_text as _write
from tests.test_gene_bank import _base, _seed

ANCHOR = "hull:fx_ship"
MISSING_START = "custom-start:nothing"


def _done(base: Path, working: Path) -> Path:
    """Done/ in archive.py's layout: the revival as Demo/Demo; the author's release as original/Demo-0.9, which differs only in
    its version (a second manifest of the same identity); two more archives whose copies fail in the tests."""
    done = base / "Done"
    for name in ("Demo", "Broken", "Errored"):
        _write(done / name / "ARCHIVE_NOTE.md", "# note\n")
        shutil.copytree(working, done / name / name)
    original = done / "Demo" / "original" / "Demo-0.9"
    shutil.copytree(working, original)
    info = json.loads((original / "mod_info.json").read_text(encoding="utf-8"))
    _write(original / "mod_info.json", json.dumps({**info, "version": "0.9"}))
    with zipfile.ZipFile(done / "Other.zip", "w") as archive:  # an archive only: counted in the report, not described
        archive.writestr("Other/mod_info.json", json.dumps({"id": "other", "version": "1"}))
    with zipfile.ZipFile(done / "Empty.zip", "w") as archive:
        archive.writestr("readme.txt", "no mod")
    _write(done / "Bad.zip", "not a zip")
    return done


def _walk(refuse=("Broken",), fail=("Errored",)):
    """The real walk, except that describe refuses the anchor of a copy named in `refuse` (its path in the reason) and a copy
    named in `fail` cannot be read."""
    from bridgeforge.genome import gene_set

    real = gene_set.walk

    def walk(mod, anchor, core, **kwargs):
        if Path(mod).name in refuse:
            return {}, {anchor: f"{anchor}: {Path(mod).resolve()} defines it twice"}
        if Path(mod).name in fail:
            raise OSError("the disk said no")
        return real(mod, anchor, core, **kwargs)

    return mock.patch("bridgeforge.genome.gene_set.walk", walk)


class RefusalRowTests(unittest.TestCase):
    def test_a_refused_anchor_is_recorded_with_a_scrubbed_reason_and_a_rebuild_elsewhere_reproduces_it(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, ANCHOR, core, bank=root / "Genes", base=base)
            refused = put(working, MISSING_START, core, bank=root / "Genes", base=base, record_refusal=True)
            with self.assertRaisesRegex(BankError, "custom-start:typo: <source>/data/config/exerelin/customStarts.json"):
                put(working, "custom-start:typo", core, bank=root / "Genes", base=base)  # no record_refusal: nothing written
            bank = Bank(root / "Genes")
            sources, refusals, problems, entries = bank.sources(), bank.refusals(), bank.verify(), bank.entries()
            other = root / "elsewhere"
            shutil.copytree(base, other / "data")
            shutil.copytree(core, other / "core")
            rebuilt = rebuild(other / "core", bank=_seed(root / "Genes", other), quiet=True, base=other / "data")
            elsewhere = Bank(other / "Genes").refusals()
        reason = f"{MISSING_START}: <source>/data/config/exerelin/customStarts.json does not exist"
        self.assertEqual((refused["stored"], refused["anchor_refused"]), (0, reason))
        self.assertEqual(sorted(s["anchor"] for s in sources), sorted([ANCHOR, MISSING_START]))  # "custom-start:typo" is absent
        self.assertEqual(([(r["anchor"], r["records"], r["refused"]) for r in refusals], problems), ([(MISSING_START, [], reason)], []))
        self.assertNotIn("refused", next(row for row in entries if row["anchor"] == ANCHOR))  # slice 1's rows are unchanged
        self.assertEqual((rebuilt["root"], rebuilt["problems"], elsewhere, rebuilt["newly_refused"]),
                         (refused["root"], [], refusals, []))

    def test_a_refusal_row_with_records_or_a_machine_path_is_a_problem_and_archive_is_a_folder_kind(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            done = _done(base, working)
            put(done / "Demo" / "Demo", ANCHOR, core, folder="archive", bank=root / "Genes", base=base)
            put(working, MISSING_START, core, bank=root / "Genes", base=base, record_refusal=True)
            bank = Bank(root / "Genes")
            kinds = {r["source"]["folder"] for r in bank.records().values()}
            entries = bank.entries()
            rid = next(row["records"][0] for row in entries if row["records"])
            tampered = [{**row, "records": [rid], "refused": "x: C:/Users/someone/mod is broken"} if row.get("refused") else row
                        for row in entries]
            (root / "Genes" / "entries.json").write_text(json.dumps(tampered), encoding="utf-8")
            record_file = root / "Genes" / "records" / f"{rid}.json"
            record = json.loads(record_file.read_text(encoding="utf-8"))
            record_file.write_text(json.dumps({**record, "needs_refused": {"variant:v": "v: /home/someone/mod"}}), encoding="utf-8")
            problems = bank.verify()
        self.assertEqual(kinds, {"archive"})
        self.assertTrue([p for p in problems if "is recorded as refused but holds records" in p])
        self.assertTrue([p for p in problems if "its refusal reason holds a machine path" in p])
        self.assertTrue([p for p in problems if "a refused need's reason holds a machine path" in p])

    def test_an_oserror_s_doubled_backslashes_are_scrubbed_and_machine_paths_are_recognised(self) -> None:
        source = Path("C:/Games/mods/Demo") if Path("C:/").drive else Path("/home/u/mods/Demo")
        quoted = str(source).replace("\\", "\\\\")
        text = f"[Errno 13] Permission denied: '{quoted}\\\\jars\\\\x.jar'"
        scrubbed = scrub_paths(text, [("<source>", source)]).replace("\\", "/")
        self.assertEqual(scrubbed, "[Errno 13] Permission denied: '<source>//jars//x.jar'")
        self.assertFalse(has_machine_path(scrubbed))
        self.assertEqual([has_machine_path(t) for t in ("D:\\x", "at /home/u/x", "data/hulls/a.ship", "e:/y")],
                         [True, True, False, True])

    def test_a_core_reporting_no_build_or_another_build_is_refused_before_anything_is_written(self) -> None:
        # Review of slice 2b (CRITICAL): a wrong core stored every copy under its build, and rebuild then refused every core.
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, ANCHOR, core, bank=root / "Genes", base=base)
            rc8 = root / "rc8"
            shutil.copytree(core, rc8)
            write_core_build(rc8, "0.98a-RC8")
            (root / "empty-core").mkdir()
            with self.assertRaisesRegex(BankError, "the core reports 0.98a-RC8, but this bank's sources were described against"):
                put(working, MISSING_START, rc8, bank=root / "Genes", base=base, record_refusal=True)
            with self.assertRaisesRegex(BankError, "reports no game build"):
                put(working, MISSING_START, root / "empty-core", bank=root / "Genes", base=base, record_refusal=True)
            with self.assertRaisesRegex(BankError, "reports no game build"):
                rebuild(root / "empty-core", bank=root / "Genes", quiet=True, base=base)
            sources = Bank(root / "Genes").sources()
        self.assertEqual([s["anchor"] for s in sources], [ANCHOR])

    def test_a_stored_source_refused_by_a_rebuild_is_listed_and_fails_the_cli(self) -> None:
        # Review of slice 2b (HIGH): such a rebuild exited 0, and its progress line said "0 gene(s)".
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            put(working, ANCHOR, core, bank=root / "Genes", base=base)
            args = SimpleNamespace(bank_command="rebuild", vanilla_core=core, bank=root / "Genes", quiet=True)
            with _walk(refuse=("working",)), mock.patch("bridgeforge.paths.data_root", return_value=base):
                with contextlib.redirect_stdout(io.StringIO()) as first_out:
                    first = run_bank_cli(args)
                with contextlib.redirect_stdout(io.StringIO()) as second_out:
                    second = run_bank_cli(args)  # refused already: nothing newly refused
        self.assertEqual((first, second), (1, 0))
        self.assertIn(f"newly refused: In operation/Demo/working (working) {ANCHOR}: {ANCHOR}: <source> defines it twice",
                      first_out.getvalue())
        self.assertIn("1 refused, 0 of them newly", second_out.getvalue())


class PutPlanTests(unittest.TestCase):
    def _setup(self, root: Path) -> tuple[Path, Path, Path, Path]:
        base, working, core, _ = _base(root)
        put(working, ANCHOR, core, bank=root / "Genes", base=base)
        done = _done(base, working)
        plan_file = root / "plan.json"
        plan_file.write_text(json.dumps(plan(done, bank=root / "Genes", quiet=True, base=base)), encoding="utf-8")
        return base, working, core, plan_file

    def test_each_copy_is_stored_or_refused_errors_are_reported_and_a_rebuild_matches(self) -> None:
        with resolved_temp_dir() as root:
            base, _, core, plan_file = self._setup(root)
            with _walk():  # the refusal is the copy's own, so a rebuild meets it again
                result = put_plan(plan_file, core, bank=root / "Genes", quiet=True, base=base)
                bank = Bank(root / "Genes")
                problems, refusals, sources = bank.verify(), bank.refusals(), bank.sources()
                in_place = rebuild(core, bank=root / "Genes", quiet=True, base=base)
                fresh = rebuild(core, bank=_seed(root / "Genes", root / "fresh"), quiet=True, base=base)
        row = result["anchors"][ANCHOR]
        self.assertEqual((row["copies"], row["stored"], row["refused"], row["errors"]), (4, 2, 1, 1))
        # The revival is the working copy's allele again; the author's release differs only in its version: a second
        # manifest of the same identity.
        self.assertEqual((row["alleles_from_plan"], row["identities_from_plan"], row["alleles_in_bank"], row["identities_in_bank"]),
                         (2, 1, 2, 1))
        self.assertEqual([r["error"] for r in result["items"] if r["error"]], ["never banked: OSError: the disk said no"])
        self.assertEqual(result["not_described"], {"zips_archive_only": 1, "zips_unreadable": 1, "zips_no_mod": 1,
                                                   "unread_archives": 0, "skipped_copies": 0, "plan_errors": 0})
        self.assertEqual([r["refused"] for r in refusals], [f"{ANCHOR}: <source> defines it twice"])
        self.assertNotIn("Done/Errored/Errored", {s["path"] for s in sources})  # an error is never banked
        self.assertEqual(problems, [])
        self.assertEqual((in_place["root"], fresh["root"], in_place["problems"], fresh["problems"], in_place["newly_refused"]),
                         (result["root"], result["root"], [], [], []))

    def test_the_cli_resumes_keeps_its_checkpoint_while_errors_remain_and_then_retries_only_those(self) -> None:
        from bridgeforge.genome import bank as bank_module

        with resolved_temp_dir() as root:
            base, _, core, plan_file = self._setup(root)
            real, calls = bank_module.put, []

            def counting(source, anchor, vanilla_core, **kwargs):
                calls.append(Path(source).name)
                if len(calls) == 2 and not (root / "report.json").exists():
                    raise KeyboardInterrupt  # an interrupted first run
                return real(source, anchor, vanilla_core, **kwargs)

            args = SimpleNamespace(plan=plan_file, vanilla_core=core, bank=root / "Genes", report=root / "report.json", quiet=True)
            checkpoint = root / "Genes" / "put-plan.partial.jsonl"
            with mock.patch.object(bank_module, "put", counting), mock.patch("bridgeforge.paths.data_root", return_value=base):
                with _walk():
                    with self.assertRaises(KeyboardInterrupt):
                        run_put_plan_cli(args)
                    with contextlib.redirect_stdout(io.StringIO()) as out:
                        first = run_put_plan_cli(args)
                kept = checkpoint.exists()
                with _walk(fail=()), contextlib.redirect_stdout(io.StringIO()):  # the disk is back
                    second = run_put_plan_cli(args)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            left = checkpoint.exists()
        self.assertEqual((first, kept, second, left), (1, True, 0, False))
        self.assertEqual(len(calls), 2 + 3 + 1)  # resumed; then only the copy that had failed
        self.assertIn(f"{ANCHOR}: 2 of 4 stored, 1 refused, 1 error(s)", out.getvalue())
        row = report["anchors"][ANCHOR]
        # Three stored copies, two manifests, one identity: the Errored copy is the revival's allele again.
        self.assertEqual((report["errors"], row["stored"], row["alleles_from_plan"], row["identities_from_plan"]), (0, 3, 2, 1))

    def test_a_stale_copy_another_bank_s_plan_and_a_non_plan_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, plan_file = self._setup(root)
            demo = base / "Done" / "Demo" / "Demo" / "mod_info.json"
            demo.write_text(demo.read_text(encoding="utf-8") + " ", encoding="utf-8")  # changed since the plan
            with _walk():
                result = put_plan(plan_file, core, bank=root / "Genes", quiet=True, base=base)
            other = root / "other-bank"
            put(working, "hull:other_ship", core, bank=other, base=base, record_refusal=True)
            with self.assertRaisesRegex(AllelesError, "the plan was made for the pilots hull:fx_ship"):
                put_plan(plan_file, core, bank=other, quiet=True, base=base)
            _write(root / "x.json", json.dumps({"schema": "other"}))
            args = SimpleNamespace(plan=root / "x.json", vanilla_core=core, bank=root / "Genes", report=root / "r.json", quiet=True)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = run_put_plan_cli(args)
        stale = [r for r in result["items"] if r["path"] == "Done/Demo/Demo"]
        self.assertEqual([r["error"] for r in stale], ["its mod_info.json changed since the plan: run gene bank alleles again"])
        self.assertEqual(code, 2)
        self.assertIn("not a bridgeforge-gene-alleles plan", err.getvalue())

    def test_a_failure_after_the_sources_line_is_written_says_so(self) -> None:
        from bridgeforge.genome.bank import Bank as BankClass

        real, failed = BankClass.set_entry, []

        def failing(self, entry, rids, refused=None):
            if entry["path"] == "Done/Demo/Demo" and not failed:
                failed.append(entry["path"])
                raise OSError("the disk filled up")
            return real(self, entry, rids, refused)

        with resolved_temp_dir() as root:
            base, _, core, plan_file = self._setup(root)
            with _walk(), mock.patch.object(BankClass, "set_entry", failing):
                result = put_plan(plan_file, core, bank=root / "Genes", quiet=True, base=base)
        errors = {r["path"]: r["error"] for r in result["items"] if r["error"]}
        self.assertEqual(errors["Done/Demo/Demo"], "partly written (its sources line is in the bank): OSError: the disk filled up")

    def test_only_pilot_anchors_are_put_and_a_plan_missing_a_key_is_refused_before_any_put(self) -> None:
        data = {"schema": "bridgeforge-gene-alleles", "schema_version": 1, "pilot_anchors": [ANCHOR], "corpus": "Done",
                "zips": [], "unread_archives": [], "skipped": [], "summary": {"errors": 0},
                "roots": [{"path": "Done/A/A", "folder": "archive", "defines": [ANCHOR, "variant:needed_v"], "mod_info_sha256": "h"},
                          {"path": "Done/B/B", "folder": "archive", "defines": ["variant:needed_v"], "mod_info_sha256": "g"}]}
        self.assertEqual(plan_items(data), [("Done/A/A", "archive", ANCHOR, "h")])  # a needed gene elsewhere is slice 3's input
        with self.assertRaisesRegex(AllelesError, "the plan lacks zips"):
            plan_items({k: v for k, v in data.items() if k != "zips"})


if __name__ == "__main__":
    unittest.main()
