"""Scanner false positives found processing the 2026-09-13 Chinese intake (Nightcross)."""

import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.models import TargetProfile
from bridgeforge.scanner import BUNDLED_LIBRARY_PACKAGE_PREFIXES, LIBRARY_DEPENDENCY_IDS, scan_mod


def _utf8(text: str) -> bytes:
    raw = text.encode("utf-8")
    return b"\x01" + struct.pack(">H", len(raw)) + raw


def _class(this_name: str, *, class_refs: tuple[str, ...] = (), strings: tuple[str, ...] = (), names: tuple[str, ...] = ()) -> bytes:
    pool = [_utf8(this_name), b"\x07" + struct.pack(">H", 1), _utf8("java/lang/Object"), b"\x07" + struct.pack(">H", 3)]
    for ref in class_refs:
        pool += [_utf8(ref), b"\x07" + struct.pack(">H", len(pool) + 1)]
    for value in strings:
        pool += [_utf8(value), b"\x08" + struct.pack(">H", len(pool) + 1)]
    pool += [_utf8(name) for name in names]
    body = b"\xca\xfe\xba\xbe" + struct.pack(">HH", 0, 52) + struct.pack(">H", len(pool) + 1) + b"".join(pool)
    return body + struct.pack(">HHH", 0x0021, 2, 4) + struct.pack(">HHHH", 0, 0, 0, 0)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


class WeaponSpecIdTests(unittest.TestCase):
    def test_wpn_is_matched_by_its_declared_id_not_its_filename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", json.dumps({"id": "fx"}))
            _write(root / "data" / "weapons" / "weapon_data.csv", "name,id\nCenter,fx_deco\n")
            _write(root / "data" / "weapons" / "fx_center.wpn", '{\n\t"id":"fx_deco",\n\t"type":"DECORATIVE",\n}\n')
            _write(root / "data" / "weapons" / "fx_orphan.wpn", '{"id":"fx_orphan"}')
            files = [f.file for f in scan_mod(root, TargetProfile()).findings if f.id == "local-weapon-spec-unregistered"]
        self.assertEqual(files, ["data/weapons/fx_orphan.wpn"])


class LooseScriptShadowTests(unittest.TestCase):
    def test_loose_script_with_a_jar_class_is_shadowed_not_a_janino_risk(self) -> None:
        # Mirfak ships data/hullmods/*.java AND the same classes in its jar; the game skips the loose copies.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}))
            risky = "class X { void f(java.util.List<String> l) { for (String s : l) {} } }\n"
            _write(root / "data" / "hullmods" / "InJar.java", risky)
            _write(root / "data" / "hullmods" / "LooseOnly.java", risky)
            (root / "jars").mkdir(parents=True)
            with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
                archive.writestr("data/hullmods/InJar.class", _class("data/hullmods/InJar"))
            findings = scan_mod(root, TargetProfile()).findings
        self.assertEqual([f.file for f in findings if f.id == "loose-script-janino-risk"], ["data/hullmods/LooseOnly.java"])
        shadow = [f for f in findings if f.id == "loose-script-shadowed-by-jar"]
        self.assertEqual(len(shadow), 1)
        self.assertEqual(shadow[0].evidence, ["count:1", "data/hullmods/InJar.java"])


class CrossModLooseScriptShadowTests(unittest.TestCase):
    """ROADMAP P14 item 12: a mod's loose script can also be shadowed by a *declared dependency's*
    jar, not just its own - found 2026-09-20 on Maelstrom Interstellar Imperium Unofficial
    Expansion (escalation E8): its Titan scripts duplicate classes the base mod's own II.jar
    already supplies, so the override silently had no effect. All mod jars share one classloader.
    """

    def _base_mod(self, root: Path, class_name: str) -> Path:
        base = root / "providers" / "basemod"
        _write(base / "mod_info.json", json.dumps({"id": "basemod", "name": "Base Mod"}))
        (base / "jars").mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(base / "jars" / "base.jar", "w") as archive:
            archive.writestr(f"{class_name.replace('.', '/')}.class", _class(class_name.replace(".", "/")))
        return base

    def test_a_loose_script_shadowed_by_a_declared_dependencys_jar_is_flagged_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._base_mod(root, "data.scripts.hullmods.Shared")
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "addon", "name": "Addon", "dependencies": [{"id": "basemod"}]}))
            _write(mod / "data" / "scripts" / "hullmods" / "Shared.java", "package data.scripts.hullmods;\nclass Shared {}\n")
            findings = scan_mod(mod, TargetProfile(), provider_roots=[root / "providers"]).findings
        shadow = [f for f in findings if f.id == "loose-script-shadowed-by-dependency-jar"]
        self.assertEqual(len(shadow), 1)
        self.assertEqual(shadow[0].classification, "MANUAL")
        self.assertEqual(shadow[0].file, "data/scripts/hullmods/Shared.java")
        self.assertIn("shadowed by: Base Mod", shadow[0].evidence)
        # The shadowed script's own janino-risk (if any) is suppressed the same way the same-mod case is.
        self.assertEqual([f for f in findings if f.id == "loose-script-janino-risk"], [])

    def test_an_undeclared_mod_sharing_a_class_name_is_not_flagged(self) -> None:
        # Only a DECLARED dependency's jar counts - an undeclared mod happening to share a class
        # name is a coincidence this check must not guess at.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._base_mod(root, "data.scripts.hullmods.Shared")
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "addon", "name": "Addon"}))  # no dependencies declared
            _write(mod / "data" / "scripts" / "hullmods" / "Shared.java", "package data.scripts.hullmods;\nclass Shared {}\n")
            findings = scan_mod(mod, TargetProfile(), provider_roots=[root / "providers"]).findings
        self.assertEqual([f for f in findings if f.id == "loose-script-shadowed-by-dependency-jar"], [])

    def test_own_jar_shadow_takes_precedence_over_dependency_shadow(self) -> None:
        # If the mod's OWN jar also supplies the class, that's still loose-script-shadowed-by-jar
        # (SAFE, item 14's existing case) - not double-reported as the dependency variant too.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._base_mod(root, "data.scripts.hullmods.Shared")
            mod = root / "mod"
            _write(mod / "mod_info.json", json.dumps({"id": "addon", "name": "Addon", "jars": ["jars/addon.jar"], "dependencies": [{"id": "basemod"}]}))
            (mod / "jars").mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(mod / "jars" / "addon.jar", "w") as archive:
                archive.writestr("data/scripts/hullmods/Shared.class", _class("data/scripts/hullmods/Shared"))
            _write(mod / "data" / "scripts" / "hullmods" / "Shared.java", "package data.scripts.hullmods;\nclass Shared {}\n")
            findings = scan_mod(mod, TargetProfile(), provider_roots=[root / "providers"]).findings
        self.assertEqual([f for f in findings if f.id == "loose-script-shadowed-by-dependency-jar"], [])
        self.assertEqual(len([f for f in findings if f.id == "loose-script-shadowed-by-jar"]), 1)


class VanillaWeaponOverrideTests(unittest.TestCase):
    def test_wpn_overriding_a_vanilla_weapon_is_not_unregistered(self) -> None:
        # Blackrock ships blinker_green.wpn, a deliberate override of vanilla's weapon of the same id.
        with tempfile.TemporaryDirectory() as directory:
            root, core = Path(directory) / "mod", Path(directory) / "core"
            _write(root / "mod_info.json", json.dumps({"id": "fx"}))
            _write(root / "data" / "weapons" / "weapon_data.csv", "name,id\n")
            _write(root / "data" / "weapons" / "blinker_green.wpn", '{"id":"blinker_green"}')
            _write(root / "data" / "weapons" / "fx_orphan.wpn", '{"id":"fx_orphan"}')
            _write(core / "data" / "weapons" / "weapon_data.csv", "name,id\nBlinker,blinker_green\n")
            with_core = [f.file for f in scan_mod(root, TargetProfile(), vanilla_core=core).findings if f.id == "local-weapon-spec-unregistered"]
            without_core = [f.file for f in scan_mod(root, TargetProfile()).findings if f.id == "local-weapon-spec-unregistered"]
        self.assertEqual(with_core, ["data/weapons/fx_orphan.wpn"])
        self.assertEqual(sorted(without_core), ["data/weapons/blinker_green.wpn", "data/weapons/fx_orphan.wpn"])


class OwnClassImportTests(unittest.TestCase):
    def test_import_of_the_mods_own_class_in_a_library_package_is_not_external(self) -> None:
        # Blackrock ships data.scripts.util.BRDYMulti itself; MagicLib's legacy package is data.scripts.util.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", json.dumps({"id": "fx"}))
            _write(root / "src" / "data" / "scripts" / "util" / "BRDYMulti.java", "package data.scripts.util;\npublic class BRDYMulti {}\n")
            _write(root / "src" / "data" / "scripts" / "Own.java", "package data.scripts;\nimport data.scripts.util.BRDYMulti;\npublic class Own {}\n")
            own_only = [f for f in scan_mod(root, TargetProfile()).findings if f.id == "external-mod-api-import"]
            _write(root / "src" / "data" / "scripts" / "Lib.java", "package data.scripts;\nimport data.scripts.util.MagicCampaign;\npublic class Lib {}\n")
            with_library = [f for f in scan_mod(root, TargetProfile()).findings if f.id == "external-mod-api-import"]
        self.assertEqual(own_only, [])
        self.assertEqual(len(with_library), 1)
        self.assertIn("data.scripts.util.MagicCampaign", with_library[0].evidence)
        self.assertNotIn("data.scripts.util.BRDYMulti", with_library[0].evidence)


class BytecodeDependencyGuardTests(unittest.TestCase):
    def _mod(self, root: Path, with_guard: bool) -> list:
        library = "LazyLib"
        prefix = BUNDLED_LIBRARY_PACKAGE_PREFIXES[library][0]
        _write(root / "mod_info.json", json.dumps({"id": "fx", "jars": ["jars/fx.jar"]}))
        classes = {"data/Uses.class": _class("data/Uses", class_refs=(prefix.rstrip("/") + "/MathUtils",))}
        if with_guard:
            classes["data/Plugin.class"] = _class("data/Plugin", strings=(LIBRARY_DEPENDENCY_IDS[library],), names=("isModEnabled",))
        (root / "jars").mkdir(parents=True)
        with zipfile.ZipFile(root / "jars" / "fx.jar", "w") as archive:
            for name, data in classes.items():
                archive.writestr(name, data)
        return [f for f in scan_mod(root, TargetProfile()).findings if f.id == "undeclared-library-dependency" and f"library:{library}" in f.evidence]

    def test_unguarded_bytecode_reference_is_review_by_owner_ruling(self) -> None:
        # Owner ruling 2026-09-27: declaring the library is the fix, so REVIEW with a standing approval.
        with tempfile.TemporaryDirectory() as directory:
            findings = self._mod(Path(directory), with_guard=False)
        self.assertEqual([f.classification for f in findings], ["REVIEW"])

    def test_class_checking_the_mod_id_marks_it_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            findings = self._mod(Path(directory), with_guard=True)
        self.assertEqual([f.classification for f in findings], ["REVIEW"])


if __name__ == "__main__":
    unittest.main()
