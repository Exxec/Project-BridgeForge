"""ROADMAP-3 98.17: rig-doctor says which name table StarsectorPrepatcher's agent will load, and fails when that table does not
describe the rig's core. On Windows RC9 the stock 0.18.9 agent loaded the Linux RC8 table and the game died at start-up
(RC9NC-LIVE4, 2026-11-26). Acceptance against the real jars: stock on RC9 picks linux-0.98.5a-RC8 with 1304 of 2962 classes
missing; the rig jar picks windows-0.98.5a-RC9 with none missing; RC3 matches no table."""
from __future__ import annotations

import struct
import unittest
import zipfile
from pathlib import Path

import tests.support  # noqa: F401  (registry guard and environment)
from bridgeforge.rig import prepatcher_namespace as pn
from tests.support import resolved_temp_dir

CANONICAL_RESULT, CANONICAL_MAP = pn.CANONICAL_RESULT, pn.CANONICAL_COMBAT_MAP


def _class_file(name: str, methods: dict[str, str] | list[tuple[str, str]], strings: tuple[str, ...] = (),
                names: tuple[str, ...] = ()) -> bytes:
    """A minimal class file: `name` extends Object, with public methods (name, descriptor), string constants `strings` and
    bare UTF8 entries `names` (a method name the class refers to, such as getCombatMap)."""
    pool: list[bytes] = []

    def utf8(text: str) -> int:
        raw = text.encode("utf-8")
        pool.append(b"\x01" + struct.pack(">H", len(raw)) + raw)
        return len(pool)

    def klass(text: str) -> int:
        index = utf8(text)
        pool.append(b"\x07" + struct.pack(">H", index))
        return len(pool)

    this, sup = klass(name), klass("java/lang/Object")
    for text in strings:
        index = utf8(text)
        pool.append(b"\x08" + struct.pack(">H", index))
    for text in names:
        utf8(text)
    pairs = methods.items() if isinstance(methods, dict) else methods
    entries = [(utf8(method), utf8(descriptor)) for method, descriptor in pairs]
    body = struct.pack(">HHHHH", 0x0021, this, sup, 0, 0) + struct.pack(">H", len(entries))
    body += b"".join(struct.pack(">HHHH", 0x0001, n, d, 0) for n, d in entries) + struct.pack(">H", 0)
    return b"\xca\xfe\xba\xbe\x00\x00\x00\x34" + struct.pack(">H", len(pool) + 1) + b"".join(pool) + body


def _core(folder: Path, results: str, combat_map: str, classes: list[str]) -> Path:
    core = folder / "starsector-core"
    core.mkdir(parents=True)
    with zipfile.ZipFile(core / "starfarer_obf.jar", "w") as jar:
        jar.writestr(pn.ENGINE, _class_file("com/fs/starfarer/combat/CombatEngine",
                                           {"getResults": f"()L{results};", "getCombatMap": f"()L{combat_map};"}))
        for name in classes:
            jar.writestr(f"{name}.class", b"\xca\xfe\xba\xbe")
    return core


def _agent(folder: Path, tables: dict[str, dict[str, str]], named: list[str], tie_break: bool) -> Path:
    agent = folder / pn.AGENT_RELATIVE
    agent.parent.mkdir(parents=True, exist_ok=True)
    # The detector's TABLES list is string constants, beside the canonical id (both real jars, 2026-11-27).
    detector = _class_file("com/starsector/prepatcher/namespace/GameNamespaceDetector", {}, strings=(pn.IDENTITY, *named, "unrelated"),
                           names=("getCombatMap",) if tie_break else ())
    with zipfile.ZipFile(agent, "w") as jar:
        jar.writestr(pn.DETECTOR, detector)
        for table_id, rows in tables.items():
            text = rows if isinstance(rows, str) else (
                "# canonical -> native\n" + "".join(f"C\t{c}\t{n}\n" for c, n in rows.items()) + "M\tx\ty\t()V\tz\n")
            jar.writestr(f"{pn.TABLE_PREFIX}{table_id}.tsv", text)
    return agent


# Two builds whose getResults() types collide (Linux RC8 and Windows RC9 both name it combat/B/D) but whose getCombatMap differ.
LINUX = {CANONICAL_RESULT: "combat/B/D", CANONICAL_MAP: "combat/A/linux", "a/Engine": "q/Linux"}
RC9 = {CANONICAL_RESULT: "combat/B/D", CANONICAL_MAP: "combat/A/super", "a/Engine": "q/Rc9"}
RC9_CLASSES = ["combat/B/D", "combat/A/super", "q/Rc9"]


class PrepatcherNamespaceTests(unittest.TestCase):
    def _check(self, tables: dict, named: list[str], tie_break: bool, results: str, combat_map: str, classes: list[str]) -> dict:
        with resolved_temp_dir() as rig:
            _core(rig, results, combat_map, classes)
            _agent(rig, tables, named, tie_break)
            return pn.check(rig)

    def test_the_stock_agent_on_rc9_loads_a_table_that_does_not_fit_and_fails(self) -> None:
        found = self._check({"linux-0.98.5a-RC8": LINUX}, ["linux-0.98.5a-RC8"], False, "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "FAIL")
        self.assertIn("linux-0.98.5a-RC8", found["detail"])
        self.assertIn("2 of its 3 classes", found["detail"])

    def test_the_rig_jar_breaks_the_tie_and_its_table_fits(self) -> None:
        tables = {"linux-0.98.5a-RC8": LINUX, "windows-0.98.5a-RC9": RC9}
        found = self._check(tables, list(tables), True, "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "PASS")
        self.assertIn("windows-0.98.5a-RC9", found["detail"])
        self.assertIn("all 3 classes", found["detail"])

    def test_two_matches_without_a_tie_break_fail_open(self) -> None:
        tables = {"linux-0.98.5a-RC8": LINUX, "windows-0.98.5a-RC9": RC9}
        found = self._check(tables, list(tables), False, "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "WARN")
        self.assertIn("2 tables", found["detail"])

    def test_no_matching_table_fails_open(self) -> None:
        found = self._check({"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True, "combat/X/Y", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "WARN")
        self.assertIn("no table", found["detail"])

    def test_the_canonical_build_needs_no_table(self) -> None:
        found = self._check({"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True, CANONICAL_RESULT, CANONICAL_MAP, [])
        self.assertEqual(found["status"], "PASS")
        self.assertIn("canonical", found["detail"])

    def test_a_table_the_detector_does_not_name_is_not_loaded(self) -> None:
        # The jar ships the RC9 table, but the stock detector's TABLES list does not name it.
        tables = {"linux-0.98.5a-RC8": LINUX, "windows-0.98.5a-RC9": RC9}
        found = self._check(tables, ["linux-0.98.5a-RC8"], False, "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "FAIL")

    def test_a_rig_without_the_agent_is_skipped(self) -> None:
        with resolved_temp_dir() as rig:
            self.assertEqual(pn.check(rig)["status"], "SKIPPED")

    # Where the real detector throws, the replay must not PASS (review, 2026-11-27: with linux-0.98a-RC8.tsv removed from the
    # rig jar, the real detector said "Missing namespace table" and rig-doctor said PASS).
    def test_a_listed_table_the_jar_lacks_fails_open(self) -> None:
        found = self._check({"windows-0.98.5a-RC9": RC9}, ["linux-0.98a-RC8", "windows-0.98.5a-RC9"], True, "combat/B/D", "combat/A/super",
                            RC9_CLASSES)
        self.assertEqual(found["status"], "WARN")
        self.assertIn("linux-0.98a-RC8 that the agent jar lacks", found["detail"])

    def test_a_listed_table_without_a_get_results_row_fails_open(self) -> None:
        bare = {k: v for k, v in LINUX.items() if k != CANONICAL_RESULT}
        found = self._check({"linux-0.98.5a-RC8": bare, "windows-0.98.5a-RC9": RC9}, ["linux-0.98.5a-RC8", "windows-0.98.5a-RC9"], True,
                            "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "WARN")
        self.assertIn(f"linux-0.98.5a-RC8 have no row for {CANONICAL_RESULT}", found["detail"])

    def test_a_tied_table_without_a_combat_map_row_fails_open(self) -> None:
        bare = {k: v for k, v in LINUX.items() if k != CANONICAL_MAP}
        found = self._check({"linux-0.98.5a-RC8": bare, "windows-0.98.5a-RC9": RC9}, ["linux-0.98.5a-RC8", "windows-0.98.5a-RC9"], True,
                            "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "WARN")
        self.assertIn(f"have no row for {CANONICAL_MAP}", found["detail"])

    def test_two_get_results_methods_fail_open(self) -> None:
        with resolved_temp_dir() as rig:
            core = rig / "starsector-core"
            core.mkdir()
            with zipfile.ZipFile(core / "starfarer_obf.jar", "w") as jar:
                jar.writestr(pn.ENGINE, _class_file("com/fs/starfarer/combat/CombatEngine",
                                                   [("getResults", "()Lcombat/B/D;"), ("getResults", "()Lcombat/X/Y;")]))
            _agent(rig, {"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True)
            found = pn.check(rig)
        self.assertEqual(found["status"], "WARN")
        self.assertIn("more than one no-argument getResults", found["detail"])

    def test_an_agent_without_a_detector_or_a_core_without_combat_engine_is_a_warning(self) -> None:
        # Both raised KeyError out of rig-doctor (review, 2026-11-27).
        with resolved_temp_dir() as rig:
            _core(rig, "combat/B/D", "combat/A/super", RC9_CLASSES)
            agent = rig / pn.AGENT_RELATIVE
            agent.parent.mkdir(parents=True)
            with zipfile.ZipFile(agent, "w") as jar:
                jar.writestr(f"{pn.TABLE_PREFIX}windows-0.98.5a-RC9.tsv", "C\ta\tb\n")
            no_detector = pn.check(rig)
        with resolved_temp_dir() as rig:
            (rig / "starsector-core").mkdir()
            with zipfile.ZipFile(rig / "starsector-core" / "starfarer_obf.jar", "w") as jar:
                jar.writestr("other/Thing.class", b"\xca\xfe\xba\xbe")
            _agent(rig, {"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True)
            no_engine = pn.check(rig)
        self.assertEqual((no_detector["status"], no_engine["status"]), ("WARN", "WARN"))
        self.assertIn(f"the agent jar has no {pn.DETECTOR}", no_detector["detail"])
        self.assertIn("no table", no_engine["detail"])

    def test_the_first_of_two_rows_wins_as_in_the_agent(self) -> None:
        text = (f"C\t{CANONICAL_RESULT}\tcombat/B/D\nC\t{CANONICAL_RESULT}\tcombat/X/Y\nC\t{CANONICAL_MAP}\tcombat/A/super\n"
                "C\ta/Engine\tq/Rc9\n")
        found = self._check({"windows-0.98.5a-RC9": text}, ["windows-0.98.5a-RC9"], True, "combat/B/D", "combat/A/super", RC9_CLASSES)
        self.assertEqual(found["status"], "PASS")

    def test_rig_doctor_runs_the_check(self) -> None:
        from unittest import mock

        from bridgeforge.rig import rig_doctor

        with resolved_temp_dir() as rig, \
                mock.patch.object(rig_doctor, "_check_launcher_prefs", return_value=rig_doctor._check("launcher_prefs", "PASS", "-")), \
                mock.patch.object(rig_doctor, "_long_paths_enabled", return_value=True):
            _core(rig, "combat/B/D", "combat/A/super", RC9_CLASSES)
            _agent(rig, {"linux-0.98.5a-RC8": LINUX}, ["linux-0.98.5a-RC8"], False)
            report = rig_doctor.rig_doctor(rig)
        found = [c for c in report["checks"] if c["name"] == "prepatcher_namespace"]
        self.assertEqual([c["status"] for c in found], ["FAIL"])
        # (No assertion on the overall status: the fixture's isolation check fails it whatever this check says. Review, 2026-11-27.)

    def test_the_run_manifest_records_the_agent_jar(self) -> None:
        import hashlib

        from bridgeforge.run_manifest import runtime_hashes

        with resolved_temp_dir() as rig:
            agent = _agent(rig, {"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True)
            with_agent = runtime_hashes(rig, None)["prepatcher_agent_sha256"]
            agent.unlink()
            without = runtime_hashes(rig, None)["prepatcher_agent_sha256"]
        self.assertEqual(len(with_agent), 64)
        self.assertNotEqual(with_agent, hashlib.sha256(b"").hexdigest())
        self.assertIsNone(without)

    def test_a_run_launched_before_the_agent_key_is_not_drift(self) -> None:
        # Review, 2026-11-27: a manifest written before 98.17 has no prepatcher_agent_sha256, and staged_drift read that as
        # "changed since launch", so record --accept refused every such run.
        import json

        from bridgeforge.run_manifest import runtime_hashes, staged_drift

        with resolved_temp_dir() as rig:
            (rig / "mods").mkdir()
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": []}), encoding="utf-8")
            agent = _agent(rig, {"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True)
            now = runtime_hashes(rig, None)
            older = {k: v for k, v in now.items() if k != "prepatcher_agent_sha256"}
            self.assertEqual(staged_drift(rig, {"enabled": [], "runtime": older}, None), [])
            agent.unlink()  # a current manifest records None: a jar added after launch is still drift
            launched = runtime_hashes(rig, None)
            _agent(rig, {"windows-0.98.5a-RC9": RC9}, ["windows-0.98.5a-RC9"], True)
            drift = staged_drift(rig, {"enabled": [], "runtime": launched}, None)
        self.assertEqual(drift, ["runtime configuration prepatcher_agent_sha256 changed since launch"])


if __name__ == "__main__":
    unittest.main()
