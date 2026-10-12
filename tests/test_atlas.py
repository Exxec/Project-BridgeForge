"""Mod Atlas (ROADMAP item 67, phases 1-3): index facts, resolve references, run the conflict rules, forecast."""
from __future__ import annotations

import io
import json
import struct
import unittest
import zipfile
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge import atlas, atlas_code
from bridgeforge.atlas_classfile import ClassFormatError, parse_class
from bridgeforge.atlas_rules import analyze, build_profile, forecast, load_facts
from bridgeforge.cli import main
from tests.support import resolved_temp_dir

INDUSTRIES_HEADER = "id,name,upgrade,downgrade\n"
HEAVY_MARKET = "Lcom/fs/starfarer/api/campaign/econ/MarketAPI;"


@contextmanager
def temp_root():
    """A resolved temp dir whose atlas connections are closed before it is removed (Windows locks open SQLite files)."""
    opened, real = [], atlas.connect

    def tracking(*args, **kwargs):
        conn = real(*args, **kwargs)
        opened.append(conn)
        return conn

    atlas.connect = tracking
    try:
        with resolved_temp_dir() as root:
            try:
                yield root
            finally:
                for conn in opened:
                    conn.close()
    finally:
        atlas.connect = real


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def make_mod(root: Path, mod_id: str, files: dict[str, str] | None = None, name: str | None = None, version: str = "1.0", folder: str | None = None) -> Path:
    mod = root / (folder or mod_id)
    write(mod / "mod_info.json", json.dumps({"id": mod_id, "name": name or mod_id, "version": version}))
    for rel, text in (files or {}).items():
        write(mod / rel, text)
    return mod


def make_vanilla(root: Path, extra: dict[str, str] | None = None) -> Path:
    core = root / "starsector-core"
    files = {
        "data/campaign/industries.csv": INDUSTRIES_HEADER + "farming,Farming,,\naquaculture,Aquaculture,,\n",
        "data/campaign/market_conditions.csv": "name,id\nFarmland,farmland_rich\n",
        "data/hulls/ship_data.csv": "name,id,hitpoints\nWolf,wolf,1000\n",
        "data/config/settings.json": '{"maxShips": 100, "tooltipDelay": 0.5}',
        "data/campaign/commodities.csv": "name,id\nFood,food\n",
        **(extra or {}),
    }
    for rel, text in files.items():
        write(core / rel, text)
    return core


def build(root: Path, quiet: bool = True) -> tuple[Path, dict]:
    db = root / "out" / "atlas.sqlite"
    roots = [root / "mods", root / "starsector-core"]
    return db, atlas.build_atlas(roots, db, quiet=quiet)


def class_bytes(name: str, super_name: str = "java/lang/Object", interfaces: tuple[str, ...] = (), strings: tuple[str, ...] = (),
                fields: tuple[tuple[str, str, int], ...] = (), calls: tuple[str, ...] = ()) -> bytes:
    pool: list[bytes] = []
    cache: dict[tuple, int] = {}

    def entry(key: tuple, raw: bytes) -> int:
        if key not in cache:
            pool.append(raw)
            cache[key] = len(pool)  # 1-based pool index; no wide (long/double) entries are used
        return cache[key]

    def utf8(text: str) -> int:
        data = text.encode("utf-8")
        return entry(("u", text), b"\x01" + struct.pack(">H", len(data)) + data)

    def klass(text: str) -> int:
        return entry(("c", text), b"\x07" + struct.pack(">H", utf8(text)))

    this_idx, super_idx = klass(name), klass(super_name)
    iface_idx = [klass(i) for i in interfaces]
    for text in strings:
        entry(("s", text), b"\x08" + struct.pack(">H", utf8(text)))
    field_idx = [(utf8(n), utf8(d), f) for n, d, f in fields]
    for call in calls:
        nat = entry(("nt", call), b"\x0c" + struct.pack(">HH", utf8(call), utf8("()V")))
        entry(("m", call), b"\x0a" + struct.pack(">HH", klass("x/Owner"), nat))
    out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, len(pool) + 1) + b"".join(pool)
    out += struct.pack(">HHHH", 0x21, this_idx, super_idx, len(iface_idx)) + b"".join(struct.pack(">H", i) for i in iface_idx)
    out += struct.pack(">H", len(field_idx)) + b"".join(struct.pack(">HHHH", f, n, d, 0) for n, d, f in field_idx)
    return out + struct.pack(">H", 0) + struct.pack(">H", 0)


def make_jar(path: Path, classes: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)


class ClassFileTests(unittest.TestCase):
    def test_parse_reads_names_strings_calls_and_fields(self):
        data = class_bytes("a/b/Thing", "a/Base", ("com/fs/starfarer/api/EveryFrameScript",), ("farming", "x y"),
                           (("market", HEAVY_MARKET, 0x0002),), ("removeIndustry",))
        info = parse_class(data)
        self.assertEqual((info.name, info.super_name, info.interfaces), ("a/b/Thing", "a/Base", ["com/fs/starfarer/api/EveryFrameScript"]))
        self.assertEqual(sorted(info.strings), ["farming", "x y"])
        self.assertEqual(info.called_methods, {"removeIndustry"})
        self.assertEqual(info.fields, [("market", HEAVY_MARKET, 0x0002)])

    def test_garbage_is_rejected(self):
        with self.assertRaises(ClassFormatError):
            parse_class(b"not a class")
        with self.assertRaises(ClassFormatError):
            parse_class(b"\xca\xfe\xba\xbe\x00\x00\x00\x34\x00\x05")


class DataFactTests(unittest.TestCase):
    def test_phase_one_data_facts_and_overrides(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "alpha", {
                "data/hulls/ship_data.csv": "name,id,hitpoints\nWolf,wolf,9999\nNew,alpha_new,5\n",
                "data/campaign/industries.csv": INDUSTRIES_HEADER + "alpha_farm,Farm,,farming\n",
                "data/config/settings.json": '{"maxShips": 300, "list": [1, 2]}',
                "data/world/factions/alpha.faction": '{"id": "alpha_f"}',
                "data/world/factions/hegemony.faction": "{}",
                "data/missions/alpha_m/descriptor.json": "{}",
            })
            db, stats = build(root)
            conn = atlas.connect(db)
            self.assertEqual(stats["mods"], 2)
            rows = {(r["kind"], r["id"], r["action"]) for r in conn.execute("SELECT * FROM facts WHERE mod = 'alpha'")}
            self.assertIn(("hull", "wolf", "overrides"), rows)  # vanilla defines wolf too
            self.assertIn(("hull", "alpha_new", "defines"), rows)
            self.assertIn(("industry", "farming", "replaces"), rows)  # the chain points past the mod's own row
            self.assertIn(("setting", "maxShips", "sets"), rows)
            self.assertIn(("faction", "alpha_f", "defines"), rows)
            self.assertIn(("faction", "hegemony", "patches"), rows)
            self.assertIn(("mission", "alpha_m", "defines"), rows)

    def test_atlas_dup_define_flags_different_hull_rows_as_manual(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "one", {"data/hulls/ship_data.csv": "name,id,hitpoints\nX,shared_hull,1\n"})
            make_mod(root / "mods", "two", {"data/hulls/ship_data.csv": "name,id,hitpoints\nX,shared_hull,2\n",
                                           "data/campaign/commodities.csv": "name,id\nFood,food\n"})
            make_mod(root / "mods", "three", {"data/campaign/commodities.csv": "name,id\nFood,food\n"})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            dups = {f.ids[0]: f for f in findings if f.rule == "ATLAS-DUP-DEFINE"}
            self.assertEqual(dups["shared_hull"].level, "MANUAL")
            self.assertEqual(dups["food"].level, "REVIEW")  # vanilla's food row is the same override intent: only two mods clash
            self.assertEqual(dups["food"].mods, ["three", "two"])

    def test_atlas_settings_override_needs_two_mods_with_different_scalars(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "one", {"data/config/settings.json": '{"maxShips": 200, "same": 1}'})
            make_mod(root / "mods", "two", {"data/config/settings.json": '{"maxShips": 300, "same": 1}'})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            hits = [f for f in findings if f.rule == "ATLAS-SETTINGS-OVERRIDE"]
            self.assertEqual([f.ids for f in hits], [["maxShips"]])

    def test_atlas_rules_clash_on_same_trigger_and_conditions(self):
        header = "id,trigger,conditions,script,text,options,notes\n"
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "one", {"data/campaign/rules.csv": header + "a1,Greet,$player.crew > 5,,Hello,,\n"})
            make_mod(root / "mods", "two", {"data/campaign/rules.csv": header + "b1,Greet,$player.crew > 5,,Goodbye,,\nb2,Other,$x,,Same,,\n"})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            hits = [f for f in findings if f.rule == "ATLAS-RULES-CLASH"]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].mods, ["one", "two"])


class CodeRuleTests(unittest.TestCase):
    def test_atlas_reads_replaced_reproduces_dneep_against_aotd(self):
        dneep_java = (
            "package data.scripts;\n"
            "public class ResourceDepositsConditionDNEEP {\n"
            "  void run(MarketAPI market) {\n"
            "    // market.getIndustry(\"commented_out\");\n"
            "    Industry farm = market.getIndustry(\"farming\");\n"
            "  }\n}\n")
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "dneep", {"data/scripts/ResourceDepositsConditionDNEEP.java": dneep_java},
                     name="Doc's Needless Economic Expansion Pack", folder="Doc-s-Needless-Economic-Expansion-Pack")
            make_mod(root / "mods", "aotd_vok", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_subsidised_farming,Subsidised Farming,,farming\n"},
                     name="AoTD- Vaults of Knowledge")
            make_mod(root / "mods", "unrelated", {"data/campaign/commodities.csv": "name,id\nGoo,goo\n"})
            db, _ = build(root)
            conn = atlas.connect(db)
            subjects = atlas.resolve_mods(conn, ["DNEEP"])  # acronym of the mod's name
            self.assertEqual([m["id"] for m in subjects], ["dneep"])
            result = forecast(conn, subjects, atlas.group_mods(conn, "aotd"))
            hits = [f for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].mods, ["dneep", "aotd_vok"])
            self.assertIn("aotd_subsidised_farming", hits[0].ids)
            self.assertEqual(hits[0].sides[0]["line"], 5)  # the comment-blanked source keeps real line numbers
            self.assertNotIn("commented_out", json.dumps([f.as_dict() for f in result["findings"]]))
            self.assertEqual(result["verdicts"]["dneep"]["status"], "REVIEW")

    def test_remove_plus_add_in_code_is_a_replacement(self):
        swapper = ('package s;\npublic class Swap {\n  void go(MarketAPI m) {\n    m.removeIndustry("farming", null, false);\n'
                   '    m.addIndustry("mine_farming");\n  }\n}\n')
        reader = 'package r;\npublic class Read {\n  boolean go(MarketAPI m) { return m.hasIndustry("farming"); }\n}\n'
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "swapper", {"data/scripts/Swap.java": swapper})
            make_mod(root / "mods", "reader", {"data/scripts/Read.java": reader})
            db, _ = build(root)
            conn = atlas.connect(db)
            mods = atlas.latest_mods(conn)
            profile = build_profile("swapper", load_facts(conn, [m for m in mods if m["id"] == "swapper"]))
            self.assertEqual(profile.replaced[("industry", "farming")]["by"], {"mine_farming"})
            findings, _ = analyze(conn, mods)
            self.assertEqual([f.rule for f in findings if f.rule == "ATLAS-READS-REPLACED"], ["ATLAS-READS-REPLACED"])

    def test_removing_and_re_adding_the_same_id_is_a_reorder_not_a_replacement(self):
        java = ('package s;\npublic class Reorder {\n  void go(MarketAPI m) {\n    m.removeCondition("hot");\n    m.addCondition("hot");\n  }\n}\n')
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "reorder", {"data/scripts/Reorder.java": java})
            db, _ = build(root)
            conn = atlas.connect(db)
            profile = build_profile("reorder", load_facts(conn, [m for m in atlas.latest_mods(conn) if m["id"] == "reorder"]))
            self.assertEqual(profile.replaced, {})
            self.assertIn("condition:hot", profile.mutates)

    def test_atlas_reads_missing_only_for_ids_nobody_defines(self):
        java = ('package m;\npublic class M {\n  void go(MarketAPI m) {\n    m.getIndustry("ghost_industry");\n    m.getIndustry("farming");\n'
                '    m.getIndustry(dynamicId);\n    m.hasCondition(Conditions.NOT_A_REAL_ONE);\n  }\n}\n')
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "needy", {"data/scripts/M.java": java})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            missing = [f for f in findings if f.rule == "ATLAS-READS-MISSING"]
            self.assertEqual([f.ids for f in missing], [["ghost_industry"]])  # defined, dynamic and constant-derived ids are not flagged
            unknown = conn.execute("SELECT confidence FROM facts WHERE id = '<dynamic>'").fetchall()
            self.assertEqual([r[0] for r in unknown], ["UNKNOWN"])

    def test_atlas_mutate_shared_for_condition_order(self):
        java = 'package x;\npublic class Order {\n  void go(MarketAPI m) { m.getConditions().clear(); }\n}\n'
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "orderone", {"data/scripts/OrderOne.java": java.replace("Order", "OrderOne")})
            make_mod(root / "mods", "ordertwo", {"data/scripts/OrderTwo.java": java.replace("Order", "OrderTwo").replace("clear()", "sort(null)")})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            shared = [f for f in findings if f.rule == "ATLAS-MUTATE-SHARED"]
            self.assertEqual([(f.ids, f.mods) for f in shared], [(["market.conditions"], ["orderone", "ordertwo"])])

    def test_atlas_pick_priority_when_two_campaign_plugins_tie(self):
        plugin = ('package p;\npublic class PLUG extends BaseCampaignPlugin {\n'
                  '  public PluginPick<X> pickBattleCreationPlugin(SectorEntityToken t) { return new PluginPick<X>(null, PickPriority.MOD_GENERAL); }\n}\n')
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "pa", {"data/scripts/PA.java": plugin.replace("PLUG", "PA")})
            make_mod(root / "mods", "pb", {"data/scripts/PB.java": plugin.replace("PLUG", "PB")})
            make_mod(root / "mods", "pc", {"data/scripts/PC.java": plugin.replace("PLUG", "PC").replace("MOD_GENERAL", "HIGHEST")})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, [m for m in atlas.latest_mods(conn) if m["id"] in ("pa", "pb")])
            ties = [f for f in findings if f.rule == "ATLAS-PICK-PRIORITY"]
            self.assertEqual([(f.ids, f.mods) for f in ties], [(["pickBattleCreationPlugin"], ["pa", "pb"])])
            findings, _ = analyze(conn, [m for m in atlas.latest_mods(conn) if m["id"] in ("pa", "pc")])
            self.assertFalse([f for f in findings if f.rule == "ATLAS-PICK-PRIORITY"])  # different known priorities

    def test_atlas_shadow_class_between_loose_scripts_and_jars(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "looseone", {"data/scripts/Same.java": "package lib;\npublic class Same { int a; }\n"})
            make_mod(root / "mods", "loosetwo", {"data/scripts/Same.java": "package lib;\npublic class Same { int b; }\n"})
            make_mod(root / "mods", "jarone", {"jars/a.jar": ""})
            make_jar(root / "mods" / "jarone" / "jars" / "a.jar", {"lib/Twin.class": class_bytes("lib/Twin", strings=("one",)), "lib/Same.class": class_bytes("lib/Same")})
            make_mod(root / "mods", "jartwo", {})
            make_jar(root / "mods" / "jartwo" / "jars" / "b.jar", {"lib/Twin.class": class_bytes("lib/Twin", strings=("one",)), "lib/Other.class": class_bytes("lib/Other")})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            shadows = {f.ids[0]: f for f in findings if f.rule == "ATLAS-SHADOW-CLASS"}
            self.assertEqual(shadows["lib.Same"].level, "MANUAL")
            self.assertEqual(set(shadows["lib.Same"].mods), {"jarone", "looseone", "loosetwo"})
            self.assertNotIn("lib.Twin", shadows)  # byte-identical bundled copies are not a conflict

    def test_atlas_save_holds_heavy_flags_station_augments_style_field(self):
        java = ('package sa;\npublic class AugmentScript implements EveryFrameScript {\n'
                '  MarketAPI market;\n  private transient SectorEntityToken skipped;\n  static CampaignFleetAPI alsoSkipped;\n'
                '  public void advance(float amount) { MarketAPI local = null; }\n}\n')
        harmless = 'package sa;\npublic class Plain {\n  MarketAPI market;\n}\n'
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "augments", {"data/scripts/AugmentScript.java": java, "data/scripts/Plain.java": harmless})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            heavy = [f for f in findings if f.rule == "ATLAS-SAVE-HOLDS-HEAVY"]
            self.assertEqual([f.ids for f in heavy], [["sa.AugmentScript.market"]])
            self.assertEqual(heavy[0].category, "crash-class")

    def test_jar_facts_hooks_saved_fields_and_literal_resolution(self):
        script = class_bytes("j/Tick", interfaces=("com/fs/starfarer/api/EveryFrameScript",),
                             fields=(("market", HEAVY_MARKET, 0), ("cache", HEAVY_MARKET, 0x0080)))
        swapper = class_bytes("j/Swap", strings=("farming", "mine_farming"), calls=("removeIndustry", "addScript"))
        reader = class_bytes("j/Read", strings=("farming",))
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "jarmod", {"mod_info.json": json.dumps({"id": "jarmod", "version": "2", "jars": ["jars/x.jar"]})})
            make_jar(root / "mods" / "jarmod" / "jars" / "x.jar", {"j/Tick.class": script, "j/Swap.class": swapper, "j/Read.class": reader, "j/Broken.class": b"nope"})
            db, _ = build(root)
            conn = atlas.connect(db)
            facts = {(r["kind"], r["id"], r["action"]) for r in conn.execute("SELECT * FROM facts WHERE mod = 'jarmod'")}
            self.assertIn(("class", "j.Tick", "defines"), facts)
            self.assertIn(("hook", "j.Tick", "registers"), facts)
            self.assertIn(("saved-field", "j.Tick.market", "persists"), facts)
            self.assertNotIn(("saved-field", "j.Tick.cache", "persists"), facts)  # transient is not saved
            self.assertNotIn(("industry", "farming", "mutates"), facts)  # 67a: a removeIndustry elsewhere in the class is no longer a guess
            self.assertIn(("industry", "farming", "references"), facts)  # plain literal in a class
            self.assertNotIn(("industry", "mine_farming", "references"), facts)  # not a known id: not a fact
            profile = build_profile("jarmod", load_facts(conn, [m for m in atlas.latest_mods(conn) if m["id"] == "jarmod"]))
            self.assertNotIn(("industry", "farming"), profile.replaced)

    def test_unreadable_jar_is_unknown_not_silent(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "badjar", {"jars/bad.jar": "not a zip"})
            db, _ = build(root)
            conn = atlas.connect(db)
            row = conn.execute("SELECT confidence, action FROM facts WHERE mod = 'badjar' AND kind = 'jar'").fetchone()
            self.assertEqual((row["action"], row["confidence"]), ("unreadable", "UNKNOWN"))

    def test_call_site_regex_ignores_concatenated_ids(self):
        facts = atlas_code._call_facts('m.getIndustry("aotd_" + suffix); m.getIndustry("plain");', "A.java")
        self.assertEqual([(f.id, f.confidence) for f in facts], [("<dynamic>", "UNKNOWN"), ("plain", "REVIEW")])


class BuildAndCliTests(unittest.TestCase):
    def test_incremental_build_progress_and_checkpoint(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "alpha", {"data/campaign/commodities.csv": "name,id\nGoo,goo\n"})
            err = io.StringIO()
            with redirect_stderr(err):
                db, first = build(root, quiet=False)
            self.assertEqual((first["indexed"], first["unchanged"]), (2, 0))
            self.assertIn("[1/2]", err.getvalue())
            self.assertFalse(db.with_suffix(".partial.jsonl").exists())  # deleted when the run completes
            _, second = build(root)
            self.assertEqual((second["indexed"], second["unchanged"]), (0, 2))
            write(root / "mods" / "alpha" / "data" / "campaign" / "commodities.csv", "name,id\nGoo,goo\nMore goo,more_goo\n")
            _, third = build(root)
            self.assertEqual((third["indexed"], third["unchanged"]), (1, 1))
            conn = atlas.connect(db)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM facts WHERE mod = 'alpha' AND kind = 'commodity'").fetchone()[0], 2)

    def test_interrupted_run_resumes_from_checkpoint(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "alpha")
            db, _ = build(root)
            write(root / "mods" / "beta" / "mod_info.json", json.dumps({"id": "beta", "version": "1"}))
            first_run = [root / "mods", root / "starsector-core"]
            folders = [f for r in first_run for f in atlas.discover_mods(r)]
            checkpoint = db.with_suffix(".partial.jsonl")
            header = {"atlas": atlas.SCHEMA_VERSION, "roots": [str(r) for r in first_run], "mods": [str(f) for f in folders]}
            with atlas.progress.Checkpoint(checkpoint, header) as saved:
                alpha = next(f for f in folders if f.name == "alpha")
                saved.add("alpha@1.0", {"hash": atlas.mod_hash(alpha), "facts": 0})
            err = io.StringIO()
            with redirect_stderr(err):
                atlas.build_atlas(first_run, db, quiet=False)
            self.assertIn("alpha 1.0: unchanged (from checkpoint)", err.getvalue())
            self.assertFalse(checkpoint.exists())

    def test_duplicate_copies_are_indexed_once(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "alpha")
            make_mod(root / "copy", "alpha")
            db = root / "out" / "atlas.sqlite"
            stats = atlas.build_atlas([root / "mods", root / "copy"], db, quiet=True)
            self.assertEqual((stats["mods"], stats["duplicates"]), (1, 1))

    def test_cli_build_show_id_forecast_and_html(self):
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "aotd_x", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_farm,Farm,,farming\n"}, name="AoTD X")
            make_mod(root / "mods", "reader", {"data/scripts/R.java": 'package r;\npublic class R { void go(MarketAPI m) { m.getIndustry("farming"); } }\n'})
            db, html_dir = root / "cli.sqlite", root / "html"
            base = ["--db", str(db)]

            def run(*argv) -> tuple[int, str]:
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    return main(list(argv)), out.getvalue()

            code, text = run("atlas", "build", str(root / "mods"), str(root / "starsector-core"), "--quiet", "--json", *base)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(text)["mods"], 3)
            code, text = run("atlas", "show", "reader", "--json", *base)
            self.assertEqual(json.loads(text)[0]["mod"]["id"], "reader")
            code, text = run("atlas", "id", "farming", *base)
            self.assertIn("reader", text)
            self.assertIn("aotd_x", text)
            code, text = run("atlas", "forecast", "reader", "--against", "aotd", "--json", "--html", str(html_dir), *base)
            data = json.loads(text)
            self.assertEqual([f["rule"] for f in data["findings"]], ["ATLAS-READS-REPLACED"])
            page = (html_dir / "forecast_reader.html").read_text(encoding="utf-8")
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)
            run("atlas", "show", "reader", "--html", str(html_dir), *base)
            run("atlas", "id", "farming", "--html", str(html_dir), *base)
            self.assertTrue((html_dir / "mod_reader.html").is_file() and (html_dir / "id_farming.html").is_file())
            code, _ = run("atlas", "show", "no-such-mod", *base)
            self.assertEqual(code, 2)
            code, _ = run("atlas", "show", "reader", "--db", str(root / "missing.sqlite"))
            self.assertEqual(code, 2)


class MatchingTests(unittest.TestCase):
    def test_match_tiers(self):
        mods = [{"id": "dneep_mod", "name": "Doc's Needless Economic Expansion Pack", "folder": "Doc-s-Needless-Economic-Expansion-Pack"},
                {"id": "aotd_vok", "name": "AoTD- Vaults of Knowledge", "folder": "AoTD- Vaults of Knowledge-5.0.7"}]
        self.assertEqual([m["id"] for m in atlas.match_mods(mods, "DNEEP")], ["dneep_mod"])
        self.assertEqual([m["id"] for m in atlas.match_mods(mods, "aotd_vok")], ["aotd_vok"])
        self.assertEqual([m["id"] for m in atlas.match_mods(mods, "vaults")], ["aotd_vok"])
        self.assertEqual(atlas.match_mods(mods, "nothing"), [])


if __name__ == "__main__":
    unittest.main()
