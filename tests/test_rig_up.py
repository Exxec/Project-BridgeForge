"""ROADMAP item 73 G3: `rig-up` syncs, enables, records the rig state and runs the doctor; it refuses a non-isolated rig."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from bridgeforge import rig_up as rig_up_module
from bridgeforge.rig_up import RigUpError, read_rig_state, rig_up
from tests.support import link_dir, resolved_temp_dir
from tests.test_probe_group import _rig, _workspace


def _fake_doctor(status: str = "PASS"):
    calls: list[dict] = []

    def doctor(rig, **kwargs):
        calls.append({"rig": rig, **kwargs})
        return {"status": status, "checks": [{"name": "x", "status": "WARN", "detail": "d"}, {"name": "y", "status": "PASS", "detail": "ok"}]}
    doctor.calls = calls
    return doctor


def _isolated_rig(root: Path, *providers: str) -> Path:
    rig = _rig(root, *providers)
    core = root / "core_real"
    core.mkdir(exist_ok=True)
    link_dir(core, rig / "starsector-core")
    return rig


class RigUpTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(rig_up_module, "_running_java_under", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_syncs_a_workspace_enables_it_with_its_dependencies_and_records_the_state(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a", deps=["lw_lazylib"])
            rig = _isolated_rig(root, "lw_lazylib", "speedUp")
            doctor = _fake_doctor()
            result = rig_up(rig, queue, ["mod_a"], doctor=doctor, today="2026-10-14")
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            copied = (rig / "mods" / "A" / "mod_info.json").is_file()
            state = read_rig_state(rig)
        self.assertEqual(enabled, ["lw_lazylib", "mod_a", "speedUp"])
        self.assertTrue(copied)
        self.assertEqual(result["synced"], {"mod_a": "copied"})
        by_id = {item["id"]: item for item in state["enabled"]}
        self.assertEqual(sorted(by_id), ["lw_lazylib", "mod_a", "speedUp"])
        self.assertEqual(len(by_id["mod_a"]["shipped_sha256"]), 64)
        self.assertIsNone(by_id["lw_lazylib"]["shipped_sha256"])
        self.assertEqual(doctor.calls[0]["working_copies"], {"mod_a": queue / "A" / "working"})
        self.assertEqual(result["doctor"]["status"], "PASS")
        self.assertEqual([c["name"] for c in result["doctor"]["checks"]], ["x"])

    def test_a_second_run_syncs_only_the_changed_file(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            working = _workspace(queue, "A", "mod_a", "hull_a")
            rig = _isolated_rig(root)
            rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())
            same = rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())
            (working / "data" / "hulls" / "ship_data.csv").write_text("id,hints\nhull_a2,\n", encoding="utf-8")
            changed = rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())
        self.assertEqual(same["synced"], {})
        self.assertEqual(changed["synced"], {"mod_a": "synced 1 file(s)"})

    def test_a_provider_already_in_the_rig_is_only_enabled(self) -> None:
        with resolved_temp_dir() as root:
            rig = _isolated_rig(root, "lw_lazylib")
            result = rig_up(rig, root / "no-queue", ["lw_lazylib"], doctor=_fake_doctor())
        self.assertEqual(result["providers"], ["lw_lazylib"])
        self.assertEqual(result["enabled_mods"], ["lw_lazylib"])

    def test_probe_config_installs_the_probe_and_writes_the_config(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _isolated_rig(root)

            def fake_install(runtime):
                (runtime / "mods" / "bridgeforge-probe").mkdir()
                (runtime / "mods" / "bridgeforge-probe" / "mod_info.json").write_text(json.dumps({"id": "bridgeforge_probe", "version": "0.2.9"}), encoding="utf-8")
                return {}

            with mock.patch("bridgeforge.probe.probe_config._install_probe_mod", fake_install):
                rig_up(rig, queue, ["mod_a"], probe_config=True, doctor=_fake_doctor())
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            config = json.loads((rig / "saves" / "common" / "bf_probe_config.data").read_text(encoding="utf-8"))
        self.assertEqual(enabled, ["mod_a", "bridgeforge_probe"])
        self.assertIn("mod_a", config["group_members"])

    def test_a_rig_without_a_junction_is_refused_before_anything_is_written(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _rig(root)
            (rig / "starsector-core").mkdir()
            with self.assertRaises(RigUpError):
                rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())
            self.assertFalse((rig / "mods" / "A").exists())
            self.assertFalse((rig / "mods" / "enabled_mods.json").exists())

    def test_an_unknown_id_and_a_missing_dependency_change_nothing(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a", deps=["absent_lib"])
            rig = _isolated_rig(root)
            with self.assertRaisesRegex(RigUpError, "no workspace"):
                rig_up(rig, queue, ["nobody"], doctor=_fake_doctor())
            with self.assertRaisesRegex(RigUpError, "absent_lib"):
                rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())
            self.assertFalse((rig / "mods" / "A").exists())

    def test_a_running_game_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _isolated_rig(root)
            with mock.patch.object(rig_up_module, "_running_java_under", return_value=[{"pid": 7}]):
                with self.assertRaisesRegex(RigUpError, "already running"):
                    rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())

    def test_the_run_record_carries_the_rig_state(self) -> None:
        from bridgeforge.live_trust import write_run_record

        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _isolated_rig(root)
            rig_up(rig, queue, ["mod_a"], doctor=_fake_doctor())
            record = write_run_record(queue, "T-1", [queue / "A"], triage={"counts": {}}, verdicts={"mod_a": "PASS"},
                                      rig_state=read_rig_state(rig), today="2026-10-14")
        self.assertEqual([item["id"] for item in record["rig_state"]["enabled"]], ["mod_a"])


if __name__ == "__main__":
    unittest.main()
