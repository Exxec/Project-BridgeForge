"""ROADMAP item 75 R1: runs are bound to their staged inputs by a pre-launch manifest; one evaluator decides acceptance. No game starts."""
from __future__ import annotations

import json
import os
import time
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import launch, run_manifest
from bridgeforge.run_manifest import ManifestError, evaluate_run, prepare_run, read_manifest, release_run
from tests.bound_runs import BASIC_LOG, COMBAT, CONTENT_IDS, LOAD, MENU, SAVED, bound_run, make_rig, stage
from tests.support import resolved_temp_dir
from tests.test_probe_group import _workspace


def _two(root: Path):
    queue = root / "q"
    _workspace(queue, "A", "mod_a", "hull_a", deps=["lib"])
    _workspace(queue, "B", "mod_b", "hull_b")
    return queue, {"mod_a": queue / "A", "mod_b": queue / "B"}


def _evaluate(rig: Path, log: Path, run_id: str, **kwargs):
    return evaluate_run(rig, read_manifest(rig, run_id), log, **kwargs)


class FullMatchTests(unittest.TestCase):
    def test_manifest_records_java_version_from_the_selected_runtime_release_file(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, targets, ["lib"])
            java = rig / "selected JDK" / "bin" / "java.exe"
            java.parent.mkdir(parents=True)
            java.write_bytes(b"test executable placeholder")
            (java.parent.parent / "release").write_text('JAVA_VERSION="25.0.1"\n', encoding="utf-8")
            launcher = rig / "run-selected.bat"
            launcher.write_text(f'"{java}" -Xmx2g\n', encoding="utf-8")
            manifest = prepare_run(rig, "R-JAVA", "campaign", targets=list(targets), expected=["main_menu"], launcher=launcher)
        self.assertEqual(manifest["runtime"]["java_executable"], str(java))
        self.assertEqual(manifest["runtime"]["java_version"], "25.0.1")
        self.assertEqual(manifest["java_version"], "25.0.1")

    def test_a_synthetic_full_match_is_acceptable_per_member(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig, log = bound_run(root, targets, "R-1", [MENU, LOAD, SAVED, CONTENT_IDS, COMBAT], providers={"lib": []},
                                 expected=("main_menu", "campaign_load", "save", "content_ids", "combat"), kind="live")
            evidence = _evaluate(rig, log, "R-1")
        self.assertEqual(evidence["status"], "ACCEPTABLE")
        self.assertEqual(evidence["problems"], [])
        self.assertTrue(all(m["ok"] for m in evidence["members"].values()))
        self.assertEqual(sorted(evidence["members"]), ["mod_a", "mod_b"])

    def test_the_manifest_records_dependencies_runtime_and_the_pinned_algorithm(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig, _ = bound_run(root, targets, "R-2", providers={"lib": []})
            manifest = read_manifest(rig, "R-2")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["fileset_algorithm"], run_manifest.FILESET_ALGORITHM)
        self.assertEqual([e["id"] for e in manifest["enabled"]], ["lib", "mod_a", "mod_b"])
        self.assertTrue(all(len(e["staged_sha256"]) == 64 for e in manifest["enabled"]))
        self.assertIsNotNone(manifest["runtime"]["enabled_mods_sha256"])
        self.assertEqual(manifest["targets"]["mod_a"]["candidate_sha256"], manifest["enabled"][1]["staged_sha256"])


class NegativeTests(unittest.TestCase):
    def _run(self, root: Path, lines=None, **kwargs):
        _, targets = _two(root)
        return bound_run(root, targets, "R-3", lines, providers={"lib": []}, **kwargs)

    def test_a_log_that_is_not_the_runs_own_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root)
            elsewhere = root / "old.stdout.log"
            elsewhere.write_text("\n".join(BASIC_LOG), encoding="utf-8")
            evidence = _evaluate(rig, elsewhere, "R-3")
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("not the manifest's run log", " ".join(evidence["problems"]))

    def test_an_old_log_from_before_the_manifest_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root)
            old = time.time() - 3600
            os.utime(log, (old, old))
            evidence = _evaluate(rig, log, "R-3")
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("older than the manifest", " ".join(evidence["problems"]))

    def test_a_wrong_run_id_has_no_manifest(self) -> None:
        with resolved_temp_dir() as root:
            rig, _ = self._run(root)
            with self.assertRaises(ManifestError):
                read_manifest(rig, "R-OTHER")
            with self.assertRaises(ManifestError):
                read_manifest(rig, "../escape")

    def test_an_edited_manifest_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            rig, _ = self._run(root)
            path = run_manifest.manifest_path(rig, "R-3")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["targets"]["mod_a"]["candidate_sha256"] = "0" * 64
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "own manifest id"):
                read_manifest(rig, "R-3")

    def test_a_target_that_was_not_staged_is_refused_at_prepare(self) -> None:
        with resolved_temp_dir() as root:
            queue, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, {"mod_a": targets["mod_a"]}, ["lib"])
            with self.assertRaisesRegex(ManifestError, "not an enabled mod"):
                prepare_run(rig, "R-4", "campaign", targets=["mod_b"], expected=["main_menu"])
            self.assertFalse(run_manifest.manifest_path(rig, "R-4").exists())

    def test_dependency_only_drift_refuses_every_member(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root)
            (rig / "mods" / "lib" / "payload.txt").write_text("a different library build", encoding="utf-8")
            evidence = _evaluate(rig, log, "R-3")
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("staged files of lib changed", " ".join(evidence["problems"]))

    def test_probe_config_and_launcher_drift_are_runtime_drift(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, targets, ["lib"])
            (rig / "saves" / "common").mkdir(parents=True)
            (rig / "saves" / "common" / "bf_probe_config.data").write_text("{}", encoding="utf-8")
            bat = rig / "run-j25-direct.bat"
            bat.write_text('"C:\\jdk\\bin\\java.exe" -Xmx2g', encoding="utf-8")
            manifest = prepare_run(rig, "R-5", "campaign", targets=list(targets), expected=["main_menu"], launcher=bat)
            self.assertEqual(manifest["runtime"]["java_executable"], "C:\\jdk\\bin\\java.exe")
            (rig / "logs" / "R-5.stdout.log").write_text(MENU + "\n", encoding="utf-8")
            release_run(rig, "R-5", bat)
            self.assertEqual(_evaluate(rig, rig / "logs" / "R-5.stdout.log", "R-5", launcher=bat)["status"], "ACCEPTABLE")
            (rig / "saves" / "common" / "bf_probe_config.data").write_text('{"changed": 1}', encoding="utf-8")
            bat.write_text('"C:\\jdk\\bin\\java.exe" -Xmx8g', encoding="utf-8")
            evidence = _evaluate(rig, rig / "logs" / "R-5.stdout.log", "R-5", launcher=bat)
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("probe_config_sha256", " ".join(evidence["problems"]))
        self.assertIn("launcher_files", " ".join(evidence["problems"]))

    def test_same_version_with_different_bytes_is_not_the_tested_candidate(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root)
            (root / "q" / "A" / "working" / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nhull_edited,\n", encoding="utf-8")
            evidence = _evaluate(rig, log, "R-3", member_verdicts={"mod_a": "PASS", "mod_b": "PASS"})
        self.assertFalse(evidence["members"]["mod_a"]["ok"])
        self.assertIn("working copy changed", " ".join(evidence["members"]["mod_a"]["problems"]))
        self.assertTrue(evidence["members"]["mod_b"]["ok"])  # an unrelated member keeps its own verdict, not the other's

    def test_mutation_between_launch_and_record_is_drift(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root, release=False)
            (rig / "mods" / "B" / "payload-added.txt").write_text("x", encoding="utf-8")
            completed = release_run(rig, "R-3")
            evidence = _evaluate(rig, log, "R-3")
        self.assertTrue(completed["drift"])
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("drifted during the run", " ".join(evidence["problems"]))

    def test_an_unreleased_run_has_no_completion_record(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root, release=False)
            evidence = _evaluate(rig, log, "R-3")
        self.assertIn("no completion record", " ".join(evidence["problems"]))

    def test_incomplete_milestones_are_refused_and_a_boot_run_cannot_claim_a_campaign(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig, log = bound_run(root, targets, "R-6", [MENU], expected=("main_menu", "campaign_load"), providers={"lib": []})
            evidence = _evaluate(rig, log, "R-6")
            with self.assertRaisesRegex(ManifestError, "cannot show"):
                prepare_run(rig, "R-7", "boot", targets=[], expected=["main_menu", "campaign_load"])
        self.assertEqual(evidence["status"], "REFUSED")
        self.assertIn("campaign_load not observed", " ".join(evidence["problems"]))

    def test_a_failing_member_does_not_borrow_another_members_success(self) -> None:
        with resolved_temp_dir() as root:
            rig, log = self._run(root)
            evidence = _evaluate(rig, log, "R-3", member_verdicts={"mod_a": "FAIL", "mod_b": "PASS"})
        self.assertFalse(evidence["members"]["mod_a"]["ok"])
        self.assertTrue(evidence["members"]["mod_b"]["ok"])

    def test_unreadable_and_duplicate_inputs_fail_preparation(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, targets, ["lib"])
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["lib", "lib", "mod_a"]}), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "more than once"):
                prepare_run(rig, "R-8", "campaign", targets=[], expected=["main_menu"])
            (rig / "mods" / "enabled_mods.json").write_text("{not json", encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "cannot read"):
                prepare_run(rig, "R-8", "campaign", targets=[], expected=["main_menu"])
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["lib", "ghost"]}), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "not installed"):
                prepare_run(rig, "R-8", "campaign", targets=[], expected=["main_menu"])
            (rig / "mods" / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["lib"]}), encoding="utf-8")
            twin = rig / "mods" / "lib-copy"
            twin.mkdir()
            (twin / "mod_info.json").write_text(json.dumps({"id": "lib", "version": "1.0"}), encoding="utf-8")
            with self.assertRaisesRegex(ManifestError, "2 rig folders"):
                prepare_run(rig, "R-8", "campaign", targets=[], expected=["main_menu"])
            with mock.patch.object(run_manifest, "_tree_hash", side_effect=ManifestError("cannot read x")):
                twin_gone = rig / "mods" / "lib-copy"
                (twin_gone / "mod_info.json").unlink()
                twin_gone.rmdir()
                with self.assertRaisesRegex(ManifestError, "cannot read"):
                    prepare_run(rig, "R-8", "campaign", targets=[], expected=["main_menu"])
            self.assertFalse(run_manifest.manifest_path(rig, "R-8").exists())

    def test_a_rig_without_a_junction_gets_no_manifest(self) -> None:
        with resolved_temp_dir() as root:
            rig = root / "rig"
            (rig / "starsector-core").mkdir(parents=True)
            (rig / "mods").mkdir()
            with self.assertRaisesRegex(ManifestError, "non-isolated"):
                prepare_run(rig, "R-9", "boot", targets=[], expected=["main_menu"])


class OwnershipTests(unittest.TestCase):
    def test_a_run_owns_the_rig_so_staging_is_refused_until_release(self) -> None:
        from bridgeforge.rig.rig_up import RigUpError, rig_up

        with resolved_temp_dir() as root:
            queue, targets = _two(root)
            rig, _ = bound_run(root, {"mod_b": targets["mod_b"]}, "R-10", release=False)
            with mock.patch("bridgeforge.rig.rig_up._running_java_under", return_value=[]):
                with self.assertRaisesRegex(RigUpError, "owns the rig"):
                    rig_up(rig, queue, ["mod_b"], doctor=lambda *a, **k: {"status": "PASS", "checks": []})
                with self.assertRaises(ManifestError):
                    prepare_run(rig, "R-11", "campaign", targets=["mod_b"], expected=["main_menu"])
                release_run(rig, "R-10")
                result = rig_up(rig, queue, ["mod_b"], doctor=lambda *a, **k: {"status": "PASS", "checks": []})
        self.assertEqual(result["enabled_mods"], ["mod_b"])

    def test_preparing_the_same_run_twice_returns_the_same_manifest_and_a_changed_one_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            _, targets = _two(root)
            rig, _ = bound_run(root, {"mod_b": targets["mod_b"]}, "R-12", release=False)
            again = prepare_run(rig, "R-12", "campaign", targets=["mod_b"], expected=["main_menu", "campaign_load"])
            self.assertEqual(again["manifest_id"], read_manifest(rig, "R-12")["manifest_id"])
            with self.assertRaisesRegex(ManifestError, "different manifest"):
                prepare_run(rig, "R-12", "campaign", targets=["mod_b"], expected=["main_menu"])

    def test_install_group_refuses_while_a_run_owns_the_rig(self) -> None:
        from bridgeforge.probe.probe_group import ProbeGroupError, install_group, plan_groups

        with resolved_temp_dir() as root:
            queue, targets = _two(root)
            rig, _ = bound_run(root, {"mod_b": targets["mod_b"]}, "R-13", release=False)
            plan = plan_groups(queue, rig)
            with self.assertRaisesRegex(ProbeGroupError, "owns the rig"):
                install_group(plan, 1, queue, rig, install_probe=False)


class LegacyAndLiveRunTests(unittest.TestCase):
    def test_a_run_without_a_manifest_is_provenance_unknown_never_acceptable(self) -> None:
        evidence = evaluate_run(Path("rig"), None, Path("x.log"))
        self.assertEqual(evidence["status"], "UNKNOWN_PROVENANCE")
        self.assertIn("provenance UNKNOWN", evidence["problems"][0])

    def test_running_game_prepares_the_manifest_before_launch_and_releases_after(self) -> None:
        from bridgeforge.live import live_run

        with resolved_temp_dir() as root:
            queue, targets = _two(root)
            rig = make_rig(root, {"lib": []})
            stage(rig, {"mod_b": targets["mod_b"]}, ["lib"])
            (rig / "run-j25-direct.bat").write_text("@echo off", encoding="utf-8")
            order: list[str] = []
            real_prepare, real_release = run_manifest.prepare_run, run_manifest.release_run

            def prepare(*args, **kwargs):
                order.append("prepare")
                return real_prepare(*args, **kwargs)

            def release(*args, **kwargs):
                order.append("release")
                return real_release(*args, **kwargs)

            class Proc:
                pid = 1
                def poll(self):
                    order.append("poll")
                    return 0

            with mock.patch.object(live_run, "_running_java_under", create=True), \
                    mock.patch("bridgeforge.boot_test._running_java_under", return_value=[]), \
                    mock.patch.object(run_manifest, "prepare_run", prepare), mock.patch.object(run_manifest, "release_run", release), \
                    mock.patch("bridgeforge.rig.rig_prefs.pinned_launcher_prefs", mock.MagicMock()), \
                    mock.patch.object(launch.subprocess, "Popen", lambda *a, **k: order.append("launch") or Proc()), \
                    mock.patch.object(live_run, "real_hands", lambda rig_, pid: mock.MagicMock()):
                with live_run.running_game(rig, "R-14") as (log, hands, rows):
                    order.append("body")
            manifest = read_manifest(rig, "R-14")
            owned = run_manifest.rig_owner(rig)
        self.assertLess(order.index("prepare"), order.index("launch"))
        self.assertLess(order.index("body"), order.index("release"))
        self.assertEqual(manifest["expected_milestones"], sorted(live_run.LIVE_EXPECTED_MILESTONES))
        self.assertIsNone(owned)


class SelectionTests(unittest.TestCase):
    def test_regress_changed_reruns_a_workspace_whose_provider_or_launcher_changed(self) -> None:
        from bridgeforge.live.live_trust import write_run_record
        from bridgeforge.regress_changed import select_workspaces

        with resolved_temp_dir() as root:
            queue, targets = _two(root)
            rig, log = bound_run(root, {"mod_b": targets["mod_b"]}, "R-15", providers={"lib": []})
            manifest = read_manifest(rig, "R-15")
            evidence = evaluate_run(rig, manifest, log)
            write_run_record(queue, "R-15", [queue / "B"], triage={"counts": {}}, verdicts={"mod_b": "PASS"}, evidence=evidence, manifest=manifest)
            unchanged = select_workspaces(queue, ["README.md"], validated=[queue / "B"], rig=rig)
            (rig / "mods" / "lib" / "payload.txt").write_text("new build", encoding="utf-8")
            changed = select_workspaces(queue, ["README.md"], validated=[queue / "B"], rig=rig)
        self.assertEqual(unchanged, {})
        self.assertIn("dependency lib changed", changed["B"])


if __name__ == "__main__":
    unittest.main()


class CampaignChecksMilestoneTests(unittest.TestCase):
    def test_only_ordered_complete_probe_campaign_events_count(self):
        from bridgeforge.run_manifest import campaign_checks_observed
        start = '1 INFO BF-PROBE|0.3.2|probe|INFO|campaign|START'
        end = '2 INFO BF-PROBE|0.3.2|probe|INFO|campaign|END'
        self.assertTrue(campaign_checks_observed(start + '\n' + end))
        for text in (start, end, end + '\n' + start,
                     'Loading rule: campaign', start + '\n' + end.replace('|INFO|', '|FAIL|')):
            with self.subTest(text=text):
                self.assertFalse(campaign_checks_observed(text))
