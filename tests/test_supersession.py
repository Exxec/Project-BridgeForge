"""`bridgeforge supersession` (2026-09-27): queued mods whose author has a newer release elsewhere."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.supersession import CHECKPOINT_FILE, RESULT_FILE, find_superseded, version_key
from tests.support import resolved_temp_dir


def _mod(folder: Path, mod_id: str, version: str, game: str, name: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": name or mod_id, "version": version, "gameVersion": game}), encoding="utf-8")


def _workspace(queue: Path, name: str, mod_id: str, original_version: str) -> None:
    _mod(queue / name / "original" / name, mod_id, original_version, "0.95.1a-RC6", name)
    _mod(queue / name / "working", mod_id, original_version + "+bf.1", "0.98a-RC8", name)


class SupersessionTests(unittest.TestCase):
    def test_version_key_drops_bridgeforge_suffix_and_letters(self) -> None:
        self.assertEqual(version_key("V18+bf.4"), (18,))
        self.assertEqual(version_key("1.8.2a"), (1, 8, 2))

    def test_verdicts_and_resumable_run(self) -> None:
        with resolved_temp_dir() as root:
            queue, ref = root / "queue", root / "mods"
            _workspace(queue, "Kazeron", "kaz", "1.2")
            _workspace(queue, "Same", "same", "2.5")
            _workspace(queue, "OldGame", "old", "1.0")
            _workspace(queue, "Older", "older", "3.0")
            _workspace(queue, "Alone", "alone", "1.0")
            _mod(ref / "Kazeron Navarchy-1.8.0", "kaz", "1.8.0", "0.98a")
            _mod(ref / "Same-2.5", "same", "2.5", "0.98a-RC8")
            _mod(ref / "download" / "OldGame-2.0", "old", "2.0", "0.97a")  # nested one folder down
            _mod(ref / "Older-2.0", "older", "2.0", "0.98a")
            _mod(ref / "Deployed", "alone", "1.0+bf.1", "0.98a-RC8")  # our own revival deployed: ignored
            (queue / CHECKPOINT_FILE).write_text(json.dumps({"stale": True}) + "\n", encoding="utf-8")
            result = find_superseded(queue, [ref], quiet=True)
            written = json.loads((queue / RESULT_FILE).read_text(encoding="utf-8"))
            checkpoint_left = (queue / CHECKPOINT_FILE).exists()
        verdicts = {m["workspace"]: m["verdict"] for m in result["mods"]}
        self.assertEqual(verdicts, {"Kazeron": "SUPERSEDED", "Same": "SAME_RELEASE", "OldGame": "NEWER_ELSEWHERE",
                                    "Older": "NOT_SUPERSEDED", "Alone": "NO_MATCH"})
        self.assertEqual(written["counts"]["SUPERSEDED"], 1)
        self.assertFalse(checkpoint_left)

    def test_corpus_index_mods_count_and_our_revival_builds_do_not(self) -> None:
        # ROADMAP P15 31.11: the Downloads archive (a corpus-index database) as a reference.
        import sqlite3
        import zipfile

        with resolved_temp_dir() as root:
            queue, downloads = root / "queue", root / "Downloads"
            _workspace(queue, "Pack", "pack", "1.0")
            _workspace(queue, "Void", "void", "0.2.2")
            _mod(downloads / "Modpack" / "mods" / "Pack", "pack", "2.0", "0.98")
            with zipfile.ZipFile(downloads / "Void-revival.zip", "w") as archive:
                archive.writestr("Void/mod_info.json", json.dumps({"id": "void", "version": "0.2.2-0.98a-revival-r13", "gameVersion": "0.98a"}))
            db = root / "index.sqlite"
            connection = sqlite3.connect(db)
            with connection:
                connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
                connection.execute("CREATE TABLE files (location TEXT PRIMARY KEY, source TEXT, size INTEGER)")
                connection.execute("INSERT INTO meta VALUES ('root', ?)", (str(downloads),))
                connection.execute("INSERT INTO files VALUES (?, ?, 1)", ("Modpack/mods/Pack/mod_info.json", "Modpack/mods/Pack/mod_info.json"))
                connection.execute("INSERT INTO files VALUES (?, ?, 1)", ("Void-revival.zip!Void/mod_info.json", "Void-revival.zip"))
            connection.close()
            result = find_superseded(queue, [], quiet=True, corpus_index=db)
        verdicts = {m["workspace"]: m["verdict"] for m in result["mods"]}
        self.assertEqual(verdicts, {"Pack": "SUPERSEDED", "Void": "NO_MATCH"})

if __name__ == "__main__":
    unittest.main()
