"""Boot one mod set across every Java version and launcher a tester might use (ROADMAP item 61).

A tester's log showed vanilla ids missing at load ("System with id [temporalshell] not found", "Ship hull
spec [afflictor] not found!") on Java 28-beta with Fast Rendering. Nothing in the rig could vary the JVM or
the launcher, so such a report could be neither reproduced nor ruled out. A *variant* is one JDK plus one
launcher; `setup_rig` writes a `run-j<major>-<launcher>.bat` per variant beside the rig's `run-java25.bat`
(which it never touches) and `run_java_matrix` boots the same mods through each, several times, and reports a
pass rate per variant, because a parallel-loading race need not show on every run.

Launchers: `direct` is the proven RC8 flag block (rig `run-java25.bat`, read 2026-10-09) on the chosen JDK;
`fr` is Fast Rendering's own `fr.bat` command (`java [-javaagent:PatchLibAgent.jar] @fr.vmparams`, read from the
install 2026-10-09) on the chosen JDK. The `fr` bat appends the rig's log path so a run never writes its log
into the real install through the `starsector-core` junction.

Needs the game install and a rig, so a live run is local-only (docs/LOCAL_HANDOFF.md).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from . import boot_test
from .progress import Checkpoint, report

LAUNCHERS = ("direct", "fr")

# Directories searched for a JDK, in addition to the install the rig links to and the rig itself.
COMMON_JDK_ROOTS = (
    Path(r"C:\Program Files\Eclipse Adoptium"),
    Path(r"C:\Program Files\Java"),
    Path(r"C:\Program Files\Microsoft"),
    Path(r"C:\Program Files\Zulu"),
    Path(r"C:\Program Files\Amazon Corretto"),
)

DIRECT_FLAGS = (
    "-noverify -XX:+UnlockDiagnosticVMOptions -XX:-BytecodeVerificationLocal -XX:-BytecodeVerificationRemote",
    "-Djava.library.path=native\\windows",
    "-Djava.util.Arrays.useLegacyMergeSort=true",
    "--enable-preview --enable-native-access=ALL-UNNAMED",
    "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED --add-opens=java.base/java.nio=ALL-UNNAMED --add-opens=java.base/java.util=ALL-UNNAMED --add-opens=java.base/java.util.concurrent=ALL-UNNAMED --add-opens=java.base/java.util.concurrent.locks=ALL-UNNAMED --add-opens=java.base/jdk.internal.ref=ALL-UNNAMED --add-opens=java.base/java.lang.reflect=ALL-UNNAMED --add-opens=java.base/java.lang.ref=ALL-UNNAMED --add-opens=java.base/java.text=ALL-UNNAMED --add-opens=java.desktop/java.awt.font=ALL-UNNAMED --add-opens=java.desktop/java.awt=ALL-UNNAMED",
    "--add-exports=java.base/jdk.internal.ref=ALL-UNNAMED --add-exports=java.base/jdk.internal.misc=ALL-UNNAMED --add-exports=java.base/sun.nio.ch=ALL-UNNAMED",
    "-Xms2g -Xmx4g -Xss4m",
)
PATH_FLAGS = (
    "-Dcom.fs.starfarer.settings.paths.saves=..\\saves",
    "-Dcom.fs.starfarer.settings.paths.screenshots=..\\screenshots",
    "-Dcom.fs.starfarer.settings.paths.mods=..\\mods",
    "-Dcom.fs.starfarer.settings.paths.logs=..\\logs",
)
CLASSPATH = (
    "janino.jar;commons-compiler.jar;commons-compiler-jdk.jar;starfarer.api.jar;starfarer_obf.jar;jogg-0.0.7.jar;"
    "jorbis-0.0.15.jar;json.jar;lwjgl.jar;jinput.jar;log4j-1.2.9.jar;lwjgl_util.jar;fs.sound_obf.jar;fs.common_obf.jar;"
    "xstream-1.4.10.jar;txw2-3.0.2.jar;jaxb-api-2.4.0-b180830.0359.jar;webp-imageio-0.1.6.jar"
)


def _major(text: str) -> int | None:
    """Major version from `25.0.4.1`, `1.8.0_503`, `28-beta` or a folder name like `jdk-28+13`."""
    match = re.search(r"(?<![\d.])(1\.(\d+)|(\d+))", text)
    if not match:
        return None
    return int(match.group(2) or match.group(3))


def _jdk_info(home: Path) -> dict | None:
    java = home / "bin" / "java.exe"
    if not java.is_file() and not (home / "bin" / "java").is_file():
        return None
    version = ""
    release = home / "release"
    if release.is_file():
        for line in release.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("JAVA_VERSION="):
                version = line.split("=", 1)[1].strip().strip('"')
    major = _major(version) or _major(home.name)
    if major is None:
        return None
    return {"major": major, "version": version or home.name, "home": str(home), "name": home.name}


def discover_jdks(rig: Path | None = None, extra_roots: list[Path] | None = None) -> list[dict]:
    """JDKs/JREs found beside the rig's linked install, inside the rig, and in the usual install folders.

    One entry per major version (the first found wins: install and rig copies come before system ones),
    sorted by major. A tester's exact JVM build is not knowable here; `describe_log_java` reads it from a log.
    """
    roots: list[Path] = []
    if rig is not None:
        rig = Path(rig).expanduser().resolve()
        roots.append(rig)
        core = rig / "starsector-core"
        try:
            install = core.resolve().parent
        except OSError:
            install = None
        if install is not None:
            roots += [install, install / "jre"]
    roots += list(extra_roots or []) + list(COMMON_JDK_ROOTS)
    found: dict[int, dict] = {}
    for root in roots:
        if not root.is_dir():
            continue
        candidates = [root] + sorted(p for p in root.iterdir() if p.is_dir())
        for home in candidates:
            if home.name != "jre" and home != root and not re.match(r"(jdk|jre|java|zulu|corretto|temurin|microsoft)", home.name, re.I) and not (home / "bin").is_dir():
                continue
            info = _jdk_info(home)
            if info and info["major"] not in found:
                found[info["major"]] = info
    return [found[m] for m in sorted(found)]


def describe_log_java(log: Path) -> dict:
    """What a tester's starsector.log says about its JVM: version line and the mods that patch rendering/loading."""
    result: dict = {"java_version": None, "fast_rendering": False, "launcher_hint": None}
    for line in Path(log).read_text(encoding="utf-8", errors="replace").splitlines():
        if result["java_version"] is None and "StarfarerLauncher" in line and "Java version:" in line:
            result["java_version"] = line.split("Java version:", 1)[1].strip()
        if "com.genir.renderer" in line or "fast-rendering" in line.lower() or "FastRendering" in line:
            result["fast_rendering"] = True
    if result["fast_rendering"]:
        result["launcher_hint"] = "fr"
    return result


def variant_id(major: int, launcher: str) -> str:
    return f"j{major}-{launcher}"


def bat_name(vid: str) -> str:
    return f"run-{vid}.bat"


def build_launcher(jdk_home: str, launcher: str, java_major: int) -> str:
    """Text of a rig launcher .bat. CWD is the starsector-core junction, as in the proven run-java25.bat."""
    if launcher not in LAUNCHERS:
        raise ValueError(f"unknown launcher {launcher!r}; expected one of {', '.join(LAUNCHERS)}")
    head = [
        "@ECHO OFF",
        f"REM BridgeForge java-matrix launcher: JDK {java_major}, {launcher}. Generated; rerun `java-matrix setup` instead of editing.",
        "SET RT=%~dp0",
        'CD /D "%RT%starsector-core"',
        "",
    ]
    java = f'"{jdk_home}\\bin\\java.exe"'
    if launcher == "direct":
        flags = list(DIRECT_FLAGS)
        if java_major < 17:
            flags = [f.replace(" --enable-native-access=ALL-UNNAMED", "") for f in flags]
        body = [java + " ^"]
        body += [f" {flag} ^" for flag in (*flags, *PATH_FLAGS)]
        body += [f" -classpath {CLASSPATH} ^", " com.fs.starfarer.StarfarerLauncher"]
    else:
        # fr.bat's own command line; the later -D wins, so the log lands in the rig, not the real install.
        logs = PATH_FLAGS[-1]
        body = [
            "IF EXIST PatchLibAgent.jar (",
            f"  {java} -javaagent:PatchLibAgent.jar @fr.vmparams {logs}",
            ") ELSE (",
            f"  {java} @fr.vmparams {logs}",
            ")",
        ]
    return "\r\n".join(head + body) + "\r\n"


def plan_variants(jdks: list[dict], launchers: list[str] | None = None, majors: list[int] | None = None) -> list[dict]:
    # RC8 targets Java 17+; the install's bundled Java 8 jre cannot take the flag block, so it is opt-in via majors.
    chosen = [j for j in jdks if (j["major"] in majors if majors else j["major"] >= 17)]
    out = []
    for jdk in chosen:
        for launcher in launchers or list(LAUNCHERS):
            vid = variant_id(jdk["major"], launcher)
            out.append({"id": vid, "major": jdk["major"], "launcher": launcher, "jdk_home": jdk["home"], "java_version": jdk["version"], "bat": bat_name(vid)})
    return out


def setup_rig(rig: Path, variants: list[dict]) -> list[str]:
    """Write one launcher .bat per variant into the rig. Refuses unless the rig's starsector-core is a link."""
    rig = Path(rig).expanduser().resolve()
    if not boot_test._is_link(rig / "starsector-core"):
        raise ValueError(f"{rig / 'starsector-core'} is not a junction/symlink; java-matrix setup refuses a non-isolated rig")
    written = []
    for variant in variants:
        path = rig / variant["bat"]
        path.write_text(build_launcher(variant["jdk_home"], variant["launcher"], variant["major"]), encoding="utf-8", newline="")
        written.append(variant["bat"])
    return written


def run_java_matrix(rig: Path, mods: list[str], variants: list[dict], repeats: int = 3, timeout: int = 240, checkpoint: Path | None = None, quiet: bool = False, log_name: str | None = None) -> dict:
    """Boot `mods` through every variant `repeats` times; one progress line per boot, resumable from `checkpoint`.

    A variant whose launcher .bat is missing is reported REFUSED (run `java-matrix setup` first), not skipped.
    """
    rig = Path(rig).expanduser().resolve()
    base = log_name or "java-matrix"
    total = len(variants) * repeats
    header = {"rig": str(rig), "mods": sorted(mods), "variants": [v["id"] for v in variants], "repeats": repeats}
    rows: dict[str, list[dict]] = {v["id"]: [] for v in variants}
    done = 0
    with Checkpoint(checkpoint, header) as ckpt:
        for variant in variants:
            for run in range(1, repeats + 1):
                key = f"{variant['id']}#{run}"
                done += 1
                saved = ckpt.get(key)
                if saved is not None:
                    rows[variant["id"]].append(saved)
                    if not quiet:
                        report(done, total, key, saved["status"], None)
                    continue
                started = time.monotonic()
                result = boot_test.run_boot_test(rig, mods, timeout=timeout, log_name=f"{base}-{variant['id']}-{run}", bat_name=variant["bat"])
                triage = result.get("triage") if isinstance(result.get("triage"), dict) else {}
                row = {"run": run, "status": result["status"], "reason": result.get("reason"), "elapsed_seconds": result.get("elapsed_seconds"), "log": result.get("log"), "triage": triage.get("counts"), "vanilla_shadowing_symptoms": len(triage.get("vanilla_shadowing_symptoms") or [])}
                ckpt.add(key, row)
                rows[variant["id"]].append(row)
                if not quiet:
                    report(done, total, key, result["status"], time.monotonic() - started)
    matrix = []
    for variant in variants:
        runs = rows[variant["id"]]
        passed = sum(1 for r in runs if r["status"] == "PASS")
        matrix.append({**{k: variant[k] for k in ("id", "major", "launcher", "java_version")}, "runs": len(runs), "passed": passed, "pass_rate": round(passed / len(runs), 2) if runs else None, "statuses": [r["status"] for r in runs], "results": runs})
    result = {"schema_version": 1, "mode": "JAVA_MATRIX", "mods": sorted(mods), "repeats": repeats, "matrix": matrix, "verdict": _verdict(matrix)}
    if checkpoint is not None and Path(checkpoint).is_file():
        Path(checkpoint).unlink()
    return result


def _verdict(matrix: list[dict]) -> str:
    if not matrix:
        return "NO_VARIANTS"
    if any(m["statuses"] and all(s == "REFUSED" for s in m["statuses"]) for m in matrix):
        return "REFUSED"
    rates = {m["pass_rate"] for m in matrix}
    if rates == {1.0}:
        return "PASS_ALL"
    if rates == {0.0}:
        return "FAIL_ALL"
    if any(m["pass_rate"] not in (0.0, 1.0) for m in matrix):
        return "FLAKY"
    return "VARIES_BY_VARIANT"


def render(result: dict) -> str:
    lines = [f"Verdict: {result['verdict']} ({result['repeats']} run(s) per variant)"]
    for m in result["matrix"]:
        lines.append(f"  {m['id']:<14} Java {m['java_version']:<12} {m['passed']}/{m['runs']} PASS  {' '.join(m['statuses'])}")
    return "\n".join(lines)

