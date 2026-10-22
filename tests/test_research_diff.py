"""ROADMAP-3 82.8 (method link) and 82.9 (`research diff`): synthetic. Vineflower and the bytecode helper are replaced at their adapter functions
(`run_vineflower`, `jar_method_index`), so no Java runs; one optional test runs the real helper when a JDK is present."""
from __future__ import annotations

import io
import json
import shutil
import struct
import subprocess
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from bridgeforge.bytecode import inspect_bytecode
from bridgeforge.bytecode_diff import changed_methods
from bridgeforge.cli import main
from bridgeforge.research_decompile import excerpt, jar_sha256, method_spans
from bridgeforge.research_diff import DiffError, build_diff, render_markdown, side_jars
from bridgeforge.research_methods import (MAPPED, UNMAPPED, MethodMap, lookup_identity, lookup_line, method_identity, parse_line_pairs, resolve_methods,
                                          split_identity)
from bridgeforge.research_render import render_markdown as render_report
from bridgeforge.research_terms import Matcher, parse_terms
from tests.support import resolved_temp_dir
from tests.test_research_inputs import (FAKE_INDEX, FAKE_PAIRS, JAVA, TOOLCHAIN, FakeDecompiler, run_report, workspace_with_jars_and_changelogs)

CLS = "data/scripts/TemCrusade"
NEW_JAVA = JAVA.replace("this.x++;", "this.x += 2;").replace("this.x = 0;", "this.x = 0;\n        this.x--;")
OLD_DETAILS = [{"name": "advance", "descriptor": "(F)V", "lines": [10, 11], "body_digest": "a1"},
               {"name": "startCrusade", "descriptor": "()V", "lines": [30, 31], "body_digest": "s1"},
               {"name": "untouched", "descriptor": "()V", "lines": [], "body_digest": "u"},
               {"name": "gone", "descriptor": "()V", "lines": [50], "body_digest": "g"}]
NEW_DETAILS = [{"name": "advance", "descriptor": "(F)V", "lines": [10, 11], "body_digest": "a2"},
               {"name": "startCrusade", "descriptor": "()V", "lines": [30, 31], "body_digest": "s1"},
               {"name": "untouched", "descriptor": "()V", "lines": [], "body_digest": "u"},
               {"name": "fresh", "descriptor": "(I)V", "lines": [60], "body_digest": "f"}]


def extra_field(pairs: list[tuple[int, int]]) -> bytes:
    body = bytes([1]) + b"".join(struct.pack("<HH", a, b) for a, b in pairs)
    return b"FF" + struct.pack("<H", len(body)) + body


def make_jar(path: Path, marker: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{CLS}.class", b"\xca\xfe\xba\xbe fake " + marker.encode())
    return path


class SideRunner:
    """Stands in for Vineflower in a diff: writes the old or the new JAVA by the marker in the class bytes, with a line mapping; counts runs."""

    def __init__(self, pairs=None) -> None:
        self.runs = 0
        self.pairs = FAKE_PAIRS if pairs is None else pairs

    def __call__(self, toolchain, source: Path, output: Path) -> tuple[int, str]:
        self.runs += 1
        for path in sorted(source.rglob("*.class")):
            name = path.relative_to(source).as_posix()[:-len(".class")]
            text = NEW_JAVA if b"new" in path.read_bytes() else JAVA
            target = output / f"{name}.java"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            (output / f"{name}.lines.json").write_text(json.dumps({"pairs": self.pairs}), encoding="utf-8")
        return 0, ""


def fake_indexer(jar: Path):
    return ({CLS: NEW_DETAILS} if jar.parent.parent.name == "new" else {CLS: OLD_DETAILS}), ""


def diff(old: Path, new: Path, runner=None, **kwargs) -> dict:
    with mock.patch("bridgeforge.research_diff.find_toolchain", return_value=(TOOLCHAIN, "")):
        return build_diff(old, new, indexer=fake_indexer, runner=runner or SideRunner(), **kwargs)


class MethodLinkTests(unittest.TestCase):
    def test_identity_round_trips_and_text_that_is_not_one_is_refused(self) -> None:
        identity = method_identity("a/b/C$D", "run", "(Ljava/lang/String;I)V")
        self.assertEqual(identity, "a/b/C$D#run (Ljava/lang/String;I)V")
        self.assertEqual(split_identity(identity), ("a/b/C$D", "run", "(Ljava/lang/String;I)V"))
        for bad in ("", "a/b/C", "a/b/C#run", "a/b/C#run V", "#run ()V"):
            with self.assertRaises(ValueError):
                split_identity(bad)

    def test_vineflower_extra_field_is_parsed_and_a_missing_or_foreign_one_is_not_guessed(self) -> None:
        self.assertEqual(parse_line_pairs(b"\x01\x02\x03\x00abc" + extra_field([(26, 25), (31, 28)])), [(26, 25), (31, 28)])
        self.assertIsNone(parse_line_pairs(b""))
        self.assertIsNone(parse_line_pairs(b"FF\x05\x00\x02\x01\x00\x02\x00"))
        self.assertIsNone(parse_line_pairs(b"\xfe\xca\x00\x00"))

    def test_each_method_gets_its_decompiled_range_and_the_lookup_works_both_ways(self) -> None:
        spans = method_spans(JAVA.splitlines())
        rows = resolve_methods(CLS, FAKE_INDEX[CLS], [tuple(p) for p in FAKE_PAIRS], spans)
        by_id = {r["id"]: r for r in rows}
        self.assertEqual(by_id[f"{CLS}#advance (F)V"]["lines"], [6, 10])
        self.assertEqual(by_id[f"{CLS}#startCrusade ()V"]["lines"], [12, 15])
        method_map = MethodMap("x", tuple(rows))
        self.assertEqual(method_map.lines_for(f"{CLS}#advance (F)V"), (6, 10))
        self.assertEqual(method_map.identities_at(8), [f"{CLS}#advance (F)V"])
        self.assertEqual(method_map.identities_at(14), [f"{CLS}#startCrusade ()V"])
        self.assertEqual(method_map.identities_at(11), [])
        self.assertEqual(method_map.identities_for_range(6, 10), [f"{CLS}#advance (F)V"])

    def test_a_method_that_cannot_be_placed_is_unmapped_with_the_reason(self) -> None:
        spans = method_spans(JAVA.splitlines())
        details = [{"name": "<init>", "descriptor": "()V", "lines": [], "body_digest": ""},
                   {"name": "lost", "descriptor": "()V", "lines": [99], "body_digest": ""},
                   {"name": "both", "descriptor": "()V", "lines": [10, 30], "body_digest": ""},
                   {"name": "field", "descriptor": "()V", "lines": [5], "body_digest": ""}]
        rows = {r["id"].split("#")[1].split(" ")[0]: r for r in resolve_methods(CLS, details, [(10, 7), (30, 13), (5, 4)], spans)}
        self.assertEqual((rows["<init>"]["status"], rows["lost"]["status"], rows["both"]["status"]), (UNMAPPED, UNMAPPED, UNMAPPED))
        self.assertIn("no line-number table", rows["<init>"]["why"])
        self.assertIn("mapped none", rows["lost"]["why"])
        self.assertIn("2 different decompiled methods", rows["both"]["why"])
        self.assertEqual((rows["field"]["status"], rows["field"]["lines"], rows["field"]["basis"]), (MAPPED, [4, 4], "lines"))
        self.assertIsNone(MethodMap("x", tuple(rows.values())).lines_for(f"{CLS}#lost ()V"))

    def test_report_excerpt_gives_each_quoted_method_its_identity_or_unmapped(self) -> None:
        rows = resolve_methods(CLS, FAKE_INDEX[CLS], [tuple(p) for p in FAKE_PAIRS], method_spans(JAVA.splitlines()))
        cut = excerpt(JAVA, Matcher(parse_terms("startCrusade,advance")), MethodMap("x", tuple(rows)))
        self.assertEqual([(b["decompiled_lines"], b["identities"]) for b in cut["bytecode"]],
                         [([6, 10], [f"{CLS}#advance (F)V"]), ([12, 15], [f"{CLS}#startCrusade ()V"])])
        bare = excerpt(JAVA, Matcher(parse_terms("advance")), None)
        self.assertEqual(bare["bytecode"], [{"decompiled_lines": [6, 10], "identities": []}])

    def test_the_decompile_step_stores_the_map_beside_the_cached_java_and_the_report_quotes_identities(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            decompiler = FakeDecompiler()
            first = run_report(root, ws, decompiler)
            second = run_report(root, ws, decompiler)
            cache = root / "out" / "decompiled"
            sha = first["decompiled"]["classes"][0]["jar_sha256"]
            stored = json.loads((cache / sha / f"{CLS}.methods.json").read_text(encoding="utf-8"))
            line_hit = lookup_line(cache, sha, f"{CLS}.java", 9)
            identity_hit = lookup_identity(cache, sha, f"{CLS}#startCrusade ()V")
            inner_hit = lookup_identity(cache, sha, f"{CLS}$1#run ()V")
            markdown = render_report(first)
        self.assertEqual(len(decompiler.runs), 1)
        self.assertEqual([c["status"] for c in second["decompiled"]["classes"]], ["CACHED"])
        self.assertEqual({m["id"]: m["status"] for m in stored["methods"]}, {f"{CLS}#<init> ()V": UNMAPPED, f"{CLS}#advance (F)V": MAPPED, f"{CLS}#startCrusade ()V": MAPPED,
                                                                          f"{CLS}$1#run ()V": UNMAPPED})
        self.assertEqual(line_hit, [f"{CLS}#advance (F)V"])
        self.assertEqual(identity_hit, (f"{CLS}.java", 12, 15))
        self.assertIsNone(inner_hit)
        self.assertIn(f"`{CLS}#startCrusade ()V`", markdown)
        self.assertIn("Bytecode identity of each quoted method", markdown)
        self.assertEqual(first["decompiled"]["classes"][0]["excerpt"]["bytecode"], second["decompiled"]["classes"][0]["excerpt"]["bytecode"])


class ChangedMethodsTests(unittest.TestCase):
    def test_only_a_changed_body_is_changed_and_line_numbers_alone_do_not_count(self) -> None:
        before = {"method_details": OLD_DETAILS}
        shifted = [{**m, "lines": [n + 100 for n in m["lines"]]} for m in OLD_DETAILS]
        self.assertEqual(changed_methods(before, {"method_details": shifted}), {"changed": [], "added": [], "removed": []})
        result = changed_methods(before, {"method_details": NEW_DETAILS})
        self.assertEqual([m["name"] for m in result["changed"]], ["advance"])
        self.assertEqual([m["name"] for m in result["added"]], ["fresh"])
        self.assertEqual([m["name"] for m in result["removed"]], ["gone"])


class DiffTests(unittest.TestCase):
    def sides(self, root: Path) -> tuple[Path, Path]:
        return make_jar(root / "old" / "jars" / "M.jar", "old"), make_jar(root / "new" / "jars" / "M.jar", "new")

    def test_bytecode_decides_which_methods_are_diffed_and_unchanged_ones_are_left_out(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            result = diff(old, new)
        ids = {m["id"]: m for m in result["methods"]}
        self.assertEqual(set(ids), {f"{CLS}#advance (F)V", f"{CLS}#fresh (I)V", f"{CLS}#gone ()V"})
        self.assertEqual((result["label"], result["status"]), ("STATIC", "DONE"))
        self.assertEqual((result["bytecode"]["methods_changed"], result["bytecode"]["methods_added"], result["bytecode"]["methods_removed"]), (1, 1, 1))
        changed = ids[f"{CLS}#advance (F)V"]
        self.assertEqual((changed["change"], changed["status"]), ("changed", "DIFFED"))
        self.assertIn("-            this.x++;", changed["diff"])
        self.assertIn("+            this.x += 2;", changed["diff"])
        self.assertFalse(any("startCrusade" in line for line in changed["diff"]))
        self.assertEqual((changed["old_lines"], changed["new_lines"]), ([6, 10], [6, 10]))

    def test_added_and_removed_methods_without_a_range_are_unmapped_not_guessed(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            result = diff(old, new)
        ids = {m["id"]: m for m in result["methods"]}
        for name in ("fresh (I)V", "gone ()V"):
            row = ids[f"{CLS}#{name}"]
            self.assertEqual((row["status"], row["diff"]), (UNMAPPED, []))
            self.assertIn("mapped none", row["why"])

    def test_without_any_line_mapping_every_method_is_unmapped_and_none_is_diffed(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            result = diff(old, new, runner=SideRunner(pairs=[]))
        self.assertTrue(all(m["status"] == UNMAPPED and m["diff"] == [] for m in result["methods"]))
        self.assertIn("old: ", result["methods"][0]["why"])

    def test_identical_text_with_changed_bytecode_is_said_so(self) -> None:
        class Same(SideRunner):
            def __call__(self, toolchain, source, output):
                code = super().__call__(toolchain, source, output)
                for path in output.rglob("*.java"):
                    path.write_text(JAVA, encoding="utf-8", newline="\n")
                return code

        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            result = diff(old, new, runner=Same(), classes="TemCrusade")
        row = next(m for m in result["methods"] if m["id"].endswith("advance (F)V"))
        self.assertEqual((row["status"], row["diff"]), ("SAME_TEXT", []))

    def test_output_is_bounded_and_the_rest_only_counted(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            one = diff(old, new, max_methods=1)
            short = diff(old, new, max_lines=3)
        self.assertEqual((one["shown"], one["not_shown"], len(one["methods"])), (1, 2, 1))
        advance = next(m for m in short["methods"] if m["id"].endswith("advance (F)V"))
        self.assertEqual(len(advance["diff"]), 3)
        self.assertGreater(advance["truncated"], 0)
        self.assertIn("more diff line(s) not shown", render_markdown(short))

    def test_classes_filter_limits_the_comparison(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            none = diff(old, new, classes="NoSuchThing")
            runner = SideRunner()
            some = diff(old, new, classes="temcrusade", runner=runner)
        self.assertEqual((none["status"], none["methods"], none["bytecode"]["classes_compared"]), ("NO_METHOD_CHANGES", [], 0))
        self.assertEqual(some["bytecode"]["classes_compared"], 1)

    def test_a_run_is_deterministic_and_the_cache_is_reused(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            runner = SideRunner()
            cache = root / "out" / "decompiled"
            first = diff(old, new, runner=runner, cache_dir=cache)
            runs_after_first = runner.runs
            second = diff(old, new, runner=runner, cache_dir=cache)
            maps = sorted(p.name for p in cache.rglob("*.methods.json"))
            old_sha = jar_sha256(old)
        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(render_markdown(first), render_markdown(second))
        self.assertEqual((runs_after_first, runner.runs), (2, 2))
        self.assertEqual(len(maps), 2)
        self.assertEqual(first["old"]["jars"][0]["sha256"], old_sha)

    def test_a_missing_decompiler_still_gives_the_bytecode_verdict(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            with mock.patch("bridgeforge.research_diff.find_toolchain", return_value=(None, "Vineflower not found (test)")):
                result = build_diff(old, new, indexer=fake_indexer, runner=SideRunner())
        self.assertEqual(result["status"], "DECOMPILER_MISSING")
        self.assertEqual({m["status"] for m in result["methods"]}, {"NOT_DECOMPILED"})
        self.assertEqual(result["bytecode"]["methods_changed"], 1)

    def test_an_unavailable_bytecode_helper_is_an_error_because_it_is_the_decider(self) -> None:
        with resolved_temp_dir() as root:
            old, new = self.sides(root)
            with self.assertRaises(DiffError):
                build_diff(old, new, indexer=lambda jar: (None, "no java"), runner=SideRunner())

    def test_sides_are_a_jar_a_mod_folder_or_a_folder_holding_one(self) -> None:
        with resolved_temp_dir() as root:
            jar = make_jar(root / "case" / "original" / "extracted" / "Mod" / "jars" / "M.jar", "old")
            (root / "case" / "original" / "extracted" / "Mod" / "mod_info.json").write_text("{}", encoding="utf-8")
            self.assertEqual(side_jars(jar), [jar])
            self.assertEqual(side_jars(root / "case" / "original"), [jar])
            self.assertEqual(side_jars(root / "case" / "original" / "extracted" / "Mod"), [jar])
            with self.assertRaises(DiffError):
                side_jars(root / "missing")
            (root / "none").mkdir()
            with self.assertRaises(DiffError):
                side_jars(root / "none")


class CliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_diff_writes_markdown_and_json_beside_a_kept_cache_and_never_into_a_version_tree(self) -> None:
        with resolved_temp_dir() as root:
            old = make_jar(root / "old" / "jars" / "M.jar", "old")
            new = make_jar(root / "new" / "jars" / "M.jar", "new")
            target = root / "out"
            with mock.patch("bridgeforge.research_diff.find_toolchain", return_value=(TOOLCHAIN, "")), mock.patch("bridgeforge.research_diff.jar_method_index", fake_indexer), \
                    mock.patch("bridgeforge.research_diff.run_vineflower", SideRunner()):
                code, out, _ = self.run_cli(["research", "diff", str(old), str(new), "--write", str(target)])
                refused = self.run_cli(["research", "diff", str(old), str(new), "--write", str(old.parent)])
            written = json.loads((target / "research-diff.json").read_text(encoding="utf-8"))
            markdown = (target / "research-diff.md").read_text(encoding="utf-8")
            cached = list((target / "decompiled").rglob("*.methods.json"))
        self.assertEqual(code, 0)
        self.assertIn("research diff (STATIC, DONE)", out)
        self.assertEqual(written["mode"], "RESEARCH_DIFF")
        self.assertIn("```diff", markdown)
        self.assertEqual(len(cached), 2)
        self.assertEqual(refused[0], 2)
        self.assertIn("never writes into a version tree", refused[2])

    def test_bad_limits_are_refused(self) -> None:
        self.assertEqual(self.run_cli(["research", "diff", "a.jar", "b.jar", "--max-methods", "0"])[0], 2)


class RealHelperTests(unittest.TestCase):
    def test_the_real_bytecode_helper_digests_bodies_and_reports_line_numbers(self) -> None:
        if not shutil.which("javac") or not shutil.which("java"):
            self.skipTest("JDK is unavailable")
        with resolved_temp_dir() as root:
            digests = {}
            for label, constant in (("one", "1"), ("two", "2")):
                folder = root / label
                folder.mkdir()
                source = folder / "Fixture.java"
                source.write_text(f"class Fixture {{\n  int same() {{ return 7; }}\n  int differs() {{\n    return {constant};\n  }}\n  String text() {{ return \"café\\t\"; }}\n}}\n", encoding="utf-8")
                done = subprocess.run(["javac", "--release", "17", "-g", "-d", str(folder), str(source)], capture_output=True, text=True, check=False)
                self.assertEqual(done.returncode, 0, done.stderr)
                details = inspect_bytecode([folder / "Fixture.class"])["classes"][0]["method_details"]
                digests[label] = {m["name"]: m for m in details}
        self.assertEqual(digests["one"]["same"]["body_digest"], digests["two"]["same"]["body_digest"])
        self.assertNotEqual(digests["one"]["differs"]["body_digest"], digests["two"]["differs"]["body_digest"])
        self.assertEqual(digests["one"]["differs"]["lines"], [4])
        self.assertEqual(digests["one"]["same"]["lines"], [2])


if __name__ == "__main__":
    unittest.main()
