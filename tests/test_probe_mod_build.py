import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from bridgeforge.jar_audit import REFLECTION_SYMBOL_PREFIXES, _resolve_jar_classes, parse_constant_pool, referenced_class_names
from bridgeforge.probe_mod_build import ProbeModBuildError, build_probe_mod, install_release

REPO_ROOT = Path(__file__).resolve().parent.parent
JDK_DIR = REPO_ROOT / "In operation" / "_rig" / "jdk-25.0.4.1+1"
CORE_DIR = Path(r"C:\Program Files (x86)\Fractal Softworks\Starsector\starsector-core")

_RIG_AVAILABLE = JDK_DIR.is_dir() and CORE_DIR.is_dir()


@unittest.skipUnless(_RIG_AVAILABLE, "requires the RC8 JDK and a local Starsector install")
class ProbeModBuildTests(unittest.TestCase):
    def test_build_compiles_and_produces_a_sandbox_clean_deterministic_jar(self) -> None:
        result = build_probe_mod(REPO_ROOT, JDK_DIR, CORE_DIR)
        try:
            self.assertTrue(result["mission_compiles"], result.get("mission_error"))
            self.assertGreater(result["class_count"], 0)

            jar_path = Path(result["jar"])
            self.assertTrue(jar_path.is_file())

            # Deterministic: building twice from identical sources must produce byte-identical jars.
            first_hash = hashlib.sha256(jar_path.read_bytes()).hexdigest()
            build_probe_mod(REPO_ROOT, JDK_DIR, CORE_DIR)
            second_hash = hashlib.sha256(jar_path.read_bytes()).hexdigest()
            self.assertEqual(first_hash, second_hash)

            # Sandbox-clean: RC8's script classloader forbids java.lang.reflect.*, java.io.File*,
            # and java.nio.file.* at class load; reuse the scanner's own class-file parser (already
            # relied on by `jar-audit`) to prove none of the compiled classes reference them.
            classes = _resolve_jar_classes(jar_path, None, "probe jar")
            self.assertGreater(len(classes), 0)
            flagged = []
            for name, data in classes.items():
                entries = parse_constant_pool(data)
                refs = referenced_class_names(entries)
                bad = sorted(r for r in refs if any(r.startswith(prefix) for prefix in REFLECTION_SYMBOL_PREFIXES))
                if bad:
                    flagged.append((name, bad))
            self.assertEqual(flagged, [])
        finally:
            build_dir = REPO_ROOT / "probe-mod" / "build"
            shutil.rmtree(build_dir, ignore_errors=True)

    def test_install_release_assembles_runtime_only_copy(self) -> None:
        # install_release writes the REAL release copy that `probe-config --install` ships into rigs.
        # This test used to delete it afterwards (every suite run left the rig with nothing to
        # install), so park any existing copy first and put it back untouched when done.
        real_release = REPO_ROOT / "probe-mod" / "releases" / "bridgeforge-probe"
        parked_root = Path(tempfile.mkdtemp())
        parked = parked_root / "bridgeforge-probe"
        had_release = real_release.exists()
        if had_release:
            shutil.move(str(real_release), str(parked))
        try:
            build_probe_mod(REPO_ROOT, JDK_DIR, CORE_DIR)
            result = install_release(REPO_ROOT)
            release_dir = Path(result["release_dir"])
            self.assertTrue((release_dir / "mod_info.json").is_file())
            self.assertTrue((release_dir / "jars" / "bridgeforge-probe.jar").is_file())
            self.assertTrue((release_dir / "data" / "missions" / "mission_list.csv").is_file())
            self.assertTrue((release_dir / "data" / "missions" / "bfprobe_combat" / "MissionDefinition.java").is_file())
            # Runtime-only: no source tree, no build scratch dir.
            self.assertFalse((release_dir / "src").exists())
            self.assertFalse((release_dir / "build").exists())
        finally:
            shutil.rmtree(real_release, ignore_errors=True)
            if had_release:
                shutil.move(str(parked), str(real_release))
            shutil.rmtree(parked_root, ignore_errors=True)
            shutil.rmtree(REPO_ROOT / "probe-mod" / "build", ignore_errors=True)


class ProbeModBuildErrorTests(unittest.TestCase):
    def test_missing_javac_raises(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fake_jdk = Path(directory) / "not-a-jdk"
            with self.assertRaises(ProbeModBuildError):
                build_probe_mod(REPO_ROOT, fake_jdk, CORE_DIR if CORE_DIR.is_dir() else Path(directory))


if __name__ == "__main__":
    unittest.main()
