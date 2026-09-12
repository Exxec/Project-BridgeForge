from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bridgeforge.dossier import DossierError, build_dossier, write_dossier


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_mod(root: Path, missing_classes: int = 3) -> None:
    """A tiny mod whose hull_mods.csv names classes that do not exist, which yields MANUAL findings."""
    _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture [BF r2]","version":"1.0+bf.2","gameVersion":"0.98a-RC8"}')
    rows = "".join(
        f"Fixture {n},fixture_hm_{n},TRUE,,0,0,0,0,data.hullmods.FixtureMissing{n},,\n" for n in range(missing_classes)
    )
    _write(
        root / "data" / "hullmods" / "hull_mods.csv",
        "name,id,unlocked,hidden,cost_frigate,cost_dest,cost_cruiser,cost_capital,script,desc,sprite\n" + rows,
    )
    _write(
        root / "data" / "hulls" / "wing_data.csv",
        "id,variant,tags,tier,rarity,fleet pts,op cost,formation,range,attack run range,num,refit,base value,role,role desc\n"
        "fixture_wing,fixture_variant,,0,,1,5,V,4000,,2,5,1000,ASSAULT,Fixture\n",
    )


def _finding_parts(result: dict) -> list[list[dict]]:
    """Findings per part, skipping parts that carry other content (e.g. an inventory moved out of the index)."""
    parts = [json.loads(part["json_text"]) for part in result["parts"]]
    return [payload["findings"] for payload in parts if "findings" in payload]


def _all_part_findings(result: dict) -> list[dict]:
    return [entry for part in _finding_parts(result) for entry in part]


class DossierTests(unittest.TestCase):
    def test_minimal_mod_writes_index_and_parts_with_all_sections(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            written = write_dossier(root, Path(out_dir) / "dossier-out")
            index = json.loads(Path(written["index_json"]).read_text(encoding="utf-8"))
            for key in ("dossier_version", "identity", "inventory", "finding_counts", "open_questions", "parts", "artifacts"):
                self.assertIn(key, index)
            self.assertEqual(index["identity"]["id"], "fixture")
            self.assertTrue(Path(written["index_markdown"]).is_file())
            self.assertGreaterEqual(len(written["parts"]), 1)
            for artifact in ("jar_audit", "copy_drift", "log_triage"):
                self.assertTrue(index["artifacts"][artifact].get("not_supplied"))

    def test_fixer_availability_is_reported_per_finding(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            findings = _all_part_findings(build_dossier(root))
            by_id = {entry["id"]: entry for entry in findings}
            self.assertTrue(by_id["wing-role-assault-removed"]["fixer_available"])
            self.assertFalse(by_id["data-class-reference-missing"]["fixer_available"])

    def test_cap_splits_into_parts_without_losing_findings(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root, missing_classes=40)
            full = build_dossier(root, max_kb=1000)
            split = build_dossier(root, max_kb=3)
            self.assertGreaterEqual(len(split["parts"]), 2)
            for part in split["parts"]:
                self.assertLessEqual(part["size_bytes"], 3 * 1024)
            key = lambda entry: (entry["id"], entry.get("file"), tuple(entry.get("evidence") or []))
            self.assertEqual(sorted(map(key, _all_part_findings(full))), sorted(map(key, _all_part_findings(split))))

    def test_manual_findings_land_in_first_part(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root, missing_classes=40)
            result = build_dossier(root, max_kb=3)
            classifications = [[entry["classification"] for entry in part] for part in _finding_parts(result)]
            self.assertIn("MANUAL", classifications[0])
            first_non_manual = next(
                (n for n, part in enumerate(classifications) if any(c != "MANUAL" for c in part)), len(classifications)
            )
            for later in classifications[first_non_manual + 1:]:
                self.assertNotIn("MANUAL", later)

    def test_index_manifest_matches_parts_on_disk_and_stale_parts_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            output = Path(out_dir) / "d"
            _fixture_mod(root, missing_classes=40)
            write_dossier(root, output, max_kb=3)
            many = sorted(p.name for p in output.glob("dossier.part-*.json"))
            self.assertGreaterEqual(len(many), 2)
            written = write_dossier(root, output, max_kb=1000)
            on_disk = sorted(p.name for p in output.glob("dossier.part-*.json"))
            index = json.loads(Path(written["index_json"]).read_text(encoding="utf-8"))
            manifest_files = sorted(entry["json_file"] for entry in index["parts"])
            self.assertEqual(on_disk, manifest_files)
            self.assertLess(len(on_disk), len(many))

    def test_output_is_deterministic_apart_from_generated_at(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root, missing_classes=10)
            first, second = build_dossier(root, max_kb=4), build_dossier(root, max_kb=4)
            self.assertEqual([p["json_text"] for p in first["parts"]], [p["json_text"] for p in second["parts"]])
            strip = lambda index: {k: v for k, v in index.items() if k != "generated_at"}
            self.assertEqual(strip(first["index"]), strip(second["index"]))

    def test_refuses_protected_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as out_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            with self.assertRaises(DossierError):
                write_dossier(root, Path(out_dir) / "In operation" / "x")

    def test_noise_findings_are_excluded_from_open_questions_but_stay_in_parts(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            # A trailing comma (non-strict-json-trailing-comma, REVIEW/medium "retain unchanged")
            # plus a # comment (json-hash-comment, SAFE/info) in the same non-mod_info JSON file.
            _write(root / "data" / "config" / "settings.json", '{\n  # a comment\n  "value": 1,\n}\n')
            result = build_dossier(root)
            noise_ids = {"non-strict-json-trailing-comma", "json-hash-comment"}
            open_question_text = "\n".join(result["index"]["open_questions"])
            for noisy_id in noise_ids:
                self.assertNotIn(noisy_id, open_question_text)
            part_ids = {entry["id"] for entry in _all_part_findings(result)}
            for noisy_id in noise_ids:
                self.assertIn(noisy_id, part_ids)

    def test_repeated_finding_id_across_many_files_collapses_to_one_open_question(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _fixture_mod(root)
            # json-encoding-unverified is REVIEW/medium, not fixer-available, and not noise, so it
            # is a legitimate collapse candidate. Four distinct files trigger the "+1 more" path.
            for n in range(4):
                _write(root / "data" / "config" / f"bad{n}.json", "placeholder")
                (root / "data" / "config" / f"bad{n}.json").write_bytes(b'{"name":"\x92bad"}')
            result = build_dossier(root)
            open_questions = result["index"]["open_questions"]
            collapsed = [q for q in open_questions if q.startswith("json-encoding-unverified")]
            self.assertEqual(len(collapsed), 1)
            self.assertIn("×4 files", collapsed[0])
            self.assertIn("+1 more", collapsed[0])
            per_file_lines = [q for q in open_questions if q.startswith("json-encoding-unverified at ")]
            self.assertEqual(per_file_lines, [])
            part_count = sum(1 for entry in _all_part_findings(result) if entry["id"] == "json-encoding-unverified")
            self.assertEqual(part_count, 4)

    def test_index_markdown_has_no_python_dict_or_list_reprs(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", json.dumps({"id": "fixture", "name": "Fixture", "version": "1.0", "gameVersion": "0.98a-RC8", "dependencies": [{"id": "MagicLib", "name": "MagicLib", "version": "0.42"}], "jars": ["jars/fixture.jar"]}))
            _write(
                root / "data" / "world" / "factions" / "fixture.faction",
                json.dumps({"id": "fixture_faction", "knownShips": ["hull1"], "shipRoles": {"combat": {"hull1": 1}}}),
            )
            result = build_dossier(root)
            markdown = result["index_markdown"]
            self.assertNotIn("{'", markdown)
            self.assertNotIn("['", markdown)

    def test_external_mod_api_import_finding_carries_a_file(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir:
            root = Path(mod_dir)
            _write(root / "mod_info.json", '{"id":"fixture","name":"Fixture"}')
            _write(
                root / "src" / "Example.java",
                "import data.scripts.util.MagicRender; class Example {}",
            )
            result = build_dossier(root)
            entries = [e for e in _all_part_findings(result) if e["id"] == "external-mod-api-import"]
            self.assertTrue(entries)
            for entry in entries:
                self.assertIsNotNone(entry["file"])


if __name__ == "__main__":
    unittest.main()
