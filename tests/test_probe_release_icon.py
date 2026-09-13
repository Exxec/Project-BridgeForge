"""The probe mission's icon is vanilla art: the public repo never carries it, the release copies it from --core."""

import tempfile
import unittest
from pathlib import Path

from bridgeforge.probe_mod_build import PROBE_MISSION_ICON, VANILLA_MISSION_ICON, ProbeModBuildError, install_release


def _repo(root: Path) -> Path:
    mod = root / "probe-mod"
    (mod / "jars").mkdir(parents=True)
    (mod / "mod_info.json").write_text('{"id":"bridgeforge_probe"}', encoding="utf-8")
    (mod / "jars" / "bridgeforge-probe.jar").write_bytes(b"PK")
    mission = mod / "data" / "missions" / "bfprobe_combat"
    mission.mkdir(parents=True)
    (mission / "descriptor.json").write_text('{"icon":"icon.jpg"}', encoding="utf-8")
    return root


class ProbeReleaseIconTests(unittest.TestCase):
    def test_icon_is_copied_from_core(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(Path(directory) / "repo")
            core = Path(directory) / "core"
            (core / VANILLA_MISSION_ICON).parent.mkdir(parents=True)
            (core / VANILLA_MISSION_ICON).write_bytes(b"vanilla-icon")
            release = Path(install_release(root, core)["release_dir"])
            self.assertEqual((release / PROBE_MISSION_ICON).read_bytes(), b"vanilla-icon")

    def test_missing_icon_without_core_fails_instead_of_shipping_a_fatal_mission(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _repo(Path(directory) / "repo")
            with self.assertRaises(ProbeModBuildError):
                install_release(root)
            self.assertFalse((root / "probe-mod" / "releases" / "bridgeforge-probe").exists())


if __name__ == "__main__":
    unittest.main()
