"""target, target-bump and retarget (ROADMAP-3 item 90, 2026-11-15): the move from 0.98a-RC8 to 0.98.5a-RC3 took a dozen
hand-run commands and a scratch merge script; these pin the one-run replacement and the registry it keeps."""
from __future__ import annotations

import argparse
import json
import unittest
import zipfile
from pathlib import Path

from bridgeforge.target_bump import apply_retarget, bump, catalogue, render_catalogue, retarget_plan
from bridgeforge.targets import (TargetError, load_build, load_target, mod_game_versions, record_build, registry,
                                 resolve_tokens, set_target)
from tests.support import resolved_temp_dir


def _core(root: Path, name: str, version: str) -> Path:
    core = root / name / "starsector-core"
    core.mkdir(parents=True)
    with zipfile.ZipFile(core / "starfarer.api.jar", "w") as jar:
        jar.writestr("META-INF/MANIFEST.MF", "Manifest-Version: 1.0\n")
    with zipfile.ZipFile(core / "starfarer_obf.jar", "w") as jar:
        jar.writestr("com/fs/V.class", b"\xca\xfe\xba\xbe.." + version.encode() + b"..")
    return core


def _mod(folder: Path, game_version: str = "0.98a-RC8", version: str = "1.0") -> Path:
    folder.mkdir(parents=True)
    (folder / "mod_info.json").write_text(json.dumps({"id": folder.parent.name.lower(), "name": folder.parent.name,
                                                      "version": version, "gameVersion": game_version}, indent=2), encoding="utf-8")
    return folder


class RegistryTests(unittest.TestCase):
    def test_set_target_records_the_build_and_registry_drops_local_paths(self) -> None:
        with resolved_temp_dir() as root:
            state, core = root / "state", _core(root, "new", "0.98.5a-RC3")
            target = set_target(state, core, status="OBSERVED")
            self.assertEqual(target["build"], "0.98.5a-RC3")
            self.assertEqual(load_target(state)["core"], str(core))
            entry = load_build(state, "0.98.5a-RC3")
            self.assertEqual(entry["mod_game_versions"], ["0.98.5a", "0.98.5a-RC3"])
            self.assertEqual(set(entry["core_fingerprint"]), {"starfarer.api.jar", "starfarer_obf.jar"})
            exported = registry(state)
            self.assertEqual(exported["target"], "0.98.5a-RC3")
            self.assertNotIn("core", exported["builds"][0])

    def test_rc8_keeps_its_known_game_version_strings(self) -> None:
        self.assertEqual(mod_game_versions("0.98a-RC8"), ["0.98a", "0.98a-RC8"])

    def test_a_different_install_claiming_a_recorded_build_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            state = root / "state"
            record_build(state, _core(root, "a", "0.98.5a-RC3"))
            other = _core(root, "b", "0.98.5a-RC3")
            with zipfile.ZipFile(other / "starfarer.api.jar", "a") as jar:
                jar.writestr("patched.txt", "x")
            with self.assertRaises(TargetError):
                record_build(state, other)

    def test_status_and_previous_survive_a_refresh(self) -> None:
        with resolved_temp_dir() as root:
            state, core = root / "state", _core(root, "a", "0.98a-RC8")
            record_build(state, core, status="QUALIFIED", previous="0.97a-RC11")
            entry = record_build(state, core)
            self.assertEqual((entry["status"], entry["previous"]), ("QUALIFIED", "0.97a-RC11"))
            with self.assertRaises(TargetError):
                record_build(state, core, status="MAYBE")


class TokenTests(unittest.TestCase):
    def test_at_target_resolves_for_paths_strings_and_lists(self) -> None:
        with resolved_temp_dir() as root:
            state, core = root / "state", _core(root, "a", "0.98a-RC8")
            set_target(state, core)
            args = argparse.Namespace(vanilla_core=Path("@target"), game_core="@target", roots=[Path("@target"), Path("x")], other=Path("y"))
            resolve_tokens(args, state)
            self.assertEqual(args.vanilla_core, core.resolve())
            self.assertEqual(args.game_core, str(core.resolve()))
            self.assertEqual(args.roots, [core.resolve(), Path("x")])
            self.assertEqual(args.other, Path("y"))

    def test_without_a_target_the_token_is_an_error_and_nothing_else_needs_one(self) -> None:
        with resolved_temp_dir() as root:
            resolve_tokens(argparse.Namespace(vanilla_core=None, roots=[Path("a")]), root / "state")
            with self.assertRaises(TargetError):
                resolve_tokens(argparse.Namespace(vanilla_core=Path("@target")), root / "state")


class BumpTests(unittest.TestCase):
    def test_bump_writes_catalogue_and_registry_then_moves_the_target(self) -> None:
        with resolved_temp_dir() as root:
            state = root / "state"
            old, new = _core(root, "old", "0.98a-RC8"), _core(root, "new", "0.98.5a-RC3")
            set_target(state, old, status="QUALIFIED")
            queue = root / "In operation"
            _mod(queue / "Alpha" / "working")
            result = bump(new, [queue], state)
            self.assertEqual((result["build"], result["previous"], result["verdicts"]["CLEAN"]), ("0.98.5a-RC3", "0.98a-RC8", 1))
            folder = Path(result["folder"])
            for name in ("api-diff.json", "impact/TARGET_IMPACT.json", "impact/TARGET_IMPACT.md", "CATALOGUE.md", "CATALOGUE.json"):
                self.assertTrue((folder / name).is_file(), name)
            self.assertFalse(list((folder / "impact").glob("*.partial.jsonl")))
            self.assertEqual(load_target(state)["build"], "0.98.5a-RC3")
            self.assertEqual(load_build(state, "0.98.5a-RC3")["previous"], "0.98a-RC8")
            self.assertEqual(load_build(state, "0.98a-RC8")["status"], "QUALIFIED")
            with self.assertRaises(TargetError):
                bump(new, [queue], state, old_core=new)

    def test_no_target_and_no_from_is_an_error(self) -> None:
        with resolved_temp_dir() as root:
            with self.assertRaises(TargetError):
                bump(_core(root, "new", "0.98.5a-RC3"), [], root / "state")


class CatalogueAndRetargetTests(unittest.TestCase):
    def _impact(self, root: Path) -> dict:
        records = [
            {"mod": "In operation/Alpha/working", "path": str(_mod(root / "Alpha" / "working")), "verdict": "CLEAN"},
            {"mod": "In operation/Beta/working", "path": str(_mod(root / "Beta" / "working")), "verdict": "BREAKS",
             "fixers_only": True, "next": ["bridgeforge fix ..."]},
            {"mod": "In operation/Gamma/working", "path": str(_mod(root / "Gamma" / "working", "0.98.5a-RC3")), "verdict": "CLEAN"},
            {"mod": "Done/Delta/Delta", "path": str(_mod(root / "Done" / "Delta" / "Delta")), "verdict": "CLEAN"},
        ]
        return {"records": records}

    def test_catalogue_joins_the_full_scan_by_folder_name(self) -> None:
        with resolved_temp_dir() as root:
            impact = self._impact(root)
            stats = {"mods": [{"workspace": "Beta", "bucket": "auto", "blocking": ["jar-call-signature-changed"]}]}
            rows = catalogue(impact, stats)
            self.assertEqual([r["tier"] for r in rows], ["unscanned", "auto", "unscanned", "unscanned"])
            text = render_catalogue("0.98.5a-RC3", "0.98a-RC8", rows, True)
            self.assertIn("Gated fixers alone clear 1 of 1 affected mods.", text)
            self.assertIn("`jar-call-signature-changed` | 1", text)

    def test_retarget_plans_clean_workspaces_only_and_apply_bumps_them(self) -> None:
        with resolved_temp_dir() as root:
            rows = retarget_plan(self._impact(root), "0.98.5a-RC3")
            self.assertEqual([r["action"] for r in rows], ["retarget", "skip", "skip", "skip"])
            self.assertIn("BREAKS", rows[1]["why"])
            self.assertIn("already", rows[2]["why"])
            self.assertIn("archive", rows[3]["why"])
            changelog = root / "MOD_CHANGELOG.md"
            result = apply_retarget(rows[0], "0.98.5a-RC3", changelog=changelog)
            info = json.loads((root / "Alpha" / "working" / "mod_info.json").read_text(encoding="utf-8"))
            self.assertEqual((info["gameVersion"], info["version"], result["new"]), ("0.98.5a-RC3", "1.0+bf.1", "1.0+bf.1"))
            report = (root / "Alpha" / "working" / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            self.assertTrue(report.rstrip().endswith("READY_FOR_LIVE_TEST"))
            self.assertIn("Retargeted to Starsector 0.98.5a-RC3", changelog.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
