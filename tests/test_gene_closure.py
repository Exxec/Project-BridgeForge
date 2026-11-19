"""94.G2: the closure rules `gene describe` adds (genome/closure.py): settings keys a member reads, vanilla commodities."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.genome.closure import keys_read_by_class, keys_read_by_source, pointer, value_sha256
from bridgeforge.genome.gene import describe, validate
from tests.support import resolved_temp_dir, write_text as _write

SCRIPT = """package data.hullmods;
import com.fs.starfarer.api.Global;
import com.fs.starfarer.api.impl.campaign.ids.Commodities;
public class tank_mod {
    private static final String RATE_KEY = "tank_mod_rate";
    float a = Global.getSettings().getFloat(RATE_KEY);
    boolean b = Global.getSettings().getBoolean("tank_mod_sfx");
    float c = Global.getSettings().getFloat("vanilla_only_key");
    float d = Global.getSettings().getFloat("nowhere_key");
    String e = Commodities.LOBSTER;
    String g = Commodities.RETIRED;
    String h = Commodities.UNHEARD_OF;
}
"""


def _mod(root: Path) -> Path:
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "tankmod", "name": "Tank Mod", "version": "1.0"}))
    _write(mod / "data" / "hullmods" / "hull_mods.csv", "name,id,script\nTanks,tank_mod,data.hullmods.tank_mod\n")
    _write(mod / "data" / "hullmods" / "tank_mod.java", SCRIPT)
    _write(mod / "data" / "config" / "settings.json",
           "{\n  # lenient: a comment and a trailing comma\n  \"tank_mod_rate\": 5.0,\n  \"tank_mod_sfx\": true,\n"
           "  \"tank_mod_unused\": 1,\n  \"other_mod_key\": 2,\n}\n")
    return mod


def _core(root: Path, with_commodities: bool) -> Path:
    core = root / "core"
    _write(core / "data" / "config" / "settings.json", json.dumps({"vanilla_only_key": 3}))
    _write(core / "data" / "campaign" / "commodities.csv", "name,id\nLobster,lobster\nFood,food\n")
    _write(core / "data" / "hullmods" / "hull_mods.csv", "name,id\n")
    if with_commodities:
        src = root / "core-src" / "com" / "fs" / "starfarer" / "api" / "impl" / "campaign" / "ids" / "Commodities.java"
        _write(src, "package com.fs.starfarer.api.impl.campaign.ids;\npublic class Commodities {\n"
                    "  public static final String LOBSTER = \"lobster\";\n  public static final String FOOD = \"food\";\n"
                    "  public static final String RETIRED = \"retired_good\";\n}\n")
        out = root / "core-classes"
        subprocess.run([shutil.which("javac"), "-encoding", "UTF-8", "-proc:none", "-d", str(out), str(src)], check=True, capture_output=True)
        with zipfile.ZipFile(core / "starfarer.api.jar", "w") as jar:
            jar.write(out / "com/fs/starfarer/api/impl/campaign/ids/Commodities.class", "com/fs/starfarer/api/impl/campaign/ids/Commodities.class")
    return core


class RuleTests(unittest.TestCase):
    def test_keys_read_by_source_take_literals_and_constants_not_mentions(self) -> None:
        text = SCRIPT + '\n// tank_mod_unused is only mentioned here\nString f = "tank_mod_unused";\n'
        self.assertEqual(keys_read_by_source(text), {"tank_mod_rate", "tank_mod_sfx", "vanilla_only_key", "nowhere_key"})

    def test_a_value_hash_ignores_layout_and_integral_floats(self) -> None:
        self.assertEqual(value_sha256(5), value_sha256(5.0))
        self.assertEqual(value_sha256({"a": 1, "b": [2.0]}), value_sha256({"b": [2], "a": 1}))
        self.assertNotEqual(value_sha256(5), value_sha256(5.5))
        self.assertEqual(pointer("a/b~c"), "/a~1b~0c")


class DescribeTests(unittest.TestCase):
    def test_settings_keys_a_script_reads_become_members_and_the_rest_are_sorted_out(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "hullmod:tank_mod", vanilla_core=_core(root, with_commodities=False))
        self.assertEqual(validate(gene), [])
        entries = {m["path"]: m["sha256"] for m in gene["members"] if m["what"] == "json-entry"}
        self.assertEqual(sorted(entries), ["data/config/settings.json#/tank_mod_rate", "data/config/settings.json#/tank_mod_sfx"])
        self.assertEqual(entries["data/config/settings.json#/tank_mod_rate"], value_sha256(5))
        self.assertIn("setting:vanilla_only_key", gene["needs"]["vanilla"])
        self.assertTrue(any(m.startswith("setting:nowhere_key") for m in gene["unknowns"]["missing"]))
        suspects = [s["path"] for s in gene["unknowns"]["suspects"]]
        self.assertEqual(suspects, ["data/config/settings.json#/tank_mod_unused"])  # key level, not the whole file
        self.assertNotIn("data/config/settings.json", suspects)

    @unittest.skipUnless(shutil.which("javac"), "needs javac")
    def test_commodity_constants_resolve_against_the_core(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "hullmod:tank_mod", vanilla_core=_core(root, with_commodities=True))
        self.assertIn("commodity:lobster", gene["needs"]["vanilla"])
        self.assertNotIn("commodity:food", gene["needs"]["vanilla"])  # the script never names FOOD
        missing = " ".join(gene["unknowns"]["missing"])
        self.assertIn("commodity:retired_good (Commodities.RETIRED; not in the core's commodities.csv)", missing)
        self.assertIn("commodity:Commodities.UNHEARD_OF", missing)

    def test_without_a_core_no_commodity_is_guessed(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "hullmod:tank_mod")
        self.assertFalse(any(need.startswith("commodity:") for need in gene["needs"]["vanilla"]))


@unittest.skipUnless(shutil.which("javac"), "needs javac")
class BytecodeTests(unittest.TestCase):
    def test_a_compiled_class_passes_its_keys_as_call_arguments(self) -> None:
        with resolved_temp_dir() as root:
            api = root / "src" / "com" / "fs" / "starfarer" / "api"
            _write(api / "SettingsAPI.java", "package com.fs.starfarer.api;\npublic interface SettingsAPI { float getFloat(String k); }\n")
            _write(api / "Global.java", "package com.fs.starfarer.api;\npublic class Global { public static SettingsAPI getSettings() { return null; } }\n")
            _write(root / "src" / "demo" / "Table.java", "package demo;\npublic class Table { public float getFloat(String k) { return 0; } }\n")
            _write(root / "src" / "demo" / "Reader.java", "package demo;\npublic class Reader {\n"
                   "  float f() { return com.fs.starfarer.api.Global.getSettings().getFloat(\"compiled_key\"); }\n"
                   "  float g(Table t) { return t.getFloat(\"not_a_settings_key\"); }\n}\n")
            files = [str(p) for p in (root / "src").rglob("*.java")]
            subprocess.run([shutil.which("javac"), "-encoding", "UTF-8", "-proc:none", "-d", str(root / "out"), *files],
                           check=True, capture_output=True)
            keys = keys_read_by_class((root / "out" / "demo" / "Reader.class").read_bytes())
        self.assertEqual(keys, {"compiled_key"})


if __name__ == "__main__":
    unittest.main()
