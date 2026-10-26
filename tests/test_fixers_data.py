"""B6 (ROADMAP item 73, revised by item 75 R4): local-weapon-spec-unregistered is evidence- or approval-only.

Fixture: Valkyrians `original/` (laserblaster.wpn is unregistered; valk_minimi is a registered BALLISTIC SMALL
projectile weapon), trimmed to the columns that matter.
"""
from __future__ import annotations

import csv
import io
import json
import unittest
from pathlib import Path

from bridgeforge.fixers import SUPPORTED_FINDINGS, FixerError, compute_fix
from bridgeforge.fixers.data import PROPOSALS_NAME, draft_weapon_row_proposals
from bridgeforge.scan.scanner import scan_mod
from tests.support import resolved_temp_dir

FINDING = "local-weapon-spec-unregistered"
HEADER = "name,id,tier,rarity,base value,range,damage/second,damage/shot,emp,impact,turn rate,OPs,type,hints,tags,tech/manufacturer"
CSV_TEXT = "\n".join([
    HEADER,
    "#small,,,,,,,,,,,,,,,",
    'Minimi DSC,valk_minimi,1,,2600,650,,20,,5,35,8,KINETIC,,"kinetic9,valk_enigma_bp",Valkyrie - Enigma Inc.',
    'Big Gun,valk_big,3,,9000,900,,200,,5,10,20,HIGH_EXPLOSIVE,,"he9",Valkyrie - Enigma Inc.',
    "",
])
# The weapon as another version of the mod registered it: its own name and its own balance.
ORIGINAL_CSV = "\n".join([
    "name,id,tier,range,damage/shot,OPs,type,tags,extra",
    'Laser Blaster,laserblaster,2,720,31,9,ENERGY,"energy5",x',
    "",
])


def _wpn(weapon: str, kind: str = "BALLISTIC", size: str = "SMALL", spec_class: str = "projectile", sprite: str = "graphics/w/base.png") -> str:
    return (
        "{\n"
        f'\t"id":"{weapon}",  # this id must match what\'s in the spreadsheet\n'
        f'\t"specClass":"{spec_class}",\n\t"type":"{kind}",\n\t"size":"{size}",\n'
        f'\t"turretSprite":"{sprite}",\n\t"hardpointSprite":"{sprite}",\n'
        '\t"barrelMode":"ALTERNATING", # or LINKED\n}\n'
    )


def _mod(base: Path, extra_wpn: str | None = None, csv_text: str = CSV_TEXT, sprite: bool = True) -> Path:
    """A workspace-shaped layout: base/working is the mod, base/original may hold the earlier version."""
    root = base / "working"
    weapons = root / "data" / "weapons"
    weapons.mkdir(parents=True)
    (weapons / "weapon_data.csv").write_bytes(csv_text.encode())
    (weapons / "valk_minimi.wpn").write_text(_wpn("valk_minimi"), encoding="utf-8")
    (weapons / "valk_big.wpn").write_text(_wpn("valk_big", size="LARGE"), encoding="utf-8")
    (weapons / "laserblaster.wpn").write_text(extra_wpn or _wpn("laserblaster"), encoding="utf-8")
    if sprite:
        (root / "graphics" / "w").mkdir(parents=True)
        (root / "graphics" / "w" / "base.png").write_bytes(b"png")
    (root / "mod_info.json").write_text('{"id":"m","name":"m","version":"1","gameVersion":"0.98a-RC8"}', encoding="utf-8")
    return root


def _original(base: Path, wpn: str | None = None) -> None:
    folder = base / "original" / "Mod" / "data" / "weapons"
    folder.mkdir(parents=True)
    (folder / "weapon_data.csv").write_text(ORIGINAL_CSV, encoding="utf-8")
    if wpn is not None:
        (folder / "laserblaster.wpn").write_text(wpn, encoding="utf-8")


def _rows(path: Path) -> list[list[str]]:
    return list(csv.reader(io.StringIO(path.read_text(encoding="utf-8"), newline="")))


def _write(plan) -> None:
    for change in plan.changes:
        change.path.write_bytes(change.after)


class LocalWeaponRowTests(unittest.TestCase):
    def test_supported(self) -> None:
        self.assertIn(FINDING, SUPPORTED_FINDINGS)

    def test_exact_row_from_the_original_is_used_with_its_own_values_and_name(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            _original(base, _wpn("laserblaster"))
            self.assertIn(FINDING, [f.id for f in scan_mod(root).findings])
            _write(compute_fix(root, FINDING, {}))
            rows = _rows(root / "data/weapons/weapon_data.csv")
            after = [f.id for f in scan_mod(root).findings]
        record = dict(zip(rows[0], rows[-1]))
        self.assertEqual((record["name"], record["range"], record["damage/shot"], record["OPs"], record["type"]), ("Laser Blaster", "720", "31", "9", "ENERGY"))
        self.assertEqual(record["rarity"], "")  # a column the source lacks stays blank, nothing is borrowed from siblings
        self.assertNotIn("extra", record)  # a column this CSV lacks is dropped
        self.assertIn("original", rows[-2][0])
        self.assertNotIn(FINDING, after)

    def test_exact_row_is_refused_when_the_earlier_wpn_is_a_different_weapon(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            _original(base, _wpn("laserblaster", kind="MISSILE"))
            with self.assertRaisesRegex(FixerError, "no exact row"):
                compute_fix(root, FINDING, {})

    def test_evidence_roots_option_names_another_version(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            other = base / "elsewhere"
            (other / "data" / "weapons").mkdir(parents=True)
            (other / "data" / "weapons" / "weapon_data.csv").write_text(ORIGINAL_CSV, encoding="utf-8")
            plan = compute_fix(root, FINDING, {"evidence_roots": [other]})
        self.assertIn("Laser Blaster", plan.changes[0].after.decode("utf-8"))

    def test_without_evidence_or_approval_nothing_is_applied(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            with self.assertRaisesRegex(FixerError, "no exact row in another version and no owner-approved proposal"):
                compute_fix(root, FINDING, {})

    def test_a_draft_writes_reports_only_and_leaves_the_mod_untouched(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            reports = base / "reports"
            path = draft_weapon_row_proposals(root, reports)
            after = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(before, after)
        self.assertEqual(path.parent, reports)
        self.assertEqual(path.name, PROPOSALS_NAME)
        entry = data["proposals"][0]
        self.assertFalse(entry["approved"])
        self.assertTrue(entry["name_is_placeholder"])
        self.assertEqual(entry["comparison"], "valk_minimi")
        record = dict(zip(data["header"], entry["row"]))
        self.assertEqual((record["name"], record["range"], record["type"]), ("laserblaster", "650", "KINETIC"))  # name is the id, never specClass
        self.assertIn({"column": "range", "value": "650", "source": "valk_minimi in data/weapons/weapon_data.csv"}, entry["copied"])
        self.assertIn("not balance evidence", entry["evidence"])

    def test_an_unapproved_proposal_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            path = draft_weapon_row_proposals(root, base / "reports")
            with self.assertRaisesRegex(FixerError, "no owner-approved proposal"):
                compute_fix(root, FINDING, {"weapon_row_proposals": str(path)})

    def test_an_approved_proposal_applies_exactly_the_approved_row(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            path = draft_weapon_row_proposals(root, base / "reports")
            data = json.loads(path.read_text(encoding="utf-8"))
            entry = data["proposals"][0]
            entry["approved"] = True
            entry["row"][data["header"].index("name")] = "Laser Blaster"  # the owner edits the placeholder
            entry["row"][data["header"].index("range")] = "700"
            _write(compute_fix(root, FINDING, {"weapon_row_proposals": data}))
            rows = _rows(root / "data/weapons/weapon_data.csv")
            with self.assertRaises(FixerError):
                compute_fix(root, FINDING, {"weapon_row_proposals": data})
        record = dict(zip(rows[0], rows[-1]))
        self.assertEqual((record["name"], record["range"], record["damage/shot"]), ("Laser Blaster", "700", "20"))
        self.assertIn("owner-approved proposal", rows[-2][0])

    def test_a_stale_approval_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            path = draft_weapon_row_proposals(root, base / "reports")
            data = json.loads(path.read_text(encoding="utf-8"))
            data["proposals"][0]["approved"] = True
            (root / "data/weapons/laserblaster.wpn").write_text(_wpn("laserblaster", spec_class="beam"), encoding="utf-8")
            with self.assertRaisesRegex(FixerError, "stale"):
                compute_fix(root, FINDING, {"weapon_row_proposals": data})
            data2 = json.loads(path.read_text(encoding="utf-8"))
            data2["proposals"][0]["approved"] = True
            (root / "data/weapons/laserblaster.wpn").write_text(_wpn("laserblaster"), encoding="utf-8")
            (root / "data/weapons/weapon_data.csv").write_bytes((CSV_TEXT + "Extra,valk_extra,1\n").encode())
            with self.assertRaisesRegex(FixerError, "stale"):
                compute_fix(root, FINDING, {"weapon_row_proposals": data2})

    def test_an_approval_for_another_weapon_or_a_malformed_row_is_refused(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base)
            data = json.loads(draft_weapon_row_proposals(root, base / "reports").read_text(encoding="utf-8"))
            data["proposals"][0]["approved"] = True
            data["proposals"][0]["row"] = ["too", "short"]
            with self.assertRaisesRegex(FixerError, "does not match this CSV's columns"):
                compute_fix(root, FINDING, {"weapon_row_proposals": data})

    def test_draft_without_a_comparable_weapon_records_a_refusal(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base, _wpn("laserblaster", kind="MISSILE"))
            data = json.loads(draft_weapon_row_proposals(root, base / "reports").read_text(encoding="utf-8"))
        self.assertIn("no registered weapon of type MISSILE and size SMALL", data["proposals"][0]["refused"])
        self.assertNotIn("row", data["proposals"][0])

    def test_missing_sprite_is_refused_in_apply_and_draft(self) -> None:
        with resolved_temp_dir() as base:
            root = _mod(base, sprite=False)
            _original(base)
            with self.assertRaisesRegex(FixerError, "sprite not found: graphics/w/base.png"):
                compute_fix(root, FINDING, {})
            data = json.loads(draft_weapon_row_proposals(root, base / "reports").read_text(encoding="utf-8"))
        self.assertIn("sprite not found", data["proposals"][0]["refused"])

    def test_a_sprite_in_the_vanilla_core_counts(self) -> None:
        with resolved_temp_dir() as base:
            core = base / "core"
            (core / "graphics" / "w").mkdir(parents=True)
            (core / "graphics" / "w" / "base.png").write_bytes(b"png")
            root = _mod(base, sprite=False)
            _original(base)
            plan = compute_fix(root, FINDING, {"vanilla_core": core})
        self.assertIn("Laser Blaster", plan.changes[0].after.decode("utf-8"))

    def test_keeps_crlf_line_endings_and_existing_bytes(self) -> None:
        text = CSV_TEXT.replace("\n", "\r\n")
        with resolved_temp_dir() as base:
            root = _mod(base, csv_text=text)
            _original(base)
            plan = compute_fix(root, FINDING, {})
        after = plan.changes[0].after
        self.assertTrue(after.startswith(text.encode()))
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))


if __name__ == "__main__":
    unittest.main()
