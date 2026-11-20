"""94.G2 P3: star-system genes (Eridani's Pantheon is the pilot) and the campaign ids a gene's code names."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.genome.campaign import campaign_ids, star_system_generators
from bridgeforge.genome.closure import keys_read_by_class
from bridgeforge.genome.gene import CLOSABLE_KINDS, GeneError, describe, validate
from bridgeforge.genome.proof import ProofError, prove
from tests.support import resolved_temp_dir, write_text as _write

API = {
    "BaseModPlugin": "package com.fs.starfarer.api;\npublic class BaseModPlugin { public void onNewGame() { } }\n",
    "Global": "package com.fs.starfarer.api;\npublic class Global { public static com.fs.starfarer.api.campaign.SectorAPI "
              "getSector() { return null; } }\n",
    "SettingsAPI": "package com.fs.starfarer.api;\npublic interface SettingsAPI { String getString(String k); "
                   "String getString(String c, String i); float getFloat(String k); }\n",
    "campaign/StarSystemAPI": "package com.fs.starfarer.api.campaign;\npublic interface StarSystemAPI { }\n",
    "campaign/SectorAPI": "package com.fs.starfarer.api.campaign;\npublic interface SectorAPI { "
                          "StarSystemAPI createStarSystem(String name); void image(String category, String key); }\n",
    "campaign/econ/EconomyAPI": "package com.fs.starfarer.api.campaign.econ;\npublic interface EconomyAPI { "
                                "void addMarket(Object market, boolean b); }\n",
}
IMPORTS = ("import com.fs.starfarer.api.SettingsAPI;\nimport com.fs.starfarer.api.campaign.SectorAPI;\n"
           "import com.fs.starfarer.api.campaign.econ.EconomyAPI;\n")
SOURCES = {
    # The plugin: onNewGame -> setUp, which calls the generator beside another feature (a relation), as Eridani's does.
    "Plugin": "public class Plugin {\n public void onNewGame() { setUp(null); }\n"
              " private void setUp(SectorAPI s) { new Gen().generate(s, null, null); s.image(\"relations\", \"x\"); "
              "Helper.run(s); }\n}\n",
    "Helper": "public class Helper { static void run(SectorAPI s) { new Via().generate(s); } }\n",
    "Via": "public class Via { public void generate(SectorAPI s) { s.createStarSystem(\"Via\"); } }\n",
    # The name reaches createStarSystem through a local; the strings-table getString is not a settings key.
    "Gen": "public class Gen {\n public void generate(SectorAPI sector, EconomyAPI economy, SettingsAPI settings) {\n"
           "  String name = \"Demo\";\n  sector.createStarSystem(name);\n  economy.addMarket(null, true);\n"
           "  settings.getString(\"scripts\", \"demo_text\");\n  settings.getFloat(\"demo_rate\");\n"
           "  String[] ids = {\"demo_industry\", \"farming\", \"demo_faction\", \"desert\", \"nav_buoy\"};\n"
           "  sector.image(\"intel\", \"demo_ill\");\n  sector.image(\"misc\", \"rings_ice0\");\n }\n}\n",
    "Ind": "public class Ind { public String submarket() { return \"storage\"; } }\n",
    "Other": "public class Other { public void generate(SectorAPI s, String suffix) { s.createStarSystem(\"Comp\" + suffix); } }\n",
    "Dup1": "public class Dup1 { public void generate(SectorAPI s) { s.createStarSystem(\"Dup\"); } }\n",
    "Dup2": "public class Dup2 { public void generate(SectorAPI s) { s.createStarSystem(\"Dup\"); } }\n",
    "Orphan": "public class Orphan { public void generate(SectorAPI s) { s.createStarSystem(\"Lonely\"); } }\n",
    "Param": "public class Param { public void generate(SectorAPI s, String name) { if (name == null) name = \"Defaulted\"; "
             "s.createStarSystem(name); } }\n",
    # A conditional name: the constant right before the call (or the store) is only one of two the jump can bring.
    "Cond": "public class Cond { public void generate(SectorAPI s, boolean c) { s.createStarSystem(c ? \"A\" : \"B\"); } }\n",
    "CondLocal": "public class CondLocal { public void generate(SectorAPI s, boolean c) { String n = c ? \"C\" : \"D\"; "
                 "s.createStarSystem(n); } }\n",
}


def _javac() -> str | None:
    return shutil.which("javac")


def _mod(root: Path) -> Path:
    mod = root / "mod"
    _write(mod / "mod_info.json", json.dumps({"id": "demo", "name": "Demo", "version": "1.0", "gameVersion": "0.98.5a-RC7",
                                              "jars": ["jars/demo.jar"], "modPlugin": "demo.Plugin"}))
    _write(mod / "data" / "campaign" / "industries.csv",
           "id,name,plugin,image\ndemo_industry,Demo Works,demo.Ind,graphics/icons/demo_ind.png\nother_industry,Other,,\n")
    _write(mod / "graphics" / "icons" / "demo_ind.png", "png bytes")
    _write(mod / "graphics" / "ill" / "demo.png", "illustration bytes")
    _write(mod / "data" / "config" / "settings.json",
           json.dumps({"demo_rate": 2, "graphics": {"intel": {"demo_ill": "graphics/ill/demo.png"}}}, indent=2))
    _write(mod / "data" / "world" / "factions" / "factions.csv", "faction\ndata/world/factions/demo.faction\n")
    _write(mod / "data" / "world" / "factions" / "demo.faction", json.dumps({"id": "demo_faction"}))
    src = root / "src"
    for name, text in API.items():
        _write(src / "com" / "fs" / "starfarer" / "api" / f"{name}.java", text)
    for name, text in SOURCES.items():
        _write(src / "demo" / f"{name}.java", f"package demo;\n{IMPORTS}{text}")
    out = root / "classes"
    subprocess.run([_javac(), "-encoding", "UTF-8", "-proc:none", "-d", str(out), *map(str, src.rglob("*.java"))],
                   check=True, capture_output=True)
    (mod / "jars").mkdir(parents=True)
    with zipfile.ZipFile(mod / "jars" / "demo.jar", "w") as jar:
        for path in sorted((out / "demo").glob("*.class")):
            jar.write(path, f"demo/{path.name}")
    return mod


def _api_jar(root: Path, core: Path) -> None:
    """The compiled stub API as the core's starfarer.api.jar (the carrier plugin compiles against it)."""
    with zipfile.ZipFile(core / "starfarer.api.jar", "w") as jar:
        for path in sorted((root / "classes" / "com").rglob("*.class")):
            jar.write(path, path.relative_to(root / "classes").as_posix())


def _core(root: Path) -> Path:
    core = root / "core"
    _write(core / "data" / "campaign" / "industries.csv", "id,name\nfarming,Farming\n")
    _write(core / "data" / "campaign" / "market_conditions.csv", "id,name\ndesert,Desert\n")
    _write(core / "data" / "campaign" / "submarkets.csv", "id,name\nstorage,Storage\n")
    _write(core / "data" / "config" / "planets.json", json.dumps({"desert": {}}))
    _write(core / "data" / "config" / "custom_entities.json", json.dumps({"nav_buoy": {}}))
    _write(core / "data" / "config" / "settings.json",
           json.dumps({"graphics": {"misc": {"rings_ice0": "graphics/rings.png"}, "campaignEntities": {"nav_buoy": "x.png"}}}))
    return core


@unittest.skipUnless(_javac(), "needs javac")
class StarSystemGeneTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = resolved_temp_dir()
        root = self._tmp.__enter__()
        self.addCleanup(self._tmp.__exit__, None, None, None)
        self.mod, self.core = _mod(root), _core(root)
        _api_jar(root, self.core)
        self.gene = describe(self.mod, "star-system:Demo", vanilla_core=self.core)

    def test_the_gene_holds_its_generator_campaign_rows_and_graphics_but_not_the_plugin(self) -> None:
        paths = {(m["what"], m["path"]) for m in self.gene["members"]}
        self.assertIn(("jar-class", "jars/demo.jar!demo/Gen.class"), paths)
        self.assertIn(("jar-class", "jars/demo.jar!demo/Ind.class"), paths)  # the industry row's plugin class
        self.assertIn(("csv-row", "data/campaign/industries.csv [demo_industry]"), paths)
        self.assertIn(("file", "graphics/icons/demo_ind.png"), paths)
        self.assertIn(("json-entry", "data/config/settings.json#/graphics/intel/demo_ill"), paths)
        self.assertIn(("file", "graphics/ill/demo.png"), paths)
        self.assertIn(("json-entry", "data/config/settings.json#/demo_rate"), paths)
        self.assertNotIn(("jar-class", "jars/demo.jar!demo/Plugin.class"), paths)  # the hook holds other features too
        self.assertNotIn(("csv-row", "data/campaign/industries.csv [other_industry]"), paths)
        self.assertEqual(self.gene["provides"], ["industry:demo_industry", "star-system:Demo"])
        self.assertEqual(validate(self.gene), [])

    def test_needs_are_typed_by_table_and_the_faction_is_a_gene_need(self) -> None:
        needs = self.gene["needs"]
        self.assertEqual(needs["genes"], ["faction:demo_faction"])
        for need in ("industry:farming", "condition:desert", "planet-type:desert", "entity-type:nav_buoy",
                     "graphics:misc/rings_ice0", "submarket:storage"):
            self.assertIn(need, needs["vanilla"])
        # A graphics key counts only when its category is also a literal of the code.
        self.assertNotIn("graphics:campaignEntities/nav_buoy", needs["vanilla"])
        self.assertNotIn("setting:scripts", " ".join(self.gene["unknowns"]["missing"]))

    def test_the_registration_names_the_call_site_and_its_hook(self) -> None:
        self.assertEqual(self.gene["registrations"], [{"locus": "demo.Plugin.setUp", "statement": "demo.Gen: <init>, generate",
                                                       "hooks": ["onNewGame"]}])
        names = [element["name"] for element in self.gene["persistent_state"]]
        self.assertEqual(names, ["star system Demo", "the markets demo.Gen adds", "industry demo_industry"])
        self.assertTrue(any("computed" in s["reason"] for s in self.gene["unknowns"]["suspects"]))

    def test_a_name_through_a_local_resolves_and_a_computed_one_does_not(self) -> None:
        generators = star_system_generators(self.mod / ".")
        self.assertEqual(generators["Demo"], ["demo.Gen"])
        self.assertEqual(generators["Dup"], ["demo.Dup1", "demo.Dup2"])
        self.assertEqual(generators[None], ["demo.Cond", "demo.CondLocal", "demo.Other", "demo.Param"])
        for constant in ("A", "B", "C", "D", "Defaulted"):  # a jump target or a parameter takes no constant
            self.assertNotIn(constant, generators)

    def test_several_generators_none_or_an_unreachable_one_are_refused(self) -> None:
        with self.assertRaisesRegex(GeneError, "several loaded classes"):
            describe(self.mod, "star-system:Dup", vanilla_core=self.core)
        with self.assertRaisesRegex(GeneError, "no call to it is reachable"):
            describe(self.mod, "star-system:Lonely", vanilla_core=self.core)
        with self.assertRaisesRegex(GeneError, "computed name: demo.Cond, demo.CondLocal, demo.Other, demo.Param"):
            describe(self.mod, "star-system:Nowhere", vanilla_core=self.core)

    def test_a_generator_reached_through_a_helper_class_is_registered_there(self) -> None:
        gene = describe(self.mod, "star-system:Via", vanilla_core=self.core)
        self.assertEqual(gene["registrations"], [{"locus": "demo.Helper.run", "statement": "demo.Via: <init>, generate",
                                                  "hooks": ["onNewGame"]}])

    def test_a_mod_row_hides_only_the_core_definition_of_the_same_kind(self) -> None:
        _write(self.mod / "data" / "campaign" / "industries.csv",
               "id,name,plugin,image\ndemo_industry,Demo Works,demo.Ind,graphics/icons/demo_ind.png\ndesert,Mod desert,,\n")
        found = campaign_ids(self.mod, [{"what": "jar-class", "path": "jars/demo.jar!demo/Gen.class"}], self.core)
        self.assertIn("industry:desert", found["provides"])
        self.assertIn("condition:desert", found["vanilla"])
        self.assertIn("planet-type:desert", found["vanilla"])
        self.assertNotIn("industry:desert", found["vanilla"])

    def test_a_graphics_value_that_is_not_an_object_names_nothing(self) -> None:
        _write(self.mod / "data" / "config" / "settings.json", json.dumps({"demo_rate": 2, "graphics": ["intel"]}))
        found = campaign_ids(self.mod, [{"what": "jar-class", "path": "jars/demo.jar!demo/Gen.class"}], self.core)
        self.assertNotIn("data/config/settings.json#/graphics/intel/demo_ill", [m["path"] for m in found["members"]])

    def test_getstring_with_a_category_is_not_a_settings_key(self) -> None:
        with zipfile.ZipFile(self.mod / "jars" / "demo.jar") as jar:
            self.assertEqual(keys_read_by_class(jar.read("demo/Gen.class")), {"demo_rate"})

    def test_an_id_two_mod_tables_define_is_named_both_ways_and_suspected(self) -> None:
        _write(self.mod / "data" / "campaign" / "market_conditions.csv", "id,name\ndemo_industry,Also a condition\n")
        found = campaign_ids(self.mod, [{"what": "jar-class", "path": "jars/demo.jar!demo/Gen.class"}], self.core)
        self.assertIn("condition:demo_industry", found["provides"])
        self.assertIn("industry:demo_industry", found["provides"])
        self.assertEqual([s["mentions"] for s in found["suspects"]], [["condition", "industry"]])

    def test_prove_passes_both_static_halves_with_a_generated_carrier_plugin(self) -> None:
        with resolved_temp_dir() as out:
            result = prove(self.mod, "star-system:Via", out / "proof", vanilla_core=self.core)
            self.assertEqual(result["verdicts"], {"subtraction-proof": "PASS", "isolation-proof": "PASS"})
            subtraction = json.loads((out / "proof" / "subtraction-proof.json").read_text(encoding="utf-8"))
            self.assertEqual(subtraction["registration_sites"][0]["locus"], "demo.Helper.run")
            self.assertIn("slice 8", subtraction["boot"])
            isolation = json.loads((out / "proof" / "isolation-proof.json").read_text(encoding="utf-8"))
            self.assertEqual(isolation["carrier_plugin"]["statement"], "new demo.Via().generate(Global.getSector())")
            source = out / "proof" / "work" / "carrier-plugin" / "bfgene" / "CarrierPlugin.java"
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), isolation["carrier_plugin"]["source_sha256"])
            carrier = out / "proof" / "work" / "carrier"
            info = json.loads((carrier / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual(info["modPlugin"], "bfgene.CarrierPlugin")
            self.assertEqual(info["jars"], ["jars/bfgene_carrier.jar", "jars/demo.jar"])  # the game loads only listed jars
            with zipfile.ZipFile(carrier / "jars" / "bfgene_carrier.jar") as jar:
                self.assertEqual(jar.namelist(), ["bfgene/CarrierPlugin.class"])
            with zipfile.ZipFile(out / "proof" / "work" / "subtraction" / "jars" / "demo.jar") as jar:
                self.assertNotIn("demo/Via.class", jar.namelist())
                self.assertIn("demo/Helper.class", jar.namelist())  # the call site stays in the donor

    def test_a_generator_the_carrier_cannot_call_refuses_the_proof(self) -> None:
        with resolved_temp_dir() as out, self.assertRaisesRegex(ProofError, "javac refused the carrier's plugin"):
            prove(self.mod, "star-system:Demo", out / "proof", vanilla_core=self.core)  # Gen.generate takes three arguments


class CarrierPluginTests(unittest.TestCase):
    def test_unsafe_names_disagreeing_calls_and_unknown_hooks_are_refused(self) -> None:
        from bridgeforge.genome.carrier_plugin import CarrierPluginRefused, call_of

        good = {"locus": "a.Plugin.setUp", "statement": "a.Gen: <init>, generate", "hooks": ["onNewGame"]}
        self.assertEqual(call_of([good]), ("a.Gen", "generate", "onNewGame"))
        for bad in ({**good, "statement": "a.Gen(){};Runtime x: <init>, generate"},
                    {**good, "statement": "a.Gen: <init>, generate()"}, {**good, "hooks": ["onApplicationLoad"]}):
            with self.subTest(bad), self.assertRaises(CarrierPluginRefused):
                call_of([bad])
        with self.assertRaisesRegex(CarrierPluginRefused, "2 distinct"):
            call_of([good, {**good, "statement": "a.Other: <init>, generate"}])

    def test_the_hook_is_taken_in_lifecycle_order_not_by_name(self) -> None:
        from bridgeforge.genome.carrier_plugin import call_of

        # `hooks` is sorted by name; onGameLoad would have generated the system on every load.
        shared = {"locus": "a.Helper.run", "statement": "a.Gen: <init>, generate", "hooks": ["onGameLoad", "onNewGame"]}
        self.assertEqual(call_of([shared])[2], "onNewGame")
        early = {**shared, "hooks": ["onApplicationLoad", "onNewGame"]}  # the first has no generated form, the second does
        self.assertEqual(call_of([early])[2], "onNewGame")

    def test_a_nested_or_default_package_generator_is_refused_by_name(self) -> None:
        from bridgeforge.genome.carrier_plugin import CarrierPluginRefused, call_of

        for generator in ("a.B$C", "Gen"):
            with self.subTest(generator), self.assertRaisesRegex(CarrierPluginRefused, "nested class or in the default package"):
                call_of([{"locus": "a.P.s", "statement": f"{generator}: <init>, generate", "hooks": ["onNewGame"]}])

    def test_a_nested_rewrite_keeps_non_ascii_text(self) -> None:
        from bridgeforge.genome.proof import subtract

        with resolved_temp_dir() as root:
            mod = root / "mod"
            _write(mod / "data" / "config" / "settings.json", json.dumps(
                {"designTypeColors": {"天苑四设计": [1, 2, 3, 255]}, "graphics": {"intel": {"x": "a.png", "y": "b.png"}}},
                ensure_ascii=False))
            gene = {"members": [{"what": "json-entry", "path": "data/config/settings.json#/graphics/intel/x"}]}
            subtract(mod, gene, root / "copy")
            text = (root / "copy" / "data" / "config" / "settings.json").read_text(encoding="utf-8")
            self.assertIn("天苑四设计", text)
            self.assertNotIn('"x"', text)

    def test_boot_notes_say_what_each_boot_half_needs(self) -> None:
        from bridgeforge.genome.proof import boot_note

        system = {"kind": "star-system", "needs": {"vanilla": [], "mods": [], "genes": ["faction:f"]}}
        self.assertIn("slice 8", boot_note("subtraction-proof", system))
        self.assertIn("faction:f", boot_note("isolation-proof", system))
        hullmod = {"kind": "hullmod", "needs": {"vanilla": [], "mods": []}}
        self.assertIn("needs the test rig", boot_note("subtraction-proof", hullmod))


def _scan(*findings):
    from types import SimpleNamespace

    return SimpleNamespace(findings=[SimpleNamespace(id=i, file=f, evidence=list(e), explanation="") for i, f, e in findings])


_SYSTEM = {"kind": "star-system", "provides": ["star-system:Demo"], "members": [
    {"what": "jar-class", "path": "jars/demo.jar!demo/Gen.class"}],
    "needs": {"vanilla": [], "mods": [], "genes": ["faction:demo_faction"]},
    "registrations": [{"locus": "demo.Plugin.setUp", "statement": "demo.Gen: <init>, generate", "hooks": ["onNewGame"]}]}


class ClassifierTests(unittest.TestCase):
    def test_the_plugin_calling_the_removed_generator_is_the_registration_not_a_leak(self) -> None:
        from bridgeforge.genome.proof import classify_subtraction

        after = _scan(("source-import-unresolved", "", ["demo.Gen"]))
        result = classify_subtraction(_scan(), after, _SYSTEM, [])
        self.assertEqual((result["verdict"], result["leaks"]), ("PASS", []))
        self.assertEqual(result["registrations"], [{"finding": "source-import-unresolved", "file": "", "reference": "demo.Gen"}])
        self.assertEqual(result["registration_sites"][0]["locus"], "demo.Plugin.setUp")
        # The simple name elsewhere is not the registration (a faction named like the generator): a false PASS before.
        named_alike = _scan(("content-reference-unresolved", "data/world/factions/x.faction", ["faction:Gen"]))
        self.assertEqual(classify_subtraction(_scan(), named_alike, _SYSTEM, [])["verdict"], "FAIL")
        simple_import = _scan(("source-import-unresolved", "", ["Gen"]))
        self.assertEqual(classify_subtraction(_scan(), simple_import, _SYSTEM, [])["verdict"], "PASS")
        hullmod = {**_SYSTEM, "kind": "hullmod", "provides": ["hullmod:x"], "registrations": []}
        self.assertEqual(classify_subtraction(_scan(), after, hullmod, [])["verdict"], "FAIL")  # only a star system's call

    def test_a_gene_need_may_stay_unresolved_in_the_carrier(self) -> None:
        from bridgeforge.genome.proof import classify_isolation

        carrier = _scan(("content-reference-unresolved", "data/campaign/industries.csv", ["faction:demo_faction"]))
        self.assertEqual(classify_isolation(_scan(), carrier, _SYSTEM)["verdict"], "PASS")
        other = _scan(("content-reference-unresolved", "data/campaign/industries.csv", ["faction:somebody_else"]))
        self.assertEqual(classify_isolation(_scan(), other, _SYSTEM)["verdict"], "FAIL")


class ParameterSlotTests(unittest.TestCase):
    def test_this_and_each_argument_take_their_slots(self) -> None:
        from bridgeforge.atlas.atlas_classfile import parameter_slots

        self.assertEqual(parameter_slots("(Ljava/lang/String;J[JI)V", False), 6)  # this, String, long (2), long[] (1), int
        self.assertEqual(parameter_slots("(D[[Ljava/lang/Object;)V", True), 3)
        self.assertEqual(parameter_slots("()V", False), 1)


class NeedsGenesTests(unittest.TestCase):
    def test_star_system_is_closable_and_needs_genes_is_optional_but_checked(self) -> None:
        self.assertIn("star-system", CLOSABLE_KINDS)
        gene = {"schema": "bridgeforge-gene", "schema_version": 4, "identity": "0" * 64, "kind": "hullmod",
                "anchors": ["hullmod:x"], "provides": ["hullmod:x"], "members": [], "needs": {"vanilla": [], "mods": []},
                "registrations": [], "conditions": [], "persistent_state": [], "build": {}, "provenance": {},
                "derived_from": None, "licence": {"decision": "LOCAL_ONLY", "mod_decision": "LOCAL_ONLY", "local_only_members": []},
                "phenotype_obligations": [], "unknowns": {"missing": [], "suspects": []}, "collected_from": []}
        without = [p for p in validate(gene) if "needs" in p]
        self.assertEqual(without, [])
        gene["needs"]["genes"] = ["no-colon"]
        self.assertIn("needs.genes, when present, is a list of 'kind:id' anchors", validate(gene))


if __name__ == "__main__":
    unittest.main()
