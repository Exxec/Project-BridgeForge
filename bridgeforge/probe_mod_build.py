from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

# Deterministic timestamp stamped on every jar entry (matches the ZIP epoch minimum
# representable in the DOS date format), so two builds from identical sources produce
# byte-identical jars regardless of when/where they were built.
_FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)

# Core jars needed on javac's classpath: starfarer.api.jar exposes public API types, but
# several public method signatures reach into types that live in these sibling jars
# (org.json from json.jar; org.apache.log4j.Logger from Global.getLogger(); lwjgl's
# Vector2f from SectorEntityToken.getLocation()). None of these are obfuscated/internal
# classes -- they are the concrete types the public API already exposes.
_CLASSPATH_JAR_NAMES = (
    "starfarer.api.jar",
    "json.jar",
    "log4j-1.2.9.jar",
    "lwjgl.jar",
    "lwjgl_util.jar",
)

MOD_ROOT_RELATIVE = Path("probe-mod")
SRC_RELATIVE = MOD_ROOT_RELATIVE / "src"
JAR_RELATIVE = MOD_ROOT_RELATIVE / "jars" / "bridgeforge-probe.jar"
MISSION_SOURCE_RELATIVE = MOD_ROOT_RELATIVE / "data" / "missions" / "bfprobe_combat" / "MissionDefinition.java"
RELEASE_RELATIVE = MOD_ROOT_RELATIVE / "releases" / "bridgeforge-probe"


class ProbeModBuildError(ValueError):
    """Raised for a refused or failed probe-mod build."""


def _find_javac(jdk_dir: Path) -> Path:
    javac = Path(jdk_dir).expanduser().resolve() / "bin" / "javac.exe"
    if not javac.is_file():
        raise ProbeModBuildError(f"{javac} not found; pass --jdk pointing at a JDK 17+ home containing bin/javac.exe.")
    return javac


def _core_classpath(core_dir: Path) -> str:
    core_dir = Path(core_dir).expanduser().resolve()
    jars = []
    for name in _CLASSPATH_JAR_NAMES:
        jar_path = core_dir / name
        if not jar_path.is_file():
            raise ProbeModBuildError(f"{jar_path} not found under --core; is this a starsector-core directory?")
        jars.append(str(jar_path))
    return ";".join(jars)


def _run_javac(javac: Path, classpath: str, sources: list[Path], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    command = [str(javac), "--release", "17", "-nowarn", "-cp", classpath, "-d", str(out_dir)]
    command.extend(str(source) for source in sources)
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ProbeModBuildError(f"javac failed (exit {completed.returncode}):\n{completed.stdout}\n{completed.stderr}")


def _write_deterministic_jar(class_dir: Path, jar_path: Path) -> list[str]:
    class_files = sorted(p.relative_to(class_dir).as_posix() for p in class_dir.rglob("*.class"))
    jar_path.parent.mkdir(parents=True, exist_ok=True)
    if jar_path.exists():
        jar_path.unlink()
    with zipfile.ZipFile(jar_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_name in class_files:
            info = zipfile.ZipInfo(relative_name, date_time=_FIXED_DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            data = (class_dir / relative_name).read_bytes()
            archive.writestr(info, data)
    return class_files


def build_probe_mod(repo_root: Path, jdk_dir: Path, core_dir: Path, keep_build_dir: bool = False) -> dict[str, object]:
    """Compile probe-mod/src, jar it deterministically, and test-compile the loose mission source.

    Never touches In operation/, Done/, or any real Starsector install: everything is
    read from/written to the repo's own probe-mod/ tree and a scratch build directory.
    """
    repo_root = Path(repo_root).expanduser().resolve()
    mod_root = repo_root / MOD_ROOT_RELATIVE
    src_dir = repo_root / SRC_RELATIVE
    if not src_dir.is_dir():
        raise ProbeModBuildError(f"{src_dir} not found.")

    javac = _find_javac(jdk_dir)
    classpath = _core_classpath(core_dir)

    build_dir = mod_root / "build"
    classes_dir = build_dir / "classes"
    if build_dir.exists():
        shutil.rmtree(build_dir)

    sources = sorted(src_dir.rglob("*.java"))
    if not sources:
        raise ProbeModBuildError(f"No .java sources found under {src_dir}.")
    _run_javac(javac, classpath, sources, classes_dir)

    jar_path = repo_root / JAR_RELATIVE
    class_files = _write_deterministic_jar(classes_dir, jar_path)

    mission_check_dir = build_dir / "mission-check"
    mission_source = repo_root / MISSION_SOURCE_RELATIVE
    mission_ok = True
    mission_error = None
    if mission_source.is_file():
        try:
            _run_javac(javac, f"{classpath};{classes_dir}", [mission_source], mission_check_dir)
        except ProbeModBuildError as exc:
            mission_ok = False
            mission_error = str(exc)

    if not keep_build_dir:
        shutil.rmtree(build_dir, ignore_errors=True)

    return {
        "jar": str(jar_path),
        "class_count": len(class_files),
        "classes": class_files,
        "mission_source": str(mission_source),
        "mission_compiles": mission_ok,
        "mission_error": mission_error,
    }


def install_release(repo_root: Path) -> dict[str, object]:
    """Assemble the runtime-only release copy (mod_info + jar + data), no source/build files."""
    repo_root = Path(repo_root).expanduser().resolve()
    mod_root = repo_root / MOD_ROOT_RELATIVE
    release_dir = repo_root / RELEASE_RELATIVE
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)

    shutil.copy2(mod_root / "mod_info.json", release_dir / "mod_info.json")

    jar_src = mod_root / "jars" / "bridgeforge-probe.jar"
    if not jar_src.is_file():
        raise ProbeModBuildError(f"{jar_src} not found; run build_probe_mod() first.")
    (release_dir / "jars").mkdir(parents=True, exist_ok=True)
    shutil.copy2(jar_src, release_dir / "jars" / "bridgeforge-probe.jar")

    # data/ is copied whole, MissionDefinition.java included: unlike src/, that loose
    # .java is a runtime artifact the game itself compiles (via Janino) when the mission
    # loads, exactly like a vanilla mission -- it is not a dev-only source file.
    data_src = mod_root / "data"
    data_dst = release_dir / "data"
    shutil.copytree(data_src, data_dst)

    return {"release_dir": str(release_dir)}
