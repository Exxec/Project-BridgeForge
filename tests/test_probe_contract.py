"""ROADMAP 70 H1.4: the probe's config has three representations that must agree.

`build_probe_config` (Python) writes it, `merge_configs` (Python) unites several members' configs for a group run, and
`ProbeConfig.java` reads it in the game. `merge_configs` once dropped `class_sweep` and `mission_fleets` (group runs never ran those
checks for weeks), and `probe-group install` once ignored `setups`: each was a key one side knew and another did not.
"""
from __future__ import annotations

import re
import json
import unittest
from pathlib import Path

from bridgeforge.probe.probe_config import _SETUP_PATTERNS, build_probe_config
from bridgeforge.probe.probe_group import install_group, merge_configs, plan_groups
from tests.support import link_dir, resolved_temp_dir
from tests.test_probe_group import _rig, _workspace

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "probe-mod" / "src" / "com" / "bridgeforge" / "probe"

# Keys Python writes that the in-game reader deliberately ignores (reports and bookkeeping only).
PYTHON_ONLY = {"schema_version", "hulls_skipped_no_variant", "apply", "mod_systems_unreached"}
# Keys the reader takes that `build_probe_config` does not produce itself: set by `install` or by the profile.
ADDED_AFTER = {"save_after_checks", "save_reload", "scenario_steps", "scenario_clock", "group_members"}  # scenario_*: install, from PROBE_SCENARIO.json; group_members: merge_configs (ProbeExercised attributes per member)
# Keys one member's config carries that a group's merged config rebuilds in its own way rather than copying.
REBUILT_BY_MERGE = {"target_mod_id", "group_members", "setups", "apply", "campaign_interval_days", "combat_seconds",
                    "combat_cap_per_side", "variants", "content_variants", "content_ship_hulls", "mod_body_types", "mission_fleets"}


def java_read_keys() -> set[str]:
    """Every top-level key the probe reads from the config's JSON root (calls on `root`), in any probe source file.

    Stages that own their config block (ContentParityProbe's `content_parity`) read it from the same root object."""
    keys: set[str] = set()
    for source in sorted(PROBE.rglob("*.java")):
        text = source.read_text(encoding="utf-8")
        keys |= set(re.findall(r'root\.(?:opt\w+|get\w+)\("(\w+)"', text)) | set(re.findall(r'addAll\(root\.optJSONArray\("(\w+)"', text))
    return keys


def java_setup_kinds() -> set[str]:
    text = (PROBE / "ProbeSetup.java").read_text(encoding="utf-8")
    return set(re.findall(r'setup\.startsWith\("([\w-]+):"\)', text))


class ProbeConfigContractTests(unittest.TestCase):
    def _config(self) -> dict:
        with resolved_temp_dir() as root:
            return build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))

    def test_every_key_python_writes_is_read_by_the_probe_or_is_listed_as_python_only(self) -> None:
        written = set(self._config())
        unread = written - java_read_keys() - PYTHON_ONLY
        self.assertEqual(unread, set(), "the probe never reads these config keys: read them in ProbeConfig.java or add them to PYTHON_ONLY")

    def test_every_key_the_probe_reads_is_written_by_python_or_added_after(self) -> None:
        missing = java_read_keys() - set(self._config()) - ADDED_AFTER - {"setups"}
        self.assertEqual(missing, set(), "the probe reads keys no Python code writes: dead reader code or a forgotten writer")

    def test_install_writes_save_reload_only_when_explicitly_enabled(self) -> None:
        with resolved_temp_dir() as root:
            queue = root / "q"
            _workspace(queue, "A", "mod_a", "hull_a")
            rig = _rig(root)
            core = root / "core"
            core.mkdir()
            link_dir(core, rig / "starsector-core")
            plan = plan_groups(queue, rig)
            config_path = rig / "saves/common/bf_probe_config.data"
            install_group(plan, 1, queue, rig, install_probe=False)
            self.assertNotIn("save_reload", json.loads(config_path.read_text(encoding="utf-8")))
            install_group(plan, 1, queue, rig, install_probe=False, save_reload_after_days=3,
                          save_reload_note="synthetic-check")
            self.assertEqual(json.loads(config_path.read_text(encoding="utf-8"))["save_reload"],
                             {"after_days": 3, "slot_note": "synthetic-check"})
            install_group(plan, 1, queue, rig, install_probe=False)
            self.assertNotIn("save_reload", json.loads(config_path.read_text(encoding="utf-8")))

    def test_a_group_merge_keeps_every_key_a_member_config_has(self) -> None:
        with resolved_temp_dir() as root:
            merged = merge_configs([build_probe_config(_workspace(root / "q", n, f"mod_{n.lower()}", f"hull_{n.lower()}")) for n in ("A", "B")])
        member_keys = set(self._config())
        self.assertEqual(member_keys - set(merged), set(), "merge_configs drops these member keys, so group runs lose the checks they drive")

    def test_merge_unites_the_list_valued_keys_it_copies(self) -> None:
        with resolved_temp_dir() as root:
            a = build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))
            b = build_probe_config(_workspace(root / "q", "B", "mod_b", "hull_b"))
        a["class_sweep"], b["class_sweep"] = ["x.A"], ["x.B"]
        a["mod_commodities"], b["mod_commodities"] = ["goo"], ["ore"]
        merged = merge_configs([a, b])
        self.assertEqual(merged["class_sweep"], ["x.A", "x.B"])
        self.assertEqual(merged["mod_commodities"], ["goo", "ore"])
        list_keys = [k for k, v in a.items() if isinstance(v, list) and k not in REBUILT_BY_MERGE]
        for key in list_keys:
            self.assertIn(key, merged, f"merged config lost the list key {key}")

    def test_setup_kinds_match_between_python_validation_and_java_application(self) -> None:
        self.assertEqual(set(_SETUP_PATTERNS), java_setup_kinds())

    def test_the_contract_checks_can_fail(self) -> None:
        """A mutation check: the key readers find real keys, and a merge that dropped class_sweep (the 2026-10-11 bug) would be seen."""
        self.assertTrue({"target_mod_id", "class_sweep", "mod_commodities", "save_after_checks"} <= java_read_keys())
        self.assertTrue({"rep", "swap-industry", "jump"} <= java_setup_kinds())
        with resolved_temp_dir() as root:
            config = build_probe_config(_workspace(root / "q", "A", "mod_a", "hull_a"))
        merged = merge_configs([config])
        merged.pop("class_sweep")
        self.assertEqual(set(config) - set(merged), {"class_sweep"})


if __name__ == "__main__":
    unittest.main()
