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


def _class_file(name: str, methods: dict[str, str]) -> bytes:
    """A minimal class file: `name` extends Object, with public methods {method name: descriptor}."""
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
    entries = [(utf8(method), utf8(descriptor)) for method, descriptor in methods.items()]
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
    agent.parent.mkdir(parents=True)
    detector = b"\xca\xfe\xba\xbe " + b" ".join(name.encode() for name in named) + (b" getCombatMap" if tie_break else b"")
    with zipfile.ZipFile(agent, "w") as jar:
        jar.writestr(pn.DETECTOR, detector)
        for table_id, rows in tables.items():
            text = "# canonical -> native\n" + "".join(f"C\t{c}\t{n}\n" for c, n in rows.items()) + "M\tx\ty\t()V\tz\n"
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

    def test_rig_doctor_runs_the_check_and_a_fail_fails_the_rig(self) -> None:
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
        self.assertEqual(report["status"], "FAIL")

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


if __name__ == "__main__":
    unittest.main()
