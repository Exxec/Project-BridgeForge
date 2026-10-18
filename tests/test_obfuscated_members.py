"""obfuscated-internal-api-use / obfuscated-internal-api-resolved (item 73 F6): obfuscated members checked against RC8's core jars."""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir
from tests.test_jar_linkage import _compile, _jar

ENG_OLD = {"com/fs/starfarer/combat/Eng.java": "package com.fs.starfarer.combat; public class Eng { public void run() {} public int gone() { return 1; } }"}
ENG_FULL = ENG_OLD
ENG_NEW = {"com/fs/starfarer/combat/Eng.java": "package com.fs.starfarer.combat; public class Eng { public void run() {} }"}
MOD_CALLS_GONE = {"data/Hook.java": "package data; import com.fs.starfarer.combat.Eng;\npublic class Hook { void go(Eng e) { e.run(); e.gone(); } }"}
MOD_CALLS_RUN = {"data/Hook.java": "package data; import com.fs.starfarer.combat.Eng;\npublic class Hook { void go(Eng e) { e.run(); } }"}


class ObfuscatedMemberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

    def _scan(self, rc8_sources: dict[str, str] | None, mod_sources: dict[str, str]):
        with resolved_temp_dir() as base:
            root = Path(base)
            old = _compile(self.javac, root / "old", ENG_OLD)
            if rc8_sources is not None:
                _jar(_compile(self.javac, root / "new", rc8_sources), root / "starsector-core" / "starfarer_obf.jar")
            else:
                (root / "starsector-core").mkdir()
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", mod_sources, classpath=old), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            findings = scan_mod(mod, vanilla_core=root / "starsector-core").findings
        return ([f for f in findings if f.id == "obfuscated-internal-api-use"], [f for f in findings if f.id == "obfuscated-internal-api-resolved"])

    def test_member_that_exists_in_rc8_is_informational(self) -> None:
        use, resolved = self._scan(ENG_FULL, MOD_CALLS_GONE)
        self.assertEqual(use, [])
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].severity, "info")
        self.assertTrue(any(e.startswith("resolved:") for e in resolved[0].evidence))

    def test_member_rc8_lacks_keeps_the_finding_and_names_it(self) -> None:
        use, resolved = self._scan(ENG_NEW, MOD_CALLS_GONE)
        self.assertEqual(resolved, [])
        self.assertEqual(len(use), 1)
        self.assertTrue(any(e.startswith("missing:method com.fs.starfarer.combat.Eng.gone") for e in use[0].evidence))

    def test_only_existing_members_used_resolves_even_if_rc8_dropped_others(self) -> None:
        use, resolved = self._scan(ENG_NEW, MOD_CALLS_RUN)
        self.assertEqual(use, [])
        self.assertEqual(len(resolved), 1)

    def test_class_absent_from_rc8_keeps_the_finding(self) -> None:
        use, _ = self._scan({"com/fs/starfarer/combat/Other.java": "package com.fs.starfarer.combat; public class Other {}"}, MOD_CALLS_RUN)
        self.assertEqual(len(use), 1)
        self.assertTrue(any(e.startswith("missing:class com.fs.starfarer.combat.Eng") for e in use[0].evidence))

    def test_without_core_jars_nothing_is_resolved(self) -> None:
        use, resolved = self._scan(None, MOD_CALLS_RUN)
        self.assertEqual(resolved, [])
        self.assertEqual(len(use), 1)


if __name__ == "__main__":
    unittest.main()
