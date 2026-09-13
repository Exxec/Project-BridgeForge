"""Live run SK13-1d: SEEKER missions set 0.6-era personality ids ("suicidal"/"fearless") that RC8 lacks.

The officer's personality stayed null and the ship AI NPE'd in Ship.getPersonality on deploy -> Fatal.
"""

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.log_triage import triage_log
from bridgeforge.models import TargetProfile
from bridgeforge.scanner import _parse_class_file, scan_mod


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class_with_strings(this_name: str, strings: list[str], extra_utf8: list[str]) -> bytes:
    """A minimal class file whose constant pool holds the given string literals and extra Utf8 names."""
    pool = [_utf8(this_name), b"\x07" + struct.pack(">H", 1), _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3)]
    for value in strings:
        pool.append(_utf8(value))
        pool.append(b"\x08" + struct.pack(">H", len(pool)))  # String -> the Utf8 just added (1-based index)
    pool.extend(_utf8(value) for value in extra_utf8)
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    body += struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">HHHH", 0, 0, 0, 0)  # no interfaces/fields/methods/attributes
    return body


def _mod(root: Path, classes: dict[str, bytes], personalities_csv: str | None = None) -> Path:
    (root / "jars").mkdir(parents=True)
    (root / "mod_info.json").write_text(json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}), encoding="utf-8")
    with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
        for name, data in classes.items():
            archive.writestr(name, data)
    if personalities_csv is not None:
        (root / "data" / "characters").mkdir(parents=True)
        (root / "data" / "characters" / "personalities.csv").write_text(personalities_csv, encoding="utf-8")
    return root


def _findings(root: Path) -> list:
    return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "personality-id-unknown"]


class PersonalityIdTests(unittest.TestCase):
    def test_parser_reports_string_constants(self) -> None:
        info = _parse_class_file(_class_with_strings("data/M", ["suicidal", "hello"], ["setPersonality"]))
        self.assertEqual(info.string_constants, {"suicidal", "hello"})
        self.assertIn("setPersonality", info.utf8_values)

    def test_legacy_id_in_class_calling_set_personality_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory), {
                "data/missions/m/MissionDefinition.class": _class_with_strings("data/missions/m/MissionDefinition", ["suicidal", "fearless"], ["setPersonality"]),
            })
            findings = _findings(root)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].evidence, ["personality:fearless", "personality:suicidal"])
        self.assertEqual(findings[0].classification, "MANUAL")

    def test_briefing_text_and_classes_without_set_personality_are_clean(self) -> None:
        # Flu-X: "The infected are fearless" is briefing text, not an id; a bare "fearless" without setPersonality is unrelated.
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory), {
                "data/A.class": _class_with_strings("data/A", ["The infected are fearless", "reckless"], ["setPersonality"]),
                "data/B.class": _class_with_strings("data/B", ["fearless"], []),
            })
            self.assertEqual(_findings(root), [])

    def test_ids_the_mod_defines_itself_are_valid(self) -> None:
        # Vacuum ships its own personalities.csv with suicidal/fearless rows.
        csv_text = "id,name,desc,bravery\nsuicidal,Suicidal,x,10\nfearless,Fearless,x,10\n"
        with tempfile.TemporaryDirectory() as directory:
            root = _mod(Path(directory), {"data/M.class": _class_with_strings("data/M", ["suicidal"], ["setPersonality"])}, csv_text)
            (root / "src").mkdir()
            (root / "src" / "S.java").write_text('class S { void f(PersonAPI p) { p.setPersonality("fearless"); } }\n', encoding="utf-8")
            self.assertEqual(_findings(root), [])

    def test_source_unknown_id_is_flagged_but_comments_are_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "mod_info.json").write_text(json.dumps({"id": "fx"}), encoding="utf-8")
            (root / "src").mkdir()
            (root / "src" / "S.java").write_text(
                "class S { void f(PersonAPI p) {\n"
                '  p.setPersonality("aggressive");\n'
                '  p.setPersonality( "suicidal" );\n'
                '  // p.setPersonality("fearless");\n'
                "} }\n",
                encoding="utf-8",
            )
            self.assertEqual([f.evidence for f in _findings(root)], [["personality:suicidal"]])


class NullPersonalityTriageTests(unittest.TestCase):
    def test_null_personality_npe_gets_specific_fatal_rule(self) -> None:
        log = (
            '98765 [Thread-2] ERROR com.fs.starfarer.combat.CombatMain  - java.lang.NullPointerException: Cannot invoke '
            '"com.fs.starfarer.api.characters.PersonalityAPI.getId()" because the return value of '
            '"com.fs.starfarer.rpg.Person.getPersonality()" is null\n'
            'java.lang.NullPointerException: Cannot invoke "com.fs.starfarer.api.characters.PersonalityAPI.getId()" because '
            'the return value of "com.fs.starfarer.rpg.Person.getPersonality()" is null\n'
            "\tat com.fs.starfarer.combat.entities.Ship.getPersonality(Unknown Source)\n"
            "\tat com.fs.starfarer.combat.ai.BasicShipAI.<init>(Unknown Source)\n"
            "\tat com.fs.starfarer.combat.CombatFleetManager.deploy(Unknown Source)\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.log"
            path.write_text(log, encoding="utf-8")
            result = triage_log(path)
        self.assertEqual(result["counts"]["FATAL"], 1)
        self.assertEqual(result["fatal"][0]["matched_rule"], "Null officer personality (unknown personality id)")


if __name__ == "__main__":
    unittest.main()
