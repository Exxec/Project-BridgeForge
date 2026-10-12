"""Mod Atlas phases 4-6 (ROADMAP item 67): probe logs join the index, a modpack is forecast whole, every mod is swept against a family."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge import atlas
from bridgeforge.atlas_rules import forecast
from bridgeforge.atlas_runtime import ingest
from bridgeforge.atlas_sweep import read_pack, sweep, sweep_text
from bridgeforge.cli import main
from tests.test_atlas import INDUSTRIES_HEADER, build, make_mod, make_vanilla, temp_root, write

DNEEP_JAVA = ('package data.scripts;\npublic class Deposits {\n  void run(MarketAPI market) {\n'
              '    Industry farm = market.getIndustry("farming");\n  }\n}\n')
LOG_FAIL = ("1 [Thread-3] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.25|market-supply|FAIL|d_grain|supplied in 0 market(s), "
            "total 0, by {}; demanded in 38 market(s): demand with no supply anywhere\n"
            "2 [Thread-3] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.25|market-supply|FAIL|commodities|checked=2 failed=1\n"
            "3 [Thread-3] INFO  com.bridgeforge.probe.ProbeLog  - BF-PROBE|0.2.25|market-supply|INFO|d_water|supplied in 7 market(s)\n"
            "4 [Thread-3] INFO  noise\n")


def _world(root):
    make_vanilla(root)
    make_mod(root / "mods", "dneep", {"data/scripts/Deposits.java": DNEEP_JAVA, "data/campaign/commodities.csv": "name,id\nGrain,d_grain\nWater,d_water\n"},
             name="Doc's Needless Economic Expansion Pack")
    make_mod(root / "mods", "aotd_vok", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_subsidised_farming,Subsidised Farming,,farming\n"},
             name="AoTD- Vaults of Knowledge")
    make_mod(root / "mods", "calm", {"data/campaign/commodities.csv": "name,id\nGoo,goo\n"})


class RuntimeTests(unittest.TestCase):
    def test_atlas_runtime_supply_names_the_commodity_owner_and_confirms_the_static_finding(self) -> None:
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            log = root / "GRP-DNEEP-SUPPLY-BEFORE-20261011.stdout.log"
            log.write_text(LOG_FAIL, encoding="utf-8")
            conn = atlas.connect(db)
            stats = ingest(conn, [log])
            self.assertEqual(stats["tests"], ["GRP-DNEEP-SUPPLY-BEFORE-20261011"])
            self.assertEqual(stats["lines"], 3)  # the FAIL, the summary FAIL and the INFO market-supply line; noise is dropped
            result = forecast(conn, atlas.resolve_mods(conn, ["dneep"]), atlas.group_mods(conn, "aotd"))
            live = [f for f in result["findings"] if f.rule == "ATLAS-RUNTIME-SUPPLY"]
            self.assertEqual([f.mods for f in live], [["dneep"]])
            self.assertIn("GRP-DNEEP-SUPPLY-BEFORE-20261011", live[0].summary)
            static = [f for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"]
            self.assertTrue(static and "[confirmed live: GRP-DNEEP-SUPPLY-BEFORE-20261011]" in static[0].summary)

    def test_a_failure_a_later_run_shows_fixed_is_kept_as_safe_history(self) -> None:
        fixed = ("1 BF-PROBE|0.2.25|market-supply|INFO|d_grain|supplied in 10 market(s), total 62, by {farming=10}; demanded in 38 market(s)\n"
                 "2 BF-PROBE|0.2.25|market-supply|OK|commodities|checked=2 expectations=0 failed=0\n")
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            before, after = root / "OLD.stdout.log", root / "NEW.stdout.log"
            before.write_text(LOG_FAIL, encoding="utf-8")
            after.write_text(fixed, encoding="utf-8")
            conn = atlas.connect(db)
            ingest(conn, [before, after])  # oldest first
            result = forecast(conn, atlas.resolve_mods(conn, ["dneep"]), atlas.group_mods(conn, "aotd"))
            live = [f for f in result["findings"] if f.rule == "ATLAS-RUNTIME-SUPPLY"]
            self.assertEqual([f.level for f in live], ["SAFE"])
            self.assertIn("fixed since: NEW", live[0].summary)
            static = [f for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"]
            self.assertIn("[seen live in OLD, fixed since]", static[0].summary)
            ingest(conn, [after, before])  # the failing run ingested last is the newest evidence: open again
            reopened = [f for f in forecast(conn, atlas.resolve_mods(conn, ["dneep"]), atlas.group_mods(conn, "aotd"))["findings"]
                        if f.rule == "ATLAS-RUNTIME-SUPPLY"]
            self.assertEqual([f.level for f in reopened], ["REVIEW"])

    def test_reingesting_a_test_replaces_its_lines_and_a_clean_run_adds_no_finding(self) -> None:
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            log = root / "T1.stdout.log"
            log.write_text(LOG_FAIL, encoding="utf-8")
            conn = atlas.connect(db)
            ingest(conn, [log])
            log.write_text("1 BF-PROBE|0.2.25|market-supply|OK|d_grain@farming|farming supplies d_grain in 10 market(s)\n", encoding="utf-8")
            ingest(conn, [log])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM runtime WHERE test = 'T1'").fetchone()[0], 1)
            result = forecast(conn, atlas.resolve_mods(conn, ["dneep"]), atlas.group_mods(conn, "aotd"))
            self.assertEqual([f for f in result["findings"] if f.rule == "ATLAS-RUNTIME-SUPPLY"], [])

    def test_the_runtime_command_reads_logs(self) -> None:
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            log = root / "T2.stdout.log"
            log.write_text(LOG_FAIL, encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["atlas", "runtime", str(log), "--db", str(db), "--json"]), 0)
            self.assertEqual(json.loads(out.getvalue())["tests"], ["T2"])


class PackAndSweepTests(unittest.TestCase):
    def test_a_pack_is_one_load_set_and_unknown_ids_are_listed_not_guessed(self) -> None:
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            pack = root / "enabled_mods.json"
            write(pack, json.dumps({"enabledMods": ["DNEEP", "aotd_vok", "not_indexed", "aotd_vok"]}))
            conn = atlas.connect(db)
            mods, missing = read_pack(conn, pack)
            self.assertEqual(sorted(m["id"] for m in mods), ["aotd_vok", "dneep"])
            self.assertEqual(missing, ["not_indexed"])
            result = forecast(conn, mods)
            self.assertTrue([f for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"])

    def test_the_forecast_command_takes_a_pack_and_refuses_a_bad_file(self) -> None:
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            pack = root / "enabled_mods.json"
            write(pack, json.dumps(["dneep", "aotd_vok", "ghost"]))
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["atlas", "forecast", "--pack", str(pack), "--db", str(db), "--json"]), 0)
            data = json.loads(out.getvalue())
            self.assertEqual(data["pack_missing"], ["ghost"])
            self.assertIn("ghost", err.getvalue())
            write(pack, '{"enabledMods": "oops"}')
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["atlas", "forecast", "--pack", str(pack), "--db", str(db)]), 2)
                self.assertEqual(main(["atlas", "forecast", "--db", str(db)]), 2)

    def test_top_pairs_rank_crash_class_manual_first_and_skip_fixed_history(self) -> None:
        from bridgeforge.atlas_report import top_pairs

        def finding(rule, level, category, mods, summary="s"):
            return {"rule": rule, "level": level, "category": category, "mods": mods, "summary": summary}

        found = [finding("ATLAS-READS-REPLACED", "REVIEW", "silent-behaviour", ["a", "b"]),
                 finding("ATLAS-READS-REPLACED", "REVIEW", "silent-behaviour", ["b", "a"]),
                 finding("ATLAS-SHADOW-CLASS", "MANUAL", "crash-class", ["c", "d"], "class shadowed"),
                 finding("ATLAS-RUNTIME-SUPPLY", "SAFE", "silent-behaviour", ["e"]),
                 finding("ATLAS-SAVE-HOLDS-HEAVY", "REVIEW", "crash-class", ["f"])]
        ranked = top_pairs(found, 10)
        self.assertEqual([p["mods"] for p in ranked], [["c", "d"], ["f"], ["a", "b"]])
        self.assertEqual(ranked[2]["count"], 2)  # the pair is the same whichever mod is named first
        self.assertEqual(ranked[0]["example"], "class shadowed")
        self.assertEqual(len(top_pairs(found, 1)), 1)

    def test_the_sweep_flags_only_the_mod_that_reads_what_the_family_replaces_and_resumes(self) -> None:
        with temp_root() as root:
            _world(root)
            db, _ = build(root)
            conn = atlas.connect(db)
            checkpoint = root / "out" / "sweep.partial.jsonl"
            with redirect_stderr(io.StringIO()) as err:
                data = sweep(conn, "aotd", checkpoint, quiet=False)
            self.assertFalse(checkpoint.exists())
            self.assertEqual({r["mod"]: bool(r["findings"]) for r in data["rows"]}, {"calm": False, "dneep": True})
            self.assertIn("[1/2]", err.getvalue())
            self.assertIn("dneep", sweep_text(data))
            self.assertEqual(data["family"], ["aotd_vok"])

    def test_the_sweep_needs_a_family_and_is_listed_as_long_running(self) -> None:
        from bridgeforge.progress import LONG_RUNNING_COMMANDS

        self.assertIn(("atlas", "sweep"), LONG_RUNNING_COMMANDS)
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "calm", {})
            db, _ = build(root)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["atlas", "sweep", "aotd", "--db", str(db), "--quiet"]), 2)


if __name__ == "__main__":
    unittest.main()
