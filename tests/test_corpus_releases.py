from __future__ import annotations

import io
import json
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from bridgeforge import corpus_releases as cr
from bridgeforge.atlas.atlas_migrations import json_pairs, mine
from bridgeforge.cli import main
from tests.support import resolved_temp_dir

try:
    import py7zr
except ImportError:  # the optional [archives] extra
    py7zr = None


def mod_folder(parent, name, mod_id, version, extra=None, version_file=None):
    folder = parent / name
    folder.mkdir(parents=True)
    info = {"id": mod_id, "name": f"Mod {mod_id}", "version": version, "gameVersion": "0.98a-RC8"}
    info.update(extra or {})
    (folder / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    if version_file is not None:
        (folder / f"{mod_id}.version").write_text(version_file, encoding="utf-8")
    return folder


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(["corpus", "releases", *map(str, argv)])
    return code, out.getvalue(), err.getvalue()


class ParsingTests(unittest.TestCase):
    def test_version_object_form_and_plain_string(self):
        self.assertEqual(cr.version_text({"major": "1", "minor": 2, "patch": "0a"}), "1.2.0a")
        self.assertEqual(cr.version_text({"major": 3, "minor": 0}), "3.0")
        self.assertEqual(cr.version_text(" 0.9.1 "), "0.9.1")
        self.assertEqual(cr.version_text(None), "")

    def test_version_file_links_with_a_lenient_comment(self):
        version_file = '{ # comment\n "masterVersionFile": "https://raw.githubusercontent.com/Someone/Repo/master/x.version",\n "modThreadId": 1234,\n}'
        copy = cr.make_copy(b'{"id": "m", "version": {"major": 1, "minor": 2, "patch": 3}}', version_file.encode(), "src", "folder")
        self.assertEqual((copy.id, copy.version), ("m", "1.2.3"))
        self.assertEqual(copy.forum, "https://fractalsoftworks.com/forum/index.php?topic=1234")
        self.assertEqual(copy.repo, "https://github.com/Someone/Repo")

    def test_thread_zero_and_unknown_host_give_no_links(self):
        copy = cr.make_copy(b'{"id": "m"}', b'{"modThreadId": "0", "masterVersionFile": "https://example.com/a/b/c"}', "s", "folder")
        self.assertEqual((copy.forum, copy.repo), ("", ""))

    def test_other_hosts_and_unreadable_info(self):
        self.assertEqual(cr.repo_link("https://gitlab.com/u/r/-/raw/x"), "https://gitlab.com/u/r")
        self.assertEqual(cr.make_copy(b"not json", None, "s", "folder").id, "")
        self.assertTrue(cr.make_copy(b"[1]", None, "s", "folder").status.startswith("unreadable"))

    def test_natural_version_order(self):
        self.assertEqual(sorted(["1.10", "1.9", "?"], key=cr.version_key), ["1.9", "1.10", "?"])


class ScanTests(unittest.TestCase):
    def test_groups_by_id_across_folders_and_a_zip_and_finds_multi(self):
        with resolved_temp_dir() as root:
            dl = root / "dl"
            mod_folder(dl / "a", "Alpha", "Alpha", "1.0", version_file='{"modThreadId": 7}')
            mod_folder(dl / "b", "Alpha", "alpha", {"major": 2, "minor": 0, "patch": 0})  # id case differs, version is an object
            mod_folder(dl, "Solo", "solo", "1")
            mod_folder(dl / "c", "Solo", "solo", "1")  # same version twice: still single
            with zipfile.ZipFile(dl / "pack.zip", "w") as archive:
                archive.writestr("Pack/Zeta/mod_info.json", json.dumps({"id": "zeta", "version": "5"}))
                archive.writestr("Pack/Zeta/zeta.version", '{"modThreadId": 99}')
            copies = cr.scan_roots([dl])
            groups = cr.group_by_id(copies)
            self.assertEqual(sorted(groups), ["alpha", "solo", "zeta"])
            self.assertEqual(cr.versions_of(groups["alpha"]), ["1.0", "2.0.0"])
            self.assertEqual(cr.versions_of(groups["solo"]), ["1"])
            self.assertEqual(cr.summary(copies), {"copies": 5, "ids": 3, "multi_version": 1, "single_version": 2, "unread": 0})
            (zeta,) = groups["zeta"]
            self.assertEqual((zeta.kind, zeta.forum[-2:]), ("zip", "99"))
            self.assertEqual(zeta.folder, "")

    def test_unreadable_archive_is_reported_not_fatal(self):
        with resolved_temp_dir() as root:
            (root / "broken.zip").write_bytes(b"this is not a zip")
            (root / "x.rar").write_bytes(b"Rar!")
            with mock.patch.object(cr, "find_seven_zip", return_value=None):
                copies = cr.scan_roots([root])
            self.assertEqual(cr.summary(copies)["unread"], 2)
            statuses = {c.source.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]: c.status for c in copies}
            self.assertIn("not a readable zip", statuses["broken.zip"])
            self.assertIn("7-Zip", statuses["x.rar"])
            _, md = cr.group_by_id(copies), cr.releases_markdown(copies, {}, frozenset(), [], 0)
            self.assertIn("broken.zip", md)

    def test_unsafe_and_oversized_members_are_skipped(self):
        entries = [("../evil/mod_info.json", 10), ("/abs/mod_info.json", 10), ("big/mod_info.json", cr.MAX_INFO_BYTES + 1),
                   ("ok\\mod_info.json", 10), ("ok/b.version", 5), ("ok/a.version", 5)]
        self.assertEqual(cr.select_members(entries), [("ok/mod_info.json", "ok/a.version")])

    def test_zip_member_over_cap_is_not_read(self):
        with resolved_temp_dir() as root:
            with zipfile.ZipFile(root / "big.zip", "w") as archive:
                archive.writestr("m/mod_info.json", '{"id": "big", "pad": "' + "x" * cr.MAX_INFO_BYTES + '"}')
            self.assertEqual(cr.scan_roots([root]), [])

    @unittest.skipIf(py7zr is None, "py7zr (the [archives] extra) is not installed")
    def test_7z_members_are_read_in_memory(self):
        with resolved_temp_dir() as root:
            source = root / "src"
            mod_folder(source, "Seven", "seven", "3", version_file='{"modThreadId": 5}')
            with py7zr.SevenZipFile(root / "s.7z", "w") as archive:
                archive.writeall(source / "Seven", "Seven")
            (copy,) = cr.scan_archive(root / "s.7z")
            self.assertEqual((copy.id, copy.version, copy.kind, copy.forum[-1]), ("seven", "3", "7z", "5"))


class OutputTests(unittest.TestCase):
    def fixture(self, root):
        dl = root / "dl"
        mod_folder(dl / "old", "Alpha", "alpha", "1.9")
        mod_folder(dl / "new", "Alpha", "alpha", "1.10")
        mod_folder(dl / "mid", "Alpha", "alpha", "1.9.5")
        mod_folder(dl, "Solo", "solo", "1")
        with zipfile.ZipFile(dl / "pack.zip", "w") as archive:  # archive-only second version of beta
            archive.writestr("Beta/mod_info.json", json.dumps({"id": "beta", "version": "2"}))
        mod_folder(dl / "b", "Beta", "beta", "1")
        repo = root / "repo"
        mod_folder(repo / "In operation" / "Solo", "working", "solo", "1")
        return dl, repo

    def test_write_outputs_and_pairs_are_accepted_by_the_migrations_loader(self):
        with resolved_temp_dir() as root:
            dl, repo = self.fixture(root)
            out = root / "out"
            code, stdout, _ = run(dl, "--write", out, "--repo-root", repo, "--quiet")
            self.assertEqual(code, 0, stdout)
            self.assertIn("6 copies, 3 ids, 2 multi-version, 1 single, 0 unread", stdout)
            self.assertEqual(sorted(p.name for p in out.iterdir()), ["RELEASES.md", "pairs.json", "releases.csv"])  # checkpoint removed
            md = (out / "RELEASES.md").read_text(encoding="utf-8")
            self.assertLess(md.index("`solo`"), md.index("## Already have two or more versions"))
            self.assertRegex(md, r"\| `solo` .*\| yes \|")  # revival target marked
            self.assertIn("1.9, 1.9.5, 1.10", md)
            self.assertIn("- `beta`: 1, 2", md)  # version 2 exists only inside a zip
            rows = (out / "releases.csv").read_text(encoding="utf-8").splitlines()
            self.assertEqual(rows[0].split(",")[:3], ["id", "name", "version"])
            data = json.loads((out / "pairs.json").read_text(encoding="utf-8"))
            self.assertEqual([p["label"] for p in data["pairs"]], ["alpha 1.9 -> 1.9.5", "alpha 1.9.5 -> 1.10"])
            self.assertEqual([u["id"] for u in data["not_pairable"]], ["beta"])
            pairs = json_pairs(out / "pairs.json")
            self.assertEqual((pairs[0].old_version, pairs[0].new_version), ("1.9", "1.9.5"))
            self.assertEqual(len(mine(pairs)["pairs"]), 2)
            mcode = main(["atlas", "migrations", "--pairs-json", str(out / "pairs.json"), "--quiet", "--json"])
            self.assertEqual(mcode, 0)

    def test_output_is_deterministic(self):
        with resolved_temp_dir() as root:
            dl, repo = self.fixture(root)
            for name in ("one", "two"):
                run(dl, "--write", root / name, "--repo-root", repo, "--quiet")
            for name in ("RELEASES.md", "pairs.json", "releases.csv"):
                self.assertEqual((root / "one" / name).read_bytes(), (root / "two" / name).read_bytes())

    def test_json_pairs_rejects_a_moved_folder(self):
        with resolved_temp_dir() as root:
            bad = root / "pairs.json"
            bad.write_text(json.dumps({"pairs": [{"label": "x", "old": str(root / "gone"), "new": str(root)}]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no mod_info.json"):
                json_pairs(bad)
            bad.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not a pairs.json"):
                json_pairs(bad)

    def test_missing_root_is_an_error(self):
        with resolved_temp_dir() as root:
            code, _, err = run(root / "nope", "--quiet")
            self.assertEqual(code, 2)
            self.assertIn("not a folder", err)


if __name__ == "__main__":
    unittest.main()
