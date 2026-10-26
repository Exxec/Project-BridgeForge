"""`bridgeforge decompile-jar`: a jar's classes as an editable source tree (ROADMAP 44, Ironclads 2026-10-04).

The first step of a whole-jar rebuild: decompile (Vineflower) -> edit -> `rebuild-jar` (javac --release 17 against
RC8 -> jar -> class diff with the original). Ironclads' IroncladsEcon.jar was rebuilt this way by hand. The output
folder holds one .java per top-level class at its package path; inner classes stay inside their outer class, as
javac recreates them. Never writes into the jar's folder unless that is the chosen output.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .java_toolchain import REPO_ROOT, find_jdk


def find_vineflower(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return Path(explicit) if Path(explicit).is_file() else None
    tools = REPO_ROOT / "In operation" / "_tools"
    found = sorted(tools.glob("vineflower*.jar")) if tools.is_dir() else []
    return found[-1] if found else None


def decompile_jar(jar: Path, output: Path, vineflower: Path | None = None, jdk: Path | None = None) -> dict:
    jar, output = Path(jar).resolve(), Path(output).resolve()
    if not jar.is_file():
        raise ValueError(f"{jar} is not a file")
    tool = find_vineflower(vineflower)
    if tool is None:
        raise ValueError("Vineflower not found: put vineflower-*.jar in In operation/_tools/ or pass --vineflower")
    toolchain = find_jdk(jdk)
    if toolchain is None:
        raise ValueError("no JDK found (pass --jdk)")
    java = toolchain.javac.with_name("java.exe" if toolchain.javac.suffix == ".exe" else "java")
    output.mkdir(parents=True, exist_ok=True)
    # -dgs=1: decompile generic signatures (Ironclads' run, 2026-10-04); the output folder receives the source tree.
    run = subprocess.run([str(java), "-jar", str(tool), "-dgs=1", str(jar), str(output)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    java_sources, kotlin_sources = count_sources(output)
    rebuild = f"edit, then: bridgeforge rebuild-jar <workspace> --sources {output} --jar <the jar> --vanilla-core <core>"
    return {"schema_version": 1, "mode": "DECOMPILE_JAR", "jar": str(jar), "output": str(output), "tool": str(tool),
            "exit_code": run.returncode, "sources": java_sources, "kotlin_sources": kotlin_sources,
            "next": KOTLIN_NEXT if kotlin_sources else rebuild,
            "log_tail": (run.stdout + run.stderr)[-800:]}


# Vineflower's Kotlin plugin writes .kt for Kotlin classes (Exotica Technologies 2.1.1-RC3, 2026-10-26: 319 .kt beside
# 56 .java). rebuild-jar compiles .java with javac only, and decompiled Kotlin does not recompile as written.
KOTLIN_NEXT = ("Kotlin classes decompiled to .kt: read them, but rebuild-jar cannot compile them; "
               "patch single classes with patch-jar-class or get the author's source")


def count_sources(output: Path) -> tuple[int, int]:
    """(.java, .kt) files under a decompiled tree."""
    return len(list(Path(output).rglob("*.java"))), len(list(Path(output).rglob("*.kt")))
