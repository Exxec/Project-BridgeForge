"""ROADMAP-3 82.7 (readable code), 82.11 (author changelogs) and the pilot fixes (--peer, duplicate class rows) of `research report`; synthetic only.

The decompiler is mocked at its two adapter functions (`find_toolchain`, `run_vineflower`): no Java runs here."""
from __future__ import annotations

import io
import json
import unittest
import zipfile
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from bridgeforge.research import research_decompile
from bridgeforge.cli import main
from bridgeforge.research.research_changelog import tree_changelog_quotes
from bridgeforge.research.research_decompile import Toolchain
from bridgeforge.research.research_decompile import excerpt
from bridgeforge.research.research_decompile import method_spans
from bridgeforge.research.research_render import render_markdown
from bridgeforge.research.research_report import ResearchError
from bridgeforge.research.research_report import build_report
from bridgeforge.research.research_terms import AUTHOR_CLAIM
from bridgeforge.research.research_terms import Matcher
from bridgeforge.research.research_terms import parse_terms
from bridgeforge.research.research_terms import weakest
from tests.support import resolved_temp_dir
from tests.test_research_report import QUESTION, _tree_digest, _write, make_atlas, make_live, make_repo, make_workspace

CLASS_BYTES = b"\xca\xfe\xba\xbe fake TemCrusade class mentioning Crusade"
CHANGELOG = "Changelog\n\nVersion 1.1\n- Crusade moved into New.jar\n- fixed a typo\n\nv1.0\n- Added the Crusade event\n- Crusade_rule tweaked\n"
JAVA = """package data.scripts;

public class TemCrusade {
    private int x;

    public void advance(float amount) {
        if (amount > 0) {
            this.x++;
        }
    }

    public void startCrusade() {
        System.out.println("{ not a brace");
        this.x = 0;
    }
}
"""


# the bytecode helper's view of the fake jar (82.8): original source lines of each method; Vineflower's pairs below map them onto JAVA
FAKE_INDEX = {"data/scripts/TemCrusade": [{"name": "<init>", "descriptor": "()V", "lines": [], "body_digest": "i"},
                                          {"name": "advance", "descriptor": "(F)V", "lines": [10, 11], "body_digest": "a"},
                                          {"name": "startCrusade", "descriptor": "()V", "lines": [30, 31], "body_digest": "s"}],
              "data/scripts/TemCrusade$1": [{"name": "run", "descriptor": "()V", "lines": [99], "body_digest": "r"}]}
FAKE_PAIRS = [[10, 7], [11, 8], [30, 13], [31, 14]]


def fake_method_index(jar: Path):
    return FAKE_INDEX, ""


def make_jar(path: Path, extra: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("data/scripts/TemCrusade.class", CLASS_BYTES + extra)
        archive.writestr("data/scripts/TemCrusade$1.class", CLASS_BYTES + extra)
        archive.writestr("data/scripts/Other.class", b"no term")


class FakeDecompiler:
    """Stands in for Vineflower: writes JAVA for every top-level class file found in the source folder and counts the runs."""

    def __init__(self) -> None:
        self.runs: list[list[str]] = []

    def __call__(self, toolchain: Toolchain, source: Path, output: Path) -> tuple[int, str]:
        classes = sorted(p.relative_to(source).as_posix() for p in source.rglob("*.class"))
        self.runs.append(classes)
        for name in classes:
            if "$" not in name:
                _write(output / (name[:-len(".class")] + ".java"), JAVA)
                _write(output / (name[:-len(".class")] + ".lines.json"), json.dumps({"pairs": FAKE_PAIRS}))
        return 0, ""


TOOLCHAIN = Toolchain(Path("java"), Path("vineflower-1.12.0.jar"), "1.12.0", "jdk-17 (test)")


class _both:
    """Two patches entered as one; reusable like a `mock.patch`."""

    def __init__(self, first, second) -> None:
        self.patches = (first, second)
        self.stack: list[ExitStack] = []

    def __enter__(self) -> None:
        stack = ExitStack()
        for patch in self.patches:
            stack.enter_context(patch)
        self.stack.append(stack)

    def __exit__(self, *exc) -> None:
        self.stack.pop().close()


def with_fake_tools(decompiler: FakeDecompiler | None):
    found = (TOOLCHAIN, "") if decompiler is not None else (None, "Vineflower not found (test)")
    return (mock.patch.object(research_decompile, "find_toolchain", return_value=found),
            _both(mock.patch.object(research_decompile, "run_vineflower", decompiler or FakeDecompiler()),
                  mock.patch.object(research_decompile, "jar_method_index", fake_method_index)))


def workspace_with_jars_and_changelogs(root: Path) -> Path:
    ws = make_workspace(root)
    make_jar(ws / "working" / "jars" / "Tem.jar")
    make_jar(ws / "original" / "extracted" / "Case" / "jars" / "Tem.jar")
    _write(ws / "working" / "CHANGELOG.txt", CHANGELOG)
    _write(ws / "original" / "extracted" / "Case" / "readme.txt", "Case mod\n\nChangelog:\n1.0\n- Crusade starts the event\n")
    make_live(root)
    return ws


def run_report(root: Path, ws: Path, decompiler: FakeDecompiler | None, **kwargs):
    kwargs.setdefault("cache_dir", root / "out" / "decompiled")
    first, second = with_fake_tools(decompiler)
    with first, second:
        return build_report("Crusade", ws, QUESTION, atlas_db=root / "atlas.sqlite" if (root / "atlas.sqlite").is_file() else make_atlas(root), repo=make_repo(root, []), build=False, **kwargs)


class ChangelogTests(unittest.TestCase):
    def test_versions_split_and_every_quote_is_an_author_claim_with_file_and_line(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "CHANGELOG.txt", CHANGELOG)
            found = tree_changelog_quotes(root, "working", Matcher(parse_terms("Crusade")))
        quotes = found["quotes"]
        self.assertEqual([(q["line"], q["version"]) for q in quotes], [(4, "1.1"), (8, "1.0"), (9, "1.0")])
        self.assertEqual({q["label"] for q in quotes}, {AUTHOR_CLAIM})
        self.assertEqual(found["files"][0]["file"], "CHANGELOG.txt")

    def test_a_readme_section_titled_changelog_is_read_and_the_rest_of_the_readme_is_not(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "README.md", "Crusade is great\n\n## Changelog\n\n### 2.0\n- Crusade rewritten\n")
            quotes = tree_changelog_quotes(root, "t", Matcher(parse_terms("Crusade")))["quotes"]
        self.assertEqual([(q["line"], q["version"], q["kind"]) for q in quotes], [(6, "2.0", "readme-section")])

    def test_a_readme_without_a_changelog_section_and_non_obvious_names_are_ignored(self) -> None:
        with resolved_temp_dir() as root:
            _write(root / "readme.txt", "Crusade is great\n")
            _write(root / "notes.txt", "Crusade notes\n")
            self.assertEqual(tree_changelog_quotes(root, "t", Matcher(parse_terms("Crusade"))), {"files": [], "quotes": []})

    def test_author_claim_is_the_weakest_label_and_never_upgraded_by_the_report(self) -> None:
        self.assertEqual(weakest(["VALIDATED", AUTHOR_CLAIM, "STATIC"]), AUTHOR_CLAIM)
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            report = run_report(root, ws, FakeDecompiler())
        claims = [c for c in report["claims"] if c["section"] == "changelog"]
        self.assertEqual({c["label"] for c in claims}, {AUTHOR_CLAIM})
        self.assertEqual(report["schema_version"], 2)
        self.assertTrue(any("working:CHANGELOG.txt:4" in c["evidence"] for c in claims))
        changelog_ids = {c["id"] for c in claims}
        self.assertFalse(any(changelog_ids & set(h["basis"]) for h in report["hypotheses"]))
        self.assertNotIn("VALIDATED", {c["label"] for c in report["claims"]})
        markdown = render_markdown(report)
        self.assertIn("AUTHOR CLAIM = a line the mod author wrote", markdown)
        self.assertIn("| working | CHANGELOG.txt:4 | 1.1 | Crusade |", markdown)


class DecompileTests(unittest.TestCase):
    def test_excerpt_keeps_the_methods_naming_a_term_and_ignores_braces_in_strings(self) -> None:
        spans = method_spans(JAVA.splitlines())
        self.assertEqual(len(spans), 2)
        cut = excerpt(JAVA, Matcher(parse_terms("Crusade")))
        self.assertEqual(cut["kind"], "methods")
        text = "\n".join(t for _, t in cut["lines"])
        self.assertIn("startCrusade", text)
        self.assertIn("this.x = 0;", text)
        self.assertNotIn("advance", text)

    def test_long_methods_are_cut_and_a_class_without_a_matching_method_shows_its_header(self) -> None:
        body = "\n".join(f"        this.x += {i};" for i in range(80))
        long_source = f"package p;\npublic class A {{\n    void crusade() {{\n{body}\n    }}\n}}\n"
        cut = excerpt(long_source, Matcher(parse_terms("crusade")))
        self.assertLessEqual(len(cut["lines"]), research_decompile.MAX_METHOD_LINES + 1)
        self.assertIn("more line(s) of this method not shown", cut["lines"][-1][1])
        header = excerpt(JAVA, Matcher(parse_terms("nothing_like_this")))
        self.assertEqual((header["kind"], header["lines"][0][1]), ("header", "public class TemCrusade {"))

    def test_classes_are_decompiled_once_cached_by_jar_hash_and_quoted_as_static(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            decompiler = FakeDecompiler()
            first = run_report(root, ws, decompiler)
            second = run_report(root, ws, decompiler)
            meta = list((root / "out" / "decompiled").glob("*/meta.json"))
            meta_text = json.loads(meta[0].read_text(encoding="utf-8"))
            java_files = [p.relative_to(root / "out" / "decompiled").as_posix() for p in (root / "out" / "decompiled").rglob("*.java")]
        section = first["decompiled"]
        self.assertEqual(section["status"], "DONE")
        self.assertEqual([c["status"] for c in section["classes"]], ["DECOMPILED"])
        self.assertEqual([c["status"] for c in second["decompiled"]["classes"]], ["CACHED"])
        self.assertEqual(len(decompiler.runs), 1)
        self.assertEqual(decompiler.runs[0], ["data/scripts/TemCrusade$1.class", "data/scripts/TemCrusade.class"])
        self.assertEqual((meta_text["vineflower"], meta_text["jdk"], len(meta_text["jar_sha256"])), ("1.12.0", "jdk-17 (test)", 64))
        self.assertEqual(len(java_files), 1)
        self.assertTrue(java_files[0].endswith("/data/scripts/TemCrusade.java"))
        self.assertEqual(section["classes"][0]["label"], "STATIC")
        self.assertEqual(section["classes"][0]["trees"], ["working", "original"])
        claim = next(c for c in first["claims"] if c["section"] == "code")
        self.assertEqual(claim["label"], "STATIC")
        markdown = render_markdown(first)
        self.assertIn("```java", markdown)
        self.assertIn("startCrusade", markdown)
        self.assertIn("never copied into a mod", markdown)

    def test_a_class_in_two_trees_is_one_row_listing_both(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            report = run_report(root, ws, FakeDecompiler())
        rows = [r for r in report["jar_classes"] if r["class"] == "data.scripts.TemCrusade"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trees"], ["working", "original"])
        self.assertTrue(rows[0]["by_name"])

    def test_a_class_that_differs_between_trees_is_read_from_each_jar(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            make_jar(ws / "original" / "extracted" / "Case" / "jars" / "Tem.jar", extra=b" older")
            report = run_report(root, ws, FakeDecompiler())
        versions = report["decompiled"]["classes"]
        self.assertEqual(sorted(tuple(v["trees"]) for v in versions), [("original",), ("working",)])
        self.assertEqual(len({v["jar_sha256"] for v in versions}), 2)

    def test_max_classes_bounds_the_work(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            with zipfile.ZipFile(ws / "working" / "jars" / "Tem.jar", "a") as archive:
                archive.writestr("data/scripts/CrusadeTwo.class", CLASS_BYTES)
            report = run_report(root, ws, FakeDecompiler(), max_classes=1)
            with self.assertRaises(ResearchError):
                run_report(root, ws, FakeDecompiler(), max_classes=0)
        self.assertEqual((report["decompiled"]["candidates"], report["decompiled"]["decompiled_classes"]), (2, 1))

    def test_no_decompile_skips_it_and_a_missing_toolchain_is_reported_with_how_to_get_it(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            skipped = run_report(root, ws, FakeDecompiler(), decompile=False)
            missing = run_report(root, ws, None)
        self.assertEqual((skipped["decompiled"]["status"], skipped["decompiled"]["classes"]), ("SKIPPED", []))
        self.assertEqual(next(i for i in skipped["inputs"] if i["name"] == "decompiler")["status"], "SKIPPED")
        self.assertEqual(missing["decompiled"]["status"], "MISSING")
        self.assertIn("vineflower-", missing["decompiled"]["how_to_get"])
        self.assertTrue(any("decompiler is missing" in u["text"] for u in missing["unknowns"]))
        self.assertIn("Readable code: not produced", render_markdown(missing))

    def test_a_failing_decompiler_is_a_status_not_an_error(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            report = run_report(root, ws, mock.Mock(return_value=(1, "boom")))
        self.assertEqual([c["status"] for c in report["decompiled"]["classes"]], ["FAILED"])
        self.assertIn("boom", report["decompiled"]["classes"][0]["log"])

    def test_decompiled_code_is_never_written_into_a_workspace(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            before = _tree_digest(root / "In operation")
            run_report(root, ws, FakeDecompiler())
            self.assertEqual(_tree_digest(root / "In operation"), before)
            with self.assertRaises(ResearchError):
                run_report(root, ws, FakeDecompiler(), cache_dir=ws / "working" / "decompiled")

    def test_without_a_cache_directory_nothing_is_kept(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            report = run_report(root, ws, FakeDecompiler(), cache_dir=None)
            self.assertFalse((root / "out").exists())
        self.assertEqual(report["decompiled"]["classes"][0]["status"], "DECOMPILED")


class PeerTests(unittest.TestCase):
    def test_peer_workspaces_are_extra_trees_and_their_mod_ids_stay_out_of_the_case(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            peer = root / "In operation" / "Sibling"
            _write(peer / "working" / "mod_info.json", '{"id": "sibling", "name": "Sibling", "version": "1"}')
            _write(peer / "working" / "data" / "campaign" / "rules.csv", "id,trigger\nCrusade_sibling,PopulateOptions\n")
            report = run_report(root, ws, FakeDecompiler(), peer_workspaces=(peer,))
            with self.assertRaises(ResearchError):
                run_report(root, ws, FakeDecompiler(), peer_workspaces=(root / "nowhere",))
            with self.assertRaises(ResearchError):
                run_report(root, ws, FakeDecompiler(), peer_workspaces=(ws,))
        self.assertIn("peer:Sibling", [t["id"] for t in report["trees"]])
        self.assertEqual(report["peer_workspaces"], ["Sibling"])
        self.assertEqual(report["case"]["mod_ids"], ["casemod"])
        row = next(r for r in report["comparison"]["rows"] if r["concept"] == "crusade_sibling")
        self.assertEqual(row["present"]["peer:Sibling"], True)
        self.assertEqual(row["change"], "added-in-working" if row["present"].get("working") else "peers-only")


class CliTests(unittest.TestCase):
    def test_flags_reach_the_report_and_the_cache_lands_beside_the_report(self) -> None:
        with resolved_temp_dir() as root:
            ws = workspace_with_jars_and_changelogs(root)
            peer = root / "In operation" / "Sibling"
            _write(peer / "working" / "mod_info.json", '{"id": "sibling"}')
            target = root / "out"
            out, err = io.StringIO(), io.StringIO()
            first, second = with_fake_tools(FakeDecompiler())
            with first, second, redirect_stdout(out), redirect_stderr(err):
                code = main(["research", "report", "Crusade", "--case", str(ws), "--question", QUESTION, "--write", str(target), "--atlas-db", str(root / "x.sqlite"),
                             "--repo", str(make_repo(root, [])), "--no-build", "--peer", str(peer), "--max-classes", "3"])
            report = json.loads((target / "research-report.json").read_text(encoding="utf-8"))
            cached = list((target / "decompiled").glob("*/data/scripts/TemCrusade.java"))
            code_skip = None
            with first, second, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code_skip = main(["research", "report", "Crusade", "--case", str(ws), "--question", QUESTION, "--atlas-db", str(root / "x.sqlite"), "--no-build", "--no-decompile", "--json"])
        self.assertEqual((code, code_skip), (0, 0))
        self.assertEqual((report["schema_version"], report["decompiled"]["max_classes"], report["peer_workspaces"]), (2, 3, ["Sibling"]))
        self.assertEqual(len(cached), 1)
        self.assertIn("jar classes", out.getvalue())


if __name__ == "__main__":
    unittest.main()
