"""target-impact (2026-11-15): what a newer game version breaks that the validated one did not.

Fixtures are tiny fake cores compiled with the JDK: the old has RC8's shapes (ShipAIConfig(), ShipAPI.isBeingIgnored()),
the new 0.98.5a-RC3's (ShipAIConfig(ShipAPI), isBeingIgnored(boolean), a new abstract isWasHulk()), as `api-diff` showed.
"""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.target_impact import default_jobs, discover_mods, render, target_impact
from tests.support import javac_path, resolved_temp_dir
from tests.test_jar_linkage import _compile, _jar

_PKG = "com/fs/starfarer/api/combat/"
OLD_CORE = {
    _PKG + "ShipAPI.java": "package com.fs.starfarer.api.combat; public interface ShipAPI { boolean isBeingIgnored(); }",
    _PKG + "ShipAIConfig.java": "package com.fs.starfarer.api.combat; public class ShipAIConfig { public ShipAIConfig() {} }",
    _PKG + "Tip.java": "package com.fs.starfarer.api.combat; public interface Tip { void table(); }",
}
NEW_CORE = {
    _PKG + "ShipAPI.java": "package com.fs.starfarer.api.combat; public interface ShipAPI { boolean isBeingIgnored(boolean byAlly); boolean isWasHulk(); }",
    _PKG + "ShipAIConfig.java": "package com.fs.starfarer.api.combat; public class ShipAIConfig { public ShipAIConfig(ShipAPI ship) {} }",
    _PKG + "Tip.java": "package com.fs.starfarer.api.combat; public interface Tip { Object table(); }",
}
DRONE = {"lib/Drone.java": "package lib; import com.fs.starfarer.api.combat.*;\n"
                           "public class Drone implements ShipAPI { ShipAPI real; public boolean isBeingIgnored() { return real.isBeingIgnored(); } }"}
AI = {"mod/Ai.java": "package mod; import com.fs.starfarer.api.combat.*;\n"
                     "public class Ai { Object make() { return new ShipAIConfig(); } void t(Tip t) { t.table(); } }"}
LOOSE = "package data.scripts; class Brain { Object c(ShipAPI s) { return s.isBeingIgnored() ? null : new ShipAIConfig(); } }\n"


def _mod(root: Path, name: str, info: dict, classes: Path | None) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    if classes is not None:
        _jar(classes, folder / "jars" / f"{name}.jar")
        info = {**info, "jars": [f"jars/{name}.jar"]}
    (folder / "mod_info.json").write_text(json.dumps({"name": name, "version": "1", **info}), encoding="utf-8")
    return folder


class TargetImpactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")

    def _fixture(self, root: Path) -> tuple[Path, Path, Path]:
        old_classes = _compile(self.javac, root / "oldbuild", OLD_CORE)
        _jar(old_classes, root / "old" / "starfarer.api.jar")
        _jar(_compile(self.javac, root / "newbuild", NEW_CORE), root / "new" / "starfarer.api.jar")
        queue = root / "queue"
        _mod(queue, "lib", {"id": "lib"}, _compile(self.javac, root / "libbuild", DRONE, classpath=old_classes))
        _mod(queue, "user", {"id": "user", "dependencies": [{"id": "lib"}]}, _compile(self.javac, root / "userbuild", AI, classpath=old_classes))
        loose = _mod(queue, "loose", {"id": "loose"}, None)
        (loose / "data" / "scripts").mkdir(parents=True)
        (loose / "data" / "scripts" / "Brain.java").write_text(LOOSE, encoding="utf-8")
        _mod(queue, "plain", {"id": "plain"}, None)
        return root / "old", root / "new", queue

    def test_each_kind_of_break_is_found_and_only_new_ones(self) -> None:
        with resolved_temp_dir() as root:
            old, new, queue = self._fixture(root)
            result = target_impact([queue], old, new)
        by_mod = {r["mod"]: r for r in result["records"]}
        self.assertEqual(result["verdicts"], {"BREAKS": 3, "RELINK": 0, "REVIEW": 0, "CLEAN": 1})
        lib = by_mod["queue/lib"]
        self.assertEqual(lib["interfaces"][0]["methods"], ["com/fs/starfarer/api/combat/ShipAPI.isBeingIgnored(Z)Z",
                                                           "com/fs/starfarer/api/combat/ShipAPI.isWasHulk()Z"])
        self.assertEqual([(p["name"], p["descriptor"]) for p in lib["linkage"]], [("isBeingIgnored", "()Z")])
        user = {(p["name"], p["descriptor"], p["return_type_only"]) for p in by_mod["queue/user"]["linkage"]}
        self.assertEqual(user, {("<init>", "()V", False), ("table", "()V", True)})
        self.assertEqual(sorted(s["call"] for s in by_mod["queue/loose"]["sources"]), ["ShipAIConfig", "isBeingIgnored"])
        self.assertEqual(by_mod["queue/plain"]["verdict"], "CLEAN")
        # Worklist (89.11): fixers first, then a relink, then hand work.
        self.assertTrue(by_mod["queue/loose"]["fixers_only"])
        self.assertIn("--finding rc8-signature-changed", by_mod["queue/loose"]["next"][0])
        user_next = by_mod["queue/user"]["next"]
        self.assertIn("--finding jar-call-signature-changed", user_next[0])
        self.assertTrue(user_next[1].startswith("relink 1 call(s)"))
        self.assertFalse(by_mod["queue/user"]["fixers_only"])
        self.assertTrue(any(step.startswith("hand: implement") for step in lib["next"]))
        self.assertIn("1 of 3 mods need only the gated fixers: queue/loose.", render(result))
        members = {e["member"]: e["mods"] for e in result["by_member"]}
        self.assertEqual(members["com.fs.starfarer.api.combat.ShipAIConfig.<init>()V"], ["queue/user"])

    def test_an_archive_is_restored_first_and_a_workspace_is_relinked_directly(self) -> None:
        """ROADMAP-3 95.13: a return-type-only call is `bridgeforge relink`'s job (recompile from source, unedited), and it works
        on a workspace; an archived copy is restored first, as `retarget` refuses archives ("archives move with archive --refresh")."""
        with resolved_temp_dir() as root:
            old, new, _ = self._fixture(root)
            old_classes = root / "oldbuild" / "classes"  # what _fixture compiled the old core into
            _mod(root / "Done" / "user", "user", {"id": "user"}, _compile(self.javac, root / "donebuild", AI, classpath=old_classes))
            _mod(root / "q" / "W", "working", {"id": "w"}, _compile(self.javac, root / "wsbuild", AI, classpath=old_classes))
            result = target_impact([root / "Done", root / "q"], old, new)
            # The same archive while the queue still holds the workspace it was archived from (`archive` copies).
            (root / "In operation" / "user" / "working").mkdir(parents=True)
            again = {r["mod"]: r for r in target_impact([root / "Done"], old, new)["records"]}
        by_mod = {r["mod"]: r for r in result["records"]}
        queue = root.resolve() / "In operation"
        restored = queue / "user"
        self.assertEqual(by_mod["Done/user"]["next"], [
            f'bridgeforge restore-from-done "{(root / "Done" / "user").resolve()}" --queue "{queue}" --for-retarget',
            f'bridgeforge fix "{restored / "working"}" --finding jar-call-signature-changed --vanilla-core "{new.resolve()}" --apply',
            f'bridgeforge relink "{restored}" --vanilla-core "{new.resolve()}" --apply'])
        workspace = (root / "q" / "W").resolve()
        self.assertEqual(by_mod["q/W"]["next"][1], f'bridgeforge relink "{workspace}" --vanilla-core "{new.resolve()}" --apply')
        self.assertFalse(by_mod["Done/user"]["fixers_only"])  # a relink is not a gated fixer
        self.assertTrue(again["Done/user"]["next"][0].startswith(f"the queue already holds {restored}"))
        self.assertEqual(again["Done/user"]["next"][2], f'bridgeforge relink "{restored}" --vanilla-core "{new.resolve()}" --apply')

    def test_a_process_pool_gives_the_same_result_in_the_same_order(self) -> None:
        """96.5 P10: mods are checked side by side in worker processes; the result is the one the in-process loop gives."""
        with resolved_temp_dir() as root:
            old, new, queue = self._fixture(root)
            seen: list[str] = []
            alone = target_impact([queue], old, new, jobs=1)
            pooled = target_impact([queue], old, new, jobs=2, progress=lambda done, total, label, record, seconds: seen.append(label))
        self.assertEqual(json.dumps(pooled, sort_keys=True), json.dumps(alone, sort_keys=True))
        self.assertEqual(sorted(seen), sorted(r["mod"] for r in alone["records"]))  # one progress line per mod
        self.assertGreaterEqual(default_jobs(), 1)

    def test_jobs_below_one_is_refused(self) -> None:
        from bridgeforge.cli import main

        with resolved_temp_dir() as root:
            old, new, queue = self._fixture(root)
            with redirect_stderr(io.StringIO()) as err:
                code = main(["target-impact", str(old), str(new), str(queue), "--jobs", "0", "--quiet"])
        self.assertEqual(code, 2)
        self.assertIn("--jobs must be 1 or more", err.getvalue())

    def test_same_core_twice_reports_nothing(self) -> None:
        with resolved_temp_dir() as root:
            old, _, queue = self._fixture(root)
            result = target_impact([queue], old, old)
        self.assertEqual(result["verdicts"], {"BREAKS": 0, "RELINK": 0, "REVIEW": 0, "CLEAN": 4})

    def test_cli_writes_report_resumes_and_drops_the_checkpoint(self) -> None:
        from bridgeforge.cli import main

        with resolved_temp_dir() as root:
            old, new, queue = self._fixture(root)
            out = root / "out"
            out.mkdir()
            # A checkpoint from an interrupted run with the same inputs: its record is reused, not recomputed.
            header = {"checkpoint": 1, "old_core": str(old), "new_core": str(new), "roots": [str(queue)]}
            fake = {"mod": "queue/plain", "id": "plain", "version": "1", "path": "x", "verdict": "RELINK",
                    "linkage": [], "interfaces": [], "sources": []}
            (out / "TARGET_IMPACT.partial.jsonl").write_text(json.dumps(header) + "\n" + json.dumps({"key": "queue/plain", "value": fake}) + "\n",
                                                            encoding="utf-8")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = main(["target-impact", str(old), str(new), str(queue), "--write", str(out)])
            data = json.loads((out / "TARGET_IMPACT.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertFalse((out / "TARGET_IMPACT.partial.jsonl").exists())
            self.assertTrue((out / "TARGET_IMPACT.md").is_file())
        # Resumed mods are reported first; the count is of finished mods, in the order they finish (96.5 P10).
        self.assertIn("[1/4] queue/plain: RELINK (0 linkage, 0 interface, 0 source, 0 data) (from checkpoint)", err.getvalue())
        self.assertEqual(err.getvalue().count("/4] "), 4)
        self.assertEqual(data["verdicts"]["RELINK"], 1)

    def test_an_archive_the_owner_closed_is_listed_not_checked(self) -> None:
        """ROADMAP-3 95.15: owner 2026-11-17, "nightcross armory has been superseded and can safely be ignored"; the RC8 -> RC7
        catalogue had listed Done/Nightcross as RELINK."""
        from bridgeforge.workspace_tools import close_workspace

        with resolved_temp_dir() as root:
            old, new, _ = self._fixture(root)
            archive = root / "Done" / "user"
            _mod(archive, "user", {"id": "user"}, _compile(self.javac, root / "donebuild", AI, classpath=root / "oldbuild" / "classes"))
            (archive / "workspace").mkdir()
            (archive / "workspace" / "REVIVAL_REPORT.md").write_text("# Revival report\n\nLIVE_VALIDATED\n", encoding="utf-8")
            close_workspace(archive, "SUPERSEDED", "Owner 2026-11-17: superseded, can safely be ignored.")
            result = target_impact([root / "Done"], old, new)
        self.assertEqual(result["records"], [])
        self.assertEqual(result["skipped"], [{"mod": "Done/user", "status": "SUPERSEDED"}])
        self.assertIn("Done/user (SUPERSEDED)", render(result))


class DiscoveryTests(unittest.TestCase):
    def test_done_archive_workspace_and_plain_mod_folders(self) -> None:
        with resolved_temp_dir() as root:
            done = root / "Done"
            (done / "A" / "A" ).mkdir(parents=True)
            (done / "A" / "A" / "mod_info.json").write_text('{"id": "a"}', encoding="utf-8")
            (done / "A" / "original" / "A").mkdir(parents=True)
            (done / "A" / "original" / "A" / "mod_info.json").write_text('{"id": "a-old"}', encoding="utf-8")
            (done / "B" / "working").mkdir(parents=True)
            (done / "B" / "working" / "mod_info.json").write_text('{"id": "b"}', encoding="utf-8")
            (done / "_previous" / "C").mkdir(parents=True)
            (done / "_previous" / "C" / "mod_info.json").write_text('{"id": "c"}', encoding="utf-8")
            found = [(label, folder.relative_to(root).as_posix()) for label, folder in discover_mods([done])]
        self.assertEqual(found, [("Done/A", "Done/A/A"), ("Done/B", "Done/B/working")])

    def test_render_lists_breaking_mods_only(self) -> None:
        result = {"mods": 2, "old_core": "o", "new_core": "n", "verdicts": {"BREAKS": 1, "RELINK": 0, "CLEAN": 1}, "note": "x",
                  "by_member": [], "records": [
                      {"mod": "Q/a", "id": "a", "version": "1", "verdict": "BREAKS", "linkage": [], "interfaces": [],
                       "sources": [{"file": "S.java", "line": 3, "call": "ShipAIConfig"}]},
                      {"mod": "Q/b", "id": "b", "version": "1", "verdict": "CLEAN", "linkage": [], "interfaces": [], "sources": []}]}
        text = render(result)
        self.assertIn("### Q/a (a 1): BREAKS", text)
        self.assertIn("`S.java:3` uses the old `ShipAIConfig(...)`", text)
        self.assertNotIn("Q/b", text)

    def test_render_shortens_obfuscated_member_names_and_the_json_keeps_them(self) -> None:
        """ROADMAP-3 95.12(i): one Station Augments descriptor ran to hundreds of characters in TARGET_IMPACT.md (2026-11-17)."""
        long_member = "implement com.fs.starfarer.combat.ai.F.super(FLcom.fs.starfarer.combat.ai." + "O0" * 200 + ";)V"
        result = {"mods": 1, "old_core": "o", "new_core": "n", "verdicts": {"BREAKS": 1, "RELINK": 0, "CLEAN": 0}, "note": "x",
                  "by_member": [{"member": long_member, "mods": ["Q/a"]}], "records": [
                      {"mod": "Q/a", "id": "a", "version": "1", "verdict": "BREAKS", "linkage": [], "sources": [],
                       "interfaces": [{"class": "a.jar!X.class", "methods": [long_member[len("implement "):].replace(".", "/")]}]}]}
        text = render(result)
        self.assertNotIn("O0" * 100, text)
        self.assertTrue(all(len(line) < 400 for line in text.splitlines()))
        self.assertIn("implement com.fs.starfarer.combat.ai.F.super(", text)
        self.assertEqual(result["by_member"][0]["member"], long_member)  # only the markdown is shortened

    def test_a_game_supertype_the_new_core_lacks_breaks_the_mod(self) -> None:
        """ROADMAP-3 98.7 (2026-11-25): Station Augments' shield-AI wrapper implements combat/ai/F, renamed G on RC9."""
        from tests.test_jar_linkage import NEW_OBF, OLD_OBF
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")
        wrapper = {"data/Shunt.java": "package data; public class Shunt implements com.fs.starfarer.combat.ai.F { public boolean o00000() { return false; } }"}
        ported = {"data/Shunt.java": "package data; public class Shunt implements com.fs.starfarer.combat.ai.G { public boolean o00000() { return false; } }"}
        with resolved_temp_dir() as root:
            old_classes = _compile(self.javac, root / "oldbuild", OLD_OBF)
            new_classes = _compile(self.javac, root / "newbuild", NEW_OBF)
            _jar(old_classes, root / "old" / "starfarer_obf.jar")
            _jar(new_classes, root / "new" / "starfarer_obf.jar")
            api = _compile(self.javac, root / "apibuild", {"com/fs/starfarer/api/Stub.java": "package com.fs.starfarer.api; public class Stub {}"})
            for core in ("old", "new"):
                _jar(api, root / core / "starfarer.api.jar")
            queue = root / "queue"
            _mod(queue, "sa", {"id": "sa"}, _compile(self.javac, root / "sabuild", wrapper, classpath=old_classes))
            _mod(queue, "saported", {"id": "saported"}, _compile(self.javac, root / "portbuild", ported, classpath=new_classes))
            result = target_impact([queue], root / "old", root / "new")
        by_mod = {r["mod"]: r for r in result["records"]}
        record = by_mod["queue/sa"]
        self.assertEqual(record["verdict"], "BREAKS")
        self.assertEqual([(p["kind"], p["owner"]) for p in record["linkage"]], [("supertype", "com/fs/starfarer/combat/ai/F")])
        self.assertIn("- jar `sa.jar!data/Shunt.class` extends or implements `com.fs.starfarer.combat.ai.F`, which the new core lacks",
                      render(result))
        self.assertTrue(any("hand port: com.fs.starfarer.combat.ai.F" in step for step in record["next"]))
        # The ported copy implements G, which only the new core has: CLEAN, and G is listed as newly resolved (no "missing").
        self.assertEqual(by_mod["queue/saported"]["verdict"], "CLEAN")
        self.assertEqual(by_mod["queue/saported"]["resolved_on_new"], ["com.fs.starfarer.combat.ai.G"])


if __name__ == "__main__":
    unittest.main()


class DataLayerTests(unittest.TestCase):
    def test_orphaned_rule_override_new_column_and_removed_setting(self) -> None:
        # 0.98.5a-RC3 (2026-11-15): 115 rule ids removed, ship_data.csv gained parts/dmod, salary, salMult,
        # settings.json dropped factionCommissionStipendPerLevel.
        from bridgeforge.target_impact import data_hits

        with resolved_temp_dir() as root:
            for name, rules, ship_cols, settings in (("old", "id,trigger\nkpAudience1,x\nkeep,y\n", "id,name", '{"stipendPerLevel": 1, "kept": 2}'),
                                                     ("new", "id,trigger\nkeep,y\n", "id,name,salary", '{"kept": 2}')):
                core = root / name / "data"
                (core / "campaign").mkdir(parents=True)
                (core / "hulls").mkdir()
                (core / "config").mkdir()
                (core / "campaign" / "rules.csv").write_text(rules, encoding="utf-8")
                (core / "hulls" / "ship_data.csv").write_text(ship_cols + "\n", encoding="utf-8")
                (core / "config" / "settings.json").write_text(settings, encoding="utf-8")
            mod = root / "mod"
            (mod / "data" / "campaign").mkdir(parents=True)
            (mod / "data" / "hulls").mkdir()
            (mod / "mod_info.json").write_text('{"id": "m", "replace": ["data/hulls/ship_data.csv"]}', encoding="utf-8")
            (mod / "data" / "campaign" / "rules.csv").write_text("id,trigger\nkpAudience1,z\nkeep,q\nmine,r\n", encoding="utf-8")
            (mod / "data" / "hulls" / "ship_data.csv").write_text("id,name\nx,X\n", encoding="utf-8")
            (mod / "S.java").write_text('float a = Global.getSettings().getFloat("stipendPerLevel"); int b = Global.getSettings().getInt("kept");',
                                        encoding="utf-8")
            hits = data_hits(mod, root / "old", root / "new")
        self.assertEqual(hits, [{"kind": "rule-override-orphaned", "detail": "kpAudience1"},
                                {"kind": "replace-lacks-new-columns", "detail": "data/hulls/ship_data.csv: salary"},
                                {"kind": "settings-key-removed", "detail": "stipendPerLevel"}])


class ClosedProviderTests(unittest.TestCase):
    def test_a_closed_library_archive_still_provides_its_jars(self) -> None:
        """Review 2026-11-17 (ROADMAP-3 95.15): a mod whose dependency's only copy is a closed archive was checked without the
        library's jars, once closed mods left the id map."""
        from unittest import mock

        from bridgeforge import target_impact as module
        from bridgeforge.workspace_tools import close_workspace

        with resolved_temp_dir() as root:
            for core in ("old", "new"):
                (root / core).mkdir()
                (root / core / "starfarer.api.jar").write_bytes(b"")
            lib = root / "Done" / "lib" / "lib"
            (lib / "jars").mkdir(parents=True)
            (lib / "jars" / "lib.jar").write_bytes(b"PK")
            (lib / "mod_info.json").write_text('{"id": "lib", "jars": ["jars/lib.jar"]}', encoding="utf-8")
            (root / "Done" / "lib" / "workspace").mkdir()
            (root / "Done" / "lib" / "workspace" / "REVIVAL_REPORT.md").write_text("# Revival report\n\nLIVE_VALIDATED\n", encoding="utf-8")
            close_workspace(root / "Done" / "lib", "SUPERSEDED", "Owner: superseded.")
            (root / "q" / "user").mkdir(parents=True)
            (root / "q" / "user" / "mod_info.json").write_text('{"id": "user", "dependencies": [{"id": "lib"}]}', encoding="utf-8")
            seen: dict[str, list[str]] = {}

            def fake(folder, old, new, providers):
                seen[Path(folder).name] = [Path(p).name for p in providers]
                return {"id": None, "version": None, "path": str(folder), "verdict": "CLEAN", "linkage": [], "interfaces": [],
                        "data": [], "sources": [], "touches": {}, "resolved_on_new": [], "next": [], "fixers_only": False}

            with mock.patch.object(module, "mod_impact", side_effect=fake):
                result = module.target_impact([root / "Done", root / "q"], root / "old", root / "new")
        self.assertEqual(seen, {"user": ["lib.jar"]})
        self.assertEqual(result["skipped"], [{"mod": "Done/lib", "status": "SUPERSEDED"}])


class WorkspaceForArchiveTests(unittest.TestCase):
    def test_a_shipped_folder_named_otherwise_is_restored_not_edited_in_place(self) -> None:
        # 96.10: Done/Station.Augments-2.4.3+bf.1/Station Augments was "any other mod folder", acted on in place.
        from bridgeforge.target_impact import _workspace_for

        with resolved_temp_dir() as root:
            shipped = root / "Done" / "Station.Augments-2.4.3+bf.1" / "Station Augments"
            shipped.mkdir(parents=True)
            steps, working = _workspace_for(shipped)
        queue = root / "In operation"
        self.assertEqual(steps, [f'bridgeforge restore-from-done "{shipped.parent}" --queue "{queue}" --for-retarget'])
        self.assertEqual(working, queue / "Station.Augments-2.4.3+bf.1" / "working")
