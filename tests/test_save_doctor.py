"""`save-doctor`: one read-only pass over a save against a whole mods folder (Salvor groundwork, 2026-10-02)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from bridgeforge.save.save_doctor import _installed, diagnose, installed_mods
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

    def test_xstream_escaped_element_names_resolve_to_the_installed_class(self) -> None:
        import zipfile
        with resolved_temp_dir() as root:
            _mod(root / "mods", "epta", "1.0")
            (root / "mods" / "epta" / "jars").mkdir()
            with zipfile.ZipFile(root / "mods" / "epta" / "jars" / "E.jar", "w") as jar:
                jar.writestr("data/scripts/world/industries_and_buildings/seven_proelefsi_industry.class", b"\xca\xfe")
                jar.writestr("data/scripts/world/industries_and_buildings/seven_proelefsi_industry$Part.class", b"\xca\xfe")
            # The game saves `_` as `__` and `$` as `_-` in element names (EPTA213-20261013), never in cl="..." values.
            body = ('<data.scripts.world.industries__and__buildings.seven__proelefsi__industry z="2">'
                    '</data.scripts.world.industries__and__buildings.seven__proelefsi__industry>\n'
                    '<data.scripts.world.industries__and__buildings.seven__proelefsi__industry_-Part z="3">'
                    '</data.scripts.world.industries__and__buildings.seven__proelefsi__industry_-Part>\n'
                    '<p cl="data.scripts.world.industries_and_buildings.seven_proelefsi_industry" ref="2"></p>')
            save = _save(root, [("epta", "1.0")], body)
            result = diagnose(save, root / "mods")
        self.assertEqual(result["verdict"], "NO_KNOWN_PROBLEM", result["problems"])

    def test_names_a_mod_plugin_registers_as_xstream_aliases_resolve(self) -> None:
        """Star Lords' LordsModPlugin.configureXStream aliases its classes to `faction.LawProposal`, `ai.LordAI` and more,
        and the game writes those names into the save. They read as CLASS_UNRESOLVED and made three of the owner's RC8
        saves WILL_LIKELY_FAIL, with no mod missing (2026-11-17)."""
        import subprocess
        import zipfile

        from tests.support import javac_path

        javac = javac_path()
        if javac is None:
            self.skipTest("no javac")
        with resolved_temp_dir() as root:
            source = root / "src" / "lords" / "LordsPlugin.java"
            source.parent.mkdir(parents=True)
            source.write_text("package lords;\npublic class LordsPlugin {\n  public void configureXStream(Object x) {\n"
                              '    String[] aliases = {"faction.LawProposal", "ai.LordAI"};\n  }\n}\n', encoding="utf-8")
            subprocess.run([javac, "-encoding", "UTF-8", "-proc:none", "-d", str(root / "classes"), str(source)], check=True, capture_output=True)
            mod = root / "mods" / "lords"
            (mod / "jars").mkdir(parents=True)
            with zipfile.ZipFile(mod / "jars" / "Lords.jar", "w") as jar:
                jar.write(root / "classes" / "lords" / "LordsPlugin.class", "lords/LordsPlugin.class")
            info = {"id": "lords", "name": "lords", "version": "1.0", "jars": ["jars/Lords.jar"], "modPlugin": "lords.LordsPlugin"}
            (mod / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
            body = ('<faction.LawProposal z="2"></faction.LawProposal>\n<ai.LordAI z="3"></ai.LordAI>\n'
                    '<faction.Other z="4"></faction.Other>')
            save = _save(root, [("lords", "1.0")], body)
            result = diagnose(save, root / "mods")
        # The aliases resolve, and so does their package: faction.Other is not reported either, as for a mod's own package.
        self.assertEqual(result["verdict"], "NO_KNOWN_PROBLEM", result["problems"])

    def test_classes_of_a_mods_loose_scripts_resolve(self) -> None:
        """The game compiles loose .java scripts at load: Emergent Threats' data/scripts/vice/listeners read as
        CLASS_UNRESOLVED in an RC8 save because only jar classes were indexed (2026-11-17)."""
        with resolved_temp_dir() as root:
            _mod(root / "mods", "et", "1.5.0")
            script = root / "mods" / "et" / "data" / "scripts" / "vice" / "listeners" / "BountyListener.java"
            script.parent.mkdir(parents=True)
            script.write_text("package data.scripts.vice.listeners;\npublic class BountyListener {}\n", encoding="utf-8")
            body = '<data.scripts.vice.listeners.BountyListener z="2"></data.scripts.vice.listeners.BountyListener>'
            save = _save(root, [("et", "1.5.0")], body)
            result = diagnose(save, root / "mods")
        self.assertEqual(result["verdict"], "NO_KNOWN_PROBLEM", result["problems"])

    def test_a_package_starting_with_a_capital_is_checked_not_taken_for_the_games_alias(self) -> None:
        """Every name starting with a capital was skipped as the game's `WSR.V` alias, so a missing mod's
        `Jaydee8652.JaydeePiracy` classes could never be reported (2026-11-17)."""
        with resolved_temp_dir() as root:
            (root / "mods").mkdir()
            body = '<WSR.V z="2"></WSR.V>\n<Jaydee8652.Piracy.Lost z="3"></Jaydee8652.Piracy.Lost>'
            result = diagnose(_save(root, [], body), root / "mods")
        self.assertEqual([p["package"] for p in result["problems"] if p["class"] == "CLASS_UNRESOLVED"], ["Jaydee8652.Piracy"])

    def test_a_faction_no_core_or_enabled_mod_defines_is_reported(self) -> None:
        """Salvor's RC7 rig run (2026-11-17): a Templars save with Templars removed still held the `templars` Faction, and
        the game stopped loading in Faction.readResolve (its transient `spec` is looked up by id and was null). Static
        checks had said NO_KNOWN_PROBLEM."""
        body = ('<sector z="2">\n<factions z="3">\n'
                '<Fctn z="4">\n<id>hegemony</id>\n<memory z="5">\n<id>not.a.faction</id>\n</memory>\n'
                '<secondaryColorSegmentsOverride>0</secondaryColorSegmentsOverride>\n</Fctn>\n'
                '<ow z="6">\n<id>templars</id>\n<relationships z="7">\n<id>nested</id>\n</relationships>\n'
                '<secondaryColorSegmentsOverride>0</secondaryColorSegmentsOverride>\n</ow>\n'
                '<ow z="8">\n<id>mine</id>\n<secondaryColorSegmentsOverride>2</secondaryColorSegmentsOverride>\n</ow>\n'
                '<ow ref="6"></ow>\n<market z="9">\n<id>orphan_id_without_faction_fields</id>\n'
                '<name>Market</name>\n<size>3</size>\n</market>\n'
                '<memory z="10">\n<id>marker_one_level_down</id>\n<d z="11">\n'
                '<secondaryColorSegmentsOverride>0</secondaryColorSegmentsOverride>\n</d>\n</memory>\n'
                '</factions>\n</sector>')
        with resolved_temp_dir() as root:
            core = root / "core"
            (core / "data" / "world" / "factions").mkdir(parents=True)
            (core / "data" / "world" / "factions" / "hegemony.faction").write_text('{"id": "hegemony"}', encoding="utf-8")
            _mod(root / "mods", "minemod", "1.0")
            # One folder down, as Roider Union 2.3.1 keeps roider_mining/roider_dust.faction.
            (root / "mods" / "minemod" / "data" / "world" / "factions" / "sub").mkdir(parents=True)
            (root / "mods" / "minemod" / "data" / "world" / "factions" / "sub" / "mine.faction").write_text(
                '{"id": "mine"}', encoding="utf-8")
            save = _save(root, [("minemod", "1.0")], body)
            result = diagnose(save, root / "mods", vanilla_core=core)
            without_core = diagnose(save, root / "mods")
        undefined = [p for p in result["problems"] if p["class"] == "FACTION_UNDEFINED"]
        self.assertEqual([p["faction"] for p in undefined], ["templars"])
        self.assertEqual(result["verdict"], "WILL_LIKELY_FAIL")
        self.assertIn("readResolve", result["recovery"]["FACTION_UNDEFINED"])
        self.assertFalse([p for p in without_core["problems"] if p["class"] == "FACTION_UNDEFINED"])
        self.assertTrue(any("FACTION_UNDEFINED" in note for note in without_core["skipped"]))

    def test_a_faction_of_an_installed_but_disabled_mod_is_still_undefined(self) -> None:
        body = '<ow z="2">\n<id>mine</id>\n<secondaryColorSegmentsOverride>0</secondaryColorSegmentsOverride>\n</ow>'
        with resolved_temp_dir() as root:
            core = root / "core"
            (core / "data" / "world" / "factions").mkdir(parents=True)
            _mod(root / "mods", "minemod", "1.0")
            (root / "mods" / "minemod" / "data" / "world" / "factions").mkdir(parents=True)
            (root / "mods" / "minemod" / "data" / "world" / "factions" / "mine.faction").write_text(
                '{"id": "mine"}', encoding="utf-8")
            result = diagnose(_save(root, [], body), root / "mods", vanilla_core=core)
        self.assertEqual([p["faction"] for p in result["problems"] if p["class"] == "FACTION_UNDEFINED"], ["mine"])

    def test_content_in_a_factions_lists_that_nothing_defines_is_reported(self) -> None:
        """Salvor's R4 run 7890f07c (Test1, 2026-11-18): Scrapyard Armories removed, the save still listed its hulls in vanilla
        factions' knownShips and shipsWhenImporting, and the load stopped at "Fatal: Ship hull spec [sa_manticore_remnant]
        not found!". RC7 keeps those saved lists unless StarfarerSettings."for.new"() holds (javap, 93.56)."""
        body = ('<sector z="2">\n<factions z="3">\n'
                '<o z="4">\n<id>remnant</id>\n<shipsWhenImporting z="5">\n<st>nova</st>\n<st>sa_manticore_remnant</st>\n'
                '</shipsWhenImporting>\n<knownShips z="6">\n<st>nova</st>\n<st>sa_manticore_remnant</st>\n<st>mod_hull</st>\n'
                '<st>skinned</st>\n</knownShips>\n<knownWeapons z="7">\n<st>pulselaser</st>\n<st>sa_rhino</st>\n</knownWeapons>\n'
                '<knownFighters z="8">\n<st>sa_grendel_wing</st>\n</knownFighters>\n<knownHullMods z="9">\n<st>heavyarmor</st>\n'
                '<st>sa_mod</st>\n</knownHullMods>\n<knownIndustries z="10">\n<st>not_checked</st>\n</knownIndustries>\n'
                '<secondaryColorSegmentsOverride>0</secondaryColorSegmentsOverride>\n</o>\n'
                '<memory z="11">\n<id>not_a_faction</id>\n<knownShips z="12">\n<st>ignored_outside_a_faction</st>\n</knownShips>\n'
                '</memory>\n</factions>\n</sector>')
        with resolved_temp_dir() as root:
            core = root / "core" / "data"
            (core / "world" / "factions").mkdir(parents=True)
            (core / "world" / "factions" / "remnant.faction").write_text('{"id": "remnant"}', encoding="utf-8")
            (core / "hulls").mkdir()
            (core / "hulls" / "nova.ship").write_text('{"hullId": "nova"}', encoding="utf-8")
            (core / "weapons").mkdir()
            (core / "weapons" / "weapon_data.csv").write_text("name,id\nPulse,pulselaser\n", encoding="utf-8")
            (core / "hullmods").mkdir()
            (core / "hullmods" / "hull_mods.csv").write_text("name,id\nArmor,heavyarmor\n", encoding="utf-8")
            _mod(root / "mods", "kept", "1.0")
            hulls = root / "mods" / "kept" / "data" / "hulls"
            hulls.mkdir(parents=True)
            (hulls / "mod_hull.ship").write_text('{"hullId": "mod_hull"}', encoding="utf-8")
            (hulls / "skins").mkdir()
            (hulls / "skins" / "skinned.skin").write_text('{"skinHullId": "skinned"}', encoding="utf-8")
            save = _save(root, [("kept", "1.0")], body)
            result = diagnose(save, root / "mods", vanilla_core=root / "core")
            without_core = diagnose(save, root / "mods")
        found = {(p["faction"], p["list"], p["kind"], tuple(p["ids"])) for p in result["problems"] if p["class"] == "FACTION_LIST_UNDEFINED"}
        self.assertEqual(found, {("remnant", "shipsWhenImporting", "hull", ("sa_manticore_remnant",)),
                                 ("remnant", "knownShips", "hull", ("sa_manticore_remnant",)),
                                 ("remnant", "knownWeapons", "weapon", ("sa_rhino",)),
                                 ("remnant", "knownFighters", "wing", ("sa_grendel_wing",)),
                                 ("remnant", "knownHullMods", "hullmod", ("sa_mod",))})
        self.assertEqual(result["verdict"], "WILL_LIKELY_FAIL")
        self.assertIn("Ship hull spec", result["recovery"]["FACTION_LIST_UNDEFINED"])
        self.assertFalse([p for p in without_core["problems"] if p["class"] == "FACTION_LIST_UNDEFINED"])

    def test_a_save_cut_off_mid_write_is_truncated(self) -> None:
        with resolved_temp_dir() as root:
            (root / "mods").mkdir()
            save = _save(root, [], "<hyperspace z=\"2\">", close=False)
            result = diagnose(save, root / "mods")
        self.assertEqual(result["verdict"], "TRUNCATED")
        self.assertIn("low", result["recovery"]["TRUNCATED"])



class InstalledModsTests(unittest.TestCase):
    def test_public_provider_matches_private_alias(self) -> None:
        with resolved_temp_dir() as root:
            mods = root / "mods"
            (mods / "alpha").mkdir(parents=True)
            (mods / "alpha" / "mod_info.json").write_text(
                json.dumps({"id": "alpha", "version": "1.0", "name": "Alpha"}), encoding="utf-8")
            found = installed_mods(mods)
            self.assertEqual(found, _installed(mods))
        self.assertEqual(found, {"alpha": {"folder": mods / "alpha", "version": "1.0", "name": "Alpha"}})

    def test_a_version_object_reads_as_the_dotted_version_the_save_records(self) -> None:
        """mod_info's {"major", "minor", "patch"} form was stored as its Python repr, so a save made with 1.20.0 read as
        VERSION_CHANGED against the same 1.20.0: 15 of 61 such findings on an RC8 save (White_Legion, 2026-11-17)."""
        with resolved_temp_dir() as root:
            mods = root / "mods"
            for mod_id, version in (("agc", {"major": "1", "minor": "20", "patch": "0"}), ("asf", {"major": 1, "minor": 7, "patch": 1})):
                (mods / mod_id).mkdir(parents=True)
                (mods / mod_id / "mod_info.json").write_text(json.dumps({"id": mod_id, "name": mod_id, "version": version}), encoding="utf-8")
            self.assertEqual({k: v["version"] for k, v in installed_mods(mods).items()}, {"agc": "1.20.0", "asf": "1.7.1"})
            save = _save(root, [("agc", "1.20.0"), ("asf", "1.7.2")], '<WSR.V z="2"></WSR.V>')
            result = diagnose(save, mods)
        self.assertEqual([(p["class"], p["mod"]) for p in result["problems"]], [("VERSION_CHANGED", "asf")])


class RemovalPlanTests(unittest.TestCase):
    def test_objects_are_droppable_unless_something_outside_refers_to_them(self) -> None:
        from bridgeforge.save.save_removal_plan import plan_removal
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
