from __future__ import annotations

import io
import json
import shutil
import subprocess
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.vendor_plan import VendorPlanError, render, vendor_plan
from tests.support import resolved_temp_dir


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    return path


def _rebal(root: Path) -> Path:
    """A Rebal-shaped provider: the FormShield closure, a weapon, a variant, and a plugin nothing references."""
    mod = root / "Xenoargh-Rebal" / "working"
    _write(mod / "mod_info.json", {"id": "@_ss_rebal_@", "name": "Rebal", "gameVersion": "0.9a"})
    _write(mod / "data/hullmods/hull_mods.csv",
           "name,id,script,sprite,desc\n(SHL) Form Shield,shields_formshield,data.hullmods.FormShield,graphics/hullmods/explorer_society_formshield.png,Nearly immune\n"
           "Other,other_mod,data.hullmods.Other,graphics/hullmods/other.png,x\n")
    _write(mod / "data/hullmods/FormShield.java",
           "package data.hullmods;\nimport data.scripts.util.ShieldMath;\n// uses Helper below\n"
           "public class FormShield { Helper h; String glow = \"graphics/fx/formshield_glow.png\"; }\n")
    _write(mod / "data/hullmods/Helper.java", "package data.hullmods;\npublic class Helper {}\n")
    _write(mod / "data/hullmods/Other.java", "package data.hullmods;\npublic class Other {}\n")
    _write(mod / "data/scripts/util/ShieldMath.java", "package data.scripts.util;\npublic class ShieldMath {}\n")
    _write(mod / "data/scripts/plugins/FormShieldPlugin.java",
           "package data.scripts.plugins;\npublic class FormShieldPlugin { String id = \"shields_formshield\"; }\n")
    for sprite in ("graphics/hullmods/explorer_society_formshield.png", "graphics/fx/formshield_glow.png", "graphics/hullmods/other.png",
                   "graphics/weapons/rail.png", "graphics/missiles/rail_shot.png"):
        _write(mod / sprite, b"\x89PNG")
    _write(mod / "data/weapons/weapon_data.csv", "name,id\nRail,rebal_rail\n")
    _write(mod / "data/weapons/rebal_rail.wpn", {"id": "rebal_rail", "turretSprite": "graphics/weapons/rail.png",
                                                  "projectileSpecId": "rebal_rail_shot", "onHitEffect": "data.scripts.weapons.RailOnHit",
                                                  "fireSoundOne": "rail_fire"})
    _write(mod / "data/weapons/proj/rebal_rail_shot.proj", {"id": "rebal_rail_shot", "sprite": "graphics/missiles/rail_shot.png"})
    _write(mod / "data/scripts/weapons/RailOnHit.java", "package data.scripts.weapons;\npublic class RailOnHit {}\n")
    _write(mod / "data/variants/lasher_Rebal.variant", {"variantId": "lasher_Rebal", "hullId": "lasher", "hullMods": ["shields_formshield", "heavyarmor"],
                                                        "wings": ["ghost_wing"], "weaponGroups": [{"weapons": {"WS1": "rebal_rail"}}]})
    return mod.parent


def _vanilla(root: Path) -> Path:
    core = root / "core"
    _write(core / "data/hullmods/hull_mods.csv", "name,id\nArmor,heavyarmor\n")
    _write(core / "data/hulls/ship_data.csv", "name,id\nLasher,lasher\n")
    _write(core / "data/hulls/lasher.ship", {"hullId": "lasher"})
    return core


class VendorPlanTests(unittest.TestCase):
    def test_formshield_closure_and_the_plugin_is_a_suspect(self):
        with resolved_temp_dir() as root:
            plan = vendor_plan(_rebal(root), ["hullmod:shields_formshield"], vanilla_core=_vanilla(root))
        included = {(e["what"], e["path"]) for e in plan["include"]}
        self.assertEqual(included, {
            ("csv-row", "data/hullmods/hull_mods.csv [shields_formshield]"),
            ("file", "data/hullmods/FormShield.java"),
            ("file", "data/hullmods/Helper.java"),                      # same-package class it uses
            ("file", "data/scripts/util/ShieldMath.java"),              # imported provider class
            ("file", "graphics/hullmods/explorer_society_formshield.png"),
            ("file", "graphics/fx/formshield_glow.png"),                 # string literal in the class
        })
        self.assertEqual([s["path"] for s in plan["suspects"]], ["data/scripts/plugins/FormShieldPlugin.java"])
        self.assertEqual([u["path"] for u in plan["used_by"]], ["data/variants/lasher_Rebal.variant"])  # a user, not a part
        self.assertEqual(plan["missing"], [])
        self.assertEqual(plan["licence"]["decision"], "LOCAL_ONLY")  # @_ss_rebal_@ in the real release_policy.json

    def test_variant_follows_weapons_projectiles_and_effects_and_skips_vanilla(self):
        with resolved_temp_dir() as root:
            plan = vendor_plan(_rebal(root), ["variant:lasher_Rebal"], vanilla_core=_vanilla(root))
        paths = {e["path"] for e in plan["include"]}
        for expected in ("data/variants/lasher_Rebal.variant", "data/weapons/rebal_rail.wpn", "data/weapons/proj/rebal_rail_shot.proj",
                         "graphics/missiles/rail_shot.png", "data/scripts/weapons/RailOnHit.java", "data/weapons/weapon_data.csv [rebal_rail]",
                         "data/hullmods/FormShield.java"):
            self.assertIn(expected, paths)
        self.assertEqual(plan["provided_by_vanilla"], ["hull:lasher", "hullmod:heavyarmor"])
        self.assertEqual([m.split(" ")[0] for m in plan["missing"]], ["wing:ghost_wing"])
        self.assertNotIn("data/hullmods/Other.java", paths)

    def test_target_reports_ids_it_has_and_file_collisions(self):
        with resolved_temp_dir() as root:
            provider = _rebal(root)
            target = root / "RevenantLib" / "working"
            _write(target / "mod_info.json", {"id": "revenantlib"})
            _write(target / "data/hullmods/hull_mods.csv", "name,id\nForm Shield,shields_formshield\n")
            _write(target / "graphics/hullmods/explorer_society_formshield.png", b"\x89PNG")
            _write(target / "graphics/fx/formshield_glow.png", b"different")
            plan = vendor_plan(provider, ["hullmod:shields_formshield"], target=target.parent)
        self.assertEqual(plan["already_in_target"], ["hullmod:shields_formshield"])
        self.assertEqual(plan["target_collisions"], [
            {"path": "graphics/fx/formshield_glow.png", "identical": False},
            {"path": "graphics/hullmods/explorer_society_formshield.png", "identical": True},
        ])
        self.assertIn("TARGET HAS graphics/fx/formshield_glow.png (DIFFERENT bytes)", render(plan))

    def test_animation_frames_and_jar_source_under_src(self):
        # The RevenantLib thruster_fighter_sm closure (PROVENANCE.md): numFrames 5 on ...generic00.png needs
        # frames 00-04, and a jar class whose source ships under src/ is vendored as that source.
        with resolved_temp_dir() as root:
            mod = root / "Vacuum"
            _write(mod / "mod_info.json", {"id": "vacuum", "name": "Vacuum"})
            _write(mod / "data/weapons/weapon_data.csv", "name,id\nThruster,thruster_fighter_sm\n")
            _write(mod / "data/weapons/thruster_fighter_sm.wpn", {"id": "thruster_fighter_sm", "numFrames": 3,
                   "turretSprite": "graphics/t/f_engine00.png", "everyFrameEffect": "vacuum.sfx.rearThrusterJet"})
            for frame in ("00", "01"):
                _write(mod / f"graphics/t/f_engine{frame}.png", b"\x89PNG")
            _write(mod / "src/vacuum/sfx/rearThrusterJet.java", "package vacuum.sfx;\npublic class rearThrusterJet {}\n")
            _write(mod / "src/vacuum/sfx/Unrelated.java", "package vacuum.sfx;\n// thruster_fighter_sm is mentioned only in this comment\npublic class Unrelated {}\n")
            plan = vendor_plan(mod, ["weapon:thruster_fighter_sm"])
        paths = {e["path"] for e in plan["include"]}
        self.assertLessEqual({"graphics/t/f_engine00.png", "graphics/t/f_engine01.png", "src/vacuum/sfx/rearThrusterJet.java"}, paths)
        self.assertEqual([m.split(" (")[0] for m in plan["missing"]], ["file graphics/t/f_engine02.png"])
        self.assertEqual(plan["suspects"], [])  # a comment mention is not a use

    def test_bad_input_and_cli(self):
        with resolved_temp_dir() as root:
            provider = _rebal(root)
            with self.assertRaises(VendorPlanError):
                vendor_plan(provider, ["nonsense"])
            with self.assertRaises(VendorPlanError):
                vendor_plan(root / "nowhere", ["hullmod:x"])
            unknown = vendor_plan(provider, ["hullmod:not_here"])
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["vendor-plan", str(provider), "--id", "hullmod:shields_formshield", "--target", str(provider)]), 0)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(["vendor-plan", str(provider), "--id", "bad"]), 2)
        self.assertEqual(unknown["missing"], ["hullmod:not_here (requested)"])
        self.assertIn("SUSPECT data/scripts/plugins/FormShieldPlugin.java (mentions shields_formshield)", out.getvalue())


class VendorPlanJarTests(unittest.TestCase):
    """Compiled-only classes, via a real javac; skipped cleanly when no JDK is on PATH."""

    def setUp(self):
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

    def test_jar_only_script_is_flagged_and_jar_string_mentions_are_suspects(self):
        with resolved_temp_dir() as root:
            provider = _rebal(root)
            mod = provider / "working"
            (mod / "data/hullmods/Other.java").unlink()
            src, out = root / "src", root / "classes"
            _write(src / "data/hullmods/Other.java", "package data.hullmods;\npublic class Other { Listener l; }\n")
            _write(src / "data/hullmods/Listener.java", "package data.hullmods;\npublic class Listener {}\n")
            _write(src / "data/scripts/Watcher.java", "package data.scripts;\npublic class Watcher { String id = \"other_mod\"; }\n")
            completed = subprocess.run([self.javac, "--release", "17", "-d", str(out), *map(str, src.rglob("*.java"))], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            with zipfile.ZipFile(_write(mod / "jars/rebal.jar", b""), "w") as archive:
                for path in sorted(out.rglob("*.class")):
                    archive.write(path, path.relative_to(out).as_posix())
            plan = vendor_plan(provider, ["hullmod:other_mod"])
        jar_entries = sorted(e["path"] for e in plan["include"] if e["what"] == "jar-class")
        self.assertEqual(jar_entries, ["rebal.jar!data/hullmods/Listener.class", "rebal.jar!data/hullmods/Other.class"])
        self.assertTrue(all("compiled only" in e["reason"] for e in plan["include"] if e["what"] == "jar-class"))
        self.assertEqual([s["path"] for s in plan["suspects"]], ["rebal.jar!data/scripts/Watcher.class"])


if __name__ == "__main__":
    unittest.main()
