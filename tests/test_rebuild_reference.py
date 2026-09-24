from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from bridgeforge.cli import main
from bridgeforge.rebuild_reference import RebuildReferenceError, merge_file, rebuild_from_reference
from tests.support import resolved_temp_dir

# A 0.9a-style vanilla weapon, the mod's edit of it, and what RC8 later did to the same file.
REFERENCE = {"id": "lightmg", "type": "BALLISTIC", "range": 500, "damage": {"amount": 25, "type": "KINETIC"},
             "tags": ["pd"], "slots": [{"id": "A", "angle": 0}, {"id": "B", "angle": 10}]}
MOD = {"id": "lightmg", "type": "BALLISTIC", "range": 600, "damage": {"amount": 25, "type": "KINETIC"},
       "tags": ["pd"], "slots": [{"id": "A", "angle": 0}, {"id": "B", "angle": 15}, {"id": "C", "angle": 20}],
       "modOnly": True}
RC8 = {"id": "lightmg", "type": "BALLISTIC", "range": 500, "damage": {"amount": 30, "type": "KINETIC"},
       "tags": ["pd", "kinetic"], "slots": [{"id": "A", "angle": 5}, {"id": "B", "angle": 10}], "rc8Only": 1}


def _write(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


class MergeFileTests(unittest.TestCase):
    def test_rc8_changes_kept_mod_edits_applied(self):
        with resolved_temp_dir() as root:
            result = merge_file(_write(root / "r.wpn", REFERENCE), _write(root / "m.wpn", MOD), _write(root / "c.wpn", RC8))
        self.assertEqual(result["status"], "MERGED", result)
        merged = result["merged"]
        self.assertEqual(merged["range"], 600)                         # the mod's edit
        self.assertEqual(merged["damage"]["amount"], 30)               # RC8's change, untouched by the mod
        self.assertEqual(merged["tags"], ["pd", "kinetic"])            # RC8's change
        self.assertEqual(merged["rc8Only"], 1)                          # RC8's addition
        self.assertTrue(merged["modOnly"])                              # the mod's addition
        self.assertEqual(merged["slots"], [{"id": "A", "angle": 5}, {"id": "B", "angle": 15}, {"id": "C", "angle": 20}])
        # RC8 left slot B alone, so the mod's B is applied whole rather than field by field.
        self.assertEqual(sorted(result["applied"]), ["modOnly", "range", "slots[id=B]", "slots[id=C]"])

    def test_both_changing_the_same_value_is_a_conflict_that_keeps_rc8(self):
        mod = {**MOD, "damage": {"amount": 40, "type": "KINETIC"}}
        with resolved_temp_dir() as root:
            result = merge_file(_write(root / "r.wpn", REFERENCE), _write(root / "m.wpn", mod), _write(root / "c.wpn", RC8))
        self.assertEqual(result["status"], "CONFLICT")
        self.assertEqual(result["conflicts"], [{"path": "damage.amount", "reference": 25, "mod": 40, "rc8": 30}])
        self.assertEqual(result["merged"]["damage"]["amount"], 30)

    def test_mod_removal_applies_only_where_rc8_left_the_value_alone(self):
        ref = {"a": 1, "b": 2}
        with resolved_temp_dir() as root:
            clean = merge_file(_write(root / "r.ship", ref), _write(root / "m.ship", {"b": 2}), _write(root / "c.ship", {"a": 1, "b": 3}))
            clash = merge_file(_write(root / "r2.ship", ref), _write(root / "m2.ship", {"b": 2}), _write(root / "c2.ship", {"a": 9, "b": 2}))
        self.assertEqual(clean["merged"], {"b": 3})
        self.assertEqual(clash["conflicts"], [{"path": "a", "reference": 1, "mod": "<absent>", "rc8": 9}])

    def test_unchanged_copy_and_unparseable(self):
        with resolved_temp_dir() as root:
            same = merge_file(_write(root / "r.wpn", REFERENCE), _write(root / "m.wpn", "# comment\n" + json.dumps(REFERENCE)), _write(root / "c.wpn", RC8))
            broken = merge_file(_write(root / "r2.wpn", REFERENCE), _write(root / "m2.wpn", "{nope"), _write(root / "c2.wpn", RC8))
        self.assertEqual(same["status"], "UNCHANGED_COPY")
        self.assertEqual(broken["status"], "UNPARSEABLE")


class RebuildFromReferenceTests(unittest.TestCase):
    def _layout(self, root: Path) -> tuple[Path, Path, Path]:
        mod, ref, cur = root / "mod", root / "ref-core", root / "rc8-core"
        weapon = Path("data/weapons/lightmg.wpn")
        _write(ref / weapon, REFERENCE)
        _write(mod / weapon, MOD)
        _write(cur / weapon, RC8)
        _write(ref / "data/hulls/wolf.ship", {"hullId": "wolf", "speed": 100})
        _write(mod / "data/hulls/wolf.ship", {"hullId": "wolf", "speed": 100})       # unchanged old copy
        _write(cur / "data/hulls/wolf.ship", {"hullId": "wolf", "speed": 110})
        _write(ref / "data/hulls/old.ship", {"hullId": "old"})
        _write(mod / "data/hulls/old.ship", {"hullId": "old", "x": 1})              # vanilla dropped it in RC8
        _write(mod / "data/hulls/new.ship", {"hullId": "new"})                       # mod's own hull
        _write(cur / "data/hulls/rc8only.ship", {"hullId": "rc8only"})
        _write(mod / "data/hulls/rc8only.ship", {"hullId": "rc8only", "y": 2})       # shadows RC8, no reference copy
        _write(mod / "data/weapons/weapon_data.csv", "id\nlightmg\n")                # CSVs are out of scope
        return mod, ref, cur

    def test_classifies_every_shadowed_file_and_writes_only_clean_merges(self):
        with resolved_temp_dir() as root:
            mod, ref, cur = self._layout(root)
            before = {p: p.read_bytes() for p in mod.rglob("*") if p.is_file()}
            result = rebuild_from_reference(mod, ref, cur, output=root / "out")
            after = {p: p.read_bytes() for p in mod.rglob("*") if p.is_file()}
            by_file = {entry["file"]: entry for entry in result["files"]}
            written = json.loads((root / "out/data/weapons/lightmg.wpn").read_text(encoding="utf-8"))
            self.assertFalse((root / "out/data/hulls/wolf.ship").exists())
        self.assertEqual(before, after)  # the mod is never written to
        self.assertEqual(result["counts"], {"MERGED": 1, "UNCHANGED_COPY": 1})
        self.assertEqual(by_file["data/hulls/wolf.ship"]["status"], "UNCHANGED_COPY")
        self.assertEqual(written["range"], 600)
        self.assertEqual(result["vanilla_removed_in_rc8"], ["data/hulls/old.ship"])
        self.assertEqual(result["shadowing_rc8_without_reference_copy"], ["data/hulls/rc8only.ship"])

    def test_class_filter_and_input_guards(self):
        with resolved_temp_dir() as root:
            mod, ref, cur = self._layout(root)
            only_wpn = rebuild_from_reference(mod, ref, cur, file_classes=["wpn"])
            self.assertEqual([e["file"] for e in only_wpn["files"]], ["data/weapons/lightmg.wpn"])
            for bad in ({"file_classes": ["csv"]}, {"output": mod / "rebuilt"}, {"output": root}):
                with self.assertRaises(RebuildReferenceError):
                    rebuild_from_reference(mod, ref, cur, **bad)
            with self.assertRaises(RebuildReferenceError):
                rebuild_from_reference(root / "missing", ref, cur)

    def test_cli_exit_code_follows_conflicts(self):
        with resolved_temp_dir() as root:
            mod, ref, cur = self._layout(root)
            args = ["rebuild-from-reference", str(mod), "--reference-core", str(ref), "--vanilla-core", str(cur)]
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(args), 0)
            _write(mod / "data/weapons/lightmg.wpn", {**MOD, "damage": {"amount": 40, "type": "KINETIC"}})
            with redirect_stdout(out):
                self.assertEqual(main(args), 1)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(args + ["--class", "java"]), 2)
        self.assertIn("MERGED 1, UNCHANGED_COPY 1", out.getvalue())
        self.assertIn("CONFLICT data/weapons/lightmg.wpn: damage.amount", out.getvalue())
        self.assertIn("vanilla removed in RC8 (now the mod's own content): data/hulls/old.ship", out.getvalue())


if __name__ == "__main__":
    unittest.main()
