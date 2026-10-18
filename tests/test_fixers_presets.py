"""preset-entry-drops-vanilla-fields fixer: field-specific approval only (ROADMAP item 73 B4, item 75 R4)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.fixers_presets import file_sha256, preset_field_proposals
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import _parse_json, scan_mod
from tests.support import resolved_temp_dir

FINDING = "preset-entry-drops-vanilla-fields"
REL = "data/config/engine_styles.json"
VANILLA = {
    "LOW_TECH": {"engineColor": [255, 125, 25, 255], "contrailColor": [255, 125, 25, 150], "contrailCampaignColor": [255, 125, 25, 150],
                 "contrailWidthMult": 1, "engineFlameSize": 2.5},
    "MIDLINE": {"engineColor": [255, 200, 100, 255], "contrailCampaignColor": [255, 200, 100, 150]},
}
OLD_VANILLA = {"LOW_TECH": {"engineColor": [255, 125, 25, 255], "contrailColor": [255, 125, 25, 150], "contrailWidthMult": 1}}
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
    _write(mod / REL, mod_text)
    _write(core / REL, json.dumps(VANILLA))
    return mod, core


def _approval(mod: Path, entry: str, field: str) -> dict:
    return {"file": REL, "entry": entry, "field": field, "file_sha256": file_sha256(mod / REL)}


def _parse(path: Path) -> dict:
    return _parse_json(path.read_text(encoding="utf-8-sig"))[0]


class PresetFieldApprovalTests(unittest.TestCase):
    def test_restores_only_the_approved_field_and_preserves_every_other_omission(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            plan = compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [_approval(mod, "LOW_TECH", "contrailCampaignColor")]})
            apply_fix(plan)
            path = mod / REL
            text, data = path.read_text(encoding="utf-8"), _parse(path)
        self.assertEqual(data["LOW_TECH"]["contrailCampaignColor"], [255, 125, 25, 150])
        self.assertNotIn("engineFlameSize", data["LOW_TECH"])  # an unapproved omission stays omitted
        self.assertEqual(data["LOW_TECH"]["engineColor"], [255, 0, 0, 255])  # the mod's own value survives
        self.assertEqual(data["LOW_TECH"]["contrailWidthMult"], 3)
        self.assertEqual(data["MY_STYLE"], {"engineColor": [1, 2, 3, 255]})
        self.assertTrue(text.startswith("# old template\n"))
        self.assertIn("# red, the mod's own", text)
        self.assertIn('\t\t"contrailCampaignColor": [255, 125, 25, 150]\n', text)  # the file's own tab indentation

    def test_finding_id_alone_never_restores_anything(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            findings = [f.__dict__ for f in scan_mod(mod, TargetProfile("0.98a-RC8", 17), core).findings if f.id == FINDING]
            self.assertTrue(findings)
            with self.assertRaisesRegex(FixerError, "field-specific approval"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "scan_findings": findings})
            with self.assertRaisesRegex(FixerError, "field-specific approval"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": []})

    def test_stale_approval_unknown_key_and_missing_core_are_refused(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            approval = _approval(mod, "LOW_TECH", "contrailCampaignColor")
            with self.assertRaisesRegex(FixerError, "unknown fields are refused"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [{**approval, "reason": "wildcard"}]})
            with self.assertRaisesRegex(FixerError, "needs --vanilla-core"):
                compute_fix(mod, FINDING, {"approved_fields": [approval]})
            (mod / REL).write_bytes((mod / REL).read_bytes() + b"\n")  # the file changes after approval
            with self.assertRaisesRegex(FixerError, "stale approval"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [approval]})

    def test_approved_edit_is_idempotent_and_a_field_rc8_lacks_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            apply_fix(compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [_approval(mod, "LOW_TECH", "engineFlameSize")]}))
            with self.assertRaises(FixerError):  # re-approved against the new bytes: nothing left to add
                compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [_approval(mod, "LOW_TECH", "engineFlameSize")]})
            with self.assertRaisesRegex(FixerError, "RC8 has no field"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [_approval(mod, "LOW_TECH", "madeUp")]})

    def test_five_field_vanilla_entry_and_three_field_mod_entry_end_with_five_when_all_are_approved(self) -> None:
        vanilla = {"star_red": {"type": "star", "texture": "a.png", "iconTexture": "b.png", "glow": "g.png", "radius": 5}}
        relative = "data/config/planets.json"
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            _write(mod / "mod_info.json", '{"id":"f","name":"F","gameVersion":"0.98a"}')
            _write(mod / relative, '{"star_red": {"type": "star", "texture": "mine.png", "radius": 9}}')
            _write(core / relative, json.dumps(vanilla))
            approvals = [{"file": relative, "entry": "star_red", "field": f, "file_sha256": file_sha256(mod / relative)} for f in ("iconTexture", "glow")]
            apply_fix(compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": approvals}))
            entry = _parse(mod / relative)["star_red"]
        self.assertEqual(sorted(entry), ["glow", "iconTexture", "radius", "texture", "type"])
        self.assertEqual((entry["texture"], entry["radius"]), ("mine.png", 9))

    def test_crlf_bom_and_one_line_entries_survive(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT.replace("\n", "\r\n"))
            path = mod / REL
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
            apply_fix(compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [_approval(mod, "LOW_TECH", "contrailCampaignColor")]}))
            raw = path.read_bytes()
            inline, core2 = _fixture(root / "b", '{"MIDLINE": {"engineColor": [1, 1, 1, 255]}}')
            apply_fix(compute_fix(inline, FINDING, {"vanilla_core": core2, "approved_fields": [_approval(inline, "MIDLINE", "contrailCampaignColor")]}))
            data = _parse(inline / REL)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertEqual(data["MIDLINE"], {"engineColor": [1, 1, 1, 255], "contrailCampaignColor": [255, 200, 100, 150]})

    def test_sounds_json_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = root / "mod", root / "core"
            _write(mod / "mod_info.json", '{"id":"f","name":"F","gameVersion":"0.98a"}')
            _write(mod / "data/config/sounds.json", '{"music": {"title": {"a": 1}}}')
            _write(core / "data/config/sounds.json", json.dumps({"music": {"title": {"a": 1, "b": 2}}}))
            approval = {"file": "data/config/sounds.json", "entry": "music", "field": "b", "file_sha256": file_sha256(mod / "data/config/sounds.json")}
            with self.assertRaisesRegex(FixerError, "nested categories"):
                compute_fix(mod, FINDING, {"vanilla_core": core, "approved_fields": [approval]})


class PresetEvidenceTests(unittest.TestCase):
    def test_proposals_carry_three_way_evidence_and_modify_nothing(self) -> None:
        with resolved_temp_dir() as root:
            mod, core = _fixture(root, MOD_TEXT)
            old = root / "old"
            _write(old / REL, json.dumps(OLD_VANILLA))
            before = (mod / REL).read_bytes()
            rows = {(r["entry"], r["field"]): r for r in preset_field_proposals(mod, core, old)}
            blind = {(r["entry"], r["field"]): r for r in preset_field_proposals(mod, core, None)}
            unchanged = (mod / REL).read_bytes() == before
            removed = preset_field_proposals(mod, core, _old_with_field(root))
        self.assertTrue(unchanged)
        self.assertIn("lacked it too", rows[("LOW_TECH", "contrailCampaignColor")]["old_state"])  # RC8 added it: likely stale
        self.assertEqual(rows[("LOW_TECH", "contrailCampaignColor")]["rc8_value"], "[255, 125, 25, 150]")
        self.assertTrue(all("unknown" in r["old_state"] for r in blind.values()))
        self.assertTrue(any("HAD this field" in r["old_state"] for r in removed))


def _old_with_field(root: Path) -> Path:
    old = root / "old2"
    _write(old / REL, json.dumps({"LOW_TECH": {**VANILLA["LOW_TECH"]}}))
    return old


if __name__ == "__main__":
    unittest.main()
