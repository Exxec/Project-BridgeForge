"""ROADMAP-3 items 92.13/92.21 (revive scans with its resolved target) and 92.17 (revive resolves the reference core and
never trims over-budget variants without one). Found reviving six mods against 0.98.5a-RC7, 2026-11-16."""
from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path

from bridgeforge.game_version import base_version, reference_core_for
from bridgeforge.revive import _fix_options, revive
from tests.support import resolved_temp_dir


def _core(install: Path, version: str) -> Path:
    core = install / "starsector-core"
    core.mkdir(parents=True)
    with zipfile.ZipFile(core / "starfarer_obf.jar", "w") as jar:
        jar.writestr("com/fs/A.class", b"\xca\xfe\xba\xbe..0.9.1a-RC8.." + version.encode())
    return core


def _mod(root: Path, game_version: str) -> Path:
    workspace = root / "In operation" / "Mod"
    (workspace / "working").mkdir(parents=True)
    (workspace / "working" / "mod_info.json").write_text(
        json.dumps({"id": "mod", "name": "Mod", "version": "1", "gameVersion": game_version}), encoding="utf-8")
    return workspace


class ReviveTargetTests(unittest.TestCase):
    def test_base_version_normalises_like_the_launcher(self) -> None:
        self.assertEqual([base_version(v) for v in ("0.98", "0.98a", "0.98a-RC8", "0.98.5a-RC7", "")],
                         ["0.98a", "0.98a", "0.98a", "0.98.5a", ""])

    def test_reference_core_is_the_installed_core_of_the_declared_version(self) -> None:
        with resolved_temp_dir() as root:
            installs = root / "Fractal Softworks"
            rc8 = _core(installs / "Starsector", "0.98a-RC8")
            new = _core(installs / "Starsector985a", "0.98.5a-RC7")
            _core(installs / "Starsector9.5.1a", "0.95.1a-RC6")
            self.assertEqual(reference_core_for("0.98", [installs], exclude=new), rc8)
            self.assertEqual(reference_core_for("0.98a-RC8", [installs], exclude=new), rc8)
            self.assertIsNone(reference_core_for("0.98.5a-RC7", [installs], exclude=new))  # the target itself is excluded
            self.assertIsNone(reference_core_for("0.7.2a", [installs]))
            self.assertIsNone(reference_core_for(None, [installs]))

    def test_a_0_98_mod_revived_on_0_98_5a_gets_its_game_version_bumped(self) -> None:
        # 92.13: Scrapyard Armories declared "0.98"; revive scanned with 0.98.x and never raised the finding.
        with resolved_temp_dir() as root:
            new = _core(root / "FS" / "Starsector985a", "0.98.5a-RC7")
            workspace = _mod(root, "0.98")
            dry = revive(workspace, vanilla_core=new)
            self.assertEqual(dry["target"], "0.98.5a-RC7")
            self.assertIn("mod-info-game-version-inexact", {p["finding"] for p in dry["packets"]} | {
                f["finding"] for r in dry["rounds"] for f in r["applied"]} | _pending_ids(workspace))
            applied = revive(workspace, vanilla_core=new, apply=True, approve=["mod-info-game-version-inexact"])
            info = json.loads((workspace / "working" / "mod_info.json").read_text(encoding="utf-8"))
        self.assertEqual(info["gameVersion"], "0.98.5a-RC7")
        self.assertIn("mod-info-game-version-inexact", [a["finding"] for a in applied["applied"]])

    def test_a_correctly_bumped_mod_is_not_flagged(self) -> None:
        # 92.21: after the bump, the generic scan flagged the correct 0.98.5a-RC7 against "0.98a".
        with resolved_temp_dir() as root:
            new = _core(root / "FS" / "Starsector985a", "0.98.5a-RC7")
            workspace = _mod(root, "0.98.5a-RC7")
            result = revive(workspace, vanilla_core=new)
        self.assertNotIn("mod-info-game-version-inexact", {p["finding"] for p in result["packets"]})

    def test_revive_records_the_resolved_reference_core(self) -> None:
        with resolved_temp_dir() as root:
            rc8 = _core(root / "FS" / "Starsector", "0.98a-RC8")
            new = _core(root / "FS" / "Starsector985a", "0.98.5a-RC7")
            workspace = _mod(root, "0.98a-RC8")
            result = revive(workspace, vanilla_core=new)
        self.assertEqual(Path(result["reference_core"]), rc8)

    def test_revive_reports_the_reference_comparison(self) -> None:
        # 92.23: over budget on the reference vs the target; the difference is what may be trimmed.
        from unittest.mock import patch

        from bridgeforge.models import Finding

        def over_budget(working, result, core):  # stand-in for the priced check: v2 goes over only on the new build
            files = ["data/variants/v1.variant"] + (["data/variants/v2.variant"] if "985a" in str(core) else [])
            for file in files:
                result.findings.append(Finding(id="variant-op-over-budget", category="variants", severity="high",
                                               classification="REVIEW", confidence="DETERMINISTIC", explanation="", file=file))

        with resolved_temp_dir() as root:
            _core(root / "FS" / "Starsector", "0.98a-RC8")
            new = _core(root / "FS" / "Starsector985a", "0.98.5a-RC7")
            workspace = _mod(root, "0.98a-RC8")
            with patch("bridgeforge.scan.scanner._scan_variant_validity", side_effect=over_budget):
                result = revive(workspace, vanilla_core=new)
        self.assertEqual(result["reference_comparison"]["variant-op-over-budget"],
                         {"reference": 1, "target": 2, "regressions": ["data/variants/v2.variant"]})

    def test_target_show_prints_what_the_core_reports(self) -> None:
        # 92.9/92.38: Test1's Starsector-0.98.5a-RC3 folder holds RC7.
        import contextlib
        import io
        from types import SimpleNamespace

        from bridgeforge.target_bump import _run_target
        from bridgeforge.targets import set_target

        def full_core(version: str) -> Path:
            core = _core(root / "Starsector-0.98.5a-RC3", version)
            for name in ("starfarer.api.jar", "fs.common_obf.jar"):
                with zipfile.ZipFile(core / name, "w") as jar:
                    jar.writestr("x.class", b"\xca\xfe\xba\xbe")
            return core

        with resolved_temp_dir() as root:
            core = full_core("0.98.5a-RC3")
            state = root / "bridgeforge-state"
            state.mkdir()
            set_target(state, core)
            for jar in core.glob("*.jar"):
                jar.unlink()
            core.rmdir()
            full_core("0.98.5a-RC7")  # the install was updated in place
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                _run_target(SimpleNamespace(target_action="show"), state)
            shown = json.loads(out.getvalue())
        self.assertEqual(shown["target_core_reports"], "0.98.5a-RC7")
        self.assertIn("registry says 0.98.5a-RC3", shown["warning"])
        self.assertNotIn(str(core), out.getvalue())  # local paths stay local

    def test_op_trim_is_refused_without_a_reference_core(self) -> None:
        # 92.17: owner ruling 2026-09-27 option 2 (RC8-06) needs the core the mod was made for.
        with resolved_temp_dir() as root:
            refused = _fix_options("variant-op-over-budget", root, "0.98.5a-RC7", root, [], None)
            allowed = _fix_options("variant-op-over-budget", root, "0.98.5a-RC7", root, [], root / "rc8")
        self.assertIn("refuse", refused[0])
        self.assertIn("2026-09-27", refused[0]["refuse"])
        self.assertNotIn("refuse", allowed[0])
        self.assertEqual(allowed[0]["reference_core"], root / "rc8")


def _pending_ids(workspace: Path) -> set[str]:
    path = workspace / "reports" / "revive" / "REVIVE.json"
    if not path.is_file():
        return set()
    return {p["finding"] for p in json.loads(path.read_text(encoding="utf-8"))["packets"]}


if __name__ == "__main__":
    unittest.main()
