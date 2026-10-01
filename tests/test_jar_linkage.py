"""jar-linkage-unresolved: a mod jar's calls into game classes checked against RC8's core jars (2026-09-30)."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path

from bridgeforge.scanner import scan_mod
from tests.support import resolved_temp_dir


def _compile(javac: str, root: Path, sources: dict[str, str], classpath: Path | None = None) -> Path:
    src, out = root / "src", root / "classes"
    for name, text in sources.items():
        (src / name).parent.mkdir(parents=True, exist_ok=True)
        (src / name).write_text(text, encoding="utf-8")
    command = [javac, "--release", "17", "-d", str(out)] + (["-cp", str(classpath)] if classpath else []) + [str(src / n) for n in sources]
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
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

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



NEW_HOOK = {"com/fs/starfarer/api/combat/Hook.java": "package com.fs.starfarer.api.combat; public interface Hook { void hit(int a, Object result, float b); }",
            "com/fs/starfarer/api/combat/BaseHook.java": "package com.fs.starfarer.api.combat; public class BaseHook implements Hook { public void hit(int a, Object result, float b) {} }"}
OLD_HOOK = {"com/fs/starfarer/api/combat/Hook.java": "package com.fs.starfarer.api.combat; public interface Hook { void hit(int a, float b); }"}
HOOK_MOD = {"data/Effect.java": "package data; public class Effect implements com.fs.starfarer.api.combat.Hook { public void hit(int a, float b) {} }",
            "data/Fine.java": "package data; public class Fine extends com.fs.starfarer.api.combat.BaseHook {}"}


class JarInterfaceMethodTests(unittest.TestCase):
    """jar-interface-method-missing (2026-10-01): an interface RC8 changed, implemented with the old signature."""

    def setUp(self) -> None:
        self.javac = shutil.which("javac")
        if self.javac is None:
            self.skipTest("no javac on PATH")

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


class SourcePortTests(unittest.TestCase):
    def test_onhit_dialog_button_and_base_class_ports(self) -> None:
        from bridgeforge.jar_batch import _port_base, _port_button, _port_dialog, _port_onhit
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
        from bridgeforge.jar_batch import BASE_CLASSES
        self.assertEqual(BASE_CLASSES["com/fs/starfarer/api/plugins/ShipSystemStatsScript"], "com.fs.starfarer.api.impl.combat.BaseShipSystemScript")


if __name__ == "__main__":
    unittest.main()
