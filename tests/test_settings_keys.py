"""settings-key-missing (owner crash log 2026-10-04): Exigency 0.8 read settings RC8 does not have."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bridgeforge.scan.scanner import scan_mod
from bridgeforge.settings_keys import javap_reads, javap_writes, loose_script_class, source_reads, source_writes

FIXTURES = Path(__file__).resolve().parent / "fixtures"

LISTING = """  public void updateCargoPrePlayerInteraction();
    Code:
     120: invokestatic  #40                 // Method com/fs/starfarer/api/Global.getSettings:()Lcom/fs/starfarer/api/SettingsAPI;
     123: ldc           #44                 // String blackMarketMinSupplies
     125: invokeinterface #46,  2           // InterfaceMethod com/fs/starfarer/api/SettingsAPI.getFloat:(Ljava/lang/String;)F
     130: ldc           #50                 // String unrelated
     132: aload_1
     133: invokeinterface #46,  2           // InterfaceMethod com/fs/starfarer/api/SettingsAPI.getFloat:(Ljava/lang/String;)F
"""


class SettingsKeysTests(unittest.TestCase):
    def test_source_and_javap_reads(self) -> None:
        self.assertEqual(source_reads('float a = Global.getSettings().getFloat("blackMarketMinFuel");\nint b = Global.getSettings().getInt("x");'),
                         [(1, "getFloat", "blackMarketMinFuel"), (2, "getInt", "x")])
        # The second getFloat takes a variable (aload_1 came between): not a literal read.
        self.assertEqual(javap_reads(LISTING), [("getFloat", "blackMarketMinSupplies")])

    def test_scan_flags_only_keys_no_settings_json_defines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core" / "data" / "config"
            core.mkdir(parents=True)
            (core / "settings.json").write_text('{"sensorRangeMult": 1, "shipMaxBurn": 20}', encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "config").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "config" / "settings.json").write_text('{"fxOwnKey": 3}', encoding="utf-8")
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "data" / "scripts" / "P.java").write_text(
                'class P { void a() { Global.getSettings().getFloat("blackMarketMinSupplies"); '
                'Global.getSettings().getFloat("shipMaxBurn"); Global.getSettings().getInt("fxOwnKey"); } }', encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "settings-key-missing"]
        self.assertEqual([f.evidence[0] for f in found], ["key:blackMarketMinSupplies"])

    def test_a_key_the_mod_sets_itself_is_not_missing(self) -> None:
        # Wide Horizons 1.5.1b (98.8) sets its LunaLib values with setFloat before reading them; here in a loose script.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core" / "data" / "config"
            core.mkdir(parents=True)
            (core / "settings.json").write_text('{"shipMaxBurn": 20}', encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "wh"}', encoding="utf-8")
            (mod / "data" / "scripts" / "Plugin.java").write_text(
                'package data.scripts;\nclass Plugin { void a() { Global.getSettings().setFloat("coreWorldScale", 1.5f); }\n'
                ' void b() { Global.getSettings().getFloat("coreWorldScale"); Global.getSettings().getFloat("neverSet"); } }',
                encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "settings-key-missing"]
        self.assertEqual([f.evidence[0] for f in found], ["key:neverSet"])

    def test_a_key_a_jar_sets_is_not_missing_for_any_read_in_the_mod(self) -> None:
        from types import SimpleNamespace
        from unittest import mock

        from bridgeforge.settings_keys import JarSettings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core" / "data" / "config"
            core.mkdir(parents=True)
            (core / "settings.json").write_text('{"shipMaxBurn": 20}', encoding="utf-8")
            mod = root / "mod"
            (mod / "jars" / "old").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "wh", "jars": ["jars/wh.jar"]}', encoding="utf-8")
            (mod / "jars" / "wh.jar").write_bytes(b"")
            (mod / "jars" / "old" / "wh-1.4.jar").write_bytes(b"")  # a leftover mod_info.json does not list: never loaded
            # A loose script reads a key only the jar sets: one mod, one set of written keys.
            (mod / "data" / "scripts").mkdir(parents=True)
            (mod / "data" / "scripts" / "P.java").write_text('class P { void a() { Global.getSettings().getFloat("setByJar"); } }',
                                                             encoding="utf-8")
            reads = [("p/A.class", getter, key) for getter, key in (("getFloat", "setByJar"), ("getFloat", "neverSet"),
                                                                     ("getInt", "setByJar"), ("getFloat", "flagSet"),
                                                                     ("getBoolean", "flagSet"), ("getFloat", "byOldJar"))]
            by_jar = {"wh.jar": JarSettings(reads, frozenset({("setByJar", "float"), ("flagSet", "boolean")})),
                      "wh-1.4.jar": JarSettings([], frozenset({("byOldJar", "float")}))}
            with mock.patch("bridgeforge.scan.scan_settings._JDK_FOR_PROCGEN", [SimpleNamespace(javap=root / "javap")]), \
                    mock.patch("bridgeforge.settings_keys.jar_settings", side_effect=lambda jar, _javap: by_jar[jar.name]):
                found = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "settings-key-missing"]
        # getInt reads the float that setFloat wrote; a boolean read as a float, and a key only an unloaded jar sets, are misses.
        self.assertEqual(sorted((f.evidence[1], f.evidence[0]) for f in found),
                         [("call:getFloat", "key:byOldJar"), ("call:getFloat", "key:flagSet"), ("call:getFloat", "key:neverSet")])

    def test_writes_in_sources_the_game_never_runs_define_nothing(self) -> None:
        # Review of 98.8: a bundled src/ tree does not run, nor a loose script whose class the jar also defines (the jar wins).
        import zipfile
        from types import SimpleNamespace
        from unittest import mock

        from bridgeforge.settings_keys import JarSettings

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core" / "data" / "config"
            core.mkdir(parents=True)
            (core / "settings.json").write_text('{"shipMaxBurn": 20}', encoding="utf-8")
            mod = root / "mod"
            (mod / "jars").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "wh", "jars": ["jars/wh.jar"]}', encoding="utf-8")
            with zipfile.ZipFile(mod / "jars" / "wh.jar", "w") as jar:
                jar.writestr("data/scripts/Shadowed.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
            for relative, cls, key in (("src/p/Plugin.java", "p", "bySrc"), ("data/scripts/Shadowed.java", "data.scripts", "byShadowed"),
                                       ("data/scripts/Runs.java", "data.scripts", "byLoose")):
                (mod / relative).parent.mkdir(parents=True, exist_ok=True)
                (mod / relative).write_text(f'package {cls};\nclass X {{ void a() {{ Global.getSettings().setFloat("{key}", 1f); }} }}',
                                            encoding="utf-8")
            jar_found = JarSettings([("p/A.class", "getFloat", key) for key in ("bySrc", "byShadowed", "byLoose")], frozenset())
            with mock.patch("bridgeforge.scan.scan_settings._JDK_FOR_PROCGEN", [SimpleNamespace(javap=root / "javap")]), \
                    mock.patch("bridgeforge.settings_keys.jar_settings", return_value=jar_found):
                found = [f for f in scan_mod(mod, vanilla_core=root / "core").findings if f.id == "settings-key-missing"]
        self.assertEqual(sorted(f.evidence[0] for f in found), ["key:byShadowed", "key:bySrc"])


def _method(code: str, table: str = "") -> str:
    """A javap -c method listing: instruction lines, then an exception table when given."""
    lines = ["  private static float m(float);", "    Code:", *[f"      {line}" for line in code.strip().splitlines()]]
    if table:
        lines += ["      Exception table:", "         from    to  target type", *[f"         {row}" for row in table.strip().splitlines()]]
    return "\n".join(lines) + "\n"


_GET = "invokestatic  #44                 // Method com/fs/starfarer/api/Global.getSettings:()Lcom/fs/starfarer/api/SettingsAPI;"
_READ = "invokeinterface #437,  2          // InterfaceMethod com/fs/starfarer/api/SettingsAPI.getFloat:(Ljava/lang/String;)F"
_SET = "invokeinterface #488,  3          // InterfaceMethod com/fs/starfarer/api/SettingsAPI.setFloat:(Ljava/lang/String;Ljava/lang/Float;)V"
_VALUE_OF = "invokestatic  #443                // Method java/lang/Float.valueOf:(F)Ljava/lang/Float;"
# Wide Horizons 1.5.1b WHPulseStarTerrainPlugin.toDays, as javap printed it (2026-11-26).
_TO_DAYS = f"""
 0: {_GET}
 3: ldc_w         #435                // String campaignSecondsPerDay
 6: {_READ}
11: fstore_1
12: fload_0
13: fload_1
14: fdiv
15: freturn
16: astore_1
17: fload_0
18: ldc           #214                // float 10.0f
20: fdiv
21: freturn
"""
_RETHROWS = f"""
 0: {_GET}
 3: ldc           #46                 // String k
 5: {_READ}
10: freturn
11: astore_1
12: new           #50                 // class java/lang/RuntimeException
15: dup
16: aload_1
17: invokespecial #52                 // Method java/lang/RuntimeException."<init>":(Ljava/lang/Throwable;)V
20: athrow
"""
_BRANCHES = f"""
 0: {_GET}
 3: ldc           #46                 // String k
 5: {_READ}
10: freturn
11: astore_1
12: aload_1
13: ifnonnull     18
16: fconst_0
17: freturn
18: aload_1
19: athrow
"""


class ReadsUnderACatchTests(unittest.TestCase):
    """98.8: RC9's getters rethrow a missing key as RuntimeException(JSONException) (javap 2026-11-26)."""

    def test_a_read_under_a_throwable_catch_that_returns_a_fallback_is_not_a_miss(self) -> None:
        self.assertEqual(javap_reads(_method(_TO_DAYS, "0    15    16   Class java/lang/Throwable")), [])
        self.assertEqual(javap_reads(_method(_TO_DAYS, "0    15    16   Class java/lang/RuntimeException")), [])
        self.assertEqual(javap_reads(_method(_TO_DAYS, "0    15    16   Class java/lang/Exception")), [])

    def test_a_catch_that_cannot_stop_the_runtime_exception_still_reports(self) -> None:
        expected = [("getFloat", "campaignSecondsPerDay")]
        self.assertEqual(javap_reads(_method(_TO_DAYS)), expected)  # no try at all
        self.assertEqual(javap_reads(_method(_TO_DAYS, "0    15    16   Class org/json/JSONException")), expected)
        self.assertEqual(javap_reads(_method(_RETHROWS, "0    10    11   any")), [("getFloat", "k")])  # a finally rethrows
        # The row ends before the call (`to` is exclusive) or starts after it.
        self.assertEqual(javap_reads(_method(_TO_DAYS, "0     6    16   Class java/lang/Throwable")), expected)
        self.assertEqual(javap_reads(_method(_TO_DAYS, "7    15    16   Class java/lang/Throwable")), expected)

    def test_a_handler_that_rethrows_or_branches_first_still_reports(self) -> None:
        # catch (Exception e) { throw new RuntimeException(e); }: the usual wrapper still crashes.
        self.assertEqual(javap_reads(_method(_RETHROWS, "0    10    11   Class java/lang/Exception")), [("getFloat", "k")])
        # A conditional before the handler leaves is undecided: report.
        self.assertEqual(javap_reads(_method(_BRANCHES, "0    10    11   Class java/lang/Throwable")), [("getFloat", "k")])

    def test_a_finally_that_returns_swallows_as_the_jvm_does(self) -> None:
        # `finally { return x; }` discards the exception in Java: an `any` row whose handler returns.
        self.assertEqual(javap_reads(_method(_TO_DAYS, "0    15    16   any")), [])

    def test_javac_shapes_that_still_crash_are_reported_and_real_swallows_are_not(self) -> None:
        """Review of 98.8, compiled by javac (tests/fixtures/settings_keys_javac_shapes.txt): the first version took any goto
        in a handler for a swallow and any covering row for the one the JVM uses, and dropped all five reads.
        - orderedKey: `catch (RuntimeException e) { throw e; } catch (Exception e) { return 1f; }`: the first matching row
          rethrows;
        - twrKey: try-with-resources, whose Throwable handler closes and jumps to an athrow;
        - logKey: a try inside the catch, then `throw e`; syncKey: a synchronized block inside the catch, then `throw t`;
        - errorKey: the handler throws `new Error(e)`, and the outer `catch (Exception)` cannot stop an Error (after a rethrow
          the thrown class is unknown, so only a Throwable row counts);
        - branchKey: the first matching handler branches (`if (flag) throw e;`): undecided, though a later row returns;
        - swallowedKey, gotoKey (a RuntimeException handler that leaves by goto to a return), pastThrowKey (the same, with
          the next handler's athrow right after the goto) and outerKey (a rethrow that an outer `catch (Throwable)` turns
          into a return) do swallow.
        Second review (class Q and V):
        - helperKey (`fail(e); return 0f;`, fail throws), resultKey (`rethrowIfFailed(failure)` after the catch), savedKey
          (`if (saved != null) throw saved;`): a call or a branch on the handler's path is undecided;
        - finExcKey (a finally, then only `catch (IllegalStateException)`), errOnlyKey (`catch (Error)`), iseKey (a
          multi-catch of two subclasses), cfKey (a subclass catch plus a finally): nothing stops the RuntimeException;
        - siblingKey: the inner rethrow reaches `catch (Exception)`, which throws past its sibling `catch (Throwable)`;
          switchKey: a switch in the handler;
        - finThrKey (a finally into `catch (Throwable)`), breakKey (a labelled break) and syncInKey (a synchronized block
          inside `catch (Throwable)`) do swallow;
        - k2 and nameKey are plain reads in a setter's value and key."""
        listing = (FIXTURES / "settings_keys_javac_shapes.txt").read_text(encoding="utf-8")
        reported = {key for _getter, key in javap_reads(listing)}
        self.assertEqual(reported, {"orderedKey", "twrKey", "logKey", "syncKey", "errorKey", "branchKey", "helperKey", "resultKey",
                                    "savedKey", "finExcKey", "errOnlyKey", "iseKey", "cfKey", "siblingKey", "switchKey", "k2",
                                    "nameKey"})

    def test_a_switchs_case_lines_are_not_instructions(self) -> None:
        # javap prints a switch's cases as `<key>: <target>`. A case key equal to the handler's offset must not be taken for the
        # handler: the walk would start at the switch's own `return` instead of the handler's athrow.
        listing = _method(f"""
 0: iload_0
 1: lookupswitch  {{ // 1
              41: 28
         default: 30
    }}
28: fconst_0
29: freturn
30: {_GET}
33: ldc           #46                 // String switchKey2
35: {_READ}
40: freturn
41: astore_1
42: aload_1
43: athrow
""", "30    40    41   Class java/lang/Throwable")
        self.assertEqual(javap_reads(listing), [("getFloat", "switchKey2")])

    def test_a_handler_that_loops_is_undecided(self) -> None:
        looping = _TO_DAYS.replace("17: fload_0\n18: ldc           #214                // float 10.0f\n20: fdiv\n21: freturn",
                                   "17: goto          16")
        self.assertIn("goto          16", looping)
        self.assertEqual(javap_reads(_method(looping, "0    15    16   Class java/lang/Throwable")), [("getFloat", "campaignSecondsPerDay")])

    def test_the_exception_table_belongs_to_its_own_method(self) -> None:
        caught = _method(_TO_DAYS, "0    15    16   Class java/lang/Throwable")
        self.assertEqual(javap_reads(caught + _method(_TO_DAYS)), [("getFloat", "campaignSecondsPerDay")])


class SettingsWritesTests(unittest.TestCase):
    def test_both_setter_shapes_wide_horizons_uses_are_writes(self) -> None:
        # WHSectorHelper (javap 2026-11-26): `fload; Float.valueOf` and `iload; i2f; Float.valueOf`.
        listing = _method(f"""
 784: {_GET}
 787: ldc_w         #364                // String sectorWidth
 790: fload         4
 792: {_VALUE_OF}
 795: {_SET}
 832: {_GET}
 835: ldc_w         #492                // String constellationCount
 838: iload         10
 840: i2f
 841: {_VALUE_OF}
 844: {_SET}
 849: return
""")
        self.assertEqual(javap_writes(listing), {("sectorWidth", "float"), ("constellationCount", "float")})

    def test_a_getter_nested_in_the_value_is_not_the_written_key(self) -> None:
        listing = _method(f"""
 0: {_GET}
 3: ldc           #1                  // String written
 5: {_GET}
 8: ldc           #2                  // String onlyRead
10: {_READ}
15: {_VALUE_OF}
18: {_SET}
23: return
""")
        self.assertEqual(javap_writes(listing), {("written", "float")})

    def test_a_receiver_that_is_stored_or_passed_on_lends_no_key(self) -> None:
        stored = _method(f"""
 0: {_GET}
 3: astore_1
 4: aload_1
 5: ldc           #1                  // String viaLocal
 7: fconst_1
 8: {_VALUE_OF}
11: {_SET}
""")
        passed = _method(f"""
 0: {_GET}
 3: ldc           #1                  // String argument
 5: invokestatic  #9                  // Method p/Helper.use:(Lcom/fs/starfarer/api/SettingsAPI;Ljava/lang/String;)F
 8: aload_1
 9: ldc           #2                  // String viaLocal
11: fconst_1
12: {_VALUE_OF}
15: {_SET}
""")
        passed_void = passed.replace(")F\n", ")V\n")
        # Handed on as an Object (no SettingsAPI parameter): only the statement's end lets go of its key.
        as_object = passed.replace("p/Helper.use:(Lcom/fs/starfarer/api/SettingsAPI;Ljava/lang/String;)F",
                                   "p/Helper.use:(Ljava/lang/Object;Ljava/lang/String;)F").replace(" 8: aload_1", " 8: astore_3\n       9: aload_1")
        as_object_void = passed.replace("p/Helper.use:(Lcom/fs/starfarer/api/SettingsAPI;Ljava/lang/String;)F",
                                        "p/Helper.log:(Ljava/lang/Object;Ljava/lang/String;)V")
        non_literal = _method(f"""
 0: {_GET}
 3: aload_2
 4: fconst_1
 5: {_VALUE_OF}
 8: {_SET}
""")
        # Wrap.of(getSettings(), "wrapped").setFloat("j", G.f(getSettings())): two receivers still open at the setter, and
        # neither is its own.
        returned = _method(f"""
 0: {_GET}
 3: ldc           #1                  // String wrapped
 5: invokestatic  #9                  // Method p/Wrap.of:(Ljava/lang/Object;Ljava/lang/String;)Lcom/fs/starfarer/api/SettingsAPI;
 8: ldc           #2                  // String j
10: {_GET}
13: invokestatic  #8                  // Method p/G.f:(Ljava/lang/Object;)F
16: {_VALUE_OF}
19: {_SET}
""")
        for listing in (stored, passed, passed_void, as_object, as_object_void, non_literal, returned):
            self.assertEqual(javap_writes(listing), set(), listing)

    def test_a_jar_gives_its_reads_and_its_writes_from_one_listing(self) -> None:
        import zipfile
        from unittest import mock

        from bridgeforge.settings_keys import jar_settings

        setter = _method(f"""
 0: {_GET}
 3: ldc           #1                  // String byJar
 5: fconst_1
 6: {_VALUE_OF}
 9: {_SET}
""")
        with tempfile.TemporaryDirectory() as directory:
            jar = Path(directory) / "wh.jar"
            with zipfile.ZipFile(jar, "w") as archive:
                archive.writestr("p/A.class", b"\xca\xfe\xba\xbe com/fs/starfarer/api/SettingsAPI")
                archive.writestr("p/B.class", b"\xca\xfe\xba\xbe com/fs/starfarer/api/SettingsAPI")
            listings = {"p/A.class": setter, "p/B.class": _method(_TO_DAYS)}
            with mock.patch("bridgeforge.settings_keys.class_listings", return_value=listings):
                found = jar_settings(jar, Path(directory) / "javap")
        self.assertEqual(found.writes, frozenset({("byJar", "float")}))
        self.assertEqual(found.reads, [("p/B.class", "getFloat", "campaignSecondsPerDay")])

    def test_the_stack_decides_which_literal_is_the_written_key(self) -> None:
        # Review of 98.8 (javac): setFloat(key("prefixedWidth"), 2f), setBoolean("boolCond", id != null) and
        # setFloat("prefix_".concat(id), 3f) name no key; setFloat("literalKey", 1.5f) and setFloat("boxedKey", new Float(2f))
        # do. use(getSettings(), "argument") before setFloat("realKey", 1f) is not the setter's receiver; (float) i++ holds an
        # iinc, which the stack model leaves out, so incKey is a missed write (reported, the safe side).
        # Second review (class Q): arrKey (arr[0]), k1 (a getter in the value), dk ((float) Math.sqrt) and boolKey
        # (Boolean.TRUE) are boxed or constant, so written. castKey ((Float) obj), lunaKey (a Float from a call), lam and mapKey
        # may be null, and a null write breaks the next read: missed. Branching values and keys are missed too.
        listing = (FIXTURES / "settings_keys_javac_shapes.txt").read_text(encoding="utf-8")
        self.assertEqual(javap_writes(listing), {("literalKey", "float"), ("boxedKey", "float"), ("realKey", "float"),
                                                 ("arrKey", "float"), ("k1", "float"), ("dk", "float"), ("boolKey", "boolean")})

    def test_source_writes(self) -> None:
        self.assertEqual(source_writes('Global.getSettings().setFloat("a", 1f); Global.getSettings().setBoolean("b", true);'
                                       ' Global.getSettings().getFloat("c"); s.setFloat("d", 2f);'), {("a", "float"), ("b", "boolean")})
        # The literal must be the whole key, the receiver the game's Global, and the value a literal (anything else may be null).
        self.assertEqual(source_writes('Global.getSettings().setFloat("wh_" + key, v); '
                                       'Global.getSettings().setBoolean("a".concat(b), true); '
                                       'Config.getSettings().setFloat("own", 1f); Global.getSettings().setFloat("boxed", value);'), set())

    def test_only_a_loose_script_the_game_runs_is_one(self) -> None:
        self.assertEqual(loose_script_class("data/scripts/Plugin.java", "package data.scripts;\nclass Plugin {}"),
                         "data.scripts.Plugin")
        self.assertEqual(loose_script_class("Data/scripts/Plugin.java", "package data.scripts;"), "data.scripts.Plugin")
        self.assertIsNone(loose_script_class("src/p/Plugin.java", "package p;"))  # a bundled source tree
        self.assertIsNone(loose_script_class("jars/src/p/Plugin.java", "package p;"))
        self.assertIsNone(loose_script_class("scripts/Foo.java", "package scripts;"))  # outside data/: not counted
        self.assertIsNone(loose_script_class("data/scripts/Plugin.java", "class Plugin {}"))  # no package: not loadable by name
        # The package must match the folders: the script loader finds data.scripts.Gen at data/scripts/Gen.java only.
        self.assertIsNone(loose_script_class("data/scripts/world/Gen.java", "package data.scripts;"))
        self.assertEqual(loose_script_class("data/scripts/world/Gen.java", "package data.scripts.world;"), "data.scripts.world.Gen")


if __name__ == "__main__":
    unittest.main()


class FactionKnownTagTests(unittest.TestCase):
    # Owner report 2026-10-04: Exigency's ships could not be bought; knownShips' tag exigency_bp was on no hull.
    def test_a_known_tag_no_hull_carries_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core"
            (core / "data" / "hulls").mkdir(parents=True)
            (core / "data" / "hulls" / "ship_data.csv").write_text("name,id,tags\nWolf,wolf,base_bp\n", encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "hulls").mkdir(parents=True)
            (mod / "data" / "world" / "factions").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "hulls" / "ship_data.csv").write_text("name,id,tags\nA,fx_a,\nB,fx_b,fx_other\n", encoding="utf-8")
            # Exigency's shape: its own tag dead, base_bp matching only vanilla hulls -> knows none of its own ships.
            (mod / "data" / "world" / "factions" / "fx.faction").write_text(
                '{"id": "fx", "knownShips": {"tags": ["fx_bp", "base_bp"], "hulls": []}}', encoding="utf-8")
            # A dead tag beside one that covers the mod's ships is harmless (2026-10-05 refinement).
            (mod / "data" / "world" / "factions" / "fy.faction").write_text(
                '{"id": "fy", "knownShips": {"tags": ["fy_bp", "fx_other"], "hulls": []}}', encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "faction-known-tag-unmatched"]
        self.assertEqual([(f.file.split("/")[-1], f.evidence) for f in found], [("fx.faction", ["list:knownShips", "tag:fx_bp"])])

    def test_skin_tags_and_tags_vanilla_factions_use_are_not_flagged(self) -> None:
        # done-audit 2026-10-04: Amogus' hegemony.faction (XIV_bp on vanilla skins; knownWeapons tag "hegemony").
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            core = root / "core"
            (core / "data" / "hulls" / "skins").mkdir(parents=True)
            (core / "data" / "world" / "factions").mkdir(parents=True)
            (core / "data" / "hulls" / "ship_data.csv").write_text("name,id,tags\nWolf,wolf,base_bp\n", encoding="utf-8")
            (core / "data" / "hulls" / "skins" / "wolf_xiv.skin").write_text('{"skinHullId": "wolf_xiv", "tags": ["XIV_bp"]}', encoding="utf-8")
            (core / "data" / "world" / "factions" / "hegemony.faction").write_text(
                '{"id": "hegemony", "knownWeapons": {"tags": ["hegemony"]}}', encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "world" / "factions").mkdir(parents=True)
            (mod / "mod_info.json").write_text('{"id": "fx"}', encoding="utf-8")
            (mod / "data" / "world" / "factions" / "hegemony.faction").write_text(
                '{"id": "hegemony", "knownShips": {"tags": ["XIV_bp"]}, "knownWeapons": {"tags": ["hegemony"]}}', encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=core).findings if f.id == "faction-known-tag-unmatched"]
        self.assertEqual(found, [])


class GuardedSettingsReadTests(unittest.TestCase):
    def test_a_read_behind_an_isModEnabled_guard_is_another_mods_setting(self) -> None:
        # Kadur Remnant (2026-10-05): isModEnabled("IndEvo") && getBoolean("PirateHaven"), IndEvo's own key.
        text = ('if (Global.getSettings().getModManager().isModEnabled("IndEvo") && Global.getSettings().getBoolean("PirateHaven")) {}\n'
                'boolean b = Global.getSettings().getBoolean("ownKey");\n')
        self.assertEqual(source_reads(text), [(2, "getBoolean", "ownKey")])
