from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _findings(result, finding_id: str):
    return [item for item in result.findings if item.id == finding_id]


def _u2(value: int) -> bytes:
    return value.to_bytes(2, "big")


def _u4(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _utf8_entry(text: str) -> bytes:
    encoded = text.encode("utf-8")
    return b"\x01" + _u2(len(encoded)) + encoded


def _class_entry(name_index: int) -> bytes:
    return b"\x07" + _u2(name_index)


def build_class_file(
    this_class: str,
    super_class: str = "java/lang/Object",
    extra_class_refs: tuple[str, ...] = (),
    methods: tuple[tuple[str, str, bool], ...] = (),
) -> bytes:
    """Build a minimal well-formed .class file for constant-pool-based tests.

    extra_class_refs become CONSTANT_Class entries in the pool (what a real
    class emits when it references, casts to, calls a method on, or catches
    that type). methods become the class's declared method_info entries as
    (name, descriptor, is_public).
    """
    pool: list[bytes] = []

    def add_utf8(text: str) -> int:
        pool.append(_utf8_entry(text))
        return len(pool)

    def add_class(name_index: int) -> int:
        pool.append(_class_entry(name_index))
        return len(pool)

    this_class_idx = add_class(add_utf8(this_class))
    super_class_idx = add_class(add_utf8(super_class))
    for ref in extra_class_refs:
        add_class(add_utf8(ref))

    method_entries: list[bytes] = []
    for name, descriptor, is_public in methods:
        name_idx = add_utf8(name)
        desc_idx = add_utf8(descriptor)
        access = 0x0001 if is_public else 0x0000
        method_entries.append(_u2(access) + _u2(name_idx) + _u2(desc_idx) + _u2(0))

    constant_pool_count = len(pool) + 1
    data = b"\xca\xfe\xba\xbe" + _u2(0) + _u2(52) + _u2(constant_pool_count)
    data += b"".join(pool)
    data += _u2(0x0021)  # access_flags: public + super
    data += _u2(this_class_idx)
    data += _u2(super_class_idx)
    data += _u2(0)  # interfaces_count
    data += _u2(0)  # fields_count
    data += _u2(len(method_entries))
    data += b"".join(method_entries)
    data += _u2(0)  # class attributes_count
    return data


def write_jar(path: Path, members: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in members.items():
            archive.writestr(member, content)


class ScriptSandboxForbiddenApiTests(unittest.TestCase):
    def test_jar_class_referencing_reflect_method_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file(
                "exi/MyPlugin",
                extra_class_refs=("java/lang/reflect/Method",),
            )
            write_jar(root / "jars" / "EXI.jar", {"exi/MyPlugin.class": class_bytes})
            result = scan_mod(root)
            findings = _findings(result, "script-sandbox-forbidden-api")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertIn("class:exi.MyPlugin", findings[0].evidence)
            self.assertIn("forbidden:java.lang.reflect.Method", findings[0].evidence)

    def test_jar_class_referencing_file_io_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file(
                "exi/Loader",
                extra_class_refs=("java/io/FileInputStream",),
            )
            write_jar(root / "jars" / "EXI.jar", {"exi/Loader.class": class_bytes})
            result = scan_mod(root)
            findings = _findings(result, "script-sandbox-forbidden-api")
            self.assertEqual(len(findings), 1)
            self.assertIn("forbidden:java.io.FileInputStream", findings[0].evidence)

    def test_reflective_operation_exception_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file(
                "exi/Safe",
                extra_class_refs=("java/lang/ReflectiveOperationException",),
            )
            write_jar(root / "jars" / "EXI.jar", {"exi/Safe.class": class_bytes})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "script-sandbox-forbidden-api"), [])

    def test_io_exception_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file(
                "exi/Safe2",
                extra_class_refs=("java/io/IOException",),
            )
            write_jar(root / "jars" / "EXI.jar", {"exi/Safe2.class": class_bytes})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "script-sandbox-forbidden-api"), [])

    def test_loose_source_referencing_nio_file_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "scripts" / "Boot.java",
                "package data.scripts;\nimport java.nio.file.Files;\nclass Boot { void go() { Files.exists(null); } }",
            )
            result = scan_mod(root)
            findings = _findings(result, "script-sandbox-forbidden-api")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertIn("data/scripts/Boot.java", findings[0].file)

    def test_loose_source_with_no_forbidden_reference_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(
                root / "data" / "scripts" / "Boot.java",
                "package data.scripts;\nimport java.io.IOException;\nclass Boot { void go() throws IOException {} }",
            )
            result = scan_mod(root)
            self.assertEqual(_findings(result, "script-sandbox-forbidden-api"), [])


class BundledLibraryClassesTests(unittest.TestCase):
    def test_graphicslib_classes_in_own_jar_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file("org/dark/shaders/light/LightData")
            write_jar(root / "jars" / "EXI.jar", {"org/dark/shaders/light/LightData.class": class_bytes})
            result = scan_mod(root)
            findings = _findings(result, "bundled-library-classes")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertIn("library:GraphicsLib", findings[0].evidence)
            self.assertIn("class-count:1", findings[0].evidence)

    def test_jar_with_no_library_packages_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file("exi/MyOwnClass")
            write_jar(root / "jars" / "EXI.jar", {"exi/MyOwnClass.class": class_bytes})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "bundled-library-classes"), [])


class LoadedJarScopeTests(unittest.TestCase):
    """Bytecode checks read only jars Starsector loads; FlowerGod's build/cp cache once produced ~9600 false findings."""

    def test_build_output_jars_are_ignored_without_mod_info(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lib = build_class_file("org/dark/shaders/light/LightData")
            write_jar(root / "build" / "cp" / "Graphics.jar", {"org/dark/shaders/light/LightData.class": lib})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "bundled-library-classes"), [])

    def test_only_mod_info_declared_jars_are_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","jars":["jars/main.jar"],}')
            write_jar(root / "jars" / "main.jar", {"fixture/Main.class": build_class_file("fixture/Main")})
            reflective = build_class_file("fixture/Old", extra_class_refs=("java/lang/reflect/Field",))
            write_jar(root / "jars" / "main_old.jar", {"fixture/Old.class": reflective})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "script-sandbox-forbidden-api"), [])

    def test_declared_jar_is_still_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture","jars":["jars/main.jar"]}')
            reflective = build_class_file("fixture/Main", extra_class_refs=("java/lang/reflect/Field",))
            write_jar(root / "jars" / "main.jar", {"fixture/Main.class": reflective})
            result = scan_mod(root)
            self.assertEqual(len(_findings(result, "script-sandbox-forbidden-api")), 1)


class VanillaClassDuplicatedTests(unittest.TestCase):
    def test_mod_copy_missing_vanilla_public_method_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            vanilla_class = build_class_file(
                "com/fs/starfarer/api/campaign/CargoAPI",
                methods=(("addCommodity", "(Ljava/lang/String;F)V", True), ("newMethodRC8", "()V", True)),
            )
            write_jar(vanilla / "starfarer.api.jar", {"com/fs/starfarer/api/campaign/CargoAPI.class": vanilla_class})
            mod_class = build_class_file(
                "com/fs/starfarer/api/campaign/CargoAPI",
                methods=(("addCommodity", "(Ljava/lang/String;F)V", True),),
            )
            write_jar(root / "jars" / "Omega.jar", {"com/fs/starfarer/api/campaign/CargoAPI.class": mod_class})
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-class-duplicated-in-jar")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")
            self.assertIn("missing-public-method:newMethodRC8()V", findings[0].evidence)

    def test_mod_copy_with_all_public_methods_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            vanilla_class = build_class_file(
                "com/fs/starfarer/api/campaign/CargoAPI",
                methods=(("addCommodity", "(Ljava/lang/String;F)V", True),),
            )
            write_jar(vanilla / "starfarer.api.jar", {"com/fs/starfarer/api/campaign/CargoAPI.class": vanilla_class})
            mod_class = build_class_file(
                "com/fs/starfarer/api/campaign/CargoAPI",
                methods=(("addCommodity", "(Ljava/lang/String;F)V", True),),
            )
            write_jar(root / "jars" / "Omega.jar", {"com/fs/starfarer/api/campaign/CargoAPI.class": mod_class})
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-class-duplicated-in-jar")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_loose_script_duplicate_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(
                vanilla / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java",
                "package data.scripts.plugins;\nclass LevelupPluginImpl {}",
            )
            mod_class = build_class_file("data/scripts/plugins/LevelupPluginImpl")
            write_jar(root / "jars" / "EdmundChurch.jar", {"data/scripts/plugins/LevelupPluginImpl.class": mod_class})
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-class-duplicated-in-jar")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("vanilla-source:loose-script", findings[0].evidence)

    def test_new_rulecmd_class_not_in_vanilla_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            unrelated_vanilla = build_class_file("com/fs/starfarer/api/campaign/CargoAPI")
            write_jar(vanilla / "starfarer.api.jar", {"com/fs/starfarer/api/campaign/CargoAPI.class": unrelated_vanilla})
            mod_class = build_class_file("com/fs/starfarer/api/impl/campaign/rulecmd/MyNewCommand")
            write_jar(root / "jars" / "FlowerGod.jar", {"com/fs/starfarer/api/impl/campaign/rulecmd/MyNewCommand.class": mod_class})
            result = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(result, "vanilla-class-duplicated-in-jar"), [])

    def test_no_vanilla_core_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mod_class = build_class_file("com/fs/starfarer/api/campaign/CargoAPI")
            write_jar(root / "jars" / "Omega.jar", {"com/fs/starfarer/api/campaign/CargoAPI.class": mod_class})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "vanilla-class-duplicated-in-jar"), [])


class ObfuscatedInternalApiUseTests(unittest.TestCase):
    def test_internal_class_reference_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file(
                "exi/MissileScript",
                extra_class_refs=("com/fs/starfarer/combat/entities/Missile", "com/fs/starfarer/api/combat/ShipAPI"),
            )
            write_jar(root / "jars" / "EXI.jar", {"exi/MissileScript.class": class_bytes})
            result = scan_mod(root)
            findings = _findings(result, "obfuscated-internal-api-use")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertIn("internal:com.fs.starfarer.combat.entities.Missile", findings[0].evidence)
            self.assertNotIn("internal:com.fs.starfarer.api.combat.ShipAPI", findings[0].evidence)

    def test_api_only_references_are_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class_bytes = build_class_file(
                "exi/CleanScript",
                extra_class_refs=("com/fs/starfarer/api/combat/ShipAPI", "com/fs/starfarer/api/combat/CombatEngineAPI"),
            )
            write_jar(root / "jars" / "EXI.jar", {"exi/CleanScript.class": class_bytes})
            result = scan_mod(root)
            self.assertEqual(_findings(result, "obfuscated-internal-api-use"), [])


class CsvDesignTypeColumnTests(unittest.TestCase):
    def test_ship_data_missing_tech_and_manufacturer_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,hints\nDrone,drone_pd,\n")
            result = scan_mod(root)
            findings = _findings(result, "csv-missing-design-type-column")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")
            self.assertEqual(findings[0].file, "data/hulls/ship_data.csv")

    def test_ship_data_with_manufacturer_column_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,manufacturer,hints\nDrone,drone_pd,Hegemony,\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "csv-missing-design-type-column"), [])

    def test_ship_data_with_combined_tech_manufacturer_column_is_not_flagged(self) -> None:
        # Vanilla's own header spells this as one combined "tech/manufacturer" cell.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "hulls" / "ship_data.csv", "name,id,tech/manufacturer,hints\nDrone,drone_pd,LOW,\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "csv-missing-design-type-column"), [])

    def test_weapon_data_missing_column_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "weapons" / "weapon_data.csv", "name,id,type\nBlaster,fx_blaster,ENERGY\n")
            result = scan_mod(root)
            findings = _findings(result, "csv-missing-design-type-column")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].file, "data/weapons/weapon_data.csv")

    def test_weapon_data_with_tech_column_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "data" / "weapons" / "weapon_data.csv", "name,id,tech\nBlaster,fx_blaster,LOW\n")
            result = scan_mod(root)
            self.assertEqual(_findings(result, "csv-missing-design-type-column"), [])


class UndeclaredLibraryDependencyTests(unittest.TestCase):
    def test_source_reference_without_declared_dependency_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"flowergod"}')
            _write(
                root / "src" / "FlowerGodPlugin.java",
                "package fg;\nimport org.dark.shaders.light.LightAPI;\nclass FlowerGodPlugin { LightAPI l; }",
            )
            result = scan_mod(root)
            findings = _findings(result, "undeclared-library-dependency")
            manual = [item for item in findings if item.classification == "MANUAL"]
            self.assertTrue(any("library:GraphicsLib" in item.evidence for item in manual))

    def test_declared_dependency_suppresses_finding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"flowergod","dependencies":[{"id":"shaderLib"}]}')
            _write(
                root / "src" / "FlowerGodPlugin.java",
                "package fg;\nimport org.dark.shaders.light.LightAPI;\nclass FlowerGodPlugin { LightAPI l; }",
            )
            result = scan_mod(root)
            findings = [item for item in _findings(result, "undeclared-library-dependency") if "library:GraphicsLib" in item.evidence]
            self.assertEqual(findings, [])

    def test_ismodenabled_guarded_nexerelin_reference_is_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            _write(
                root / "src" / "NexIntegration.java",
                "package fx;\nimport exerelin.api.NexerelinFactionAPI;\n"
                "class NexIntegration { void go() { if (Global.getSettings().isModEnabled(\"nexerelin\")) { } } }",
            )
            result = scan_mod(root)
            findings = [item for item in _findings(result, "undeclared-library-dependency") if "library:Nexerelin" in item.evidence]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")

    def test_bytecode_only_reference_without_declared_dependency_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write(root / "mod_info.json", '{"id":"fixture"}')
            class_bytes = build_class_file("fx/Plugin", extra_class_refs=("lunalib/lunaSettings/LunaSettings",))
            write_jar(root / "jars" / "fixture.jar", {"fx/Plugin.class": class_bytes})
            result = scan_mod(root)
            findings = [item for item in _findings(result, "undeclared-library-dependency") if "library:LunaLib" in item.evidence]
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")


class VanillaPathShadowingJavaExtensionTests(unittest.TestCase):
    def test_loose_script_with_different_bytes_is_manual(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java", "class LevelupPluginImpl { int a = 2; }")
            _write(vanilla / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java", "class LevelupPluginImpl { int a = 1; }")
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-path-shadowing")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "MANUAL")

    def test_byte_identical_loose_script_is_not_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            same_text = "class LevelupPluginImpl { int a = 1; }"
            _write(root / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java", same_text)
            _write(vanilla / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java", same_text)
            result = scan_mod(root, vanilla_core=vanilla)
            self.assertEqual(_findings(result, "vanilla-path-shadowing"), [])

    def test_total_conversion_loose_script_shadow_is_downgraded(self) -> None:
        with tempfile.TemporaryDirectory() as mod_dir, tempfile.TemporaryDirectory() as vanilla_dir:
            root = Path(mod_dir)
            vanilla = Path(vanilla_dir)
            _write(root / "mod_info.json", '{"id":"fixture_tc","totalConversion":true,}')
            _write(root / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java", "class LevelupPluginImpl { int a = 2; }")
            _write(vanilla / "data" / "scripts" / "plugins" / "LevelupPluginImpl.java", "class LevelupPluginImpl { int a = 1; }")
            result = scan_mod(root, vanilla_core=vanilla)
            findings = _findings(result, "vanilla-path-shadowing")
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].classification, "REVIEW")


if __name__ == "__main__":
    unittest.main()
