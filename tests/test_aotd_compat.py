"""ROADMAP item 63 (cloud-buildable steps): Prepatcher matrix axis, env-check, aotd set, Toolbox version, per-frame work."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge import java_matrix
from bridgeforge.compat_sets import load_compat_sets, set_mod_ids
from bridgeforge.env_check import env_check
from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir

AGENT = "StarsectorPrepatcherAgent.jar"


class PrepatcherMatrixTests(unittest.TestCase):
    JDKS = [{"major": 28, "home": "C:\\jdk-28", "version": "28"}]

    def test_prep_twins_exist_and_direct_is_known_fail(self) -> None:
        variants = {v["id"]: v for v in java_matrix.plan_variants(self.JDKS, prepatcher=True)}
        self.assertEqual(sorted(variants), ["j28-direct", "j28-direct-prep", "j28-fr", "j28-fr-prep"])
        self.assertIn("ClassFormatError", variants["j28-direct-prep"]["known_fail"])
        self.assertNotIn("known_fail", variants["j28-fr-prep"])

    def test_default_has_no_prepatcher(self) -> None:
        self.assertEqual([v["id"] for v in java_matrix.plan_variants(self.JDKS)], ["j28-direct", "j28-fr"])

    def test_direct_bat_puts_agent_last_among_agents(self) -> None:
        text = java_matrix.build_launcher("C:\\jdk-28", "direct", 28, [], 4, "x", True)
        self.assertIn(f"-javaagent:..\\mods\\StarsectorPrepatcher\\agent\\{AGENT}", text)
        self.assertNotIn("-javaagent", java_matrix.build_launcher("C:\\jdk-28", "direct", 28))

    def test_fr_vmparams_copy_ends_with_agent(self) -> None:
        with resolved_temp_dir() as tmp:
            core, target = tmp / "core", tmp / "rig"
            core.mkdir()
            target.mkdir()
            (core / "fr.vmparams").write_text("-javaagent:fr.agent.jar\n-Xmx2g\n", encoding="utf-8")
            variant = {"id": "j28-fr-prep", "major": 28, "launcher": "fr", "jdk_home": str(tmp / "nojdk"), "bat": "run.bat", "prepatcher": True}
            java_matrix.write_launcher_files(target, variant, core)
            lines = (target / "fr.filtered.vmparams").read_text(encoding="utf-8").split()
            self.assertEqual(lines[-1], java_matrix.PREPATCHER_AGENT_FLAG)
            self.assertEqual(lines[0], "-javaagent:fr.agent.jar")

    def test_known_fail_variant_is_reported_not_booted(self) -> None:
        variants = java_matrix.plan_variants(self.JDKS, ["direct"], prepatcher=True)
        with resolved_temp_dir() as tmp:
            result = java_matrix.run_java_matrix(tmp, [], [v for v in variants if v["prepatcher"]], quiet=True)
        self.assertEqual(result["matrix"][0]["statuses"], ["KNOWN_FAIL"])
        self.assertEqual(result["verdict"], "NO_VARIANTS")


class EnvCheckTests(unittest.TestCase):
    def _launcher(self, tmp: Path, agents: list[str]) -> Path:
        (tmp / "jdk-28+13" / "bin").mkdir(parents=True)
        (tmp / "args.txt").write_text("\n".join([*(f"-javaagent:{a}" for a in agents), "-Xmx16g", "-Xms16g"]) + "\n", encoding="utf-8")
        bat = tmp / "Launch.bat"
        bat.write_text('@ECHO OFF\r\nREM comment\r\n"jdk-28+13\\bin\\java.exe" @args.txt\r\n', encoding="utf-8")
        return bat

    def test_follows_argfile_and_reports_prepatcher_last(self) -> None:
        with resolved_temp_dir() as tmp:
            result = env_check(self._launcher(tmp, ["fr.agent.jar", f"mods\\StarsectorPrepatcher\\agent\\{AGENT}"]))
        self.assertEqual(result["java_major"], 28)
        self.assertEqual(result["heap"], "16g")
        self.assertTrue(result["prepatcher_last"])
        self.assertEqual(len(result["javaagents"]), 2)
        self.assertEqual([f["id"] for f in result["findings"]], ["prepatcher-java-unvalidated"])

    def test_prepatcher_not_last_is_flagged(self) -> None:
        with resolved_temp_dir() as tmp:
            result = env_check(self._launcher(tmp, [f"mods\\StarsectorPrepatcher\\agent\\{AGENT}", "fr.agent.jar"]))
        self.assertIn("prepatcher-not-last-agent", [f["id"] for f in result["findings"]])

    def test_enabled_toolbox_without_agent_is_flagged(self) -> None:
        with resolved_temp_dir() as tmp:
            bat = self._launcher(tmp, ["fr.agent.jar"])
            mods = tmp / "mods"
            (mods / "vok").mkdir(parents=True)
            (mods / "vok" / "mod_info.json").write_text(json.dumps({"id": "aotd_vok", "dependencies": [{"id": "aotd_theory_of_toolbox"}]}), encoding="utf-8")
            (mods / "enabled_mods.json").write_text(json.dumps({"enabledMods": ["aotd_vok"]}), encoding="utf-8")
            result = env_check(bat, mods_dir=mods)
        self.assertEqual(result["mods_needing_prepatcher"], [{"mod": "aotd_vok", "needs": ["aotd_theory_of_toolbox"]}])
        self.assertIn("prepatcher-needed-but-missing", [f["id"] for f in result["findings"]])


class AotdSetAndPolicyTests(unittest.TestCase):
    def test_aotd_set_has_the_named_mods(self) -> None:
        ids = set_mod_ids(load_compat_sets(), "aotd")
        for wanted in ("aotd_vok", "aotd_theory_of_toolbox", "starsector_prepatcher", "bmo", "ashlib", "MagicLib", "lunalib", "lw_lazylib"):
            self.assertIn(wanted, ids)

    def test_release_policy_records_aotd_and_fork(self) -> None:
        policy = json.loads((Path(java_matrix.__file__).with_name("release_policy.json")).read_text(encoding="utf-8"))["mods"]
        for mod_id in ("aotd_vok", "aotd_sop", "aotd_qol", "Cryo_but_better", "aotd_theory_of_toolbox"):
            self.assertTrue(policy[mod_id]["local_only"], mod_id)
        self.assertIn("Kirill", policy["aotd_theory_of_toolbox"]["reason"])


class ScannerChecksTests(unittest.TestCase):
    def _mod(self, tmp: Path, deps: list[dict]) -> Path:
        mod = tmp / "m"
        mod.mkdir()
        (mod / "mod_info.json").write_text(json.dumps({"id": "m", "dependencies": deps}), encoding="utf-8")
        return mod

    def test_aotd_toolbox_version_below_minimum(self) -> None:
        with resolved_temp_dir() as tmp:
            old = scan_mod(self._mod(tmp, [{"id": "aotd_theory_of_toolbox", "version": "1.0.11"}]))
            ids = [f.id for f in old.findings]
        self.assertIn("aotd-toolbox-version-below-minimum", ids)
        with resolved_temp_dir() as tmp:
            new = scan_mod(self._mod(tmp, [{"id": "aotd_theory_of_toolbox", "version": "1.0.14-spp13"}]))
        self.assertNotIn("aotd-toolbox-version-below-minimum", [f.id for f in new.findings])

    def _script(self, body: str) -> list[str]:
        with resolved_temp_dir() as tmp:
            mod = self._mod(tmp, [])
            (mod / "src").mkdir()
            (mod / "src" / "S.java").write_text("public class S implements EveryFrameScript {\n public void advance(float amount) {\n" + body + "\n }\n}\n", encoding="utf-8")
            return [f.id for f in scan_mod(mod).findings]

    def test_per_frame_market_work_flags_unguarded_loop(self) -> None:
        self.assertIn("per-frame-market-work", self._script("for (MarketAPI m : Global.getSector().getEconomy().getMarketsCopy()) { m.reapplyIndustries(); }"))

    def test_per_frame_market_work_quiet_with_interval(self) -> None:
        self.assertNotIn("per-frame-market-work", self._script("interval.advance(amount); if (!interval.intervalElapsed()) return; Global.getSector().getEconomy().getMarketsCopy();"))


if __name__ == "__main__":
    unittest.main()
