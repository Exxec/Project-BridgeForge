from __future__ import annotations

import io
import json
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout

from bridgeforge import move_machine as migrate
from bridgeforge.cli import main
from tests.support import link_dir, resolved_temp_dir

OLD = "C:\\Users\\exxec\\Documents\\Project BridgeForge"
NEW = "D:\\Work\\BF"


def run_git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def make_repo(root):
    (root / "bridgeforge").mkdir()
    (root / "bridgeforge" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "In operation" / "_rig").mkdir(parents=True)
    (root / "In operation" / "mod").mkdir()
    (root / "In operation" / "mod" / "f.txt").write_text("hello", encoding="utf-8")
    (root / "Done").mkdir()
    (root / "Done" / "z.zip").write_bytes(b"1234")
    (root / ".venv").mkdir()
    (root / ".venv" / "x").write_text("v", encoding="utf-8")
    (root / ".gitignore").write_text("In operation/\nDone/\n.venv/\nbridgeforge-state/\nconfig/\n", encoding="utf-8")
    run_git(root, "init", "-q")
    run_git(root, "add", ".gitignore", "bridgeforge")


def write_hazards(root):
    (root / "config").mkdir()
    (root / "config" / "bridgeforge.local.psd1").write_text(f"@{{ ProjectRoot = '{OLD}'; Done = '{OLD}\\Done' }}", encoding="utf-8")
    state = root / "bridgeforge-state"
    (state / "reference-rigs").mkdir(parents=True)
    (state / "provider-index.json").write_text(json.dumps({"p": OLD + "\\Done\\a", "q": "relative/x"}), encoding="utf-8")
    (state / "reference-rigs" / "r.json").write_text(json.dumps({"jre": "C:\\Other\\jre"}), encoding="utf-8")
    (root / "In operation" / "_rig" / "launch.bat").write_text(f'"{OLD}\\tools\\x.exe" %*\r\n', encoding="utf-8")


class InventoryTests(unittest.TestCase):
    def test_classifies_top_level_items_and_finds_hazards(self):
        with resolved_temp_dir() as root, resolved_temp_dir() as home:
            make_repo(root)
            write_hazards(root)
            memory = migrate.claude_memory_dir(root, home)
            memory.mkdir(parents=True)
            (memory / "MEMORY.md").write_text("m", encoding="utf-8")
            out = root.parent / (root.name + "-inv.json")
            with redirect_stderr(io.StringIO()) as err:
                result = migrate.migrate_inventory(root, out, root.parent / (root.name + ".partial.jsonl"), False, home)
            classes = {i["name"]: i["class"] for i in result["items"]}
            self.assertEqual(classes["bridgeforge"], migrate.IN_GIT)
            self.assertEqual(classes[".git"], migrate.IN_GIT)
            self.assertEqual(classes["In operation"], migrate.IRREPLACEABLE)
            self.assertEqual(classes["Done"], migrate.IRREPLACEABLE)
            self.assertEqual(classes[".venv"], migrate.REGENERABLE)
            self.assertEqual(classes["bridgeforge-state"], migrate.IRREPLACEABLE)
            by_name = {i["name"]: i for i in result["items"]}
            self.assertEqual((by_name["Done"]["files"], by_name["Done"]["bytes"]), (1, 4))
            self.assertEqual(result["outside"][0]["files"], 1)
            kinds = {(h["kind"], h["file"]) for h in result["hazards"]}
            self.assertIn(("psd1", "config/bridgeforge.local.psd1"), kinds)
            self.assertIn(("state-json", "bridgeforge-state/provider-index.json"), kinds)
            self.assertIn(("state-json", "bridgeforge-state/reference-rigs/r.json"), kinds)
            self.assertTrue(any(k == "rig-bat" for k, _ in kinds))
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["root"], str(root))
            self.assertIn("[1/", err.getvalue())
            out.unlink()

    def test_game_files_are_classified_and_junction_is_listed_not_followed(self):
        with resolved_temp_dir() as root, resolved_temp_dir() as game:
            make_repo(root)
            (game / "big.jar").write_bytes(b"x" * 100)
            link_dir(game, root / "In operation" / "_rig" / "starsector-core")
            self.assertEqual(migrate.classify("Starsector9a", set()), migrate.GAME_FILES)
            with redirect_stderr(io.StringIO()):
                result = migrate.migrate_inventory(root, None, None, True, root.parent / "nohome")
            rig = next(i for i in result["items"] if i["name"] == "In operation")
            self.assertEqual(rig["links"], 1)
            self.assertEqual(rig["bytes"], 5)  # the 100-byte jar behind the junction is not counted
            self.assertTrue(any(h["kind"] == "rig-junction" and h["paths"] for h in result["hazards"]))

    def test_resumes_from_checkpoint_and_removes_it(self):
        with resolved_temp_dir() as root, resolved_temp_dir() as work:
            make_repo(root)
            partial = work / "inv.partial.jsonl"
            with redirect_stderr(io.StringIO()):
                migrate.migrate_inventory(root, None, partial, True, work)
            self.assertFalse(partial.exists())
            names = sorted(p.name for p in root.iterdir())
            header = {"command": "migrate-inventory", "root": str(root), "items": names}
            with migrate.Checkpoint(partial, header) as saved:
                saved.add("Done", {"name": "Done", "kind": "dir", "class": "x", "files": 99, "bytes": 1, "links": 0, "link_list": []})
            err = io.StringIO()
            with redirect_stderr(err):
                result = migrate.migrate_inventory(root, None, partial, False, work)
            self.assertEqual(next(i for i in result["items"] if i["name"] == "Done")["files"], 99)
            self.assertIn("Done:", err.getvalue())
            self.assertIn("(from checkpoint)", err.getvalue())

    def test_memory_key_derivation(self):
        from pathlib import Path
        key = migrate.claude_memory_dir(Path("C:\\Users\\exxec\\Documents\\Project BridgeForge"), Path("H")).parent.name
        self.assertEqual(key, "c--Users-exxec-Documents-Project-BridgeForge")


class RelocateTests(unittest.TestCase):
    def test_dry_run_changes_nothing_then_apply_rewrites_with_backups(self):
        with resolved_temp_dir() as root:
            make_repo(root)
            write_hazards(root)
            psd1 = root / "config" / "bridgeforge.local.psd1"
            before = psd1.read_text(encoding="utf-8")
            dry = migrate.relocate(root, OLD, NEW)
            self.assertEqual(psd1.read_text(encoding="utf-8"), before)
            self.assertEqual({c["file"] for c in dry["changes"]},
                             {"config/bridgeforge.local.psd1", "bridgeforge-state/provider-index.json", "In operation/_rig/launch.bat"})
            self.assertFalse(list(root.rglob("*" + migrate.BACKUP_SUFFIX)))
            done = migrate.relocate(root, OLD, NEW, apply=True)
            self.assertTrue(all(c["applied"] for c in done["changes"]))
            text = psd1.read_text(encoding="utf-8")
            self.assertIn(f"ProjectRoot = '{NEW}'", text)
            self.assertIn(f"{NEW}\\Done", text)
            self.assertNotIn("exxec", text)
            self.assertEqual((psd1.parent / (psd1.name + migrate.BACKUP_SUFFIX)).read_text(encoding="utf-8"), before)
            state = json.loads((root / "bridgeforge-state" / "provider-index.json").read_text(encoding="utf-8"))
            self.assertEqual(state, {"p": NEW + "\\Done\\a", "q": "relative/x"})
            other = (root / "bridgeforge-state" / "reference-rigs" / "r.json").read_text(encoding="utf-8")
            self.assertIn("C:\\\\Other", other)  # a path it does not recognise is left alone
            again = migrate.relocate(root, OLD, NEW, apply=True)
            self.assertEqual(again["changes"], [])
            self.assertEqual((psd1.parent / (psd1.name + migrate.BACKUP_SUFFIX)).read_text(encoding="utf-8"), before)

    def test_only_whole_path_prefixes_match_and_game_files_are_skipped(self):
        text, count = migrate.rewrite_text("a C:\\Users\\exxec2\\x and c:/users/exxec/x", "C:\\Users\\exxec", "D:\\n")
        self.assertEqual((text, count), ("a C:\\Users\\exxec2\\x and D:/n/x", 1))
        with resolved_temp_dir() as root, resolved_temp_dir() as game:
            make_repo(root)
            (game / "evil.bat").write_text(OLD, encoding="utf-8")
            link_dir(game, root / "In operation" / "_rig" / "starsector-core")
            result = migrate.relocate(root, OLD, NEW, apply=True)
            self.assertEqual(result["changes"], [])
            self.assertEqual((game / "evil.bat").read_text(encoding="utf-8"), OLD)
            self.assertTrue(any("junction" in n for n in result["notes"]))


class VerifyTests(unittest.TestCase):
    def build_tree(self, root):
        (root / "a").mkdir()
        (root / "a" / "one.txt").write_text("1", encoding="utf-8")
        (root / "a" / "two.txt").write_text("22", encoding="utf-8")
        (root / "top.txt").write_text("t", encoding="utf-8")
        (root / "skip.log").write_text("noise", encoding="utf-8")

    def test_write_then_check_reports_missing_changed_extra(self):
        with resolved_temp_dir() as work, resolved_temp_dir() as tree:
            self.build_tree(tree)
            manifest = work / "m.json"
            with redirect_stderr(io.StringIO()) as err:
                written = migrate.verify_write(tree, manifest, False, ("*.log",))
            self.assertEqual(written["files"], 3)
            self.assertIn("[1/2] a:", err.getvalue())
            self.assertFalse((work / "m.json.partial.jsonl").exists())
            with redirect_stderr(io.StringIO()):
                self.assertTrue(migrate.verify_check(tree, manifest, True)["ok"])
            (tree / "a" / "one.txt").write_text("X", encoding="utf-8")
            (tree / "a" / "two.txt").unlink()
            (tree / "new.txt").write_text("n", encoding="utf-8")
            with redirect_stderr(io.StringIO()):
                result = migrate.verify_check(tree, manifest, True)
            self.assertEqual((result["missing"], result["changed"], result["extra"]), (["a/two.txt"], ["a/one.txt"], ["new.txt"]))
            self.assertFalse(result["ok"])

    def test_write_resumes_hashing_only_unfinished_files(self):
        with resolved_temp_dir() as work, resolved_temp_dir() as tree:
            self.build_tree(tree)
            manifest = work / "m.json"
            stat = (tree / "top.txt").stat()
            header = {"command": "migrate-verify", "dir": str(tree), "mode": "write", "excludes": [], "tops": ["a", "skip.log", "top.txt"]}
            with migrate.Checkpoint(work / "m.json.partial.jsonl", header) as saved:  # a prior run hashed top.txt (fake digest)
                saved.add("top.txt", {"size": stat.st_size, "sha256": "f" * 64, "mtime_ns": stat.st_mtime_ns})
            with redirect_stderr(io.StringIO()):
                migrate.verify_write(tree, manifest, True)
            files = {f["path"]: f["sha256"] for f in json.loads(manifest.read_text(encoding="utf-8"))["files"]}
            self.assertEqual(files["top.txt"], "f" * 64)  # taken from the checkpoint, not rehashed
            self.assertEqual(len(files["a/one.txt"]), 64)

    def test_cli_round_trip_exit_codes(self):
        with resolved_temp_dir() as work, resolved_temp_dir() as tree:
            self.build_tree(tree)
            manifest = str(work / "m.json")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["migrate-verify", "write", str(tree), "--manifest", manifest, "--quiet"]), 0)
                self.assertEqual(main(["migrate-verify", "check", str(tree), "--manifest", manifest, "--quiet"]), 0)
                (tree / "top.txt").write_text("changed", encoding="utf-8")
                self.assertEqual(main(["migrate-verify", "check", str(tree), "--manifest", manifest, "--quiet"]), 1)

    def test_cli_relocate_and_inventory_run(self):
        with resolved_temp_dir() as root, resolved_temp_dir() as work:
            make_repo(root)
            write_hazards(root)
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["relocate", "--root", str(root), "--from", OLD, "--to", NEW]), 0)
                self.assertEqual(main(["migrate-inventory", "--root", str(root), "--quiet", "--checkpoint", str(work / "c.jsonl"),
                                       "--claude-home", str(work)]), 0)
            self.assertIn("DRY RUN", out.getvalue())
            self.assertIn("Absolute-path hazards", out.getvalue())


if __name__ == "__main__":
    unittest.main()
