"""94.G1 GR-2: the gene census counts feature kinds and how many features each plugin hook sets up together."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.atlas.atlas_classfile import parse_class
from bridgeforge.cli import main
from bridgeforge.genome.census import census_mod, features, mod_roots, run_census
from tests.support import resolved_temp_dir, write_text as _write

PLUGIN = """package demo;
public class Plugin {
    public void onNewGame() { setUp(); }
    public void onApplicationLoad() { }
    private void setUp() {
        new demo.Gen().generate();
        Faction f = new Faction();
        f.setRelationship("pirates");
        Sector.addScript(new Object());
    }
}
"""
GEN = "package demo;\npublic class Gen { public void generate() { } }\n"
API = {
    "Faction.java": "package com.fs.api;\npublic class Faction { public void setRelationship(String s) { } }\n",
    "Sector.java": "package com.fs.api;\npublic class Sector { public static void addScript(Object o) { } }\n",
}


def _javac() -> str | None:
    return shutil.which("javac")


def _mod(root: Path, with_plugin: bool = True) -> Path:
    """A mod whose jar holds demo.Plugin (onNewGame -> setUp: one mod class, one API mutation, one addScript) and demo.Gen."""
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demo", "name": "Demo", "version": "1.0", "jars": ["jars/demo.jar"],
                                              **({"modPlugin": "demo.Plugin"} if with_plugin else {})}))
    _write(mod / "data" / "hullmods" / "hull_mods.csv", "name,id\nA,a_mod\nB,b_mod\n")
    _write(mod / "data" / "campaign" / "rules.csv", "id,trigger\nr1,OpenInteractionDialog\n")
    src = root / "src"
    for name, text in API.items():
        _write(src / "com" / "fs" / "api" / name, text)
    _write(src / "demo" / "Plugin.java", PLUGIN.replace("Faction f", "com.fs.api.Faction f").replace("new Faction()", "new com.fs.api.Faction()")
           .replace("Sector.addScript", "com.fs.api.Sector.addScript"))
    _write(src / "demo" / "Gen.java", GEN)
    out = root / "classes"
    files = [str(p) for p in src.rglob("*.java")]
    subprocess.run([_javac(), "-encoding", "UTF-8", "-proc:none", "-d", str(out), *files], check=True, capture_output=True)
    (mod / "jars").mkdir(parents=True)
    shutil.make_archive(str(mod / "jars" / "demo"), "zip", out / "demo" / "..", "demo")
    (mod / "jars" / "demo.zip").rename(mod / "jars" / "demo.jar")
    return mod


@unittest.skipUnless(_javac(), "needs javac")
class CensusModTests(unittest.TestCase):
    def test_a_hook_is_followed_into_the_plugins_own_methods_and_counted(self) -> None:
        with resolved_temp_dir() as root:
            row = census_mod(_mod(root))
        self.assertEqual(row["kinds"], {"hullmod": 2, "rule": 1})
        hooks = row["plugin"]["hooks"]
        self.assertEqual(set(hooks), {"onNewGame", "onApplicationLoad"})
        new_game = hooks["onNewGame"]
        self.assertEqual(new_game["depth"], 1)
        self.assertEqual(new_game["mod_classes"], ["demo/Gen"])
        self.assertEqual(new_game["api_mutations"], ["com/fs/api/Faction.setRelationship"])
        self.assertEqual(new_game["registration_calls"], 1)
        self.assertEqual(features(new_game), 3)
        self.assertEqual(features(hooks["onApplicationLoad"]), 0)

    def test_no_plugin_and_a_loose_script_plugin_are_named_not_measured(self) -> None:
        with resolved_temp_dir() as root:
            mod = _mod(root, with_plugin=False)
            self.assertEqual(census_mod(mod)["plugin"], {"status": "none"})
            info = json.loads((mod / "mod_info.json").read_text(encoding="utf-8"))
            _write(mod / "mod_info.json", json.dumps({**info, "modPlugin": "loose.Plugin"}))
            _write(mod / "loose" / "Plugin.java", "package loose; public class Plugin { }\n")
            self.assertEqual(census_mod(mod)["plugin"]["status"], "source-only")


class CorpusTests(unittest.TestCase):
    def _corpus(self, root: Path) -> Path:
        done = root / "Done"
        for folder, version, layout in (("Mod-A", "1.0", "workspace/working"), ("Mod A raw", "1.0", ""),
                                        ("Mod-B", "2.0", "Mod B 2.0"), ("_replaced-2026-11-19", "0.1", "")):
            base = done / folder / layout if layout else done / folder
            mod_id = "mod_a" if folder.startswith("Mod A") or folder == "Mod-A" else "mod_b" if folder == "Mod-B" else "old"
            _write(base / "mod_info.json", json.dumps({"id": mod_id, "version": version}))
        return done

    def test_each_mod_once_archive_preferred_and_underscore_folders_skipped(self) -> None:
        with resolved_temp_dir() as root:
            done = self._corpus(root)
            self.assertEqual([(f, s) for f, _, s in mod_roots(done)], [("Mod A raw", "raw"), ("Mod-A", "archive"), ("Mod-B", "raw")])
            out = root / "out" / "census.json"
            with redirect_stderr(io.StringIO()) as err:
                result = run_census(done, out)
            self.assertEqual([(row["id"], row["source"]) for row in result["mods"]], [("mod_a", "archive"), ("mod_b", "raw")])
            self.assertEqual(result["duplicates_skipped"], ["Mod A raw"])
            self.assertIn("[1/2] Mod-A:", err.getvalue())
            self.assertTrue(out.is_file())
            self.assertFalse(out.with_name("census.json.partial.jsonl").exists())
            self.assertEqual(result["summary"]["plugins"], {"none": 2})

    def test_an_interrupted_run_resumes_from_its_checkpoint(self) -> None:
        from unittest import mock

        from bridgeforge.genome import census
        with resolved_temp_dir() as root:
            done = self._corpus(root)
            out = root / "out" / "census.json"
            real, calls = census.census_mod, []

            def failing(path):
                calls.append(path)
                if len(calls) == 2:
                    raise KeyboardInterrupt
                return real(path)

            with mock.patch.object(census, "census_mod", failing), redirect_stderr(io.StringIO()), self.assertRaises(KeyboardInterrupt):
                run_census(done, out)
            self.assertTrue(out.with_name("census.json.partial.jsonl").exists())
            with mock.patch.object(census, "census_mod", side_effect=real) as again, redirect_stderr(io.StringIO()) as err:
                run_census(done, out)
            self.assertEqual(again.call_count, 1)  # Mod-A came from the checkpoint
            self.assertIn("(from checkpoint)", err.getvalue())

    def test_the_cli_prints_the_summary_and_writes_the_rows(self) -> None:
        with resolved_temp_dir() as root:
            done = self._corpus(root)
            out = root / "out" / "census.json"
            with redirect_stdout(io.StringIO()) as printed, redirect_stderr(io.StringIO()):
                self.assertEqual(main(["gene", "census", str(done), "--write", str(out), "--quiet"]), 0)
            self.assertIn("Gene census: 2 mod(s)", printed.getvalue())
            self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["mods"]), 2)


class ClassfileTargetsTests(unittest.TestCase):
    def test_method_targets_parallel_method_calls(self) -> None:
        if not _javac():
            self.skipTest("needs javac")
        with resolved_temp_dir() as root:
            _write(root / "A.java", "public class A { void f() { g(); } void g() { } }\n")
            subprocess.run([_javac(), "-encoding", "UTF-8", "-proc:none", "-d", str(root), str(root / "A.java")], check=True, capture_output=True)
            info = parse_class((root / "A.class").read_bytes())
        self.assertEqual(len(info.method_targets), len(info.method_calls))
        self.assertIn(("A", "g"), info.method_targets[info.code_methods.index("f")])


if __name__ == "__main__":
    unittest.main()
