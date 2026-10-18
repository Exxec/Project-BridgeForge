"""`bridgeforge descriptions draft` (ROADMAP item 73 D1; owner decision 2026-10-14)."""
import json
import unittest
from pathlib import Path

from bridgeforge.descriptions import CREDITS_FILE, apply_draft, parse_draft, parse_draft_sources
from bridgeforge.descriptions_draft import DRAFT_RELATIVE, check_crafted, draft_descriptions, draft_workspace
from tests.support import resolved_temp_dir

SHIP_DATA = "name,id,designation,tech/manufacturer,hints\n{rows}"
GOOD = "A sturdy escort hull. It carries light weapons and a modest cargo bay."


def make_mod(root: Path, name: str, mod_id: str, hulls: list[str], described: dict[str, str] | None = None) -> Path:
    working = root / name / "working"
    (working / "data" / "hulls").mkdir(parents=True)
    (working / "data" / "strings").mkdir(parents=True)
    (working / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": name, "author": "Someone", "version": "1"}), encoding="utf-8")
    (working / "data" / "hulls" / "ship_data.csv").write_text(
        SHIP_DATA.format(rows="".join(f"{h.title()},{h},Frigate,Low Tech,\n" for h in hulls)), encoding="utf-8")
    rows = "".join(f"{cid},SHIP,{text},,,,,\n" for cid, text in (described or {}).items())
    (working / "data" / "strings" / "descriptions.csv").write_text("id,type,text1,text2,text3,text4,text5,notes\n" + rows, encoding="utf-8")
    return root / name


class StubCrafter:
    def __init__(self, text: str = GOOD) -> None:
        self.text, self.calls, self.entries = text, 0, []

    def __call__(self, chunk_file: Path) -> str:
        self.calls += 1
        document = json.loads(chunk_file.read_text(encoding="utf-8"))
        for entry in document["entries"]:
            entry["text"] = self.text
            self.entries.append(entry)
        chunk_file.write_text(json.dumps(document), encoding="utf-8")
        return "ok"


class DraftSourceOrderTests(unittest.TestCase):
    def test_version_beats_sibling_beats_crafted(self) -> None:
        with resolved_temp_dir() as root:
            target = make_mod(root, "Mod", "modid", ["h_version", "h_sibling", "h_crafted"])
            # Another version of the same mod and a sibling mod both describe h_version; only the sibling has h_sibling.
            make_mod(root, "Mod old", "modid", ["h_version"], {"h_version": "From the old version."})
            make_mod(root, "Pack mate", "other", ["h_version", "h_sibling"], {"h_version": "From the sibling.", "h_sibling": "From the sibling."})
            crafter = StubCrafter()
            result = draft_workspace(target, crafter=crafter)
            rows = {(r[0]): r for r in parse_draft(target / DRAFT_RELATIVE)}
            sources = parse_draft_sources(target / DRAFT_RELATIVE)
        self.assertEqual(rows["h_version"][2], "From the old version.")
        self.assertEqual(sources[("h_version", "SHIP")], "version: Mod old")
        self.assertEqual(rows["h_sibling"][2], "From the sibling.")
        self.assertEqual(sources[("h_sibling", "SHIP")], "sibling: Pack mate")
        self.assertEqual(rows["h_crafted"][2], GOOD)
        self.assertEqual(sources[("h_crafted", "SHIP")], "crafted")
        self.assertEqual(result["by_source"], {"version": 1, "sibling": 1, "crafted": 1})
        self.assertEqual([e["id"] for e in crafter.entries], ["h_crafted"])  # the agent only sees what no copy had
        self.assertEqual(crafter.entries[0]["facts"]["name"], "H_Crafted")

    def test_no_crafted_skips_the_agent_and_lists_the_rest_unresolved(self) -> None:
        with resolved_temp_dir() as root:
            target = make_mod(root, "Mod", "modid", ["h_one"])
            result = draft_workspace(target, crafter=None)
            text = (target / DRAFT_RELATIVE).read_text(encoding="utf-8")
        self.assertEqual(result["rows"], 0)
        self.assertEqual(result["unresolved"][0]["id"], "h_one")
        self.assertIn("## Unresolved", text)

    def test_extra_version_source_folder_is_searched_by_mod_id(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "queue"
            queue.mkdir()
            target = make_mod(queue, "Mod", "modid", ["h_one"])
            done = root / "Done"
            make_mod(done, "Mod archive", "modid", ["h_one"], {"h_one": "Archived text."})
            draft_workspace(target, crafter=None, version_sources=[done])
            sources = parse_draft_sources(target / DRAFT_RELATIVE)
        self.assertTrue(sources[("h_one", "SHIP")].startswith("version:"))


class CraftedRowTests(unittest.TestCase):
    def test_bad_crafted_text_is_rejected_not_written(self) -> None:
        with resolved_temp_dir() as root:
            target = make_mod(root, "Mod", "modid", ["h_one"])
            result = draft_workspace(target, crafter=StubCrafter("One sentence only."))
        self.assertEqual(result["rows"], 0)
        self.assertIn("sentence", result["unresolved"][0]["reason"])

    def test_check_crafted_rules(self) -> None:
        self.assertIsNone(check_crafted(GOOD))
        self.assertEqual(check_crafted(""), "blank")
        self.assertIsNotNone(check_crafted("Has | a bar. And two."))
        self.assertIsNotNone(check_crafted("舰船. Second sentence."))
        self.assertIsNotNone(check_crafted("One. Two. Three. Four. Five."))

    def test_only_crafted_rows_are_credited_as_crafted_on_apply(self) -> None:
        with resolved_temp_dir() as root:
            target = make_mod(root, "Mod", "modid", ["h_version", "h_crafted"])
            make_mod(root, "Mod old", "modid", ["h_version"], {"h_version": "From the old version."})
            draft_workspace(target, crafter=StubCrafter())
            apply_draft(target, target / DRAFT_RELATIVE)
            credits = (target / "working" / CREDITS_FILE).read_text(encoding="utf-8")
            csv_text = (target / "working" / "data" / "strings" / "descriptions.csv").read_text(encoding="utf-8")
        self.assertIn("h_crafted", credits)
        self.assertNotIn("h_version", credits)
        self.assertIn("From the old version.", csv_text)
        self.assertIn(GOOD, csv_text)

    def test_a_hand_written_three_column_draft_still_counts_as_crafted(self) -> None:
        with resolved_temp_dir() as root:
            target = make_mod(root, "Mod", "modid", [])
            draft = root / "d.md"
            draft.write_text("| ID | Type | Text |\n| --- | --- | --- |\n| `x_ship` | SHIP | A hull. |\n", encoding="utf-8")
            apply_draft(target, draft)
            credits = (target / "working" / CREDITS_FILE).read_text(encoding="utf-8")
        self.assertIn("x_ship", credits)


class QueueTests(unittest.TestCase):
    def test_queue_run_writes_a_sheet_per_workspace_and_removes_the_checkpoint(self) -> None:
        with resolved_temp_dir() as root:
            make_mod(root, "A", "a", ["a_hull"])
            make_mod(root, "B", "b", ["b_hull"])
            checkpoint = root / "description-drafts.partial.jsonl"
            result = draft_descriptions(root, crafter=StubCrafter(), checkpoint_path=checkpoint, quiet=True)
            sheets = [(root / n / DRAFT_RELATIVE).is_file() for n in ("A", "B")]
        self.assertEqual((result["mods"], result["rows"], result["by_source"]["crafted"]), (2, 2, 2))
        self.assertEqual(sheets, [True, True])
        self.assertFalse(checkpoint.exists())


if __name__ == "__main__":
    unittest.main()
