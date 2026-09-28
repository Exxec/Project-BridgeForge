"""`bridgeforge descriptions apply` (ROADMAP P15 31.5; owner request 2026-09-28: credit crafted descriptions)."""
import csv
import io
import unittest
from pathlib import Path

from bridgeforge.descriptions import CREDITS_FILE, apply_draft, parse_draft
from tests.support import resolved_temp_dir

DRAFT = "| ID | Type | Text |\n| --- | --- | --- |\n| `x_ship` | SHIP | A sturdy hull. |\n| `x_gun` | WEAPON | Fires, with a comma. |\n"


class DescriptionsApplyTests(unittest.TestCase):
    def test_rows_credits_and_original_copy(self) -> None:
        with resolved_temp_dir() as root:
            ws = root / "Mod"
            strings = ws / "working" / "data" / "strings"
            strings.mkdir(parents=True)
            (ws / "working" / "mod_info.json").write_text('{"id": "x", "name": "X Mod", "author": "Someone"}', encoding="utf-8")
            original = b"id,type,text1,text2,notes\r\nx_old,SHIP,By the author,,\r\n"
            (strings / "descriptions.csv").write_bytes(original)
            draft = root / "draft.md"
            draft.write_text(DRAFT, encoding="utf-8")
            first = apply_draft(ws, draft)
            second = apply_draft(ws, draft)  # idempotent: nothing added twice, credits kept
            text = (strings / "descriptions.csv").read_bytes()
            credits = (ws / "working" / CREDITS_FILE).read_text(encoding="utf-8")
            alt = (ws / "alt-original-descriptions" / "Mod" / "data" / "strings" / "descriptions.csv").read_bytes()
        rows = list(csv.reader(io.StringIO(text.decode("utf-8"))))
        self.assertEqual(first["added"], ["x_ship", "x_gun"])
        self.assertEqual(second["added"], [])
        self.assertEqual([r[0] for r in rows], ["id", "x_old", "x_ship", "x_gun"])
        self.assertEqual(rows[3][2], "Fires, with a comma.")
        self.assertNotIn(b"\n", text.replace(b"\r\n", b""))  # CRLF kept
        self.assertTrue(credits.startswith("X Mod: BridgeForge revival credits"))
        self.assertIn("Original mod: Someone", credits)
        self.assertIn("x_ship", credits)
        self.assertIn("x_gun", credits)
        self.assertEqual(alt, original)

    def test_parse_draft_reads_only_table_rows(self) -> None:
        with resolved_temp_dir() as root:
            draft = Path(root) / "d.md"
            draft.write_text("# Title\n\nSome text | with a pipe\n" + DRAFT, encoding="utf-8")
            self.assertEqual([r[0] for r in parse_draft(draft)], ["x_ship", "x_gun"])


if __name__ == "__main__":
    unittest.main()
