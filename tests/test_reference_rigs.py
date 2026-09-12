from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge.cli import main
from bridgeforge.reference_rigs import (
    ReferenceRigError,
    build_reference_rig_manifest,
    verify_reference_rig_manifest,
    write_reference_rig_manifest,
)
from bridgeforge.rig_doctor import rig_doctor


def _make_install(root: Path, *, java_release: bool = True) -> Path:
    install = root / "Starsector-0.7.2a-reference"
    core = install / "starsector-core"
    core.mkdir(parents=True)
    (core / "starfarer.api.jar").write_bytes(b"historical-api")
    (install / "starsector.bat").write_text("@echo off\n", encoding="utf-8")
    java = install / "jre" / "bin" / "java.exe"
    java.parent.mkdir(parents=True)
    java.write_bytes(b"historical-java")
    if java_release:
        (install / "jre" / "release").write_text('JAVA_VERSION="1.7.0_80"\n', encoding="utf-8")
    (install / "mods").mkdir()
    (install / "mods" / "enabled_mods.json").write_text('{"enabledMods": []}', encoding="utf-8")
    return install


class ReferenceRigTests(unittest.TestCase):
    def test_manifest_records_core_java_command_and_save_location(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            install = _make_install(Path(directory))
            result = build_reference_rig_manifest(install, game_version="0.7.2a")
            self.assertEqual(result["game_version"], "0.7.2a")
            self.assertEqual(result["bundled_java"]["version"], "1.7.0_80")
            self.assertTrue(result["core_api"]["sha256"])
            self.assertTrue(result["run_command"]["path"].endswith("starsector.bat"))
            self.assertEqual(result["probe_support"], "UNSUPPORTED_USE_SAVE_BASELINE")

    def test_invalid_install_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ReferenceRigError):
                build_reference_rig_manifest(Path(directory), game_version="0.7.2a")

    def test_verification_detects_core_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = _make_install(root)
            manifest = write_reference_rig_manifest(install, game_version="0.7.2a", output=root / "rig.json")
            self.assertEqual(verify_reference_rig_manifest(manifest)["status"], "PASS")
            (install / "starsector-core" / "starfarer.api.jar").write_bytes(b"changed")
            result = verify_reference_rig_manifest(manifest)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(next(c for c in result["checks"] if c["name"] == "reference_core_identity")["status"], "FAIL")

    def test_cli_writes_explicit_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = _make_install(root)
            output = root / "manifest.json"
            self.assertEqual(main(["rig-create", "--game-version", "0.7.2a", "--install", str(install), "--output", str(output), "--json"]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["mode"], "REFERENCE_RIG")

    def test_existing_manifest_is_preserved_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = _make_install(root)
            output = root / "manifest.json"
            output.write_text('{"known":"good"}', encoding="utf-8")
            with self.assertRaises(ReferenceRigError):
                write_reference_rig_manifest(install, game_version="0.7.2a", output=output)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8")), {"known": "good"})

    def test_rig_doctor_uses_historical_version_and_skips_rc8_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = _make_install(root)
            manifest = write_reference_rig_manifest(install, game_version="0.7.2a", output=root / "rig.json")
            with mock.patch("bridgeforge.rig_doctor._running_java_under", return_value=[]):
                result = rig_doctor(install, reference_manifest=manifest)
            self.assertEqual(result["status"], "PASS")
            probe = next(c for c in result["checks"] if c["name"] == "probe_installed")
            self.assertEqual(probe["status"], "SKIPPED")


if __name__ == "__main__":
    unittest.main()
