"""ROADMAP item 73 H3: a revision that drops ids or classes of the previous archive needs a migration pack or a written reason."""
from __future__ import annotations

import json
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bridgeforge.revision_renames import (EVIDENCE_FILE, PACK_FIELDS, class_names, migration_requirement, removed_since, write_evidence)
from tests.support import resolved_temp_dir

REASON = "no save can hold the removed hull: it was never spawned by the campaign scripts"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _mod(root: Path, hulls: list[str], java: list[str] = (), jar_classes: list[str] = ()) -> Path:
    _write(root / "mod_info.json", json.dumps({"id": "m", "version": "1"}))
    _write(root / "data" / "hulls" / "ship_data.csv", "id,name\n" + "".join(f"{h},{h}\n" for h in hulls))
    for hull in hulls:
        _write(root / "data" / "hulls" / f"{hull}.ship", json.dumps({"hullId": hull, "hullName": hull}))
    for name in java:
        _write(root / "data" / "scripts" / f"{name}.java", f"class {name} {{}}")
    if jar_classes:
        (root / "jars").mkdir()
        with zipfile.ZipFile(root / "jars" / "m.jar", "w") as archive:
            for name in jar_classes:
                archive.writestr(name.replace(".", "/") + ".class", b"\xca\xfe\xba\xbe")
    return root


class RemovedTests(unittest.TestCase):
    def test_removed_hulls_and_classes_are_found_and_additions_are_not(self) -> None:
        with resolved_temp_dir() as root:
            old = _mod(root / "old", ["a_hull", "b_hull"], ["Old", "Kept"], ["com.m.OldJar", "com.m.Same"])
            new = _mod(root / "new", ["a_hull", "c_hull"], ["Kept", "Added"], ["com.m.Same", "com.m.NewJar"])
            removed = removed_since(old, new)
            names = class_names(new)
        self.assertEqual(removed["ids"], {"hull": ["b_hull"]})
        self.assertEqual(removed["classes"], ["com.m.OldJar", "data.scripts.Old"])
        self.assertIn("com.m.NewJar", names)


class RequirementTests(unittest.TestCase):
    def _case(self, root: Path):
        old = _mod(root / "Done" / "M" / "M", ["a_hull", "b_hull"])
        ws = root / "ws"
        new = _mod(ws / "working", ["a_hull"])
        return ws, old, new

    def test_no_previous_archive_or_nothing_removed_requires_nothing(self) -> None:
        with resolved_temp_dir() as root:
            ws, old, new = self._case(root)
            first = migration_requirement(ws, None, new)
            same = migration_requirement(ws, old, _mod(root / "same", ["a_hull", "b_hull"]))
        self.assertEqual((first["required"], same["required"]), (False, False))
        self.assertTrue(first["satisfied"] and same["satisfied"])

    def test_a_removed_id_requires_evidence_until_a_reason_is_written(self) -> None:
        with resolved_temp_dir() as root:
            ws, old, new = self._case(root)
            missing = migration_requirement(ws, old, new)
            write_evidence(ws, missing, reason=REASON)
            done = migration_requirement(ws, old, new)
            short = dict(missing)
            write_evidence(ws, short, reason="not needed")
            too_short = migration_requirement(ws, old, new)
        self.assertTrue(missing["required"] and not missing["satisfied"])
        self.assertIn("migration pack or a written reason", missing["problems"][0])
        self.assertEqual((done["satisfied"], done["how"]), (True, "reason"))
        self.assertFalse(too_short["satisfied"])

    def test_evidence_for_another_removed_set_is_stale(self) -> None:
        with resolved_temp_dir() as root:
            ws, old, new = self._case(root)
            write_evidence(ws, migration_requirement(ws, old, new), reason=REASON)
            (new / "data" / "hulls" / "a_hull.ship").unlink()  # a_hull is gone too now
            again = migration_requirement(ws, old, new)
        self.assertFalse(again["satisfied"])
        self.assertIn("different set", again["problems"][0])

    def test_a_pack_needs_every_contract_field_and_save_compat_loads(self) -> None:
        with resolved_temp_dir() as root:
            ws, old, new = self._case(root)
            requirement = migration_requirement(ws, old, new)
            full = {field: f"{field} text" for field in PACK_FIELDS}
            full["save_compat"] = {"save": str(root / "save")}
            incomplete = {k: v for k, v in full.items() if k != "idempotence"}
            write_evidence(ws, requirement, pack=incomplete)
            with mock.patch("bridgeforge.save.save_compat.check_save_compat", return_value={"status": "LOADS", "missing": []}):
                lacking = migration_requirement(ws, old, new)
            write_evidence(ws, requirement, pack=full)
            with mock.patch("bridgeforge.save.save_compat.check_save_compat", return_value={"status": "WILL_FAIL", "missing": [{"reference": "x"}]}):
                failing = migration_requirement(ws, old, new)
            with mock.patch("bridgeforge.save.save_compat.check_save_compat", return_value={"status": "LOADS", "missing": []}):
                good = migration_requirement(ws, old, new)
        self.assertIn("lacks idempotence", " ".join(lacking["problems"]))
        self.assertIn("save-compat says WILL_FAIL", " ".join(failing["problems"]))
        self.assertEqual((good["satisfied"], good["how"]), (True, "pack"))

    def test_evidence_cannot_be_written_when_nothing_is_required_or_ambiguous(self) -> None:
        with resolved_temp_dir() as root:
            ws, old, new = self._case(root)
            requirement = migration_requirement(ws, old, new)
            with self.assertRaises(ValueError):
                write_evidence(ws, requirement)
            with self.assertRaises(ValueError):
                write_evidence(ws, migration_requirement(ws, None, new), reason=REASON)
            self.assertFalse((ws / "reports" / EVIDENCE_FILE).exists())


if __name__ == "__main__":
    unittest.main()
