"""ROADMAP-3 78.5: the probe's salvor profile keeps its marker, JVM properties and log lines in step with Salvor's harness."""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from bridgeforge import probe_salvor_profile as profile
from tests.support import resolved_temp_dir

PROBE = Path(__file__).resolve().parent.parent / "probe-mod" / "src" / "com" / "bridgeforge" / "probe"
JAVA = (PROBE / "SalvorProfile.java").read_text(encoding="utf-8")
PLUGIN = (PROBE / "BfProbeModPlugin.java").read_text(encoding="utf-8")


class SalvorProfileTests(unittest.TestCase):
    def test_marker_selects_the_profile_and_java_reads_the_same_path_and_name(self) -> None:
        self.assertEqual(json.loads(profile.marker_text()), {"profile": "salvor"})
        self.assertIn(f'MARKER = "{profile.MARKER_RELATIVE}"', JAVA)
        self.assertIn(f'PROFILE_NAME = "{profile.PROFILE_NAME}"', JAVA)
        self.assertIn(f'MOD_ID = "{profile.PROBE_MOD_ID}"', JAVA)
        mod_info = json.loads((PROBE.parents[3] / "mod_info.json").read_text(encoding="utf-8"))
        self.assertEqual(mod_info["id"], profile.PROBE_MOD_ID)

    def test_write_marker_only_into_the_given_mod_folder(self) -> None:
        with resolved_temp_dir() as root:
            written = profile.write_marker(root / "mod")
            self.assertEqual(written, root / "mod" / "data" / "config" / "bf_probe_profile.json")
            self.assertEqual(json.loads(written.read_text(encoding="utf-8"))["profile"], "salvor")
        self.assertFalse((PROBE.parents[3] / profile.MARKER_RELATIVE).exists(), "the repo's own probe must never carry the marker")

    def test_jvm_properties_are_the_ones_salvor_rig_auto_passes(self) -> None:
        self.assertIn(f'MODE_PROPERTY = "{profile.MODE_PROPERTY}"', JAVA)
        self.assertIn(f'DAYS_PROPERTY = "{profile.DAYS_PROPERTY}"', JAVA)

    def test_java_emits_every_salvor_line_shape(self) -> None:
        emitted = set(re.findall(r'"(salvor-rig\|INFO\|[^"]*)"', JAVA))
        for line in profile.LOG_LINES:
            head = line.split("<")[0]
            self.assertTrue(any(e.startswith(head) for e in emitted), f"no Java line starts {head!r}")

    def test_selected_profile_skips_every_bridgeforge_check_in_the_plugin(self) -> None:
        load = PLUGIN.split("public void onGameLoad")[1]
        self.assertLess(load.index("SalvorProfile.isSelected()"), load.index("maybeStartCampaignProbe"))
        self.assertLess(load.index("return;"), load.index("maybeStartCampaignProbe"))
        new_game = PLUGIN.split("public void onNewGameAfterTimePass")[1]
        self.assertLess(new_game.index("SalvorProfile.isSelected()"), new_game.index("maybeStartCampaignProbe"))

    def test_the_profile_adds_no_forbidden_file_apis(self) -> None:
        for name in ("SalvorProfile.java", "DayCountScript.java"):
            self.assertNotRegex((PROBE / name).read_text(encoding="utf-8"), r"java\.(io|nio)")


if __name__ == "__main__":
    unittest.main()
