"""preset-entry-drops-vanilla-fields fixer (ROADMAP item 73 B4)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import _parse_json, scan_mod
from tests.support import resolved_temp_dir

FINDING = "preset-entry-drops-vanilla-fields"
VANILLA = {
    "LOW_TECH": {"engineColor": [255, 125, 25, 255], "contrailColor": [255, 125, 25, 150], "contrailCampaignColor": [255, 125, 25, 150],
                 "contrailWidthMult": 1, "engineFlameSize": 2.5},
    "MIDLINE": {"engineColor": [255, 200, 100, 255], "contrailCampaignColor": [255, 200, 100, 150]},
}
# Zorg18's shape (2026-09-20): an old template, hand-indented, with a comment and a trailing comma.
MOD_TEXT = """# old template
{
\t"LOW_TECH": {
\t\t"engineColor": [255, 0, 0, 255],   # red, the mod's own
\t\t"contrailColor": [255, 125, 25, 150],
\t\t"contrailWidthMult": 3,
\t},
\t"MY_STYLE": {"engineColor": [1, 2, 3, 255]},
}
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _fixture(root: Path, mod_text: str) -> tuple[Path, Path]:
    mod, core = root / "mod", root / "core"
    _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
    _write(mod / "data" / "config" / "engine_styles.json", mod_text)
    _write(core / "data" / "config" / "engine_styles.json", json.dumps(VANILLA))
    return mod, core


def _parse(path: Path) -> dict:
    return _parse_json(path.read_text(encoding="utf-8-sig"))[0]


class PresetFieldMergeTests(unittest.TestCase):
    def test_restores_missing_fields_keeps_mod_values_and_the_finding_clears(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            plan = compute_fix(mod, FINDING, {"vanilla_core": core})
            apply_fix(plan)
            path = mod / "data" / "config" / "engine_styles.json"
            text = path.read_text(encoding="utf-8")
            data = _parse(path)
            after = [f.id for f in scan_mod(mod, TargetProfile("0.98a-RC8", 17), core).findings]
        self.assertEqual(data["LOW_TECH"]["engineColor"], [255, 0, 0, 255])  # the mod's value survives
        self.assertEqual(data["LOW_TECH"]["contrailWidthMult"], 3)
        self.assertEqual(data["LOW_TECH"]["contrailCampaignColor"], [255, 125, 25, 150])
        self.assertEqual(data["LOW_TECH"]["engineFlameSize"], 2.5)
        self.assertEqual(data["MY_STYLE"], {"engineColor": [1, 2, 3, 255]})  # a mod-only id is untouched
        self.assertTrue(text.startswith("# old template\n"))
        self.assertIn("# red, the mod's own", text)
        self.assertIn('\t\t"contrailCampaignColor": [255, 125, 25, 150],', text)  # file's own tab indentation
        self.assertNotIn(FINDING, after)

    def test_five_field_vanilla_entry_and_three_field_mod_entry_end_with_five_and_it_is_idempotent(self) -> None:
        vanilla = {"star_red": {"type": "star", "texture": "a.png", "iconTexture": "b.png", "glow": "g.png", "radius": 5}}
        mine = '{"star_red": {"type": "star", "texture": "mine.png", "radius": 9}}'
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            _write(mod / "mod_info.json", '{"id":"f","name":"F","gameVersion":"0.98a"}')
            _write(mod / "data" / "config" / "planets.json", mine)
            _write(core / "data" / "config" / "planets.json", json.dumps(vanilla))
            apply_fix(compute_fix(mod, FINDING, {"vanilla_core": core}))
            entry = _parse(mod / "data" / "config" / "planets.json")["star_red"]
            with self.assertRaises(FixerError):
                compute_fix(mod, FINDING, {"vanilla_core": core})
        self.assertEqual(sorted(entry), ["glow", "iconTexture", "radius", "texture", "type"])
        self.assertEqual((entry["texture"], entry["radius"]), ("mine.png", 9))

    def test_crlf_and_bom_survive(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT.replace("\n", "\r\n"))
            path = mod / "data" / "config" / "engine_styles.json"
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
            apply_fix(compute_fix(mod, FINDING, {"vanilla_core": core}))
            raw = path.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))

    def test_one_line_entries_get_inline_members(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, '{"MIDLINE": {"engineColor": [1, 1, 1, 255]}}')
            apply_fix(compute_fix(mod, FINDING, {"vanilla_core": core}))
            data = _parse(mod / "data" / "config" / "engine_styles.json")
        self.assertEqual(data["MIDLINE"], {"engineColor": [1, 1, 1, 255], "contrailCampaignColor": [255, 200, 100, 150]})

    def test_refuses_without_the_vanilla_core(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            findings = [f.__dict__ if hasattr(f, "__dict__") else f for f in scan_mod(mod, TargetProfile("0.98a-RC8", 17), core).findings]
            with self.assertRaisesRegex(FixerError, "needs --vanilla-core"):
                compute_fix(mod, FINDING, {"scan_findings": findings})

    def test_sounds_json_is_refused_with_a_reason(self) -> None:
        vanilla = {"music": {"title": "a.ogg", "campaign": "b.ogg"}}
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            _write(mod / "mod_info.json", '{"id":"f","name":"F","gameVersion":"0.98a"}')
            _write(mod / "data" / "config" / "sounds.json", '{"music": {"title": {"a": 1}}}')
            _write(core / "data" / "config" / "sounds.json", json.dumps({"music": {"title": {"a": 1, "b": 2}}}))
            finding = {"id": FINDING, "file": "data/config/sounds.json", "evidence": ["music.title: loses b"]}
            with self.assertRaisesRegex(FixerError, "sounds.json"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "scan_findings": [finding]})
        self.assertIn("music", vanilla)


if __name__ == "__main__":
    unittest.main()
