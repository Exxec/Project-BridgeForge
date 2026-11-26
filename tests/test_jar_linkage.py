"""jar-linkage-unresolved: a mod jar's calls into game classes checked against RC8's core jars (2026-09-30)."""
from __future__ import annotations

import json
import os
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scan.scanner import scan_mod
from tests.support import javac_path, resolved_temp_dir


def _compile(javac: str, root: Path, sources: dict[str, str], classpath: Path | None = None) -> Path:
    src, out = root / "src", root / "classes"
    for name, text in sources.items():
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_text(text, encoding="utf-8")
    command = [javac, "-encoding", "UTF-8", "--release", "17", "-d", str(out)] + (["-cp", str(classpath)] if classpath else []) + [str(src / n) for n in sources]
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stderr
    return out


def _jar(classes: Path, jar: Path) -> None:
    jar.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(jar, "w") as archive:
        for path in classes.rglob("*.class"):
            archive.write(path, path.relative_to(classes).as_posix())


OLD_API = {"com/fs/starfarer/api/ui/Tip.java": "package com.fs.starfarer.api.ui; public interface Tip { void table(float w); int rows(); }"}
NEW_API = {"com/fs/starfarer/api/ui/Tip.java": "package com.fs.starfarer.api.ui; public interface Tip { Object table(float w); int rows(); }"}
MOD = {"data/hullmods/Info.java": "package data.hullmods; import com.fs.starfarer.api.ui.Tip;\n"
                                  "public class Info { void draw(Tip t) { t.table(1f); t.rows(); t.toString(); } }"}


class JarLinkageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")

    def test_a_call_whose_rc8_return_type_changed_is_reported_as_a_relink(self) -> None:
        with resolved_temp_dir() as root:
            old_api = _compile(self.javac, root / "old", OLD_API)
            _jar(_compile(self.javac, root / "new", NEW_API), root / "starsector-core" / "starfarer.api.jar")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", MOD, classpath=old_api), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "starsector-core").findings if f.id == "jar-linkage-unresolved"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].file, "jars/m.jar!data/hullmods/Info.class")
        self.assertEqual(len(found[0].evidence), 1)  # rows() and Object.toString() resolve
        self.assertIn("Tip.table(F)V (RC8: (F)Ljava/lang/Object;)", found[0].evidence[0])
        self.assertIn("return type", found[0].explanation)

    def test_a_library_class_in_the_game_namespace_resolves_through_provider_roots(self) -> None:
        # ROADMAP-3 item 92.35 (2026-11-16): Bultach's custom start calls Nexerelin's
        # com.fs...rulecmd.newgame.NGCAddStartingShipsByFleetType; with no rig it read "class missing".
        lib_api = {"com/fs/starfarer/api/impl/Lib.java": "package com.fs.starfarer.api.impl; public class Lib { public static void go() {} }"}
        start = {"data/Start.java": "package data; public class Start { void s() { com.fs.starfarer.api.impl.Lib.go(); } }"}
        with resolved_temp_dir() as root:
            lib_classes = _compile(self.javac, root / "lib", lib_api)
            _jar(_compile(self.javac, root / "new", NEW_API), root / "starsector-core" / "starfarer.api.jar")
            library = root / "OtherInstall" / "mods" / "nexlike"
            _jar(lib_classes, library / "jars" / "lib.jar")
            (library / "mod_info.json").write_text(json.dumps({"id": "nexlike", "name": "n", "version": "1", "jars": ["jars/lib.jar"]}), encoding="utf-8")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", start, classpath=lib_classes), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            alone = [f.id for f in scan_mod(mod, vanilla_core=root / "starsector-core").findings]
            provided = [f.id for f in scan_mod(mod, vanilla_core=root / "starsector-core",
                                               provider_roots=[root / "OtherInstall" / "mods"]).findings]
        self.assertIn("jar-linkage-unresolved", alone)
        self.assertNotIn("jar-linkage-unresolved", provided)

    def test_a_removed_no_argument_constructor_is_reported(self) -> None:
        # 0.98.5a-RC3 (2026-11-15): ShipAIConfig() became ShipAIConfig(ShipAPI). Constructors are not inherited, but the
        # hierarchy walk reached Object.<init>()V and called Polaris Prime's `new ShipAIConfig()` resolved.
        old = {"com/fs/starfarer/api/combat/Cfg.java": "package com.fs.starfarer.api.combat; public class Cfg { public Cfg() {} }"}
        new = {"com/fs/starfarer/api/combat/Cfg.java": "package com.fs.starfarer.api.combat; public class Cfg { public Cfg(Object ship) {} }"}
        mod_src = {"data/Ai.java": "package data; public class Ai { Object make() { return new com.fs.starfarer.api.combat.Cfg(); } }"}
        with resolved_temp_dir() as root:
            old_api = _compile(self.javac, root / "old", old)
            _jar(_compile(self.javac, root / "new", new), root / "starsector-core" / "starfarer.api.jar")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", mod_src, classpath=old_api), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "starsector-core").findings if f.id == "jar-linkage-unresolved"]
        self.assertEqual(len(found), 1)
        self.assertIn("Cfg.<init>()V", found[0].evidence[0])
        self.assertIn("(Ljava/lang/Object;)V", found[0].evidence[0])



NEW_HOOK = {"com/fs/starfarer/api/combat/Hook.java": "package com.fs.starfarer.api.combat; public interface Hook { void hit(int a, Object result, float b); }",
            "com/fs/starfarer/api/combat/BaseHook.java": "package com.fs.starfarer.api.combat; public class BaseHook implements Hook { public void hit(int a, Object result, float b) {} }"}
OLD_HOOK = {"com/fs/starfarer/api/combat/Hook.java": "package com.fs.starfarer.api.combat; public interface Hook { void hit(int a, float b); }"}
HOOK_MOD = {"data/Effect.java": "package data; public class Effect implements com.fs.starfarer.api.combat.Hook { public void hit(int a, float b) {} }",
            "data/Fine.java": "package data; public class Fine extends com.fs.starfarer.api.combat.BaseHook {}"}


class JarInterfaceMethodTests(unittest.TestCase):
    """jar-interface-method-missing (2026-10-01): an interface RC8 changed, implemented with the old signature."""

    def setUp(self) -> None:
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")

    def test_a_class_built_against_the_old_interface_is_reported(self) -> None:
        with resolved_temp_dir() as root:
            old_api = _compile(self.javac, root / "old", {**OLD_HOOK, "com/fs/starfarer/api/combat/BaseHook.java":
                               "package com.fs.starfarer.api.combat; public class BaseHook implements Hook { public void hit(int a, float b) {} }"})
            _jar(_compile(self.javac, root / "new", NEW_HOOK), root / "starsector-core" / "starfarer.api.jar")
            mod = root / "mod"
            _jar(_compile(self.javac, root / "modbuild", HOOK_MOD, classpath=old_api), mod / "jars" / "m.jar")
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98a-RC8",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            found = [f for f in scan_mod(mod, vanilla_core=root / "starsector-core").findings if f.id == "jar-interface-method-missing"]
        self.assertEqual([f.file for f in found], ["jars/m.jar!data/Effect.class"])  # Fine inherits the new method
        self.assertIn("Hook.hit(ILjava.lang.Object;F)V", found[0].evidence[0])


# ROADMAP-3 98.7 (2026-11-25): 0.98.5a-RC9 renamed the obfuscated interface combat/ai/F to G. Station Augments' shield-AI
# wrapper implements F and names none of its members, so no reference reached the check, and the class failed to load.
OLD_OBF = {"com/fs/starfarer/combat/ai/F.java": "package com.fs.starfarer.combat.ai; public interface F { boolean o00000(); }",
           "com/fs/starfarer/combat/Base.java": "package com.fs.starfarer.combat; public abstract class Base { public abstract void go(); }"}
NEW_OBF = {"com/fs/starfarer/combat/ai/G.java": "package com.fs.starfarer.combat.ai; public interface G { boolean o00000(); }",
           "com/fs/starfarer/combat/Other.java": "package com.fs.starfarer.combat; public class Other {}"}
LIB_FACE = {"com/fs/starfarer/api/impl/LibFace.java": "package com.fs.starfarer.api.impl; public interface LibFace {}"}
SUPERTYPE_MOD = {
    "data/Shunt.java": "package data; public class Shunt implements com.fs.starfarer.combat.ai.F { public boolean o00000() { return false; } }",
    "data/Sub.java": "package data; public class Sub extends com.fs.starfarer.combat.Base { public void go() {} }",
    "data/Both.java": "package data; public class Both implements com.fs.starfarer.combat.ai.F {\n"
                      "  public boolean o00000() { return false; }\n  void x(com.fs.starfarer.combat.Base b) { b.go(); } }",
    "data/Plain.java": "package data; public class Plain implements Runnable { public void run() {} }",
    "com/fs/starfarer/combat/ai/admiral/Own.java": "package com.fs.starfarer.combat.ai.admiral; public class Own {}",
    "data/UsesOwn.java": "package data; public class UsesOwn extends com.fs.starfarer.combat.ai.admiral.Own {}",
    "data/FromLib.java": "package data; public class FromLib implements com.fs.starfarer.api.impl.LibFace {}",
}
_F = "com/fs/starfarer/combat/ai/F"


class RemovedSupertypeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.javac = javac_path()
        if self.javac is None:
            self.skipTest("no JDK found")

    def _build(self, root: Path) -> tuple[Path, Path, Path, Path]:
        old_classes = _compile(self.javac, root / "oldbuild", OLD_OBF)
        _jar(old_classes, root / "old" / "starfarer_obf.jar")
        _jar(_compile(self.javac, root / "newbuild", NEW_OBF), root / "new" / "starfarer_obf.jar")
        lib_classes = _compile(self.javac, root / "libbuild", LIB_FACE)
        _jar(lib_classes, root / "lib" / "lib.jar")
        classpath = Path(os.pathsep.join([str(old_classes), str(lib_classes)]))
        _jar(_compile(self.javac, root / "modbuild", SUPERTYPE_MOD, classpath=classpath), root / "mod" / "jars" / "m.jar")
        return root / "old", root / "new", root / "lib" / "lib.jar", root / "mod" / "jars" / "m.jar"

    def test_a_game_supertype_the_new_core_lacks_is_reported_and_only_that(self) -> None:
        from bridgeforge.linkage import unresolved_references
        with resolved_temp_dir() as root:
            old, new, lib, jar = self._build(root)
            on_old = unresolved_references([jar], old, [lib])
            on_new = unresolved_references([jar], new, [lib])
        self.assertEqual(on_old, {})
        # Not Plain (a JDK interface), UsesOwn (the mod's own game-package class) or FromLib (a library's).
        self.assertEqual(sorted(on_new), ["m.jar!data/Both.class", "m.jar!data/Shunt.class", "m.jar!data/Sub.class"])
        self.assertEqual(on_new["m.jar!data/Shunt.class"], [{"kind": "supertype", "owner": _F, "name": "", "descriptor": "",
                                                             "candidates": []}])
        # A missing superclass is already the `class` problem of super(): named once, not twice.
        self.assertEqual([(p["kind"], p["owner"], p["name"]) for p in on_new["m.jar!data/Sub.class"]],
                         [("class", "com/fs/starfarer/combat/Base", "<init>")])
        # The supertype comes after the references, so an existing finding's first evidence line does not change.
        self.assertEqual([(p["kind"], p["owner"]) for p in on_new["m.jar!data/Both.class"]],
                         [("class", "com/fs/starfarer/combat/Base"), ("supertype", _F)])

    def test_a_game_package_supertype_no_jar_provides_is_reported(self) -> None:
        from bridgeforge.linkage import reference_text, unresolved_references
        with resolved_temp_dir() as root:
            old, _new, _lib, jar = self._build(root)
            found = unresolved_references([jar], old)  # LibFace's library is not given
        self.assertEqual(list(found), ["m.jar!data/FromLib.class"])
        self.assertEqual(found["m.jar!data/FromLib.class"][0]["kind"], "supertype")
        self.assertEqual(reference_text(found["m.jar!data/FromLib.class"][0]), "com.fs.starfarer.api.impl.LibFace")

    def test_the_scan_names_the_missing_supertype(self) -> None:
        with resolved_temp_dir() as root:
            _old, new, _lib, jar = self._build(root)
            mod = jar.parent.parent
            (mod / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "gameVersion": "0.98.5a-RC7",
                                                           "jars": ["jars/m.jar"]}), encoding="utf-8")
            found = {f.file: f.evidence for f in scan_mod(mod, vanilla_core=new).findings if f.id == "jar-linkage-unresolved"}
        self.assertEqual(found["jars/m.jar!data/Shunt.class"], ["com.fs.starfarer.combat.ai.F [supertype missing]"])
        self.assertEqual(found["jars/m.jar!data/Both.class"][1], "com.fs.starfarer.combat.ai.F [supertype missing]")

    def test_relink_lists_a_missing_supertype_as_a_port(self) -> None:
        from bridgeforge.bytecode.jar_batch import relink_workspace
        with resolved_temp_dir() as root:
            _old, new, _lib, jar = self._build(root)
            working = root / "ws" / "working"
            (working / "jars").mkdir(parents=True)
            (working / "jars" / "m.jar").write_bytes(jar.read_bytes())
            (working / "mod_info.json").write_text(json.dumps({"id": "m", "name": "m", "version": "1", "jars": ["jars/m.jar"]}),
                                                   encoding="utf-8")
            result = relink_workspace(root / "ws", new)
        self.assertEqual(result["state"], "NEEDS_PORT")
        self.assertIn("com.fs.starfarer.combat.ai.F", result["port"])


class SourcePortTests(unittest.TestCase):
    def test_onhit_dialog_button_and_base_class_ports(self) -> None:
        from bridgeforge.bytecode.jar_batch import _port_base, _port_button, _port_dialog, _port_onhit
        onhit = "public void onHit(DamagingProjectileAPI p, CombatEntityAPI t, Vector2f v, boolean s, CombatEngineAPI e) {}"
        self.assertIn("boolean s, com.fs.starfarer.api.combat.listeners.ApplyDamageResultAPI damageResult, CombatEngineAPI e)", _port_onhit(onhit))
        self.assertIsNone(_port_onhit(_port_onhit(onhit)))  # never twice
        self.assertIn("CustomDialogCallback callback)", _port_dialog("public void createCustomDialog(CustomPanelAPI panel) {}"))
        self.assertIn("void buttonPressed(Object buttonId)", _port_button("public class P implements CustomUIPanelPlugin {\n}\n", "P"))
        self.assertEqual(_port_base("public class H implements HullModEffect {}", "H", {"com/fs/starfarer/api/combat/HullModEffect"}),
                         "public class H extends com.fs.starfarer.api.combat.BaseHullMod implements HullModEffect {}")
        self.assertIsNone(_port_base("public class H extends Other implements HullModEffect {}", "H", {"com/fs/starfarer/api/combat/HullModEffect"}))



class PortTableTests(unittest.TestCase):
    def test_ship_system_scripts_extend_base_ship_system_script(self) -> None:
        from bridgeforge.bytecode.jar_batch import BASE_CLASSES
        self.assertEqual(BASE_CLASSES["com/fs/starfarer/api/plugins/ShipSystemStatsScript"], "com.fs.starfarer.api.impl.combat.BaseShipSystemScript")


if __name__ == "__main__":
    unittest.main()
