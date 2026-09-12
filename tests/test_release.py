from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.build_tag import apply_build_tag
from bridgeforge.release import release_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _u2(value: int) -> bytes:
    return value.to_bytes(2, "big")


def _build_minimal_class(this_name: str) -> bytes:
    constants: list[bytes] = []

    def add_utf8(text: str) -> int:
        raw = text.encode("utf-8")
        constants.append(bytes([1]) + _u2(len(raw)) + raw)
        return len(constants)

    def add_class(name_index: int) -> int:
        constants.append(bytes([7]) + _u2(name_index))
        return len(constants)

    this_index = add_class(add_utf8(this_name))
    super_index = add_class(add_utf8("java/lang/Object"))
    body = b"\xca\xfe\xba\xbe" + _u2(0) + _u2(61) + _u2(len(constants) + 1)
    for entry in constants:
        body += entry
    body += _u2(0x0021) + _u2(this_index) + _u2(super_index) + _u2(0) + _u2(0) + _u2(0) + _u2(0)
    return body


def _write_jar(path: Path, classes: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)


def _clean_fixture_mod(root: Path) -> None:
    """A mod with no findings at all, a jar matching its 'original', and no build tag yet."""
    _write(root / "mod_info.json", '{"id":"fixture_mod","name":"Fixture Mod","version":"1.0","jars":["jars/fixture.jar"]}')
    _write(root / "data" / "hulls" / "ship_data.csv", "id\nfixture_hull\n")
    _write_jar(root / "jars" / "fixture.jar", {"data/Fixture.class": _build_minimal_class("data/Fixture")})


def _write_empty_baseline(path: Path) -> None:
    _write(path, json.dumps({"findings": []}))


class ReleaseGateTests(unittest.TestCase):
    def test_d_series_release_gate_blocks_when_behavior_evidence_is_required_but_missing(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            baseline = root / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            result = release_mod(root, original=root / "jars" / "fixture.jar", baseline=baseline, out_dir=Path(out_dir), require_behavior_evidence=True)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("behavior", result["blocking_gates"])

    def test_release_note_lists_only_approved_expected_changes_by_build(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            baseline = root / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            diff = root / "behavior-diff.json"
            _write(diff, json.dumps({"schema_version": 1, "status": "PASS", "deltas": [], "counts": {}, "blocking_count": 0}))
            expected = root / "expected-changes.json"
            _write(expected, json.dumps({"schema_version": 1, "mod_id": "fixture_mod", "changes": [
                {"id": "EXP-FIX-001", "build": "r1", "layer": "runtime", "summary": "Approved behavior", "why": "Required fix", "links": {"test": ["TEST-ONE"]}, "match": {"observation": "x", "subject": "y", "change": "any"}, "status": "APPROVED", "approved_by": "owner", "approved_on": "2026-09-11"},
                {"id": "EXP-FIX-002", "build": "r2", "layer": "runtime", "summary": "Pending behavior", "why": "Not accepted", "links": {"risk": ["RISK-TWO"]}, "match": {"observation": "x", "subject": "z", "change": "any"}, "status": "PROPOSED"},
            ]}))
            result = release_mod(root, original=root / "jars" / "fixture.jar", baseline=baseline, out_dir=Path(out_dir), behavior_diff_path=diff, expected_changes_path=expected, require_behavior_evidence=True, apply=True)
            self.assertEqual(result["status"], "RELEASED")
            note = Path(result["release_note"]).read_text(encoding="utf-8")
            self.assertIn("## Changes from the original", note)
            self.assertIn("Approved behavior", note)
            self.assertNotIn("Pending behavior", note)

    def test_missing_build_tag_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            baseline = Path(mod_dir) / "baseline.json"
            _write_empty_baseline(baseline)
            original = root / "jars" / "fixture.jar"

            result = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir), apply=True)

            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("build_tag", result["blocking_gates"])
            self.assertEqual(result["written"], [])
            self.assertEqual(list(Path(out_dir).iterdir()), [])

    def test_new_manual_finding_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            baseline = Path(mod_dir) / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            # Introduce a MANUAL-classification finding: a hullmod script referencing a class that
            # is neither in source nor in the jar.
            _write(
                root / "data" / "hullmods" / "hull_mods.csv",
                "name,id,unlocked,hidden,cost_frigate,cost_dest,cost_cruiser,cost_capital,script,desc,sprite\n"
                "Fixture,fixture_hm,TRUE,,0,0,0,0,data.hullmods.FixtureMissing,,\n",
            )
            original = root / "jars" / "fixture.jar"

            result = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir), apply=True)

            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("scan", result["blocking_gates"])
            self.assertEqual(result["written"], [])

    def test_licence_local_only_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir, tempfile.TemporaryDirectory() as policy_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            _write(root / "mod_info.json", '{"id":"exigency","name":"Exigency","version":"1.0","jars":["jars/fixture.jar"]}')
            baseline = Path(mod_dir) / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            policy_path = Path(policy_dir) / "policy.json"
            _write(policy_path, json.dumps({"mods": {"exigency": {"local_only": True, "reason": "test policy"}}, "default": {"local_only": False}}))
            original = root / "jars" / "fixture.jar"

            result = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir), policy_path=policy_path, apply=True)

            self.assertEqual(result["status"], "BLOCKED")
            self.assertIn("licence", result["blocking_gates"])
            self.assertEqual(result["gates"]["licence"]["reason"], "test policy")
            self.assertEqual(result["written"], [])

    def test_dry_run_writes_nothing_even_when_all_gates_pass(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            baseline = Path(mod_dir) / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            original = root / "jars" / "fixture.jar"

            result = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir), apply=False)

            self.assertEqual(result["status"], "DRY_RUN_READY")
            self.assertEqual(result["blocking_gates"], [])
            self.assertEqual(result["written"], [])
            self.assertEqual(list(Path(out_dir).iterdir()), [])

    def test_apply_with_passing_gates_writes_forward_slash_zip_and_layout(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            baseline = Path(mod_dir) / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            original = root / "jars" / "fixture.jar"

            result = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir), apply=True)

            self.assertEqual(result["status"], "RELEASED")
            self.assertTrue(result["written"])
            zip_path = Path(result["zip_path"])
            self.assertTrue(zip_path.is_file())
            with zipfile.ZipFile(zip_path) as archive:
                names = archive.namelist()
                self.assertIn("jars/fixture.jar", names)
                self.assertIn("mod_info.json", names)
                for name in names:
                    self.assertNotIn("\\", name)
                    self.assertFalse(name.endswith(".bak"))
            release_dir = Path(result["release_dir"])
            self.assertTrue((release_dir / "jars" / "fixture.jar").is_file())
            self.assertTrue((release_dir / "mod_info.json").is_file())
            self.assertFalse((release_dir / "src").exists())
            note_path = Path(result["release_note"])
            self.assertTrue(note_path.is_file())
            self.assertIn("Fixture Mod", note_path.read_text(encoding="utf-8"))

    def test_jars_not_listed_in_mod_info_are_reported_and_not_shipped(self) -> None:
        # Real case: Omega-Trauma's jars/ holds Omega_Psychasthenia_old/_oldest/_oldish.jar that mod_info never loads.
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _clean_fixture_mod(root)
            _write_jar(root / "jars" / "fixture_old.jar", {"data/Old.class": _build_minimal_class("data/Old")})
            baseline = Path(mod_dir) / "baseline.json"
            _write_empty_baseline(baseline)
            apply_build_tag(root, record_manifest=False)
            original = root / "jars" / "fixture.jar"

            dry = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir))
            self.assertEqual(dry["excluded_unlisted_jars"], ["jars/fixture_old.jar"])

            result = release_mod(root, original=original, baseline=baseline, out_dir=Path(out_dir), apply=True)
            self.assertEqual(result["status"], "RELEASED")
            with zipfile.ZipFile(result["zip_path"]) as archive:
                names = archive.namelist()
            self.assertIn("jars/fixture.jar", names)
            self.assertNotIn("jars/fixture_old.jar", names)
            self.assertFalse((Path(result["release_dir"]) / "jars" / "fixture_old.jar").exists())


if __name__ == "__main__":
    unittest.main()
