"""96.5 P5/P8: a scan parses each JSON file and jar class once, and the AST facts resolve each source file once."""
from __future__ import annotations

import base64
import collections
import pathlib
import subprocess
import unittest
import zipfile
from unittest import mock

from bridgeforge import analysis_reuse
from bridgeforge.analysis_reuse import no_reuse, reuse_parses, reuse_within
from bridgeforge.bytecode import java_ast
from bridgeforge.scan import scan_classfile, scan_json
from bridgeforge.scan.scanner import scan_mod
from tests.support import javac_path, resolved_temp_dir
from tests.support import write_text as _write


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class AstFactsTests(unittest.TestCase):
    def setUp(self) -> None:
        java_ast.clear_memo()  # these tests fake the helper's output: start clean and leave nothing behind
        self.addCleanup(java_ast.clear_memo)

    def test_the_same_sources_run_the_helper_once_and_each_caller_gets_a_copy(self) -> None:
        """96.5 P9: the suite ran the JVM helper 460 times on 329 distinct inputs; a repeat is answered from memory."""
        with resolved_temp_dir() as root:
            source = root / "data" / "scripts" / "A.java"
            _write(source, "class A {}")
            line = f"M\t{_b64(str(source))}\t1\t0\t{_b64('call')}"
            done = subprocess.CompletedProcess([], 0, stdout=line, stderr="")
            with mock.patch.object(java_ast, "_ensure_helper", return_value=root / "helper"), \
                    mock.patch.object(java_ast, "_java_tools", return_value=("javac", "java")), \
                    mock.patch.object(java_ast, "_run", return_value=done) as run:
                first = java_ast.analyze_sources(root)
                first[0]["value"] = "changed by a caller"
                second = java_ast.analyze_sources(root)
                self.assertEqual(run.call_count, 1)
                self.assertEqual(second[0]["value"], "call")  # the caller's change did not reach the memo
                _write(source, "class A { int x; }")  # new bytes: run again
                java_ast.analyze_sources(root)
                self.assertEqual(run.call_count, 2)

    def test_each_source_file_is_resolved_once_however_many_facts_name_it(self) -> None:
        with resolved_temp_dir() as root:
            sources = [root / "data" / "scripts" / f"{name}.java" for name in ("A", "B")]
            for source in sources:
                _write(source, "class X {}")
            lines = [f"M\t{_b64(str(source))}\t{n}\t0\t{_b64(f'call{n}')}" for source in sources for n in range(1, 51)]
            done = subprocess.CompletedProcess([], 0, stdout="\n".join(lines), stderr="")
            original = pathlib.Path.resolve
            resolved = collections.Counter()

            def counting(self, *args, **kwargs):
                resolved[self.name] += 1
                return original(self, *args, **kwargs)

            with mock.patch.object(java_ast, "_ensure_helper", return_value=root / "helper"), \
                    mock.patch.object(java_ast, "_java_tools", return_value=("javac", "java")), \
                    mock.patch.object(java_ast, "_run", return_value=done), \
                    mock.patch.object(pathlib.Path, "resolve", counting):
                facts = java_ast.analyze_sources(root)
        self.assertEqual(len(facts), 100)
        self.assertEqual({f["file"] for f in facts}, {"data/scripts/A.java", "data/scripts/B.java"})
        self.assertEqual([f["value"] for f in facts[:2]], ["call1", "call2"])
        self.assertEqual((resolved["A.java"], resolved["B.java"]), (1, 1))  # was 50 each


class ScanReuseTests(unittest.TestCase):
    def test_reuse_within_keeps_an_enclosing_scope_and_opens_one_otherwise(self) -> None:
        with reuse_parses(max_entries=4, max_payload_bytes=4096) as outer:
            with reuse_within(max_entries=99, max_payload_bytes=99) as inner:
                self.assertIs(inner, outer)
        self.assertIsNone(analysis_reuse._active.get())
        with reuse_within(max_entries=7, max_payload_bytes=4096) as own:
            self.assertEqual(own.max_entries, 7)
            self.assertIs(analysis_reuse._active.get(), own)
        self.assertIsNone(analysis_reuse._active.get())

    def test_a_scan_parses_each_json_file_once(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id": "m", "name": "M", "version": "1.0", "gameVersion": "0.98a-RC8", # comment\n}')
            _write(mod / "data" / "config" / "settings.json", '{"a": 1,}')
            _write(mod / "data" / "world" / "factions" / "m_faction.faction", '{"id": "m_faction", "displayName": "M",}')
            _write(mod / "data" / "world" / "factions" / "factions.csv", "faction\ndata/world/factions/m_faction.faction\n")
            parsed = collections.Counter()
            original = scan_json._parse_json_uncached

            def counting(text, object_pairs_hook=None):
                if object_pairs_hook is None:
                    parsed[text] += 1
                return original(text, object_pairs_hook)

            with mock.patch.object(scan_json, "_parse_json_uncached", counting):
                scan_mod(mod)
        self.assertTrue(parsed, "the scan parsed no JSON")
        self.assertEqual({text[:30]: n for text, n in parsed.items() if n > 1}, {})
        self.assertIsNone(analysis_reuse._active.get())  # the scan's scope is closed afterwards

    def test_a_scan_parses_each_jar_class_once(self) -> None:
        javac = javac_path()
        if javac is None:
            self.skipTest("no javac")
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id": "m", "name": "M", "version": "1.0", "gameVersion": "0.98a-RC8", "jars": ["jars/m.jar"]}')
            _write(root / "src" / "m" / "Plugin.java", "package m; public class Plugin { public String hi() { return \"x\"; } }")
            subprocess.run([javac, "-encoding", "UTF-8", "-proc:none", "-d", str(root / "classes"), str(root / "src" / "m" / "Plugin.java")], check=True,
                           capture_output=True)
            (mod / "jars").mkdir()
            with zipfile.ZipFile(mod / "jars" / "m.jar", "w") as jar:
                jar.write(root / "classes" / "m" / "Plugin.class", "m/Plugin.class")
            parsed = collections.Counter()
            original = scan_classfile._parse_class_file_uncached

            def counting(data):
                parsed[data] += 1
                return original(data)

            with mock.patch.object(scan_classfile, "_parse_class_file_uncached", counting):
                scan_mod(mod)
        self.assertEqual(list(parsed.values()), [1])  # the one class, parsed once however many checks read it

    def test_scan_mod_joins_an_enclosing_scope_and_no_reuse_turns_it_off(self) -> None:
        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "mod_info.json", '{"id": "m", "name": "M", "version": "1.0", "gameVersion": "0.98a-RC8",}')
            with reuse_parses(max_entries=1000, max_payload_bytes=1 << 22) as outer:
                scan_mod(mod)
            self.assertGreater(outer.hits + outer.misses, 0)  # the scan used the caller's scope, not a fresh one
            parsed = collections.Counter()
            original = scan_json._parse_json_uncached

            def counting(text, object_pairs_hook=None):
                parsed[text] += 1
                return original(text, object_pairs_hook)

            with no_reuse(), mock.patch.object(scan_json, "_parse_json_uncached", counting):
                scan_mod(mod)
        self.assertGreater(max(parsed.values()), 1)  # with reuse off, checks parse mod_info.json again as before


if __name__ == "__main__":
    unittest.main()
