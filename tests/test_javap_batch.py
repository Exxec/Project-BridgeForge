"""ROADMAP-3 96.5 P1: the settings-key and procgen-argument checks launch javap once per jar, not once per class."""
from __future__ import annotations

import subprocess
import unittest
import zipfile
from unittest import mock

from bridgeforge.bytecode import javap_batch
from bridgeforge.bytecode.java_toolchain import find_jdk
from tests.support import resolved_temp_dir

# One javap call over three classes, in the shape JDK 25 prints (2026-11-17): a "Compiled from" line except for a class without
# a SourceFile attribute, the declaration at column 0, indented members, "}" at column 0. A string constant holding a newline
# and a brace stays escaped.
_BATCHED = """\
Compiled from "Outer.java"
public class p.Outer {
  static final java.lang.String FIELD = "x\\n}\\nclass evil.Fake {\\n";

  public float read(com.fs.starfarer.api.SettingsAPI);
    Code:
       0: aload_1
       1: ldc           #7                  // String someKey
       3: invokeinterface #9,  2            // InterfaceMethod com/fs/starfarer/api/SettingsAPI.getFloat:(Ljava/lang/String;)F
       8: freturn
}
Compiled from "Outer.java"
class p.Outer$Inner implements java.lang.Runnable {
  public void run();
    Code:
       0: return
}
public abstract class q.Gen<K, V> {
  public void generate(com.fs.starfarer.api.campaign.StarSystemAPI);
    Code:
      47: ldc           #49                 // String zorg_balls_star_000
      49: ldc           #51                 // String star_zorg
      51: ldc           #53                 // float 200.0f
      53: ldc           #54                 // float -10000.0f
      55: invokeinterface #56,  5           // InterfaceMethod com/fs/starfarer/api/campaign/StarSystemAPI.initStar:(Ljava/lang/String;Ljava/lang/String;FF)Lcom/fs/starfarer/api/campaign/PlanetAPI;
      60: return
}
"""
_CLASSES = ["p/Outer.class", "p/Outer$Inner.class", "q/Gen.class"]


def _jar(path, marker: bytes) -> None:
    with zipfile.ZipFile(path, "w") as out:
        for name in _CLASSES:
            out.writestr(name, b"\xca\xfe\xba\xbe " + marker)
        out.writestr("z/Unrelated.class", b"\xca\xfe\xba\xbe")


def _recorded(output: str):
    calls: list[list[str]] = []

    def run(args, **_kwargs):
        calls.append(list(args))
        return mock.Mock(stdout=output, stderr="", returncode=0)

    return calls, mock.patch.object(javap_batch.subprocess, "run", side_effect=run)


class SplitListingsTests(unittest.TestCase):
    def test_each_class_gets_exactly_its_own_listing(self) -> None:
        listings = javap_batch.split_listings(_BATCHED)
        self.assertEqual(list(listings), ["p.Outer", "p.Outer$Inner", "q.Gen"])
        self.assertTrue(listings["p.Outer"].startswith('Compiled from "Outer.java"\npublic class p.Outer {'))
        self.assertIn("class evil.Fake", listings["p.Outer"])  # an escaped constant stays inside its class
        self.assertTrue(listings["q.Gen"].startswith("public abstract class q.Gen<K, V> {"))
        self.assertEqual("".join(listings.values()), _BATCHED)

    def test_lines_outside_any_listing_are_dropped(self) -> None:
        listings = javap_batch.split_listings("Warning: something\n" + _BATCHED)
        self.assertEqual("".join(listings.values()), _BATCHED)


class OneLaunchPerJarTests(unittest.TestCase):
    def test_settings_reads_launch_javap_once_for_all_of_a_jars_classes(self) -> None:
        from bridgeforge import settings_keys

        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            _jar(jar, b"com/fs/starfarer/api/SettingsAPI")
            calls, patch = _recorded(_BATCHED)
            with patch:
                found = settings_keys.jar_settings(jar, root / "javap.exe").reads
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index("-cp") + 2:], ["p.Outer", "p.Outer$Inner", "q.Gen"])
        self.assertEqual(found, [("p/Outer.class", "getFloat", "someKey")])

    def test_procgen_suspects_launch_javap_once_for_all_of_a_jars_classes(self) -> None:
        from bridgeforge import procgen_args

        with resolved_temp_dir() as root:
            jar = root / "mod.jar"
            _jar(jar, b"initStar")
            calls, patch = _recorded(_BATCHED)
            with patch:
                found = procgen_args.jar_suspects(jar, root / "javap.exe")
        self.assertEqual(len(calls), 1)
        self.assertEqual(found, [("q/Gen.class", "generate", "initStar", ["corona -10000"])])

    def test_a_long_class_list_is_split_under_the_command_line_budget(self) -> None:
        entries = [f"pkg{i:04d}/{'Long' * 8}Name{i:04d}.class" for i in range(2000)]
        calls: list[list[str]] = []

        def javap(args, **_kwargs):  # one minimal listing per class asked for, as javap prints them
            calls.append(list(args))
            return mock.Mock(stdout="".join(f"class {name} {{\n}}\n" for name in args[args.index("-cp") + 2:]))

        with mock.patch.object(javap_batch.subprocess, "run", side_effect=javap):
            listings = javap_batch.class_listings("javap.exe", "mod.jar", entries)
        self.assertGreater(len(calls), 1)
        passed = [name for call in calls for name in call[call.index("-cp") + 2:]]
        self.assertEqual(passed, [entry[:-6].replace("/", ".") for entry in entries])
        for call in calls:
            self.assertLessEqual(len(subprocess.list2cmdline(call)), javap_batch.COMMAND_LINE_BUDGET)
        self.assertEqual(listings[entries[7]], f"class {entries[7][:-6].replace('/', '.')} {{\n}}\n")


def _javap_by_class(outputs: dict[tuple[str, ...], str]):
    """A javap whose stdout depends on the classes asked for; records each call's class list."""
    calls: list[tuple[str, ...]] = []

    def run(args, **_kwargs):
        asked = tuple(args[args.index("-cp") + 2:])
        calls.append(asked)
        return mock.Mock(stdout=outputs.get(asked, ""))

    return calls, mock.patch.object(javap_batch.subprocess, "run", side_effect=run)


class DeclaredNameTests(unittest.TestCase):
    """Review 2026-11-17: a listing names the class its file declares. `p/Foo.class` declaring `p.A` prints as `p.A`, which one
    call per class still credited to `p/Foo.class`. A batch whose listings do not name exactly the classes asked for, in order,
    is read again one class at a time."""

    _FOO_AS_A = "public interface p.A {\n  public abstract void decoy();\n}\n"
    _REAL_A = "public class p.A {\n  public p.A();\n}\n"

    def test_a_file_declaring_another_class_keeps_its_listing(self) -> None:
        calls, patch = _javap_by_class({("p.Foo",): self._FOO_AS_A})
        with patch:
            listings = javap_batch.class_listings("javap.exe", "mod.jar", ["p/Foo.class"])
        self.assertEqual(listings, {"p/Foo.class": self._FOO_AS_A})
        self.assertEqual(calls, [("p.Foo",), ("p.Foo",)])  # the batch, then the one-class call

    def test_a_decoy_cannot_replace_a_real_classs_listing(self) -> None:
        calls, patch = _javap_by_class({("p.Foo", "p.A"): self._FOO_AS_A + self._REAL_A,
                                        ("p.Foo",): self._FOO_AS_A, ("p.A",): self._REAL_A})
        with patch:
            listings = javap_batch.class_listings("javap.exe", "mod.jar", ["p/Foo.class", "p/A.class"])
        self.assertEqual(listings, {"p/Foo.class": self._FOO_AS_A, "p/A.class": self._REAL_A})

    def test_a_class_javap_cannot_read_leaves_the_others_as_they_were(self) -> None:
        good = "public class p.B {\n}\n"
        calls, patch = _javap_by_class({("p.Bad", "p.B"): good, ("p.B",): good})
        with patch:
            listings = javap_batch.class_listings("javap.exe", "mod.jar", ["p/Bad.class", "p/B.class"])
        self.assertEqual(listings, {"p/Bad.class": "", "p/B.class": good})

    def test_listing_segments_keep_javaps_order_and_repeats(self) -> None:
        self.assertEqual([name for name, _ in javap_batch.listing_segments(self._FOO_AS_A + self._REAL_A)], ["p.A", "p.A"])


_SOURCES = {
    "p/Outer.java": 'package p;\npublic class Outer {\n  static final String FIELD = "x\\n}\\nclass evil.Fake {\\n";\n'
                    '  public float size() { return FIELD.length(); }\n'
                    '  class Inner implements Runnable { public void run() { System.out.println("inner"); } }\n'
                    '  enum Kind { A, B }\n}\n',
    "q/Shape.java": "package q;\npublic interface Shape<T extends Number> { T area(); }\n",
}


@unittest.skipIf(find_jdk() is None, "needs a JDK (javac and javap)")
class RealJavapTests(unittest.TestCase):
    """Each listing must equal that class's own javap call, whether the batch is used or read again class by class."""

    def _jar(self, root, *, odd: bool):
        jdk = find_jdk()
        for relative, text in _SOURCES.items():
            (root / "src" / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / "src" / relative).write_text(text, encoding="utf-8")
        subprocess.run([str(jdk.javac), "-encoding", "UTF-8", "-d", str(root / "out"), *[str(root / "src" / r) for r in _SOURCES]], check=True,
                       capture_output=True)
        (root / "src" / "r").mkdir()
        (root / "src" / "r" / "Bare.java").write_text("package r;\npublic class Bare { int x; }\n", encoding="utf-8")
        subprocess.run([str(jdk.javac), "-encoding", "UTF-8", "-g:none", "-d", str(root / "out"), str(root / "src" / "r" / "Bare.java")], check=True,
                       capture_output=True)  # no SourceFile attribute: no "Compiled from" line
        jar = root / "t.jar"
        with zipfile.ZipFile(jar, "w") as out:
            for path in sorted((root / "out").rglob("*.class")):
                out.write(path, path.relative_to(root / "out").as_posix())
            if odd:
                out.write(root / "out" / "q" / "Shape.class", "q/Other.class")  # the file declares q.Shape
        entries = sorted(zipfile.ZipFile(jar).namelist()) + (["does/not/Exist.class"] if odd else [])
        return jdk, jar, entries

    def _own(self, jdk, jar, entry: str) -> str:
        return subprocess.run([str(jdk.javap), *javap_batch.FLAGS, "-cp", str(jar), entry[:-6].replace("/", ".")],
                              capture_output=True, text=True, encoding="utf-8", errors="replace").stdout

    def test_a_plain_jar_is_read_in_one_call_and_split_exactly(self) -> None:
        real_run = subprocess.run
        with resolved_temp_dir() as root:
            jdk, jar, entries = self._jar(root, odd=False)
            with mock.patch.object(javap_batch.subprocess, "run", wraps=real_run) as run:
                listings = javap_batch.class_listings(jdk.javap, jar, entries)
            self.assertEqual(run.call_count, 1)
            for entry in entries:
                self.assertEqual(listings[entry], self._own(jdk, jar, entry), entry)
        self.assertLessEqual({"p/Outer.class", "p/Outer$Inner.class", "p/Outer$Kind.class", "q/Shape.class", "r/Bare.class"},
                             set(entries))
        self.assertFalse(listings["r/Bare.class"].startswith("Compiled from"))
        self.assertTrue(all(text.strip() for text in listings.values()))

    def test_a_jar_with_a_misnamed_and_a_missing_class_reads_like_one_call_per_class(self) -> None:
        with resolved_temp_dir() as root:
            jdk, jar, entries = self._jar(root, odd=True)
            listings = javap_batch.class_listings(jdk.javap, jar, entries)
            for entry in entries:
                self.assertEqual(listings[entry], self._own(jdk, jar, entry), entry)
        self.assertIn("interface q.Shape", listings["q/Other.class"])
        self.assertEqual(listings["does/not/Exist.class"], "")


if __name__ == "__main__":
    unittest.main()
