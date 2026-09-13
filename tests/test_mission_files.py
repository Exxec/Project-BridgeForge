"""Live bug PRB-MISSION-01: a listed mission missing mission_text.txt is a Fatal dialog at startup."""

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import scan_mod

REPO_ROOT = Path(__file__).resolve().parent.parent


def _mission_mod(root: Path, files: dict[str, str]) -> Path:
    (root / "mod_info.json").write_text(json.dumps({"id": "fixture", "name": "Fixture", "version": "1", "gameVersion": "0.98a-RC8"}), encoding="utf-8")
    missions = root / "data" / "missions"
    (missions / "fx_mission").mkdir(parents=True)
    (missions / "mission_list.csv").write_text("mission,\nfx_mission,\n", encoding="utf-8")
    for name, text in files.items():
        (missions / "fx_mission" / name).write_text(text, encoding="utf-8")
    return root


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "mission-required-file-missing"]


class MissionRequiredFilesTests(unittest.TestCase):
    def test_missing_mission_text_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mission_mod(Path(directory), {"descriptor.json": '{"title":"X","difficulty":"EASY",}', "MissionDefinition.java": "class X {}"})
            findings = _findings(root)
            self.assertEqual(len(findings), 1)
            self.assertIn("missing:mission_text.txt", findings[0].evidence)
            self.assertEqual(findings[0].classification, "MANUAL")

    def test_declared_icon_must_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mission_mod(Path(directory), {
                "descriptor.json": '{"title":"X","icon":"icon.jpg",}',
                "MissionDefinition.java": "class X {}",
                "mission_text.txt": "text",
            })
            findings = _findings(root)
            self.assertEqual(len(findings), 1)
            self.assertIn("missing:icon.jpg (descriptor icon)", findings[0].evidence)

    def test_complete_mission_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mission_mod(Path(directory), {
                "descriptor.json": '{"title":"X","icon":"icon.jpg"}',
                "MissionDefinition.java": "class X {}",
                "mission_text.txt": "text",
                "icon.jpg": "not really a jpg",
            })
            self.assertEqual(_findings(root), [])

    def test_mission_definition_compiled_into_a_loaded_jar_counts(self) -> None:
        # SEEKER, Exigency, FlowerGod, Flu-X and Arkgneisis ship their MissionDefinition compiled in the jar.
        import zipfile
        with tempfile.TemporaryDirectory() as directory:
            root = _mission_mod(Path(directory), {"descriptor.json": '{"title":"X"}', "mission_text.txt": "text"})
            (root / "mod_info.json").write_text(json.dumps({"id": "fixture", "gameVersion": "0.98a-RC8", "jars": ["jars/fx.jar"]}), encoding="utf-8")
            (root / "jars").mkdir()
            with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
                archive.writestr("data/missions/fx_mission/MissionDefinition.class", b"\xca\xfe\xba\xbe")
            self.assertEqual(_findings(root), [])

    def test_listed_mission_without_folder_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mission_mod(Path(directory), {})
            (root / "data" / "missions" / "mission_list.csv").write_text("mission,\nfx_mission,\nghost_mission,\n", encoding="utf-8")
            evidence = [f.evidence for f in _findings(root)]
            self.assertIn(["mission:ghost_mission", "missing: folder"], evidence)

    def test_probe_mod_mission_is_complete(self) -> None:
        # The probe's own combat mission once shipped without mission_text.txt (Fatal at the first live run).
        # Its icon is vanilla art: gitignored, and install_release copies it from --core, so a clean
        # checkout may lack exactly that file (tests/test_probe_release_icon.py) and nothing else.
        allowed = {"mission:bfprobe_combat", "missing:icon.jpg (descriptor icon)"}
        evidence = [item for finding in _findings(REPO_ROOT / "probe-mod") for item in finding.evidence]
        self.assertEqual([item for item in evidence if item not in allowed], [])


if __name__ == "__main__":
    unittest.main()
