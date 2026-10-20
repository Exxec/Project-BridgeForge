"""`vanilla-path-shadowing` triage against the reference rig (ROADMAP item 73 D3, revised by item 75 R4)."""
import json
import unittest
from pathlib import Path

from bridgeforge.fixers import FixerError, apply_fix, compute_fix
from bridgeforge.reference_rigs import reference_core_for_game_version
from bridgeforge.shadow_triage import REMOVED_SHADOW_FOLDER, read_rulings, record_ruling, triage
from tests.support import resolved_temp_dir

OLD_SYSTEM = '{"id":"damper","type":"STAT_MOD","regen":1}'
RC8_SYSTEM = '{"id":"damper","type":"STAT_MOD","regen":2}'
EDITED_SYSTEM = '{"id":"damper","type":"STAT_MOD","regen":5}'
DAMPER = "data/shipsystems/damper.system"
FLARE = "data/shipsystems/flare.system"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _layout(root: Path) -> tuple[Path, Path, Path, Path]:
    """(working, rc8 core, reference core, workspace) with damper = unchanged old vanilla, flare = edited by the mod."""
    workspace = root / "Mod"
    working = workspace / "working"
    rc8, reference = root / "rc8", root / "ref"
    _write(working / "mod_info.json", '{"id":"m","gameVersion":"0.9a-RC8"}')
    for name in ("damper", "flare"):
        _write(rc8 / f"data/shipsystems/{name}.system", RC8_SYSTEM.replace("damper", name))
        _write(reference / f"data/shipsystems/{name}.system", OLD_SYSTEM.replace("damper", name))
    _write(working / DAMPER, OLD_SYSTEM)
    _write(working / FLARE, EDITED_SYSTEM.replace("damper", "flare"))
    return working, rc8, reference, workspace


def _opts(rc8: Path, reference: Path) -> dict:
    return {"vanilla_core": rc8, "reference_core": reference}


class ShadowTriageTests(unittest.TestCase):
    def test_identical_but_unapproved_is_retained_and_a_three_way_report_is_written(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, workspace = _layout(root)
            apply_fix(compute_fix(working, "vanilla-path-shadowing", _opts(rc8, reference)))
            report = (workspace / "reports" / "SHADOW_TRIAGE.md").read_text(encoding="utf-8")
            self.assertTrue((working / DAMPER).is_file())  # byte-identical to old vanilla, still not removed
            self.assertFalse((workspace / "scratch" / REMOVED_SHADOW_FOLDER).exists())
            with self.assertRaises(FixerError):  # rerun: nothing new
                compute_fix(working, "vanilla-path-shadowing", _opts(rc8, reference))
        self.assertIn("approval: none", report)
        self.assertIn("Old vanilla -> current RC8", report)
        self.assertIn("regen: 1 -> 2", report)  # what the game changed
        self.assertIn("regen: 1 -> 5", report)  # what the mod changed (flare)
        self.assertIn("regen: 2 -> 5", report)  # what the file does to current RC8

    def test_approved_move_is_backed_up_and_a_changed_file_stays(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, workspace = _layout(root)
            record_ruling(working, rc8, reference, DAMPER, reason="owner: old copy, RC8's is meant", today="2026-10-18")
            apply_fix(compute_fix(working, "vanilla-path-shadowing", _opts(rc8, reference)))
            moved = workspace / "scratch" / REMOVED_SHADOW_FOLDER / DAMPER
            self.assertEqual(moved.read_text(encoding="utf-8"), OLD_SYSTEM)  # the copy is the backup
            self.assertFalse((working / DAMPER).exists())
            self.assertTrue((working / FLARE).is_file())
            entry = read_rulings(root / "ESCALATION_RULINGS.jsonl")[0]
        self.assertEqual((entry["finding"], entry["ruling"], entry["mods"], entry["file"]),
                         ("vanilla-path-shadowing", "approve-shadow-removal", ["Mod"], DAMPER))

    def test_a_changed_file_cannot_be_approved(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, _ = _layout(root)
            with self.assertRaises(ValueError):
                record_ruling(working, rc8, reference, FLARE, reason="x")

    def test_stale_approval_is_refused(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, _ = _layout(root)
            record_ruling(working, rc8, reference, DAMPER, reason="owner")
            _write(rc8 / DAMPER, RC8_SYSTEM.replace("2", "3"))  # RC8's file changed after the approval
            with self.assertRaisesRegex(FixerError, "stale"):
                compute_fix(working, "vanilla-path-shadowing", _opts(rc8, reference))
            self.assertTrue((working / DAMPER).is_file())

    def test_a_revoked_approval_does_not_move(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, workspace = _layout(root)
            record_ruling(working, rc8, reference, DAMPER, reason="owner")
            record_ruling(working, rc8, reference, DAMPER, reason="changed my mind", revoke=True)
            apply_fix(compute_fix(working, "vanilla-path-shadowing", _opts(rc8, reference)))
            self.assertTrue((working / DAMPER).is_file())

    def test_an_approval_for_another_mod_does_not_apply(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, _ = _layout(root)
            (root / "ESCALATION_RULINGS.jsonl").write_text(json.dumps(
                {"finding": "vanilla-path-shadowing", "ruling": "approve-shadow-removal", "mods": ["Other"], "file": DAMPER,
                 "sha256": triage(working, rc8, reference)["shadows"][0]["hashes"]}) + "\n", encoding="utf-8")
            result = triage(working, rc8, reference, read_rulings(root / "ESCALATION_RULINGS.jsonl"))
        self.assertEqual({s["path"]: s["approval"] for s in result["shadows"]}, {DAMPER: "none", FLARE: "none"})

    def test_triage_sorts_identical_changed_and_missing_in_reference(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, reference, _ = _layout(root)
            _write(rc8 / "data/shipsystems/new.system", RC8_SYSTEM)  # only RC8 has it
            _write(working / "data/shipsystems/new.system", EDITED_SYSTEM)
            _write(working / "data/shipsystems/same_as_rc8.system", RC8_SYSTEM)
            _write(rc8 / "data/shipsystems/same_as_rc8.system", RC8_SYSTEM)  # not a shadow
            kinds = {s["path"]: s["kind"] for s in triage(working, rc8, reference)["shadows"]}
        self.assertEqual(kinds, {DAMPER: "identical", FLARE: "changed", "data/shipsystems/new.system": "no-reference"})

    def test_without_a_reference_core_the_fixer_behaves_as_before(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, _reference, _ = _layout(root)
            with self.assertRaises(FixerError):
                compute_fix(working, "vanilla-path-shadowing", {"vanilla_core": rc8, "repo_root": root / "empty-repo"})

    def test_a_local_reference_rig_manifest_does_not_reach_a_fixture_run(self) -> None:
        with resolved_temp_dir() as root:
            working, rc8, _reference, _ = _layout(root)
            local_repo = root / "local-repo"
            install = root / "LocalStarsector"
            (install / "starsector-core").mkdir(parents=True)
            registry = local_repo / "bridgeforge-state" / "reference-rigs"
            registry.mkdir(parents=True)
            (registry / "0.9a.json").write_text(json.dumps({"schema_version": 1, "mode": "REFERENCE_RIG", "install": str(install)}), encoding="utf-8")
            with self.assertRaises(FixerError):
                compute_fix(working, "vanilla-path-shadowing", {"vanilla_core": rc8, "repo_root": root / "empty-repo"})
            found = reference_core_for_game_version("0.9a-RC8", repo_root=local_repo)
        self.assertEqual(found, install / "starsector-core")  # the fake manifest is real only under its own repo root

    def test_reference_rig_is_found_by_the_mods_game_version(self) -> None:
        with resolved_temp_dir() as root:
            install = root / "Starsector9a"
            (install / "starsector-core").mkdir(parents=True)
            registry = root / "bridgeforge-state" / "reference-rigs"
            registry.mkdir(parents=True)
            (registry / "0.9a.json").write_text(json.dumps({"schema_version": 1, "mode": "REFERENCE_RIG", "install": str(install)}), encoding="utf-8")
            found = reference_core_for_game_version("0.9a-RC8", repo_root=root)
            near = reference_core_for_game_version("0.95a", repo_root=root)
        self.assertEqual(found, install / "starsector-core")
        self.assertIsNone(near)  # no nearest-version guess


if __name__ == "__main__":
    unittest.main()
