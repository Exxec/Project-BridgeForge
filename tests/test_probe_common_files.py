"""Live bug PRB-COMMON-01: Starsector appends ".data" to common-file names, so BridgeForge must too."""

import re
import unittest
from pathlib import Path

from bridgeforge.probe_config import COMMON_FILE_SUFFIX, CONFIG_FILE, PROFILE_FILE, RIG_MARKER_FILE

PROBE_FILES_JAVA = Path(__file__).resolve().parent.parent / "probe-mod" / "src" / "com" / "bridgeforge" / "probe" / "ProbeFiles.java"


def _java_constant(name: str) -> str:
    match = re.search(rf'String\s+{name}\s*=\s*"([^"]+)"', PROBE_FILES_JAVA.read_text(encoding="utf-8"))
    assert match, f"ProbeFiles.{name} not found"
    return match.group(1)


class CommonFileNamingTests(unittest.TestCase):
    def test_suffix_is_what_the_game_appends(self) -> None:
        # Seen on disk in the rig: LunaCommons.json.data, core_sim_settings.json.data, and the probe's
        # own bf_probe_report.data written through writeTextFileToCommon("bf_probe_report").
        self.assertEqual(COMMON_FILE_SUFFIX, ".data")

    def test_python_on_disk_names_are_the_java_names_plus_suffix(self) -> None:
        self.assertEqual(RIG_MARKER_FILE, _java_constant("RIG_MARKER") + COMMON_FILE_SUFFIX)
        self.assertEqual(CONFIG_FILE, _java_constant("CONFIG") + COMMON_FILE_SUFFIX)
        self.assertEqual(PROFILE_FILE, _java_constant("PROFILE") + COMMON_FILE_SUFFIX)


if __name__ == "__main__":
    unittest.main()
