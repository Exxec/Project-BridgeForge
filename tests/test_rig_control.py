"""ROADMAP 70 H1.7: no hand edits of the rig between runs: `install --also-enable` and `rig-reset`."""
from __future__ import annotations

import json
import os
import time
import unittest

from bridgeforge.probe_group import ProbeGroupError, expand_also_enable, install_group, plan_groups
from bridgeforge.rig_reset import apply_reset, plan_reset
from tests.support import link_dir, resolved_temp_dir
from tests.test_probe_group import _rig, _workspace


class AlsoEnableTests(unittest.TestCase):
    def test_a_named_set_expands_and_an_unknown_mod_is_named_not_skipped(self) -> None:
        installed = {m: m for m in ("aotd_vok", "aotd_theory_of_toolbox", "starsector_prepatcher", "bmo", "ashlib", "extra")}
        self.assertEqual(expand_also_enable(["AoTD", "extra", "bmo"], installed),
                         ["aotd_vok", "aotd_theory_of_toolbox", "starsector_prepatcher", "bmo", "ashlib", "extra"])
        with self.assertRaises(ProbeGroupError) as caught:
            expand_also_enable(["aotd"], {"aotd_vok": "x"})
        self.assertIn("aotd_theory_of_toolbox", str(caught.exception))

    def test_install_enables_the_extras_with_their_dependencies_before_the_probe(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _rig(root, "lw_lazylib", "extra_mod")
            (rig / "mods" / "extra_mod" / "mod_info.json").write_text(json.dumps({"id": "extra_mod", "dependencies": [{"id": "lw_lazylib"}]}), encoding="utf-8")
            core = root / "core_real"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig)
            result = install_group(plan, 1, queue, rig, install_probe=False, also_enable=["extra_mod"])
            enabled = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))["enabledMods"]
            with self.assertRaises(ProbeGroupError):
                install_group(plan, 1, queue, rig, install_probe=False, also_enable=["not_there"])
        self.assertEqual(enabled, ["mod_a", "lw_lazylib", "extra_mod", "bridgeforge_probe"])  # the member, the extra's dependency, the extra, the probe
        self.assertEqual(result["enabled_mods"], enabled)


class RigResetTests(unittest.TestCase):
    def _rig(self, root):
        rig = root / "rig"
        core = root / "real"
        core.mkdir()
        rig.mkdir()
        link_dir(core, rig / "starsector-core")
        (rig / "mods").mkdir()
        (rig / "mods" / "enabled_mods.json.pre-bftest.bak").write_text('{"enabledMods": ["original"]}', encoding="utf-8")
        (rig / "mods" / "enabled_mods.json").write_text('{"enabledMods": ["a", "b", "aotd_vok"]}', encoding="utf-8")
        common = rig / "saves" / "common"
        common.mkdir(parents=True)
        (common / "bf_probe_combat_round.data").write_text("2", encoding="utf-8")
        (common / "keep.data").write_text("x", encoding="utf-8")
        for name, age_days in (("save_Old_1", 30), ("save_New_2", 1)):
            folder = rig / "saves" / name
            folder.mkdir()
            (folder / "campaign.xml").write_text("<x/>", encoding="utf-8")
            then = time.time() - age_days * 86400
            os.utime(folder, (then, then))
        return rig

    def test_a_dry_run_changes_nothing_and_apply_restores_cleans_and_archives_without_deleting_saves(self) -> None:
        with resolved_temp_dir() as root:
            rig = self._rig(root)
            plan = plan_reset(rig, keep_days=7)
            self.assertEqual({s["action"] for s in plan["actions"]}, {"restore-enabled-mods", "remove-probe-state", "archive-save"})
            self.assertIn("aotd_vok", (rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))  # planning wrote nothing
            apply_reset(rig, plan)
            restored = json.loads((rig / "mods" / "enabled_mods.json").read_text(encoding="utf-8"))
            saves = sorted(p.name for p in (rig / "saves").iterdir())
            archived = [p.name for d in (rig / "saves").glob("_archived-*") for p in d.iterdir()]
            self.assertEqual(restored, {"enabledMods": ["original"]})
            self.assertFalse((rig / "saves" / "common" / "bf_probe_combat_round.data").exists())
            self.assertTrue((rig / "saves" / "common" / "keep.data").is_file())
            self.assertIn("save_New_2", saves)
            self.assertNotIn("save_Old_1", saves)
            self.assertEqual(archived, ["save_Old_1"])  # moved aside, not deleted
            self.assertEqual(plan_reset(rig, keep_days=7)["actions"], [])  # idempotent

    def test_a_rig_without_a_core_link_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            (root / "starsector-core").mkdir()
            with self.assertRaises(ValueError):
                plan_reset(root)


if __name__ == "__main__":
    unittest.main()
