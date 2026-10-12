"""Mod Atlas follow-ups 67a-67f: per-call jar attribution, mod constants, originals, more indexed kinds, scripts, id prefixes."""
from __future__ import annotations

import io
import json
import struct
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge import atlas, atlas_code
from bridgeforge.atlas_classfile import ACC_FINAL, ACC_STATIC, ACC_SYNTHETIC, parse_class
from bridgeforge.atlas_rules import analyze, build_profile, forecast, load_facts
from bridgeforge.atlas_report import show_data, show_text
from bridgeforge.cli import main
from tests.test_atlas import HEAVY_MARKET, INDUSTRIES_HEADER, build, make_jar, make_mod, make_vanilla, temp_root

MARKET = "com/fs/starfarer/api/campaign/econ/MarketAPI"
STRING_CALL = "(Ljava/lang/String;)V"
PRINT = ("java/io/PrintStream", "println", STRING_CALL)
RETURN = b"\xb1"
INVOKE_INTERFACE = 0xb9
INVOKE_SPECIAL = 0xb7
INVOKE_STATIC = 0xb8
ALOAD_0, DUP = b"\x2a", b"\x59"
CONDITIONS = "name,id\nFarmland,farmland_rich\nHabitable,habitable\n"


class ClassBuilder:
    """Assembles a small class file with real Code attributes, so the call-site scan has bytecode to read."""

    def __init__(self, name: str, super_name: str = "java/lang/Object", interfaces: tuple[str, ...] = ()) -> None:
        self.pool: list[bytes] = []
        self.cache: dict[tuple, int] = {}
        self.fields: list[bytes] = []
        self.methods: list[bytes] = []
        self.this_idx, self.super_idx = self.klass(name), self.klass(super_name)
        self.iface_idx = [self.klass(i) for i in interfaces]

    def _entry(self, key: tuple, raw: bytes) -> int:
        if key not in self.cache:
            self.pool.append(raw)
            self.cache[key] = len(self.pool)
        return self.cache[key]

    def utf8(self, text: str) -> int:
        data = text.encode("utf-8")
        return self._entry(("u", text), b"\x01" + struct.pack(">H", len(data)) + data)

    def klass(self, text: str) -> int:
        return self._entry(("c", text), b"\x07" + struct.pack(">H", self.utf8(text)))

    def string(self, text: str) -> int:
        return self._entry(("s", text), b"\x08" + struct.pack(">H", self.utf8(text)))

    def ref(self, tag: int, owner: str, name: str, desc: str) -> int:
        nat = self._entry(("n", name, desc), b"\x0c" + struct.pack(">HH", self.utf8(name), self.utf8(desc)))
        return self._entry((tag, owner, name, desc), bytes([tag]) + struct.pack(">HH", self.klass(owner), nat))

    def ldc(self, text: str) -> bytes:
        return bytes([0x12, self.string(text)])

    def invoke(self, owner: str, name: str, desc: str, kind: int = 0xb6) -> bytes:
        idx = self.ref(11 if kind == INVOKE_INTERFACE else 10, owner, name, desc)
        return bytes([kind]) + struct.pack(">H", idx) + (b"\x02\x00" if kind == INVOKE_INTERFACE else b"")

    def getstatic(self, owner: str, name: str) -> bytes:
        return b"\xb2" + struct.pack(">H", self.ref(9, owner, name, "Ljava/lang/String;"))

    def new(self, cls: str) -> bytes:
        return b"\xbb" + struct.pack(">H", self.klass(cls))

    def field(self, name: str, desc: str, flags: int = 0, constant: str | None = None, signature: str | None = None) -> "ClassBuilder":
        attrs = []
        if constant is not None:
            attrs.append(struct.pack(">HIH", self.utf8("ConstantValue"), 2, self.string(constant)))
        if signature is not None:
            attrs.append(struct.pack(">HIH", self.utf8("Signature"), 2, self.utf8(signature)))
        self.fields.append(struct.pack(">HHHH", flags, self.utf8(name), self.utf8(desc), len(attrs)) + b"".join(attrs))
        return self

    def method(self, name: str, code: bytes, desc: str = "()V") -> "ClassBuilder":
        body = struct.pack(">HHI", 8, 4, len(code)) + code + struct.pack(">HH", 0, 0)
        attr = struct.pack(">HI", self.utf8("Code"), len(body)) + body
        self.methods.append(struct.pack(">HHHH", 1, self.utf8(name), self.utf8(desc), 1) + attr)
        return self

    def build(self) -> bytes:
        out = b"\xca\xfe\xba\xbe" + struct.pack(">HHH", 0, 52, len(self.pool) + 1) + b"".join(self.pool)
        out += struct.pack(">HHHH", 0x21, self.this_idx, self.super_idx, len(self.iface_idx))
        out += b"".join(struct.pack(">H", i) for i in self.iface_idx)
        out += struct.pack(">H", len(self.fields)) + b"".join(self.fields)
        return out + struct.pack(">H", len(self.methods)) + b"".join(self.methods) + struct.pack(">H", 0)


def jar_mod(root: Path, mod_id: str, classes: dict[str, bytes], files: dict[str, str] | None = None, **kwargs) -> Path:
    info = json.dumps({"id": mod_id, "name": kwargs.get("name", mod_id), "version": kwargs.get("version", "1"), "jars": ["jars/x.jar"]})
    mod = make_mod(root, mod_id, {"mod_info.json": info, **(files or {})}, name=kwargs.get("name"), folder=kwargs.get("folder"))
    make_jar(mod / "jars" / "x.jar", classes)
    return mod


def fact_rows(conn, mod: str, kind: str | None = None) -> set[tuple]:
    sql, args = "SELECT kind, id, action, confidence, evidence FROM facts WHERE mod = ?", [mod]
    if kind:
        sql, args = sql + " AND kind = ?", [mod, kind]
    return {tuple(r) for r in conn.execute(sql, args)}


class CallAttributionTests(unittest.TestCase):
    def test_ldc_is_attributed_to_the_call_that_consumes_it(self):
        b = ClassBuilder("a/Run")
        b.method("run", b.ldc("habitable") + b.invoke(*PRINT) + b.ldc("farming") + ALOAD_0 + b.invoke(MARKET, "removeIndustry", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        info = parse_class(b.build(), frozenset({"removeIndustry"}))
        self.assertTrue(info.code_ok)
        self.assertEqual([(c.name, c.args) for c in info.calls], [("removeIndustry", (("str", "farming", ""),))])

    def test_atlas_reads_replaced_ignores_a_class_that_only_contains_the_word(self):
        """67a: HegemonyHeavy holds "habitable" and calls removeCondition(variable); it must not look like it removes "habitable"."""
        heavy = ClassBuilder("a/HegemonyHeavy")
        heavy.method("run", heavy.ldc("habitable") + heavy.invoke(*PRINT) + ALOAD_0 + heavy.invoke(MARKET, "removeCondition", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        farm = ClassBuilder("a/Farm")
        farm.method("run", farm.ldc("farming") + farm.invoke(MARKET, "removeIndustry", STRING_CALL, INVOKE_INTERFACE)
                    + farm.ldc("aotd_farm") + farm.invoke(MARKET, "addIndustry", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        java = 'package r;\npublic class R { void go(MarketAPI m) { m.hasCondition("habitable"); m.getIndustry("farming"); } }\n'
        with temp_root() as root:
            make_vanilla(root, {"data/campaign/market_conditions.csv": CONDITIONS})
            jar_mod(root / "mods", "aotd_vok", {"a/HegemonyHeavy.class": heavy.build(), "a/Farm.class": farm.build()}, name="AoTD VoK")
            make_mod(root / "mods", "reader", {"data/scripts/R.java": java})
            db, _ = build(root)
            conn = atlas.connect(db)
            rows = fact_rows(conn, "aotd_vok")
            self.assertIn(("condition", "habitable", "references", "REVIEW", "literal: string constant equal to a known id"), rows)
            self.assertNotIn("habitable", {r[1] for r in rows if r[2] == "mutates"})
            self.assertIn(("industry", "farming", "mutates", "REVIEW", "method=removeIndustry (jar call site)"), rows)
            result = forecast(conn, atlas.resolve_mods(conn, ["reader"]), atlas.group_mods(conn, "aotd"))
            replaced = [f for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"]
            self.assertEqual([f.ids for f in replaced], [["farming", "aotd_farm"]])

    def test_atlas_reads_replaced_needs_an_addition_in_the_same_class(self):
        """A bare removal (AoTD's terraforming inserter: removeCondition("cold")) is a mutation, not a replacement, even when
        another class of the mod adds conditions (2026-10-11: cold/hot/very_cold were reported replaced for DNEEP)."""
        remover = ClassBuilder("a/Inserter")
        remover.method("run", remover.ldc("habitable") + remover.invoke(MARKET, "removeCondition", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        adder = ClassBuilder("a/Other")
        adder.method("run", adder.ldc("aotd_x") + adder.invoke(MARKET, "addCondition", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        java = 'package r;\npublic class R { void go(MarketAPI m) { m.hasCondition("habitable"); } }\n'
        with temp_root() as root:
            make_vanilla(root, {"data/campaign/market_conditions.csv": CONDITIONS})
            jar_mod(root / "mods", "aotd_vok", {"a/Inserter.class": remover.build(), "a/Other.class": adder.build()}, name="AoTD VoK")
            make_mod(root / "mods", "reader", {"data/scripts/R.java": java})
            db, _ = build(root)
            conn = atlas.connect(db)
            result = forecast(conn, atlas.resolve_mods(conn, ["reader"]), atlas.group_mods(conn, "aotd"))
            self.assertEqual([f for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"], [])

    def test_atlas_reads_replaced_a_bare_string_in_a_jar_is_a_mention_not_a_use(self):
        """javac inlines Industries.FARMING as "farming" into every jar that names it; only a call site is a use (AoTD sweep 2026-10-12)."""
        mention = ClassBuilder("m/Mention")
        mention.method("run", mention.ldc("farming") + mention.invoke(*PRINT) + RETURN)
        lookup = ClassBuilder("l/Lookup")
        lookup.method("run", lookup.ldc("farming") + ALOAD_0 + lookup.invoke(MARKET, "getIndustry", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "aotd_vok", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_subsidised_farming,Subsidised Farming,,farming\n"},
                     name="AoTD VoK")
            jar_mod(root / "mods", "mentions", {"m/Mention.class": mention.build()})
            jar_mod(root / "mods", "looks", {"l/Lookup.class": lookup.build()})
            db, _ = build(root)
            conn = atlas.connect(db)
            family = atlas.group_mods(conn, "aotd")
            by_mod = {}
            for mod_id in ("mentions", "looks"):
                result = forecast(conn, atlas.resolve_mods(conn, [mod_id]), family)
                by_mod[mod_id] = ([f.level for f in result["findings"] if f.rule == "ATLAS-READS-REPLACED"], result["verdicts"][mod_id]["status"])
            self.assertEqual(by_mod["mentions"][0], ["UNKNOWN"])
            self.assertTrue(by_mod["mentions"][1].startswith("UNKNOWN"))
            self.assertEqual(by_mod["looks"], (["REVIEW"], "REVIEW"))

    def test_unscanned_class_falls_back_to_unknown_class_level_guess(self):
        b = ClassBuilder("a/Broken")
        b.string("farming")
        b.ref(10, MARKET, "removeIndustry", STRING_CALL)
        b.method("run", b"\xfe")  # not a valid opcode: the scan fails, the constant pool still reads
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "brokenmod", {"a/Broken.class": b.build()})
            db, _ = build(root)
            conn = atlas.connect(db)
            rows = fact_rows(conn, "brokenmod", "industry")
            self.assertEqual({(r[1], r[2], r[3]) for r in rows}, {("farming", "mutates", "UNKNOWN")})
            profile = build_profile("brokenmod", load_facts(conn, [m for m in atlas.latest_mods(conn) if m["id"] == "brokenmod"]))
            self.assertEqual(profile.replaced, {})


class ConstantTests(unittest.TestCase):
    def test_atlas_reads_missing_resolves_mod_constants_and_names_the_closest_provider_id(self):
        """67b: Tritachyon x TASC. The mod's own BoggledIndustries.AI_STATION is not an id the provider defines."""
        loose = ('package tri;\npublic class TriCondition {\n  void go(MarketAPI m) { m.getIndustry(BoggledIndustries.AI_STATION); }\n}\n')
        constants = 'package tri;\npublic class BoggledIndustries {\n  public static final String AI_STATION = "BOGGLED_AI_STATION";\n}\n'
        ids = ClassBuilder("j/Ids").field("AI_STATION", "Ljava/lang/String;", ACC_STATIC | ACC_FINAL, constant="BOGGLED_AI_STATION")
        user = ClassBuilder("j/User")
        user.method("go", ALOAD_0 + user.getstatic("j/Ids", "AI_STATION") + user.invoke(MARKET, "getIndustry", STRING_CALL, INVOKE_INTERFACE) + RETURN)
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "tritachyon_like", {"data/scripts/TriCondition.java": loose, "data/scripts/BoggledIndustries.java": constants})
            jar_mod(root / "mods", "jar_like", {"j/Ids.class": ids.build(), "j/User.class": user.build()})
            make_mod(root / "mods" / "nested", "tasc_provider", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "BOGGLED_REMNANT_STATION,Remnant Station,,\n"},
                     name="Terraforming & Station Construction", folder="Terraforming & Station Construction")
            db, stats = build(root)
            conn = atlas.connect(db)
            self.assertIn("tasc_provider", {m["id"] for m in atlas.latest_mods(conn)})  # a provider mod anywhere under the roots is indexed
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            missing = {f.mods[0]: f for f in findings if f.rule == "ATLAS-READS-MISSING"}
            self.assertEqual(set(missing), {"tritachyon_like", "jar_like"})
            for finding in missing.values():
                self.assertEqual(finding.ids, ["BOGGLED_AI_STATION", "BOGGLED_REMNANT_STATION"])
                self.assertIn("closest id a provider does define: 'BOGGLED_REMNANT_STATION'", finding.summary)
            self.assertIn("BoggledIndustries.AI_STATION", missing["tritachyon_like"].sides[0]["evidence"])
            self.assertIn("BOGGLED_AI_STATION", {r[1] for r in fact_rows(conn, "jar_like", "industry") if r[2] == "reads" and r[3] == "REVIEW"})

    def test_unresolvable_constant_stays_dynamic_unknown(self):
        loose = 'package x;\npublic class X { void go(MarketAPI m) { m.getIndustry(Elsewhere.NAME); } }\n'
        facts = atlas_code._call_facts(loose, "X.java")
        self.assertEqual([(f.id, f.confidence) for f in facts], [("<dynamic>", "UNKNOWN")])
        self.assertIn("constref=Elsewhere.NAME", facts[0].evidence)


class OriginalsTests(unittest.TestCase):
    def test_include_originals_and_atlas_diff(self):
        with temp_root() as root:
            make_mod(root / "In operation" / "Foo" / "working", "foo", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "new_ind,New,,\nshared,Shared,,\n"}, version="1.1")
            make_mod(root / "In operation" / "Foo" / "original" / "Foo Mod", "foo", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "old_ind,Old,,\nshared,Shared,,\n"}, version="1.0")
            db = root / "atlas.sqlite"

            def run(*argv) -> tuple[int, str]:
                out = io.StringIO()
                with redirect_stdout(out), redirect_stderr(io.StringIO()):
                    return main(list(argv)), out.getvalue()

            code, text = run("atlas", "build", "--base", str(root), "--include-originals", "--quiet", "--json", "--db", str(db))
            self.assertEqual((code, json.loads(text)["mods"]), (0, 2))
            conn = atlas.connect(db)
            self.assertEqual({r["version"] for r in conn.execute("SELECT version FROM mods")}, {"1.1", "1.0+original"})
            self.assertEqual([m["version"] for m in atlas.latest_mods(conn)], ["1.1"])  # the working copy stays the current one
            conn.close()
            code, text = run("atlas", "diff", "foo", "--json", "--db", str(db))
            data = json.loads(text)[0]
            self.assertEqual(([r["id"] for r in data["only_working"]], [r["id"] for r in data["only_original"]]), (["new_ind"], ["old_ind"]))
            code, text = run("atlas", "diff", "foo", "--db", str(db))
            self.assertIn("only in the original", text)

    def test_diff_without_an_original_is_an_error(self):
        with temp_root() as root:
            make_mod(root / "mods", "lonely", {})
            db = root / "atlas.sqlite"
            atlas.build_atlas([root / "mods"], db, quiet=True)
            with redirect_stderr(io.StringIO()):
                self.assertEqual(main(["atlas", "diff", "lonely", "--db", str(db)]), 2)


class IndexedKindTests(unittest.TestCase):
    def test_ship_wpn_planet_terrain_and_settings_lists_are_indexed(self):
        files = {
            "data/hulls/zeta.ship": '{"hullId":"zeta_hull"}',
            "data/weapons/gun.wpn": '{"id":"zeta_gun"}',
            "data/config/planets.json": '{"zeta_world":{"name":"Z"},"note":1}',
            "data/config/settings.json": '{"maxShips":5,"graphics":{"terrain":{"zeta_nebula":"graphics/z.png"}},"shipRoles":["a","b"]}',
        }
        other = {"data/config/settings.json": '{"maxShips":7,"shipRoles":["c"]}'}
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "zeta", files)
            make_mod(root / "mods", "other", other)
            db, _ = build(root)
            conn = atlas.connect(db)
            rows = {(r[0], r[1], r[2]) for r in conn.execute("SELECT kind, id, action FROM facts WHERE mod = 'zeta'")}
            for expected in [("hull-file", "zeta_hull", "defines"), ("weapon-file", "zeta_gun", "defines"), ("planet-type", "zeta_world", "defines"),
                             ("terrain", "zeta_nebula", "defines"), ("setting-list", "shipRoles", "appends")]:
                self.assertIn(expected, rows)
            self.assertNotIn(("planet-type", "note", "defines"), rows)
            self.assertEqual(sorted(r[0] for r in conn.execute("SELECT evidence FROM facts WHERE mod = 'zeta' AND kind = 'setting-list'")), ['"a"', '"b"'])
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            overrides = [f for f in findings if f.rule == "ATLAS-SETTINGS-OVERRIDE"]
            self.assertEqual([f.ids for f in overrides], [["maxShips"]])  # the differing lists append; only the scalar overrides

    def test_atlas_save_holds_heavy_sees_collection_signatures_and_skips_synthetic_fields(self):
        script = (ClassBuilder("s/Tick", interfaces=("com/fs/starfarer/api/EveryFrameScript",))
                  .field("markets", "Ljava/util/List;", 0, signature="Ljava/util/List<" + HEAVY_MARKET + ">;")
                  .field("this$0", HEAVY_MARKET, ACC_SYNTHETIC).field("val$m", HEAVY_MARKET, ACC_SYNTHETIC).field("names", "Ljava/util/List;", 0,
                                                                                                                  signature="Ljava/util/List<Ljava/lang/String;>;"))
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "listmod", {"s/Tick.class": script.build()})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            heavy = [f for f in findings if f.rule == "ATLAS-SAVE-HOLDS-HEAVY"]
            self.assertEqual([f.ids for f in heavy], [["s.Tick.markets"]])
            self.assertIn("inside a collection", heavy[0].sides[0]["evidence"])


class RegisteredScriptTests(unittest.TestCase):
    def _registrar(self, method: str, target: str):
        b = ClassBuilder("r/Plugin")
        b.method("onGameLoad", b.invoke("com/fs/starfarer/api/Global", "getSector", "()Lcom/fs/starfarer/api/campaign/SectorAPI;", INVOKE_STATIC)
                 + b.new(target) + DUP + b.invoke(target, "<init>", "()V", INVOKE_SPECIAL)
                 + b.invoke("com/fs/starfarer/api/campaign/SectorAPI", method, "(Lcom/fs/starfarer/api/EveryFrameScript;)V", INVOKE_INTERFACE) + RETURN)
        return b

    def test_registrations_are_read_from_new_x_before_addscript(self):
        info = parse_class(self._registrar("addScript", "r/Saved").build())
        self.assertEqual(info.registrations, [("addScript", "r/Saved")])

    def test_atlas_save_holds_heavy_follows_addscript_and_addtransientscript(self):
        saved = ClassBuilder("r/Saved").field("market", HEAVY_MARKET)  # no saved base: only addScript makes it saved
        transient = ClassBuilder("r/Temp", interfaces=("com/fs/starfarer/api/EveryFrameScript",)).field("market", HEAVY_MARKET)
        with temp_root() as root:
            make_vanilla(root)
            jar_mod(root / "mods", "scripts", {"r/Plugin.class": self._registrar("addScript", "r/Saved").build(), "r/Saved.class": saved.build(),
                                                "r/Plugin2.class": self._registrar("addTransientScript", "r/Temp").build(), "r/Temp.class": transient.build()})
            db, _ = build(root)
            conn = atlas.connect(db)
            findings, _ = analyze(conn, atlas.latest_mods(conn))
            heavy = [f.ids for f in findings if f.rule == "ATLAS-SAVE-HOLDS-HEAVY"]
            self.assertEqual(heavy, [["r.Saved.market"]])  # the transient script is not saved
            hooks = {r["id"] for r in conn.execute("SELECT id FROM facts WHERE kind = 'hook' AND evidence LIKE 'jar: add%'")}
            self.assertEqual(hooks, {"r.Saved", "r.Temp"})


class PrefixTests(unittest.TestCase):
    def test_prefix_is_recorded_and_resolved_to_known_ids_in_loose_java(self):
        java = 'package p;\npublic class P { void go(MarketAPI m, String s) { m.getIndustry("aotd_" + s); m.getIndustry("x" + s); } }\n'
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "aotd_base", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_one,One,,\naotd_two,Two,,\n"})
            make_mod(root / "mods", "dyn", {"data/scripts/P.java": java})
            db, _ = build(root)
            conn = atlas.connect(db)
            rows = fact_rows(conn, "dyn", "industry")
            self.assertIn(("industry", "<dynamic>", "reads", "UNKNOWN", "method=getIndustry non-literal argument: \"aotd_\" + s prefix=aotd_"), rows)
            resolved = {(r[1], r[3]) for r in rows if r[4].startswith("prefix-resolved:")}
            self.assertEqual(resolved, {("aotd_one", "REVIEW"), ("aotd_two", "REVIEW")})  # "x" is too short to resolve
            shown = show_text(show_data(conn, [m for m in atlas.latest_mods(conn) if m["id"] == "dyn"]), 25)
            self.assertIn("prefix-resolved", shown)
            self.assertIn("prefix=aotd_", shown)

    def test_stringbuilder_concatenation_prefix_in_a_jar(self):
        sb = "java/lang/StringBuilder"
        b = ClassBuilder("p/Build")
        b.method("go", b.new(sb) + DUP + b.invoke(sb, "<init>", "()V", INVOKE_SPECIAL) + b.ldc("aotd_")
                 + b.invoke(sb, "append", "(Ljava/lang/String;)Ljava/lang/StringBuilder;") + ALOAD_0
                 + b.invoke(sb, "append", "(Ljava/lang/String;)Ljava/lang/StringBuilder;") + b.invoke(sb, "toString", "()Ljava/lang/String;")
                 + b.invoke(MARKET, "getIndustry", "(Ljava/lang/String;)Lcom/fs/starfarer/api/campaign/econ/Industry;", INVOKE_INTERFACE) + RETURN)
        info = parse_class(b.build(), frozenset({"getIndustry"}))
        self.assertEqual([(c.name, c.args) for c in info.calls], [("getIndustry", (("prefix", "aotd_", ""),))])
        with temp_root() as root:
            make_vanilla(root)
            make_mod(root / "mods", "aotd_base", {"data/campaign/industries.csv": INDUSTRIES_HEADER + "aotd_one,One,,\n"})
            jar_mod(root / "mods", "jarprefix", {"p/Build.class": b.build()})
            db, _ = build(root)
            conn = atlas.connect(db)
            resolved = {r[1] for r in fact_rows(conn, "jarprefix", "industry") if r[4].startswith("prefix-resolved:")}
            self.assertEqual(resolved, {"aotd_one"})


if __name__ == "__main__":
    unittest.main()
