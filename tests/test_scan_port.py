"""`port-dropped-feature` (ROADMAP item 73 E4) and the `recreation` packet skeleton."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from bridgeforge.models import ScanResult
from bridgeforge.recreation_plan import PLAN_FILE, render_skeleton, section_numbers, write_skeleton
from bridgeforge.revive import packet_id, revive
from bridgeforge.scan_port import PORT_SOURCE_FILE, _scan_port_dropped_feature, dropped_features
from tests.support import resolved_temp_dir

REPO = Path(__file__).resolve().parent.parent
EVENTS = '{\n "tem_crusade": {"script": "data.scripts.campaign.events.TEM_CrusadeEvent"},\n "tem_other": {},\n}\n'
REPORTS = "event_type,event_stage,p\ntem_crusade,planning,\ntem_crusade,start,\n"
RULES = "id,trigger,conditions,script\nr1,OpenCommLink,,\nr2,TEMCrusadeNews,,\n"
OLD_SETTINGS = '{"plugins": {"TEM_Old": "data.scripts.TEM_Old", "TEM_Keep": "data.scripts.TEM_Keep"}, "graphics": {"a": "b.png"}, "x": 1,}'
NEW_SETTINGS = '{"plugins": {"TEM_Keep": "data.scripts.TEM_Keep"}, "graphics": {}, "x": 1}'


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _port(root: Path, *, record: dict | None = None):
    ws = root / "Templars-0.9.8f"
    old = ws / "scratch" / "port-before"
    new = ws / "working"
    _write(old / "data/campaign/events.json", EVENTS)
    _write(old / "data/campaign/reports.csv", REPORTS)
    _write(old / "data/campaign/rules.csv", RULES)
    _write(old / "data/config/settings.json", OLD_SETTINGS)
    _write(old / "data/scripts/campaign/events/TEM_CrusadeEvent.java", "package data.scripts.campaign.events;\npublic class TEM_CrusadeEvent {}\n")
    _write(old / "data/scripts/campaign/TEM_Manager.java", "package data.scripts.campaign;\npublic class TEM_Manager {}\n")
    _write(new / "mod_info.json", '{"id": "templars", "name": "Templars", "version": "1"}')
    _write(new / "data/campaign/events.json", '{"tem_other": {}}')
    _write(new / "data/campaign/reports.csv", "event_type,event_stage,p\ntem_crusade,planning,\n")
    _write(new / "data/campaign/rules.csv", "id,trigger,conditions,script\nr1,OpenCommLink,,\n")
    _write(new / "data/config/settings.json", NEW_SETTINGS)
    _write(new / "data/scripts/campaign/TEM_Manager.java", "package data.scripts.campaign;\npublic class TEM_Manager {}\n")
    _write(new / PORT_SOURCE_FILE, json.dumps(record or {"schema_version": 1, "old_version": "0.9.8f", "onto": "0.9.9e", "old_tree": "scratch/port-before"}))
    return ws, old, new


def _findings(new: Path):
    result = ScanResult.__new__(ScanResult)
    result.findings = []
    _scan_port_dropped_feature(new, result)
    return result.findings


class DroppedFeatureTests(unittest.TestCase):
    def test_lists_each_category_of_dropped_features(self) -> None:
        with resolved_temp_dir() as root:
            _, old, new = _port(root)
            dropped = dropped_features(old, new)
        self.assertEqual(dropped["classes"], ["data.scripts.campaign.events.TEM_CrusadeEvent"])
        self.assertEqual(dropped["events.json"], ["tem_crusade"])
        self.assertEqual(dropped["reports.csv"], ["tem_crusade/start"])
        self.assertEqual(dropped["settings"], ["plugins.TEM_Old"])  # the graphics asset map is not compared
        self.assertEqual(dropped["rules.csv"], ["TEMCrusadeNews"])

    def test_one_review_finding_per_category_with_its_own_baseline_key(self) -> None:
        with resolved_temp_dir() as root:
            _, _, new = _port(root)
            findings = _findings(new)
        self.assertEqual({f.id for f in findings}, {"port-dropped-feature"})
        self.assertEqual({f.classification for f in findings}, {"REVIEW"})
        self.assertEqual(sorted(f.evidence[0].split(":")[0] for f in findings), ["classes", "events.json", "reports.csv", "rules.csv", "settings"])
        classes = next(f for f in findings if f.evidence[0].startswith("classes"))
        self.assertEqual(classes.evidence, ["classes: data.scripts.campaign.events: TEM_CrusadeEvent"])
        self.assertIn("0.9.8f", classes.explanation)

    def test_nothing_without_a_record_or_with_an_unusable_old_tree(self) -> None:
        with resolved_temp_dir() as root:
            _, _, new = _port(root)
            (new / PORT_SOURCE_FILE).unlink()
            self.assertEqual(_findings(new), [])
        for bad in ("scratch/missing", "../outside", str(Path(__file__).resolve().parent), ""):
            with self.subTest(bad), resolved_temp_dir() as root:
                _, _, new = _port(root, record={"schema_version": 1, "old_tree": bad})
                self.assertEqual(_findings(new), [])

    def test_nothing_when_the_new_version_still_has_everything(self) -> None:
        with resolved_temp_dir() as root:
            _, old, new = _port(root)
            _write(old / "data/campaign/events.json", '{"tem_other": {}}')
            _write(old / "data/campaign/reports.csv", "event_type,event_stage,p\ntem_crusade,planning,\n")
            _write(old / "data/campaign/rules.csv", "id,trigger,conditions,script\nr1,OpenCommLink,,\n")
            _write(old / "data/config/settings.json", NEW_SETTINGS)
            (old / "data/scripts/campaign/events/TEM_CrusadeEvent.java").unlink()
            self.assertEqual(_findings(new), [])

    def test_a_whole_old_version_below_original_is_found_by_its_mod_info(self) -> None:
        with resolved_temp_dir() as root:
            ws, _, new = _port(root, record={"schema_version": 1, "old_tree": "original/extracted"})
            _write(ws / "original/extracted/Templars/mod_info.json", '{"id": "templars"}')
            _write(ws / "original/extracted/Templars/data/campaign/events.json", EVENTS)
            findings = _findings(new)
        self.assertEqual([f.evidence[0].split(":")[0] for f in findings], ["events.json"])


class RecreationPacketTests(unittest.TestCase):
    def test_the_skeleton_has_every_section_of_the_worked_plan(self) -> None:
        plan = (REPO / "docs" / "TEMPLAR_CRUSADE_PLAN.md").read_text(encoding="utf-8")
        wanted = [m.group(1) for m in re.finditer(r"^#{2,3} (\d+[a-z]?(?:\.\d+)?)\.? ", plan, re.M)]
        self.assertEqual(list(section_numbers()), wanted)
        skeleton = render_skeleton("Mod", {"findings": [{"evidence": ["classes: x: A"]}]})
        for number in wanted:
            self.assertRegex(skeleton, rf"(?m)^#{{2,3}} {re.escape(number)}\. ")
        self.assertIn("classes: x: A", skeleton)

    def test_revive_makes_a_recreation_packet_and_writes_the_skeleton_once(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "In operation"
            ws, _, _ = _port(queue)
            result = revive(ws)
            wanted = [p for p in result["packets"] if p["finding"] == "port-dropped-feature"]
            skeleton = ws / "reports" / PLAN_FILE
            text = skeleton.read_text(encoding="utf-8")
            skeleton.write_text("owner edits", encoding="utf-8")
            revive(ws)
            kept = skeleton.read_text(encoding="utf-8")
            prompt = (ws / "reports" / "escalations" / f"{wanted[0]['id']}.md").read_text(encoding="utf-8")
            self.assertIsNone(write_skeleton(ws, {"findings": []}))
        self.assertEqual({p["kind"] for p in wanted}, {"recreation"})
        self.assertEqual(len(wanted), 1)  # one packet: the five category findings share a file
        self.assertEqual(wanted[0]["id"], packet_id("port-dropped-feature", ""))
        self.assertIn("## 3.8. Save safety", text)
        self.assertEqual(kept, "owner edits")
        self.assertIn("Nothing is restored automatically", prompt)


if __name__ == "__main__":
    unittest.main()
