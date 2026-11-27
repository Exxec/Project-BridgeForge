"""target, target-bump and retarget (ROADMAP-3 item 90, 2026-11-15): the move from 0.98a-RC8 to 0.98.5a-RC3 took a dozen
hand-run commands and a scratch merge script; these pin the one-run replacement and the registry it keeps."""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import unittest
from unittest.mock import patch
import zipfile
from pathlib import Path

from bridgeforge.target_bump import apply_retarget, bump, catalogue, render_catalogue, retarget_plan
from bridgeforge.targets import (TargetError, load_build, load_target, mod_game_versions, record_build, registry,
                                 resolve_tokens, set_target)
from tests.support import resolved_temp_dir
from bridgeforge.mod_changelog import merged_text


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
    def test_invalid_target_state_returns_cli_error_without_traceback(self) -> None:
        from bridgeforge.cli import main

        with resolved_temp_dir() as state:
            path = state / "target.json"
            for content in ('{', '[]', '{}', '{"build": "v", "core": null}',
                            '{"build": "", "core": "x"}', '{"build": "v", "core": ""}'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    error = io.StringIO()
                    with patch('bridgeforge.targets.state_dir', return_value=state), contextlib.redirect_stderr(error):
                        self.assertEqual(main(['scan', '@target']), 2)
                    self.assertIn('target set CORE', error.getvalue())
                    self.assertNotIn('Traceback', error.getvalue())
                    self.assertEqual(path.read_text(encoding="utf-8"), content)

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
            self.assertIn("Retargeted to Starsector 0.98.5a-RC3", merged_text(changelog))

    def test_retarget_carries_a_current_baseline_and_leaves_a_stale_one_stale(self) -> None:
        """ROADMAP-3 95.10: a retarget changes only mod_info.json, so acceptances current at the old version stay valid at the new
        one; each key keeps the owner's reason. A baseline already stale before the retarget is still the owner's to re-justify."""
        from bridgeforge.baseline_audit import audit_workspace, stamp_baseline

        key = "design-type-without-color|data/config/settings.json|"
        with resolved_temp_dir() as root:
            rows = retarget_plan(self._impact(root), "0.98.5a-RC3")
            working = root / "Alpha" / "working"
            baseline = working / "reports" / "baseline.json"
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(json.dumps({"findings": [key], "reasons": {key: "cosmetic, owner 2026-11-01"}}), encoding="utf-8")
            stamp_baseline(baseline, working, today="2026-11-01")
            carried = apply_retarget(rows[0], "0.98.5a-RC3", changelog=root / "MOD_CHANGELOG.md")
            row = audit_workspace(root / "Alpha")
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            # The same retarget on a baseline accepted at an older version than the one retargeted.
            payload["stamp"]["version"] = "0.9"
            baseline.write_text(json.dumps(payload), encoding="utf-8")
            again = apply_retarget({**rows[0], "from": "0.98.5a-RC3"}, "0.98.5a-RC7", changelog=root / "MOD_CHANGELOG.md")
            stale = audit_workspace(root / "Alpha")
        self.assertEqual((row["status"], row["stamped_version"]), ("OK", "1.0+bf.1"))
        self.assertEqual(payload["reasons"][key], "cosmetic, owner 2026-11-01")
        self.assertEqual(payload["stamp"]["carried"]["from"], "1.0")
        self.assertIn("0.98.5a-RC3", payload["stamp"]["carried"]["why"])
        self.assertTrue(carried["baseline_carried"])
        self.assertFalse(again["baseline_carried"])
        self.assertEqual((stale["status"], stale["stamped_version"]), ("STALE_VERSION", "0.9"))

    def test_a_retarget_after_a_hand_port_names_what_changed_since_the_archive(self) -> None:
        """98.10: Neutrino Corporation and Station Augments were restored from Done/, their jars hand-ported to RC9, then
        retargeted, and the record said `target-impact` "found no API, linkage or data change affecting this mod"."""
        import shutil

        def retarget(edit) -> tuple[dict, str]:
            with resolved_temp_dir() as root:
                rows = retarget_plan(self._impact(root), "0.98.5a-RC3")
                working = root / "Alpha" / "working"
                (working / "jars").mkdir()
                (working / "jars" / "alpha.jar").write_bytes(b"PK rc7 classes")
                (working / "jars" / "old.jar").write_bytes(b"PK dropped by the port")
                shutil.copytree(working, root / "Done" / "Alpha" / "Alpha")  # the archive the workspace came from
                (working / "reports").mkdir()
                (working / "reports" / "REVIVAL_REPORT.previous-build.md").write_text("restored report", encoding="utf-8")
                edit(working)
                changelog = root / "MOD_CHANGELOG.md"
                result = apply_retarget(rows[0], "0.98.5a-RC3", changelog=changelog, done_root=root / "Done")
                return result, merged_text(changelog)

        def port(working: Path) -> None:
            (working / "jars" / "alpha.jar").write_bytes(b"PK rc9 classes")  # changed
            (working / "jars" / "old.jar").unlink()  # removed
            (working / "data" / "config").mkdir(parents=True)
            (working / "data" / "config" / "settings.json").write_text("{}", encoding="utf-8")  # added

        def baseline(working: Path) -> None:
            from bridgeforge.baseline_audit import stamp_baseline

            path = working / "reports" / "baseline.json"
            path.write_text(json.dumps({"findings": ["k|f|"], "reasons": {"k|f|": "owner 2026-11-01"}}), encoding="utf-8")
            stamp_baseline(path, working, today="2026-11-01")

        ported, ported_log = retarget(port)
        untouched, untouched_log = retarget(lambda working: None)
        # Acceptances given before a hand port may not hold for the ported files: the baseline is not carried (review of 98.10).
        # The same current baseline on an untouched workspace is.
        ported_baseline, _ = retarget(lambda working: (port(working), baseline(working)))
        untouched_baseline, _ = retarget(baseline)
        self.assertEqual((ported_baseline["baseline_carried"], untouched_baseline["baseline_carried"]), (False, True))
        self.assertEqual(ported["changed_since_archive"], ["data/config/settings.json", "jars/alpha.jar", "jars/old.jar"])
        self.assertIn("3 file(s) differ from the last archive (`data/config/settings.json`, `jars/alpha.jar`, `jars/old.jar`)",
                      ported_log)
        self.assertIn("found nothing left to change", ported_log)
        self.assertNotIn("found no API", ported_log)
        # The workspace's own reports are not part of what ships, so a restored workspace compares equal.
        self.assertEqual(untouched["changed_since_archive"], [])
        self.assertIn("found no API, linkage or data change affecting this mod. Not yet", untouched_log)

    def test_retarget_apply_looks_for_archives_in_the_data_roots_done(self) -> None:
        from bridgeforge import target_bump
        from bridgeforge.paths import data_root

        with resolved_temp_dir() as root:
            state = root / "state"
            set_target(state, _core(root, "new", "0.98.5a-RC3"))
            impact = root / "TARGET_IMPACT.json"
            impact.write_text(json.dumps(self._impact(root)), encoding="utf-8")
            args = argparse.Namespace(command="retarget", impact=impact, apply=True, json=True)
            with patch.object(target_bump, "state_dir", return_value=state), \
                    patch.object(target_bump, "apply_retarget", return_value={"new": "1.0+bf.1"}) as applied, \
                    contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(target_bump.run_cli(args), 0)
        self.assertEqual(applied.call_count, 1)
        self.assertEqual(applied.call_args.kwargs["done_root"], data_root() / "Done")

    def test_a_retarget_with_no_archive_says_it_was_not_compared(self) -> None:
        from bridgeforge.target_bump import retarget_note

        from bridgeforge.target_bump import changed_since_archive

        with resolved_temp_dir() as root:
            rows = retarget_plan(self._impact(root), "0.98.5a-RC3")
            result = apply_retarget(rows[0], "0.98.5a-RC3", changelog=root / "MOD_CHANGELOG.md", done_root=root / "Done")
            log = merged_text(root / "MOD_CHANGELOG.md")
            (root / "Done" / "Alpha" / "notes").mkdir(parents=True)  # an Alpha folder in Done/ with no shipped mod folder
            folderless = changed_since_archive(root / "Alpha", root / "Done")
        self.assertIsNone(result["changed_since_archive"])
        self.assertIn("(no archive with a mod folder to compare it with)", log)
        self.assertIsNone(folderless)
        many = retarget_note("0.98a-RC8", "0.98.5a-RC9", [f"data/f{n}.csv" for n in range(7)])
        self.assertIn("7 file(s) differ", many)
        self.assertIn("`data/f4.csv` and 2 more", many)
        self.assertNotIn("f5", many)

    def test_a_retarget_whose_version_bump_fails_is_undone_and_planned_again(self) -> None:
        """Review 2026-11-17: the new gameVersion stayed written when bump_version failed (a locked MOD_CHANGELOG.md), so the next
        plan skipped the mod as "already <build>" and its version bump, report section and changelog line never happened."""
        from unittest import mock

        with resolved_temp_dir() as root:
            impact = self._impact(root)
            rows = retarget_plan(impact, "0.98.5a-RC3")
            info_path = root / "Alpha" / "working" / "mod_info.json"
            before = info_path.read_bytes()
            with mock.patch("bridgeforge.workspace_tools.bump_version", side_effect=OSError("MOD_CHANGELOG.md is locked")):
                with self.assertRaises(OSError):
                    apply_retarget(rows[0], "0.98.5a-RC3", changelog=root / "MOD_CHANGELOG.md")
            after = info_path.read_bytes()
            replanned = retarget_plan(impact, "0.98.5a-RC3")  # the plan reads mod_info.json again
        self.assertEqual(after, before)
        self.assertEqual(replanned[0]["action"], "retarget")


if __name__ == "__main__":
    unittest.main()
