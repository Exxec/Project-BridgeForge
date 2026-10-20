"""Archive content parity (ROADMAP 77.18): classes, verdicts, junk refusal, the --write path."""
from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bridgeforge.archive import ArchiveError, archive_mod
from bridgeforge.archive_intake import inspect_zip_archive
from bridgeforge.content_parity import audit_shipped, classify_missing, content_parity, is_junk, junk_members, open_tree
from tests.support import link_dir, resolved_temp_dir

INFO = '{"id": "m", "version": "1"}'


def _write(path: Path, text: str | bytes = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))


def _zip(path: Path, members: dict[str, str | bytes]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in members.items():
            archive.writestr(name, body)
    return path


def _jar(classes: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as jar:
        for name in classes:
            jar.writestr(name, b"\xca\xfe")
    return buffer.getvalue()


def _original(root: Path, files: dict[str, str | bytes]) -> Path:
    """`root/original/M` holding the files; returns `root/original`."""
    base = root / "original" / "M"
    _write(base / "mod_info.json", INFO)
    for name, body in files.items():
        _write(base / name, body)
    return root / "original"


class ClassifierTests(unittest.TestCase):
    def test_each_class(self) -> None:
        with resolved_temp_dir() as root:
            vanilla = root / "vanilla"
            _write(vanilla / "data" / "config" / "settings.json")
            _write(vanilla / "data" / "campaign" / "rules.csv")
            old = _original(root, {
                "data/config/settings.json": "s", "data/campaign/rules.csv": "r", "data/hulls/gone.ship": "g",
                "data/hulls/moved.ship": "m", "data/hulls/same.bin": "samebytes", "data/x/a.csv.old": "j",
                "data/x/Copy of b.csv": "j", "data/x/desktop.ini": "j", "data/x/c.zip": "j",
                "data/scripts/Foo.java": "src", "data/scripts/Lost.java": "src", "data/kept.csv": "k"}) / "M"
            shipped = _zip(root / "s.zip", {"M/mod_info.json": INFO, "M/data/kept.csv": "k", "M/elsewhere/moved.ship": "m",
                                            "M/other/renamed.bin": "samebytes", "M/jars/m.jar": _jar(["data/scripts/Foo.class"])})
            with open_tree(shipped) as tree:
                result = classify_missing(old, tree.under("M"), vanilla)
        self.assertEqual(result["SHADOW_REMOVAL"], ["data/config/settings.json"])
        self.assertEqual([m.split(" [")[0] for m in result["MISSING"]],
                         ["data/campaign/rules.csv", "data/hulls/gone.ship", "data/scripts/Lost.java"])
        self.assertIn("vanilla-path CSV", result["MISSING"][0])
        self.assertEqual(sorted(r.split(" -> ")[0] for r in result["RENAMED"]), ["data/hulls/moved.ship", "data/hulls/same.bin"])
        self.assertEqual(sorted(result["JUNK"]), ["data/x/Copy of b.csv", "data/x/a.csv.old", "data/x/c.zip", "data/x/desktop.ini"])
        self.assertEqual(result["SOURCE_OMITTED"], ["data/scripts/Foo.java"])

    def test_junk_predicate(self) -> None:
        for name in ("a.old", "a.csv~", "Desktop.ini", "Foo - Copy.jar", "copy of x.jar", "jars/копия.jar", "a (1).png"):
            self.assertTrue(is_junk(name), name)
        self.assertFalse(is_junk("data/hulls/a.ship"))
        self.assertEqual(junk_members(["a.zip", "a.old"]), ["a.old"])  # nested archives are audited, not refused


class VerdictTests(unittest.TestCase):
    def _audit(self, root: Path, files: dict, shipped_files: dict) -> dict:
        original = _original(root, files)
        shipped = _zip(root / "s.zip", {"M/mod_info.json": INFO, **{f"M/{k}": v for k, v in shipped_files.items()}})
        return audit_shipped(shipped, original, name="M")

    def test_verdicts(self) -> None:
        with resolved_temp_dir() as root:
            clean = self._audit(root / "a", {"data/a.csv": "1"}, {"data/a.csv": "1"})
            loss = self._audit(root / "b", {"data/a.csv": "1", "data/campaign/rules.csv": "r"}, {"data/a.csv": "1"})
            review = self._audit(root / "c", {"data/a.csv": "1", "data/n.csv.old": "j"}, {"data/a.csv": "1"})
            no_original = audit_shipped(_zip(root / "d.zip", {"M/mod_info.json": INFO}), None, name="M")
            other = _original(root / "e", {"data/a.csv": "1"})
            wrong_id = audit_shipped(_zip(root / "f.zip", {"X/mod_info.json": '{"id": "x"}'}), other, name="M")
            bad = root / "bad.zip"
            _write(bad, "not a zip")
            unreadable = audit_shipped(bad, other, name="M")
        # A lone original root is matched even when the id differs (noted); several roots would need the id.
        self.assertEqual([r["verdict"] for r in (clean, loss, review, no_original, wrong_id, unreadable)],
                         ["CLEAN", "LOSS_SUSPECTED", "REVIEW", "UNDETERMINED", "LOSS_SUSPECTED", "UNDETERMINED"])
        self.assertEqual(loss["missing"], ["data/campaign/rules.csv"])
        self.assertIn("original matched as the only mod root (id differs)", wrong_id["notes"])

    def test_aliased_temporary_parent_preserves_missing_content_findings(self) -> None:
        with resolved_temp_dir() as root:
            temporary = root / "temporary"
            temporary.mkdir()
            alias = root / "alias"
            link_dir(temporary, alias)
            with patch("bridgeforge.content_parity.tempfile.tempdir", str(alias)):
                row = self._audit(root, {"data/gone.csv": "gone"}, {})
            self.assertEqual(row["verdict"], "LOSS_SUSPECTED")
            self.assertEqual(row["missing"], ["data/gone.csv"])
            self.assertEqual(list(temporary.iterdir()), [])

    def test_failed_comparison_cannot_report_clean_after_matching_an_original(self) -> None:
        with resolved_temp_dir() as root:
            with patch("bridgeforge.content_parity.compare_root", side_effect=OSError("synthetic read failure")):
                row = self._audit(root, {"data/gone.csv": "gone"}, {})
        self.assertEqual(row["verdict"], "UNDETERMINED")
        self.assertFalse(row["determined"])
        self.assertIn("unreadable: synthetic read failure", row["notes"])

    def test_shipped_junk_is_review_not_undetermined(self) -> None:
        with resolved_temp_dir() as root:
            row = self._audit(root, {"data/a.csv": "1"}, {"data/a.csv": "1", "jars/Foo - Copy.jar": "x"})
        self.assertEqual(row["verdict"], "REVIEW")
        self.assertEqual(row["shipped_junk"], ["M/jars/Foo - Copy.jar"])

    def test_folder_shipped_tree(self) -> None:
        with resolved_temp_dir() as root:
            original = _original(root, {"data/a.csv": "1", "data/gone.ship": "g"})
            shipped = root / "ship"
            _write(shipped / "M" / "mod_info.json", INFO)
            _write(shipped / "M" / "data" / "a.csv", "1")
            row = audit_shipped(shipped, original, name="M")
        self.assertEqual(row["missing"], ["data/gone.ship"])
        self.assertEqual(row["verdict"], "LOSS_SUSPECTED")


class WritePathTests(unittest.TestCase):
    def test_write_dir_and_nothing_in_done(self) -> None:
        with resolved_temp_dir() as root:
            done, queue, out = root / "Done", root / "queue", root / "out"
            _original(done / "Mod", {"data/a.csv": "1", "data/b.csv": "2"})
            _zip(done / "Mod" / "Mod-1.zip", {"M/mod_info.json": INFO, "M/data/a.csv": "1"})
            result = content_parity(done, queue, out, quiet=True)
            names = sorted(p.name for p in out.iterdir())
            data = json.loads((out / "CONTENT_PARITY.json").read_text(encoding="utf-8"))
            done_listing = sorted(p.name for p in done.iterdir())
        self.assertEqual(result["counts"]["LOSS_SUSPECTED"], 1)
        self.assertEqual(names, ["CONTENT_PARITY.json", "CONTENT_PARITY.md"])  # the checkpoint is removed when the run finishes
        self.assertEqual(data["mods"][0]["missing"], ["data/b.csv"])
        self.assertEqual(done_listing, ["Mod"])


class JunkRefusalTests(unittest.TestCase):
    def test_preflight_refuses_junk_and_warns_on_missing(self) -> None:
        with resolved_temp_dir() as root:
            junk = _zip(root / "j.zip", {"M/mod_info.json": INFO, "M/jars/Foo - Copy.jar": "x", "M/data/a.old": "x"})
            ok = _zip(root / "ok.zip", {"M/mod_info.json": INFO})
            original = _original(root, {"data/a.csv": "1"})
            refused = inspect_zip_archive(junk)
            warned = inspect_zip_archive(ok, original=original)
        found = {f["id"]: f for f in refused["findings"]}
        self.assertEqual(sorted(found["archive-junk-member"]["entries"]), ["M/data/a.old", "M/jars/Foo - Copy.jar"])
        self.assertFalse(refused["safe_to_stage"])
        self.assertTrue(warned["safe_to_stage"])
        self.assertIn("archive-content-missing", [f["id"] for f in warned["findings"]])

    def test_archive_mod_refuses_junk(self) -> None:
        with resolved_temp_dir() as root:
            workspace = root / "Mod"
            _write(workspace / "working" / "mod_info.json", INFO)
            _write(workspace / "working" / "data" / "Foo - Copy.csv")
            with self.assertRaises(ArchiveError) as caught:
                archive_mod(workspace, root / "Done")
        self.assertIn("Foo - Copy.csv", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
