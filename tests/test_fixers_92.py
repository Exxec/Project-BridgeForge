"""Fixer and check gaps from the six-mod 0.98.5a batch (ROADMAP-3 items 92.14, 92.18, 92.19, 92.31; 2026-11-16)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.fixers import apply_fix, compute_fix
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

INFO = '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8"}'


def _write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))


class FixerGapTests(unittest.TestCase):
    def test_paired_guillemets_are_cp1252_typography(self) -> None:
        # Musashi Manufactorum: NBSP plus three «...» pairs, refused as "not CP-1252 punctuation".
        with resolved_temp_dir() as root:
            _write(root / "mod_info.json", INFO)
            _write(root / "data" / "strings" / "descriptions.csv",
                   b"id,type,text1\nmm_a,SHIP,The \xabcage\xbb and the\xa0dome.\n")
            apply_fix(compute_fix(root, "data-file-not-utf8", {}))
            text = (root / "data" / "strings" / "descriptions.csv").read_text(encoding="utf-8")
        self.assertIn("The «cage» and the dome.", text)

    def test_an_unpaired_guillemet_is_still_refused(self) -> None:
        from bridgeforge.fixers import FixerError

        with resolved_temp_dir() as root:
            _write(root / "mod_info.json", INFO)
            _write(root / "data" / "strings" / "descriptions.csv", b"id,type,text1\nmm_a,SHIP,Half \xab open.\n")
            with self.assertRaises(FixerError):
                compute_fix(root, "data-file-not-utf8", {})

    def test_removing_an_empty_work_file_leaves_no_orphan_backup(self) -> None:
        # Musashi: an empty graphics/mm/ships/isetsu/debug.log left a 0-byte .bak, then fixer-backup-orphaned.
        with resolved_temp_dir() as root:
            working = root / "In operation" / "Mod" / "working"
            _write(working / "mod_info.json", INFO)
            _write(working / "graphics" / "ships" / "debug.log", b"log line\n")
            _write(working / "graphics" / "ships" / "sub" / "debug.log", b"")
            apply_fix(compute_fix(working, "shippable-work-file", {}))
            leftovers = sorted(p.name for p in working.rglob("*.bak"))
            ids = [f.id for f in scan_mod(working).findings]
        self.assertEqual(leftovers, [])
        self.assertNotIn("fixer-backup-orphaned", ids)

    def test_json_comments_and_keys_are_not_player_text(self) -> None:
        # Eridani Combine: trailing '#' comments in .faction/*_styles.json and a designTypeColors key.
        with resolved_temp_dir() as root:
            _write(root / "mod_info.json", INFO)
            _write(root / "data" / "config" / "engine_styles.json", '{"S": {"color":[1,2,3,4], # 示例注释\n}}\n')
            _write(root / "data" / "config" / "settings.json", '{"designTypeColors": {"示例设计":[1,2,3,255]}}\n')
            clean = [f.id for f in scan_mod(root).findings]
            _write(root / "data" / "config" / "settings.json", '{"name": "示例名"}\n')  # a value is player text
            flagged = [f.id for f in scan_mod(root).findings]
        self.assertNotIn("player-text-non-english", clean)
        self.assertIn("player-text-non-english", flagged)

    def test_captain_fix_edits_a_jar_mods_src_and_asks_for_the_rebuild(self) -> None:
        # 92.27: Navarchy of Tania's spawner is a jar-backed source; the fixer refused it and 16 calls were fixed by hand.
        import zipfile

        with resolved_temp_dir() as root:
            _write(root / "mod_info.json", '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8","jars":["jars/demo.jar"]}')
            (root / "jars").mkdir()
            with zipfile.ZipFile(root / "jars" / "demo.jar", "w") as jar:
                jar.writestr("data/scripts/Spawner.class", b"\xca\xfe\xba\xbe")
            _write(root / "src" / "data" / "scripts" / "Spawner.java",
                   "package data.scripts;\nclass Spawner { void go(Object e, Object p) {\n"
                   "    engine.getFleetManager(1).spawnShipOrWing(\"tania_amalgam_med_Var1\", p, 0f);\n} }\n")
            apply_fix(compute_fix(root, "spawned-ship-captain-personality-risk", {}))
            text = (root / "src" / "data" / "scripts" / "Spawner.java").read_text(encoding="utf-8")
            ids = [f.id for f in scan_mod(root).findings]
        self.assertIn('"tania_amalgam_med_Var1", p, 0f, 0f, bfSpawnCaptain())', text)
        self.assertIn("jar-source-not-rebuilt", ids)

    def test_fullwidth_punctuation_in_english_text_is_made_ascii(self) -> None:
        # 92.32: Eridani after translation: a full-width colon in its author credit and a full-width comma in a hull mod's
        # text (fixed by hand), outside the game font. Synthetic text below.
        with resolved_temp_dir() as root:
            _write(root / "mod_info.json", '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98a-RC8","author":"Art Support：Demo"}\r\n')
            _write(root / "data" / "hullmods" / "hull_mods.csv",
                   'name,id,desc\r\nPulse,demo_t,"Burst of %s seconds，holds %s charges."\r\nUntranslated,demo_u,"示例，名"\r\n')
            found = [f for f in scan_mod(root).findings if f.id == "fullwidth-punctuation-in-text"]
            apply_fix(compute_fix(root, "fullwidth-punctuation-in-text", {}))
            info = (root / "mod_info.json").read_bytes()
            csv_text = (root / "data" / "hullmods" / "hull_mods.csv").read_bytes().decode("utf-8")
            after = [f.id for f in scan_mod(root).findings]
        self.assertEqual(found[0].classification, "SAFE")
        self.assertIn(b'"author":"Art Support:Demo"}\r\n', info)  # line ending kept
        self.assertIn("Burst of %s seconds, holds %s charges.", csv_text)
        self.assertIn("示例，名", csv_text)  # an untranslated line is left to translation
        self.assertNotIn("fullwidth-punctuation-in-text", after)

    def test_fix_rescans_with_its_own_target(self) -> None:
        # 92.14: `fix --target-game-version 0.98.5a-RC7` set the value and still reported "STILL PRESENT".
        import contextlib
        import io

        from bridgeforge.cli import main

        with resolved_temp_dir() as root:
            _write(root / "mod_info.json", '{"id":"demo","name":"Demo","version":"1.0","gameVersion":"0.98"}')
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["fix", str(root), "--finding", "mod-info-game-version-inexact",
                             "--target-game-version", "0.98.5a-RC7", "--apply"])
            info = json.loads((root / "mod_info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["gameVersion"], "0.98.5a-RC7")
        self.assertIn("resolved after rescan", out.getvalue())
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
