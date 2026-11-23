"""94.G3 slice 2b: refusal rows, the `archive` folder kind and `gene bank put-plan` (docs/GENE_BANK_DESIGN.md). Synthetic
fixtures only."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from bridgeforge.genome.alleles import plan, put_plan, run_put_plan_cli
from bridgeforge.genome.bank import Bank, BankError, put, rebuild
from tests.support import resolved_temp_dir, write_text as _write
from tests.test_gene_bank import SHIP, _base, _seed

ANCHOR = "hull:fx_ship"
MISSING_START = "custom-start:nothing"


def _done(base: Path, working: Path) -> Path:
    """Done/ in archive.py's layout: the revival as Demo/Demo, the author's release (one value changed: a second allele) as
    original/Demo-1.0, and two more archives whose copies fail in the tests."""
    done = base / "Done"
    for name in ("Demo", "Broken", "Errored"):
        _write(done / name / "ARCHIVE_NOTE.md", "# note\n")
        shutil.copytree(working, done / name / name)
    original = done / "Demo" / "original" / "Demo-1.0"
    shutil.copytree(working, original)
    _write(original / SHIP, json.dumps({"hullId": "fx_ship", "style": "FX_STYLE", "hitpoints": 7}))
    return done


def _failing_walk():
    """The real walk, except that describe refuses the Broken copy's anchor and the Errored copy cannot be read."""
    from bridgeforge.genome import gene_set

    real = gene_set.walk

    def walk(mod, anchor, core, **kwargs):
        if Path(mod).name == "Broken":
            return {}, {anchor: f"{anchor}: {Path(mod).resolve()} defines it twice"}
        if Path(mod).name == "Errored":
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
            sources, refusals, problems = bank.sources(), bank.refusals(), bank.verify()
            other = root / "elsewhere"
            shutil.copytree(base, other / "data")
            shutil.copytree(core, other / "core")
            rebuilt = rebuild(other / "core", bank=_seed(root / "Genes", other), quiet=True, base=other / "data")
            elsewhere = Bank(other / "Genes").refusals()
        reason = f"{MISSING_START}: <source>/data/config/exerelin/customStarts.json does not exist"
        self.assertEqual((refused["stored"], refused["anchor_refused"]), (0, reason))
        self.assertEqual(sorted(s["anchor"] for s in sources), sorted([ANCHOR, MISSING_START]))  # "custom-start:typo" is absent
        self.assertEqual(([(r["anchor"], r["records"], r["refused"]) for r in refusals], problems), ([(MISSING_START, [], reason)], []))
        self.assertEqual((rebuilt["root"], rebuilt["problems"], elsewhere), (refused["root"], [], refusals))

    def test_a_refusal_row_holding_records_is_a_problem_and_archive_is_a_folder_kind(self) -> None:
        with resolved_temp_dir() as root:
            base, working, core, _ = _base(root)
            done = _done(base, working)
            put(done / "Demo" / "Demo", ANCHOR, core, folder="archive", bank=root / "Genes", base=base)
            put(working, MISSING_START, core, bank=root / "Genes", base=base, record_refusal=True)
            bank = Bank(root / "Genes")
            kinds = {r["source"]["folder"] for r in bank.records().values()}
            entries = bank.entries()
            rid = next(row["records"][0] for row in entries if row["records"])
            (root / "Genes" / "entries.json").write_text(json.dumps([{**row, "records": [rid]} if row.get("refused") else row
                                                                      for row in entries]), encoding="utf-8")
            problems = bank.verify()
        self.assertEqual(kinds, {"archive"})
        self.assertTrue([p for p in problems if "is recorded as refused but holds records" in p])


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
            with _failing_walk():  # the refusal is the copy's own, so a rebuild meets it again
                result = put_plan(plan_file, core, bank=root / "Genes", quiet=True, base=base)
                bank = Bank(root / "Genes")
                problems, refusals, sources = bank.verify(), bank.refusals(), bank.sources()
                in_place = rebuild(core, bank=root / "Genes", quiet=True, base=base)
                fresh = rebuild(core, bank=_seed(root / "Genes", root / "fresh"), quiet=True, base=base)
        row = result["anchors"][ANCHOR]
        self.assertEqual((row["copies"], row["stored"], row["refused"], row["errors"]), (4, 2, 1, 1))
        # The revival is the working copy's allele again; the author's release, with one value changed, is a second.
        self.assertEqual((row["alleles_from_plan"], row["alleles_in_bank"]), (2, 2))
        self.assertEqual([r["error"] for r in result["items"] if r["error"]], ["OSError: the disk said no"])
        self.assertEqual([r["refused"] for r in refusals], [f"{ANCHOR}: <source> defines it twice"])
        self.assertNotIn("Done/Errored/Errored", {s["path"] for s in sources})  # an error is never banked
        self.assertEqual(problems, [])
        self.assertEqual((in_place["root"], fresh["root"], in_place["problems"], fresh["problems"]),
                         (result["root"], result["root"], [], []))

    def test_the_cli_resumes_retries_errors_writes_the_report_and_removes_its_checkpoint(self) -> None:
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
            with _failing_walk(), mock.patch.object(bank_module, "put", counting), mock.patch("bridgeforge.paths.data_root",
                                                                                               return_value=base):
                with self.assertRaises(KeyboardInterrupt):
                    run_put_plan_cli(args)
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    code = run_put_plan_cli(args)
            report = json.loads((root / "report.json").read_text(encoding="utf-8"))
            left = (root / "Genes" / "put-plan.partial.jsonl").exists()
        self.assertEqual((code, left, report["errors"], report["refused"]), (1, False, 1, 1))
        self.assertEqual(len(calls), 2 + 3)  # the first copy came from the checkpoint; the interrupted one ran again
        self.assertIn(f"{ANCHOR}: 2 of 4 stored, 1 refused, 1 error(s)", out.getvalue())

    def test_a_file_that_is_not_a_plan_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            base, _, core, _ = _base(root)
            _write(root / "x.json", json.dumps({"schema": "other"}))
            args = SimpleNamespace(plan=root / "x.json", vanilla_core=core, bank=root / "Genes", report=root / "r.json", quiet=True)
            with contextlib.redirect_stderr(io.StringIO()) as err:
                code = run_put_plan_cli(args)
        self.assertEqual(code, 2)
        self.assertIn("not a bridgeforge-gene-alleles plan", err.getvalue())


if __name__ == "__main__":
    unittest.main()
