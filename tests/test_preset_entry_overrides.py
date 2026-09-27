from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

VANILLA_ENGINE_STYLES = {
    "LOW_TECH": {"engineColor": [255, 125, 25, 255], "contrailColor": [255, 125, 25, 150], "contrailCampaignColor": [255, 125, 25, 150]},
    "MIDLINE": {"engineColor": [255, 200, 100, 255], "contrailCampaignColor": [255, 200, 100, 150]},
    "HIGH_TECH": {"engineColor": [100, 165, 255, 255], "contrailCampaignColor": [100, 165, 255, 150]},
}


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")


def _scan(root: Path, mod_files: dict[str, object], vanilla_files: dict[str, object]):
    mod, core = root / "mod", root / "core"
    _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
    for name, data in mod_files.items():
        _write(mod / "data" / "config" / name, data)
    for name, data in vanilla_files.items():
        _write(core / "data" / "config" / name, data)
    result = scan_mod(mod, TargetProfile("0.98a-RC8", 17), core)
    return {f.id: f for f in result.findings if f.id.startswith("preset-entry-")}


class PresetEntryOverrideTests(unittest.TestCase):
    def test_zorg18_stale_template_drops_a_field_game_wide(self):
        # Zorg18 (2026-09-20): an old copy of the three vanilla styles, without contrailCampaignColor.
        stale = {key: {k: v for k, v in value.items() if k != "contrailCampaignColor"} for key, value in VANILLA_ENGINE_STYLES.items()}
        stale["ZORG_TECH"] = {"engineColor": [1, 2, 3, 255]}
        with resolved_temp_dir() as root:
            findings = _scan(root, {"engine_styles.json": "# old template\n" + json.dumps(stale)}, {"engine_styles.json": VANILLA_ENGINE_STYLES})
        dropped = findings["preset-entry-drops-vanilla-fields"]
        self.assertEqual(dropped.classification, "MANUAL")
        self.assertEqual(dropped.file, "data/config/engine_styles.json")
        self.assertEqual(dropped.evidence, [f"{key}: loses contrailCampaignColor" for key in ("HIGH_TECH", "LOW_TECH", "MIDLINE")])
        self.assertNotIn("preset-entry-overrides-vanilla", findings)

    def test_changed_values_are_review_and_identical_or_new_ids_are_silent(self):
        mod = {"LOW_TECH": {**VANILLA_ENGINE_STYLES["LOW_TECH"], "engineColor": [255, 0, 0, 255]},
               "MIDLINE": VANILLA_ENGINE_STYLES["MIDLINE"], "MY_STYLE": {"engineColor": [0, 0, 0, 0]}}
        with resolved_temp_dir() as root:
            findings = _scan(root, {"engine_styles.json": mod}, {"engine_styles.json": VANILLA_ENGINE_STYLES})
        self.assertEqual(list(findings), ["preset-entry-overrides-vanilla"])
        self.assertEqual(findings["preset-entry-overrides-vanilla"].classification, "REVIEW")
        self.assertEqual(findings["preset-entry-overrides-vanilla"].evidence, ["LOW_TECH: changes engineColor[1], engineColor[2]"])

    def test_every_preset_file_is_covered_and_missing_counterparts_are_skipped(self):
        vanilla = {"star_red": {"type": "star", "texture": "a.png", "iconTexture": "b.png"}}
        mine = {"star_red": {"type": "star", "texture": "a.png"}}
        names = ("hull_styles.json", "custom_entities.json", "sounds.json", "planets.json")
        with resolved_temp_dir() as root:
            mod, core = root / "a" / "mod", root / "a" / "core"
            _write(mod / "mod_info.json", '{"id":"fixture","name":"Fixture","gameVersion":"0.98a"}')
            for name in names:
                _write(mod / "data" / "config" / name, mine)
                _write(core / "data" / "config" / name, vanilla)
            covered = [f for f in scan_mod(mod, TargetProfile("0.98a-RC8", 17), core).findings if f.id == "preset-entry-drops-vanilla-fields"]
            nothing = _scan(root / "b", {"planets.json": mine}, {})
        self.assertEqual(sorted(f.file for f in covered), sorted(f"data/config/{name}" for name in names))
        self.assertTrue(all(f.evidence == ["star_red: loses iconTexture"] for f in covered))
        self.assertEqual(nothing, {})


if __name__ == "__main__":
    unittest.main()
