"""ROADMAP 70 H3.1: forecast findings are predictions; live-tested outcomes are recorded, shown on findings and counted per rule."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from bridgeforge import atlas, atlas_predictions
from bridgeforge.atlas_rules import forecast
from bridgeforge.cli import main
from tests.support import resolved_temp_dir
from tests.test_atlas import INDUSTRIES_HEADER, build, make_mod, make_vanilla, temp_root

JAVA = 'package d;\npublic class D { void go(MarketAPI m) { m.getIndustry("farming"); } }\n'


def _world(root):
    make_vanilla(root)
    make_mod(root / "mods", "dneep", {"data/scripts/D.java": JAVA}, name="Doc's Needless Economic Expansion Pack")
    make_mod(root / "mods", "aotd_vok", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_subsidised_farming,Subsidised Farming,,farming\n"}, name="AoTD VoK")


class PredictionLedgerTests(unittest.TestCase):
    def test_an_outcome_needs_a_run_and_a_note_and_is_stored(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "predictions.json"
            with self.assertRaises(ValueError):
                atlas_predictions.record("ATLAS-X", "m", "i", "confirmed", " ", "note", path=path)
            with self.assertRaises(ValueError):
                atlas_predictions.record("ATLAS-X", "m", "i", "confirmed", "RUN-20261012", "", path=path)
            with self.assertRaises(ValueError):
                atlas_predictions.record("ATLAS-X", "m", "i", "maybe", "RUN-20261012", "n", path=path)
            atlas_predictions.record("ATLAS-X", "m", "i", "confirmed", "RUN-20261012", "seen", path=path, today="2026-10-12")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["predictions"][0]["date"], "2026-10-12")
            self.assertEqual(len(atlas_predictions.load(path)), 1)

    def test_precision_counts_decided_cases_per_rule(self) -> None:
        entries = [{"rule": "R1", "outcome": "confirmed"}, {"rule": "R1", "outcome": "refuted"}, {"rule": "R1", "outcome": "confirmed"},
                   {"rule": "R2", "outcome": "inconclusive"}]
        table = atlas_predictions.precision(entries)
        self.assertEqual((table["R1"]["confirmed"], table["R1"]["refuted"], table["R1"]["hit_rate"]), (2, 1, 0.67))
        self.assertIsNone(table["R2"]["hit_rate"])

    def test_a_matching_finding_is_annotated_and_an_unrelated_one_is_not(self) -> None:
        entries = [{"rule": "ATLAS-READS-REPLACED", "mod": "dneep", "other": "aotd_vok", "id": "farming", "outcome": "confirmed",
                    "run": "GRP-DNEEP-SUPPLY-BEFORE-20261011", "note": "no food"},
                   {"rule": "ATLAS-READS-REPLACED", "mod": "dneep", "other": "someone_else", "id": "farming", "outcome": "refuted", "run": "X-20261012", "note": "n"}]
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            conn = atlas.connect(db)
            subjects, family = atlas.resolve_mods(conn, ["dneep"]), atlas.group_mods(conn, "aotd")
            plain = forecast(conn, subjects, family)
            annotated = forecast(conn, subjects, family, predictions=entries)
        self.assertNotIn("[prediction", plain["findings"][0].summary)  # no ledger passed: library calls stay isolated from the real file
        self.assertIn("[prediction confirmed by GRP-DNEEP-SUPPLY-BEFORE-20261011: no food]", annotated["findings"][0].summary)
        self.assertNotIn("refuted", annotated["findings"][0].summary)  # the entry for another partner mod does not match

    def test_the_commands_record_and_report_and_the_committed_ledger_holds_decided_cases(self) -> None:
        with resolved_temp_dir() as root:
            path = root / "p.json"
            from unittest import mock

            with mock.patch.object(atlas_predictions, "DEFAULT_PATH", path):
                out = io.StringIO()
                with redirect_stdout(out):
                    self.assertEqual(main(["atlas", "outcome", "ATLAS-READS-REPLACED", "--mod", "m", "--id", "i", "--outcome", "refuted", "--run", "R-20261012", "--note", "n"]), 0)
        self.assertIn("Recorded: ATLAS-READS-REPLACED m/i refuted by R-20261012", out.getvalue())
        committed = atlas_predictions.load()
        self.assertTrue({e["outcome"] for e in committed} >= {"confirmed", "refuted"})
        for entry in committed:
            self.assertTrue(entry["run"] and entry["note"])


if __name__ == "__main__":
    unittest.main()
