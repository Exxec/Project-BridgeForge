"""`save-doctor`: one read-only pass over a save against a whole mods folder (Salvor groundwork, 2026-10-02)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.save_doctor import diagnose
from tests.support import resolved_temp_dir

DESCRIPTOR = """<?xml version="1.0" ?>
<SaveGameData z="1">
<characterName>Test Pilot</characterName>
<gameVersion>0.98a-RC8</gameVersion>
<saveDate z="3">2026-10-02 10:00:00.000 UTC</saveDate>
<allModsEverEnabled z="4">
{specs}
</allModsEverEnabled>
<enabledMods z="40">
{refs}
</enabledMods>
</SaveGameData>
"""
SPEC = """<EnabledModData z="{z}"><spec z="{s}"><id>{id}</id><name>{id}</name>
<gameVersion z="{g}"><string>0.98a-RC8</string></gameVersion>
<versionInfo z="{v}"><string>{version}</string></versionInfo>
<dirName>{id}</dirName></spec></EnabledModData>"""


def _save(root: Path, mods: list[tuple[str, str]], body: str, *, close: bool = True) -> Path:
    save = root / "saves" / "save_Test_1"
    save.mkdir(parents=True)
    specs, refs = [], []
    for n, (mod_id, version) in enumerate(mods):
        base = 10 + n * 10
        specs.append(SPEC.format(z=base, s=base + 1, g=base + 2, v=base + 3, id=mod_id, version=version))
        refs.append(f'<EnabledModData z="{base + 5}"><spec ref="{base + 1}"/></EnabledModData>')
    (save / "descriptor.xml").write_text(DESCRIPTOR.format(specs="\n".join(specs), refs="\n".join(refs)), encoding="utf-8")
    (save / "campaign.xml").write_text('<?xml version="1.0" ?>\n<CampaignEngine z="1">\n' + body + ("\n</CampaignEngine>\n" if close else ""), encoding="utf-8")
    return save


def _mod(mods: Path, mod_id: str, version: str) -> None:
    (mods / mod_id).mkdir(parents=True)
    (mods / mod_id / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": mod_id, "version": version}), encoding="utf-8")


class SaveDoctorTests(unittest.TestCase):
    def test_a_clean_save_has_no_known_problem(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root / "mods", "lib", "1.0")
            save = _save(root, [("lib", "1.0")], '<WSR.V z="2"></WSR.V>\n<if.new z="3"></if.new>')
            result = diagnose(save, root / "mods")
        self.assertEqual(result["verdict"], "NO_KNOWN_PROBLEM", result["problems"])

    def test_a_missing_mod_a_foreign_class_and_a_nan_are_reported(self) -> None:
        with resolved_temp_dir() as root:
            _mod(root / "mods", "lib", "2.0")
            body = ('<industries><data.scripts.PopulationDNEEP z="2"></data.scripts.PopulationDNEEP></industries>\n'
                    '<orbit><period>NaN</period></orbit>')
            save = _save(root, [("lib", "1.0"), ("gone", "1.0")], body)
            result = diagnose(save, root / "mods")
        classes = {p["class"] for p in result["problems"]}
        self.assertEqual(result["verdict"], "WILL_LIKELY_FAIL")
        self.assertEqual(classes, {"MOD_MISSING", "VERSION_CHANGED", "CLASS_UNRESOLVED", "NON_FINITE"})
        self.assertIn("high", result["recovery"]["MOD_MISSING"])

    def test_a_save_cut_off_mid_write_is_truncated(self) -> None:
        with resolved_temp_dir() as root:
            (root / "mods").mkdir()
            save = _save(root, [], "<hyperspace z=\"2\">", close=False)
            result = diagnose(save, root / "mods")
        self.assertEqual(result["verdict"], "TRUNCATED")
        self.assertIn("low", result["recovery"]["TRUNCATED"])



class RemovalPlanTests(unittest.TestCase):
    def test_objects_are_droppable_unless_something_outside_refers_to_them(self) -> None:
        from bridgeforge.save_removal_plan import plan_removal
        with resolved_temp_dir() as root:
            (root / "mods").mkdir()
            body = ("<markets><Market z=\"2\"><industries>\n"
                    "<gone.mod.Factory z=\"3\"><script z=\"4\"></script></gone.mod.Factory>\n"
                    "<gone.mod.Mine z=\"5\"></gone.mod.Mine>\n"
                    "</industries>\n"
                    "<lookAt ref=\"5\"/>\n"
                    "<scr><gone.mod.Lamp z=\"6\"><owner ref=\"3\"/></gone.mod.Lamp></scr>\n"
                    "</Market></markets>")
            save = _save(root, [], body)
            plan = plan_removal(save, root / "mods")
        states = {row["class"]: row["state"] for row in plan["rows"]}
        self.assertEqual(states, {"gone.mod.Factory": "DROPPABLE", "gone.mod.Mine": "BLOCKED", "gone.mod.Lamp": "DROPPABLE"})
        self.assertEqual((plan["droppable"], plan["blocked"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
