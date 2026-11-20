"""94.G2 slice 10: faction genes: the file, its factions.csv row and named files are members; its lists are needs."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.genome.gene import CLOSABLE_KINDS, GeneError, describe, keyed_rows, validate
from bridgeforge.genome.proof import ProofError, prove
from tests.support import resolved_temp_dir, write_text as _write

FACTION = {"id": "demo_faction", "logo": "graphics/factions/demo.png", "crest": "graphics/factions/core_crest.png",
           "portraits": {"standard_male": ["graphics/portraits/demo_p.png", "graphics/portraits/core_p.png"]},
           "knownShips": {"tags": [], "hulls": ["demo_hull", "wolf", "gone_hull"]},
           "knownWeapons": {"tags": ["demo_bp"], "weapons": ["demo_gun"]},
           "weaponSellFrequency": {"lightmg": 1}}


def _javac() -> str | None:
    return shutil.which("javac")


def _mod(root: Path, *, with_row: bool = True, code: bool = False, faction: dict | None = None) -> Path:
    mod = root / "mod"
    info = {"id": "demo", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7"}
    if code:
        info.update(jars=["jars/demo.jar"], modPlugin="demo.Plugin")
    _write(mod / "mod_info.json", json.dumps(info))
    _write(mod / "data" / "world" / "factions" / "demo.faction", json.dumps(faction or FACTION, indent=2))
    if with_row:
        _write(mod / "data" / "world" / "factions" / "factions.csv", "faction\ndata/world/factions/demo.faction\n")
    _write(mod / "graphics" / "factions" / "demo.png", "logo")
    _write(mod / "graphics" / "portraits" / "demo_p.png", "portrait")
    _write(mod / "data" / "hulls" / "ship_data.csv", "name,id\nDemo,demo_hull\n")
    _write(mod / "data" / "weapons" / "weapon_data.csv", "name,id\nGun,demo_gun\n")
    if code:
        src = root / "src"
        _write(src / "com" / "fs" / "starfarer" / "api" / "campaign" / "SectorAPI.java",
               "package com.fs.starfarer.api.campaign;\npublic interface SectorAPI { Object getFaction(String id);"
               " void setRelationship(String a, String b, float r); }\n")
        # `other` names another faction and sets relations too: neither its call nor its setRelationship is this gene's.
        _write(src / "demo" / "Plugin.java", "package demo;\nimport com.fs.starfarer.api.campaign.SectorAPI;\n"
               "public class Plugin {\n public void onNewGame() { setUp(null); }\n"
               " private void setUp(SectorAPI s) { s.getFaction(\"demo_faction\"); s.setRelationship(\"demo_faction\", \"pirates\", -0.5f); }\n"
               " private void other(SectorAPI s) { s.getFaction(\"pirates\"); s.setRelationship(\"pirates\", \"x\", 0.5f); }\n"
               " private void quiet(SectorAPI s) { s.getFaction(\"demo_faction\"); }\n}\n")  # registers, sets no relations
        out = root / "classes"
        subprocess.run([_javac(), "-encoding", "UTF-8", "-proc:none", "-d", str(out), *map(str, src.rglob("*.java"))],
                       check=True, capture_output=True)
        (mod / "jars").mkdir(parents=True)
        with zipfile.ZipFile(mod / "jars" / "demo.jar", "w") as jar:
            jar.write(out / "demo" / "Plugin.class", "demo/Plugin.class")
    return mod


def _core(root: Path) -> Path:
    core = root / "core"
    _write(core / "data" / "hulls" / "ship_data.csv", "name,id\nWolf,wolf\n")
    _write(core / "data" / "weapons" / "weapon_data.csv", "name,id\nLight MG,lightmg\n")
    _write(core / "graphics" / "factions" / "core_crest.png", "crest")
    _write(core / "graphics" / "portraits" / "core_p.png", "portrait")
    _write(core / "data" / "world" / "factions" / "hegemony.faction", json.dumps({"id": "hegemony"}))
    return core


class FactionGeneTests(unittest.TestCase):
    def test_the_file_its_row_and_its_own_files_are_members_and_its_lists_are_needs(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root), "faction:demo_faction", vanilla_core=_core(root))
        paths = {(m["what"], m["path"]) for m in gene["members"]}
        self.assertEqual(paths, {("file", "data/world/factions/demo.faction"),
                                 ("csv-row", "data/world/factions/factions.csv [data/world/factions/demo.faction]"),
                                 ("file", "graphics/factions/demo.png"), ("file", "graphics/portraits/demo_p.png")})
        self.assertEqual(gene["needs"]["genes"], ["hull:demo_hull", "weapon:demo_gun"])  # the faction carries none of them
        self.assertEqual(gene["needs"]["vanilla"], ["file:graphics/factions/core_crest.png", "file:graphics/portraits/core_p.png",
                                                    "hull:wolf", "weapon:lightmg"])
        self.assertEqual(gene["unknowns"]["missing"], ["hull:gone_hull (listed by the faction; neither the mod nor the core defines it)"])
        self.assertEqual(gene["unknowns"]["suspects"][0]["mentions"], ["demo_bp"])  # a tag: recorded, not expanded
        self.assertEqual(gene["persistent_state"][0]["name"], "faction demo_faction")
        self.assertEqual(validate(gene), [])
        self.assertIn("faction", CLOSABLE_KINDS)

    def test_a_faction_without_its_row_is_missing_its_registration(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, with_row=False), "faction:demo_faction", vanilla_core=_core(root))
        self.assertTrue(any(m.startswith("data/world/factions/factions.csv row") for m in gene["unknowns"]["missing"]))

    def test_a_core_faction_or_an_unknown_one_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _mod(root), _core(root)
            _write(mod / "data" / "world" / "factions" / "hegemony.faction", json.dumps({"id": "hegemony"}))
            with self.assertRaisesRegex(GeneError, "is a core faction"):
                describe(mod, "faction:hegemony", vanilla_core=core)
            with self.assertRaisesRegex(GeneError, "ships no .faction file"):
                describe(mod, "faction:nobody", vanilla_core=core)

    def test_factions_csv_rows_are_keyed_by_their_faction_column(self) -> None:
        # RC7's SpecStore reads factions.csv with the key `faction` (javap 2026-11-20); other tables stay keyed by `id`.
        with resolved_temp_dir() as root:
            mod = _mod(root)
            self.assertEqual(list(keyed_rows(mod, "data/world/factions/factions.csv")), ["data/world/factions/demo.faction"])
            self.assertEqual(list(keyed_rows(mod, "data/hulls/ship_data.csv")), ["demo_hull"])

    @unittest.skipUnless(_javac(), "needs javac")
    def test_code_passing_the_id_to_getfaction_is_a_registration_element(self) -> None:
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, code=True), "faction:demo_faction", vanilla_core=_core(root))
        self.assertEqual(gene["registrations"], [
            {"locus": "demo.Plugin.quiet", "statement": 'getFaction("demo_faction")', "hooks": []},  # no hook reaches it
            {"locus": "demo.Plugin.setUp", "statement": 'getFaction("demo_faction")', "hooks": ["onNewGame"]}])
        relations = [s for s in gene["unknowns"]["suspects"] if "setRelationship" in s["reason"]]
        self.assertEqual([(s["path"], s["mentions"]) for s in relations], [("jars/demo.jar!demo/Plugin.class", ["demo_faction"])])
        self.assertTrue(relations[0]["reason"].startswith("demo.Plugin.setUp "))  # a jar class path: a dependent check skips it

    def test_a_list_field_holding_a_string_names_nothing(self) -> None:
        faction = {**FACTION, "knownShips": {"hulls": "wolf", "tags": "demo_bp"}, "knownWeapons": {"weapons": {"demo_gun": 1}}}
        with resolved_temp_dir() as root:
            gene = describe(_mod(root, faction=faction), "faction:demo_faction", vanilla_core=_core(root))
        named = gene["needs"]["genes"] + gene["needs"]["vanilla"] + gene["unknowns"]["missing"]
        self.assertFalse([n for n in named if n.startswith(("hull:", "weapon:demo"))], named)  # not hull:w, hull:o, ...
        self.assertEqual(gene["unknowns"]["suspects"], [])  # nor tags d, e, m, o

    def test_a_named_file_outside_the_mod_is_no_member(self) -> None:
        faction = {**FACTION, "logo": "../outside/logo.png", "crest": "graphics\\factions\\demo.png"}
        with resolved_temp_dir() as root:
            _write(root / "outside" / "logo.png", "another mod's logo")
            gene = describe(_mod(root, faction=faction), "faction:demo_faction", vanilla_core=_core(root))
        self.assertNotIn("../outside/logo.png", [m["path"] for m in gene["members"]])
        self.assertIn("file:../outside/logo.png (named by the faction; in neither the mod nor the core)", gene["unknowns"]["missing"])
        self.assertTrue(any(m.startswith("file:graphics\\factions\\demo.png") for m in gene["unknowns"]["missing"]))

    def test_without_the_core_a_faction_is_refused(self) -> None:
        # Without the core, a mod's merge fragment for a core faction would pass for a gene.
        with resolved_temp_dir() as root, self.assertRaisesRegex(GeneError, "give --vanilla-core"):
            describe(_mod(root), "faction:demo_faction")

    def test_prove_refuses_a_faction_until_its_slice(self) -> None:
        with resolved_temp_dir() as root, self.assertRaisesRegex(ProofError, "faction gene come with its own slice"):
            prove(_mod(root), "faction:demo_faction", root / "proof", vanilla_core=_core(root))


if __name__ == "__main__":
    unittest.main()
