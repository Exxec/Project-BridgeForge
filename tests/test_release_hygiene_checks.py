"""Checks added from the 2026-09-13 Flu-X / translation work: jar CRC, archaeology output folder,
stale report dependency claims, release junk, non-English text and designTypeColors consistency."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.behavior_discovery import write_archaeology
from bridgeforge.copy_drift import _collect
from bridgeforge.models import TargetProfile
from bridgeforge.revival_audit import REQUIRED_VALIDATIONS, audit_revival
from bridgeforge.scanner import scan_mod


def _mod(root: Path, **mod_info) -> Path:
    mod = root / "mod"
    mod.mkdir(parents=True, exist_ok=True)
    info = {"id": "fx", "name": "fx", "version": "1", "gameVersion": "0.98a-RC8", **mod_info}
    (mod / "mod_info.json").write_text(json.dumps(info), encoding="utf-8")
    return mod


def _ids(result, finding_id: str) -> list:
    return [f for f in result.findings if f.id == finding_id]


class JarCrcTests(unittest.TestCase):
    def test_bad_crc_entry_is_named_and_the_rest_of_the_jar_is_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory), jars=["jars/x.jar"])
            jar = mod / "jars" / "x.jar"
            jar.parent.mkdir()
            good_class = b"\xca\xfe\xba\xbe\x00\x00\x00\x34" + b"\x00" * 8
            with zipfile.ZipFile(jar, "w", zipfile.ZIP_STORED) as archive:
                archive.writestr("a/Good.class", good_class)
                archive.writestr("a/strings.txt", b"CORRUPT-ME-PLEASE")
            raw = jar.read_bytes()
            jar.write_bytes(raw.replace(b"CORRUPT-ME-PLEASE", b"CORRUPT-ME-PLEASX"))  # data changes, stored CRC doesn't
            result = scan_mod(mod, TargetProfile())
        bad = _ids(result, "jar-entry-unreadable")
        self.assertEqual(len(bad), 1)
        self.assertIn("a/strings.txt", bad[0].evidence[0])
        self.assertEqual(_ids(result, "unreadable-jar"), [])
        self.assertIn("a.Good", result.compiled_class_names)


class ArchaeologyOutputTests(unittest.TestCase):
    def test_passing_the_archaeology_folder_itself_does_not_nest_another(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root)
            written = write_archaeology(mod, root / "discovery" / "archaeology")
            self.assertEqual(Path(written["architecture"]), (root / "discovery" / "archaeology" / "architecture.json").resolve())
            self.assertFalse((root / "discovery" / "archaeology" / "archaeology").exists())


class RevivalAuditDependencyClaimTests(unittest.TestCase):
    CLAIM = "PASS (LazyLib, MagicLib present and declared; Nex optional, loads with and without)"

    def _candidate(self, root: Path, dependencies: list, claim: str = CLAIM) -> Path:
        mod = _mod(root, dependencies=dependencies)
        reports = mod / "reports"
        reports.mkdir()
        lines = ["# Report", ""]
        for label in REQUIRED_VALIDATIONS:
            value = claim if label == "DEPENDENCY CHECK" else "PASS"
            lines.append(f"- {label} — {value}")
        lines += ["", "**READY**"]
        (reports / "REVIVAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (reports / "REVIVAL_PLAN.md").write_text("# Plan\n", encoding="utf-8")
        return mod

    def test_report_claiming_libraries_mod_info_dropped_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = audit_revival(self._candidate(Path(directory), []))
        stale = [issue for issue in audit["issues"] if issue["id"] == "dependency-claim-stale"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["evidence"], ["LazyLib", "MagicLib"])  # Nexerelin is called optional: not claimed

    def test_history_of_a_removal_is_not_a_claim(self) -> None:
        # Flu-X r3's updated wording.
        claim = "PASS (no required dependencies since r3: LazyLib and MagicLib were declared by the revival but never used, and were removed on owner request; Nex optional)"
        with tempfile.TemporaryDirectory() as directory:
            audit = audit_revival(self._candidate(Path(directory), [], claim))
        self.assertFalse([issue for issue in audit["issues"] if issue["id"] == "dependency-claim-stale"])

    def test_not_performed_is_not_read_as_done(self) -> None:
        # Zorg18 r1: an unticked plan box beside "NOT PERFORMED" was reported as stale.
        with tempfile.TemporaryDirectory() as directory:
            mod = self._candidate(Path(directory), [])
            report = (mod / "reports" / "REVIVAL_REPORT.md").read_text(encoding="utf-8")
            report = report.replace("- LIVE STARSECTOR TEST — PASS", "- LIVE STARSECTOR TEST — NOT PERFORMED (tests pending)")
            (mod / "reports" / "REVIVAL_REPORT.md").write_text(report, encoding="utf-8")
            (mod / "reports" / "REVIVAL_PLAN.md").write_text("# Plan\n- [ ] LIVE STARSECTOR TEST\n- [ ] COMPILE\n", encoding="utf-8")
            audit = audit_revival(mod)
        stale = [issue["evidence"][0] for issue in audit["issues"] if issue["id"] == "plan-validation-state-stale"]
        self.assertEqual(stale, ["COMPILE"])  # COMPILE says PASS but is unticked; LIVE is honestly not done

    def test_claims_matching_mod_info_are_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit = audit_revival(self._candidate(Path(directory), [{"id": "lw_lazylib", "name": "LazyLib"}, {"id": "MagicLib", "name": "MagicLib"}]))
        self.assertFalse([issue for issue in audit["issues"] if issue["id"] == "dependency-claim-stale"])


class ReleaseJunkTests(unittest.TestCase):
    def test_os_litter_never_ships_and_work_files_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            graphics = mod / "graphics" / "ships"
            graphics.mkdir(parents=True)
            for name in ("ship.png", "ship.psd", "Thumbs.db", "notes.txt~"):
                (graphics / name).write_bytes(b"x")
            (mod / "graphics" / "__MACOSX").mkdir()
            (mod / "graphics" / "__MACOSX" / "ship.png").write_bytes(b"x")
            shipped = set(_collect(mod))
            result = scan_mod(mod, TargetProfile())
        self.assertIn("graphics/ships/ship.png", shipped)
        self.assertNotIn("graphics/ships/Thumbs.db", shipped)
        self.assertNotIn("graphics/__MACOSX/ship.png", shipped)
        work = _ids(result, "shippable-work-file")
        self.assertEqual(len(work), 1)
        self.assertEqual(work[0].evidence, ["graphics/ships/notes.txt~", "graphics/ships/ship.psd"])


class NonEnglishTextTests(unittest.TestCase):
    def test_cjk_outside_comments_is_counted_per_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mod = _mod(Path(directory))
            strings = mod / "data" / "strings"
            strings.mkdir(parents=True)
            (strings / "descriptions.csv").write_text("id,type,text1\n# 注释,,\nfx_a,SHIP,护卫舰\n", encoding="utf-8")
            (strings / "english.csv").write_text("id,type,text1\nfx_b,SHIP,Frigate\n", encoding="utf-8")
            result = scan_mod(mod, TargetProfile())
        text = _ids(result, "player-text-non-english")
        self.assertEqual(len(text), 1)
        self.assertEqual(text[0].evidence, ["data/strings/descriptions.csv: 3"])


class DesignTypeColorTests(unittest.TestCase):
    def test_duplicate_unused_and_uncoloured_design_types(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod = _mod(root)
            (mod / "data" / "config").mkdir(parents=True)
            (mod / "data" / "config" / "settings.json").write_text('{\n  "designTypeColors": {\n    "Infected": [200,70,70,255],\n    # a comment "Ghost": [1,1,1,1]\n    "Infected": [1,2,3,255],\n    "黑岩": [9,9,9,255],\n    "Common": [5,5,5,255]\n  }\n}\n', encoding="utf-8")
            (mod / "data" / "hulls").mkdir(parents=True)
            (mod / "data" / "hulls" / "ship_data.csv").write_text("name,id,tech/manufacturer\nA,fx_a,Infected\nB,fx_b,Blackrock\nC,fx_c,Low Tech\n", encoding="utf-8")
            core = root / "core" / "data" / "config"
            core.mkdir(parents=True)
            (core / "settings.json").write_text('{"designTypeColors": {"Low Tech": [1,1,1,255], "Common": [2,2,2,255]}}', encoding="utf-8")
            with_vanilla = scan_mod(mod, TargetProfile(), root / "core")
            without_vanilla = scan_mod(mod, TargetProfile())
        self.assertEqual(_ids(with_vanilla, "design-type-color-duplicate-key")[0].evidence, ["Infected"])
        self.assertEqual(_ids(with_vanilla, "design-type-color-unused")[0].evidence, ["黑岩"])  # Common overrides vanilla: fine
        self.assertEqual(_ids(with_vanilla, "design-type-without-color")[0].evidence, ["Blackrock"])
        self.assertEqual(_ids(without_vanilla, "design-type-without-color"), [])
        self.assertEqual(_ids(without_vanilla, "design-type-color-unused")[0].evidence, ["Common", "黑岩"])


if __name__ == "__main__":
    unittest.main()
