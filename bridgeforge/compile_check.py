"""`bridgeforge compile-check`: compile a mod's loose scripts against RC8 with javac and report every error.

Loose `data\\**.java` scripts are what Starsector actually compiles at startup -- with Janino, not
javac (see docs/BUG_CLASSES.md; live bug PRB-MISSION-02: Janino ignores generics and predates
lambdas). A javac PASS here is real evidence the sources are syntactically and API-wise sound
against RC8, but it does not prove Janino will accept them; `janino_gap_warnings` flags cheap,
purely textual signs of syntax Janino is known to reject, and `janino_note` restates the limit.

Read-only: everything compiles into a temporary directory that is removed afterward. Never
writes into a mod's working copy.
"""
from __future__ import annotations

import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from .java_toolchain import assemble_classpath, find_jdk, run_javac

SCHEMA_VERSION = 1

# Cheap (regex, not a parser), comment-blanked signs of Java 8+ syntax Janino predates/rejects:
# a lambda, a method reference, the diamond operator, try-with-resources, multi-catch, `var`.
# False positives/negatives are expected; this is a warning, not a verdict.
#
# Version evidence (2026-09-15): RC8's starsector-core/janino.jar manifest
# (META-INF/MANIFEST.MF) reads `Implementation-Version: 2.7.8` (and `Bundle-Version: 2.7.8`) -- so
# RC8 runs Janino 2.7.8, not a later 3.x line. Janino's own changelog
# (https://janino-compiler.github.io/janino/changelog.html) dates every one of these constructs to
# releases well after 2.7.8: a diamond-operator test was added in 3.0.7 (2017-03-22), the
# try-with-resources statement was implemented in 3.0.9 (2018-08-23), and multi-catch parsing plus
# lambda/method-reference parsing were added in 3.0.13 (2019-06-23; lambda COMPILATION was still
# "NYI" there). `var` (a Java 10 feature) has no earlier claim at all. None of that is in 2.7.8, so
# every pattern below stays exactly as flagged -- there is no construct here Janino 2.7.8 is
# documented to accept; keep flagging all of them.
_JANINO_GAP_PATTERNS = (
    ("lambda", re.compile(r"(?:\)|\b[A-Za-z_$][\w$]*)\s*->\s*")),
    ("method-reference", re.compile(r"\b[A-Za-z_$][\w.$]*::\w+")),
    ("diamond-operator", re.compile(r"\bnew\s+[A-Za-z_$][\w.$]*<>\s*\(")),
    ("try-with-resources", re.compile(r"\btry\s*\(\s*(?:final\s+)?[A-Za-z_$][\w.$<>\[\]]*\s+\w+\s*=")),
    ("multi-catch", re.compile(r"\bcatch\s*\([^)]*\|[^)]*\)")),
    ("var-keyword", re.compile(r"(?:^|[;{}])\s*var\s+\w+\s*=")),
)


def _blank_comments(text: str) -> str:
    """A cheap (not string-literal-aware) comment blanker, so a comment mentioning e.g. "->" doesn't count."""
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def discover_loose_scripts(root: Path) -> list[Path]:
    """Loose data/**.java scripts the game compiles at startup; skips disabled_files/.

    Sources under src/ or jars/src/ belong to a jar (compiled ahead of time, not by the game) and
    are deliberately excluded.
    """
    data_dir = root / "data"
    if not data_dir.is_dir():
        return []
    return sorted(path for path in data_dir.rglob("*.java") if "disabled_files" not in path.relative_to(root).parts)


def dependency_shadowed_scripts(root: Path, sources: list[Path], dependency_jars: dict[str, list[str]]) -> list[dict[str, object]]:
    """Loose scripts whose class a declared dependency's jar already compiles (ROADMAP P14 item 12).

    All mod jars share one classloader, so the game loads the dependency's class and skips the loose
    file ("already loaded (perhaps from jar file) ... skipping compilation"): the mod's edit does
    nothing. Found on Maelstrom Interstellar Imperium Unofficial Expansion (E8, 2026-09-20), whose two
    Titan scripts base Interstellar Imperium's II.jar shadows. Uses the same class-file walk and
    class-name rule as `verify-shadow`; the mod's own jars are `loose-script-shadowed-by-jar`'s job.
    """
    from .scanner import _parse_class_file, iter_class_files_in_jars
    from .verify_shadow import script_class_name

    owners: dict[str, tuple[str, str]] = {}
    for dependency, jars in sorted(dependency_jars.items()):
        for jar, member, data in iter_class_files_in_jars([Path(jar) for jar in jars]):
            info = _parse_class_file(data)
            if info is not None and info.this_class:
                owners.setdefault(info.this_class.replace("/", "."), (dependency, f"{jar}!{member}"))
    shadowed = []
    for source in sources:
        class_name, _derived = script_class_name(source)
        if class_name in owners:
            dependency, supplied_by = owners[class_name]
            shadowed.append({"file": source.relative_to(root).as_posix(), "class": class_name, "dependency": dependency, "supplied_by": supplied_by})
    return shadowed


def vanilla_loose_scripts(vanilla_core: Path) -> list[Path]:
    """RC8's own loose data/**.java scripts (e.g. BaseSpawnPoint, hullmods -- ~116 in RC8).

    These are never in a jar: the game compiles them itself at startup, the same way it compiles a
    mod's loose scripts, and mod loose scripts routinely extend/reference them (a spawn point
    extending BaseSpawnPoint, say). Putting only the core JARs on the classpath is not enough to
    validate that; these sources have to be compiled alongside the mod's own for symbols to resolve,
    exactly like the real game's Janino classloader sees both.
    """
    data_dir = Path(vanilla_core).expanduser().resolve() / "data"
    if not data_dir.is_dir():
        return []
    return sorted(data_dir.rglob("*.java"))


def _janino_gap_warnings(sources: list[Path], root: Path) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    for source in sources:
        try:
            text = _blank_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        hits = sorted({kind for kind, pattern in _JANINO_GAP_PATTERNS if pattern.search(text)})
        if hits:
            warnings.append({"file": str(source.relative_to(root)).replace("\\", "/"), "java8plus_syntax": hits})
    return warnings


_JANINO_JARS = ("janino.jar", "commons-compiler.jar")
_JANINO_HARNESS = Path(__file__).with_name("java") / "JaninoCheck.java"


def janino_compile(jdk_javac: Path, vanilla_core: Path | None, root: Path, sources: list[Path], classpath: str, work_dir: Path,
                   timeout: int = 600) -> dict[str, object]:
    """Compile loose scripts with RC8's own Janino (ROADMAP P15 item 22.1): the ground truth the
    `loose-script-janino-risk` pattern only guesses at. Source roots are the mod and the vanilla core
    (vanilla loose scripts resolve as the game's do); the parent classpath is javac's. Returns
    {"status": PASS|FAIL|UNAVAILABLE, "failures": {relative file: message}, "checked": n}."""
    import subprocess

    if vanilla_core is None:
        return {"status": "UNAVAILABLE", "reason": "no --vanilla-core, so no janino.jar", "failures": {}, "checked": 0}
    jars = [Path(vanilla_core) / name for name in _JANINO_JARS]
    if not all(jar.is_file() for jar in jars) or not _JANINO_HARNESS.is_file():
        return {"status": "UNAVAILABLE", "reason": "janino.jar / commons-compiler.jar not found in the vanilla core", "failures": {}, "checked": 0}
    if not sources:
        return {"status": "PASS", "failures": {}, "checked": 0}
    janino_cp = os.pathsep.join(str(jar) for jar in jars)
    harness = run_javac(jdk_javac, janino_cp, [_JANINO_HARNESS], work_dir / "janino-harness")
    if harness.returncode != 0:
        return {"status": "UNAVAILABLE", "reason": "could not compile the Janino harness", "failures": {}, "checked": 0}
    by_class = {".".join(source.relative_to(root).with_suffix("").parts): source.relative_to(root).as_posix() for source in sources}
    java = jdk_javac.with_name("java.exe" if jdk_javac.suffix.lower() == ".exe" else "java")
    completed = subprocess.run(
        [str(java), "-cp", os.pathsep.join([janino_cp, str(work_dir / "janino-harness")]), "JaninoCheck",
         os.pathsep.join([str(root), str(vanilla_core)]), ",".join(by_class), classpath],
        capture_output=True, text=True, check=False, timeout=timeout,
    )
    failures: dict[str, str] = {}
    seen = 0
    for line in completed.stdout.splitlines():
        if line.startswith("JANINO_OK "):
            seen += 1
        elif line.startswith("JANINO_FAIL "):
            seen += 1
            name, _, message = line[len("JANINO_FAIL "):].partition(" :: ")
            failures[by_class.get(name, name)] = message.strip()
    if seen < len(by_class):
        return {"status": "UNAVAILABLE", "reason": ("Janino harness stopped early: " + completed.stderr.strip())[:400], "failures": failures, "checked": seen}
    return {"status": "FAIL" if failures else "PASS", "failures": failures, "checked": seen}


def compile_loose_scripts(root: Path, vanilla_core: Path | None = None, jdk: Path | None = None, provider_roots: list[Path] | None = None) -> dict:
    """Compile a mod's loose scripts against RC8 with javac; return a JSON-serialisable result.

    Written so the scanner (or anything else) can call this one function directly to get
    findings-ready data, without duplicating classpath/compile logic; it does not itself touch
    scanner.py or emit ScanResult findings.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"{root} is not an existing directory.")
    base = {"schema_version": SCHEMA_VERSION, "mode": "COMPILE_CHECK", "mod": str(root), "vanilla_core": str(vanilla_core) if vanilla_core else None}

    jdk_info = find_jdk(jdk)
    if jdk_info is None:
        return {
            **base, "status": "UNAVAILABLE",
            "reason": "No JDK found (checked --jdk, In operation/_rig/jdk-*, JAVA_HOME, PATH).",
            "files": [], "errors": [], "error_count": 0, "error_counts_by_kind": {}, "classpath": {}, "janino_gap_warnings": [],
        }

    sources = discover_loose_scripts(root)
    classpath_result = assemble_classpath(root, vanilla_core, provider_roots)
    base["jdk"] = {"home": str(jdk_info.home), "source": jdk_info.source}
    base["classpath"] = classpath_result.summary()

    if not sources:
        return {**base, "status": "PASS", "reason": "No loose scripts (data/**.java) found.", "files": [], "errors": [], "error_count": 0, "error_counts_by_kind": {}, "janino_gap_warnings": []}

    companions = vanilla_loose_scripts(vanilla_core) if vanilla_core is not None else []
    base["vanilla_loose_script_companions"] = len(companions)
    with tempfile.TemporaryDirectory(prefix="bf-compile-check-") as tmp:
        run = run_javac(jdk_info.javac, classpath_result.classpath(), sources + companions, Path(tmp) / "classes")
        # Janino only for scripts javac accepted and the game actually compiles (not shadowed by a jar);
        # the rest already carry a javac error or never load.
        javac_failed = {str(error["file"]) for error in run.errors}
        from .scanner import mod_jar_class_names as _jar_names

        _shadow = _jar_names(root)
        janino_sources = [source for source in sources if str(source) not in javac_failed
                          and ".".join(source.relative_to(root).with_suffix("").parts) not in _shadow]
        janino = janino_compile(jdk_info.javac, vanilla_core, root, janino_sources, classpath_result.classpath(), Path(tmp))

    # A loose script with the same class name as one already compiled into the mod's own jar never
    # actually gets Janino-compiled by the game (it loads the jar's class and skips the loose copy --
    # see scanner.mod_jar_class_names / the loose-script-shadowed-by-jar finding), so an
    # error in it here is not a real launch blocker. Real case (Thule-Legacy, 2026-09-22): its
    # TLPlugin.java references Nexerelin's package, an intentionally undeclared soft dependency (an
    # isModEnabled guard gates the only call), so it never compiles clean without declaring Nexerelin
    # hard-required -- but the shipped jar's own, unrelated TLPlugin.class is what the game actually
    # loads, so this was reporting a compile-check FAIL for a script that can't block the game.
    from .scanner import mod_jar_class_names

    mod_source_paths = {str(source) for source in sources}
    # mod_jar_class_names re-reads every jar; call it once for the whole mod, not once per source
    # (a per-source call here made compile-check quadratic in loose-script count on a big mod).
    jar_classes = mod_jar_class_names(root)
    shadowed_source_paths = {
        str(source) for source in sources
        if ".".join(source.relative_to(root).with_suffix("").parts) in jar_classes
    }
    all_mod_errors = [error for error in run.errors if error["file"] in mod_source_paths]
    mod_errors = [error for error in all_mod_errors if error["file"] not in shadowed_source_paths]
    shadowed_errors = [error for error in all_mod_errors if error["file"] in shadowed_source_paths]
    shadowed = dependency_shadowed_scripts(root, sources, classpath_result.dependency_jars)
    shadowed_files = {entry["file"] for entry in shadowed}
    shadowed_paths = {str(source) for source in sources if source.relative_to(root).as_posix() in shadowed_files}
    # The game never compiles a dependency-shadowed script, so its javac errors cannot fail a load.
    dependency_shadowed_errors = [error for error in run.errors if error["file"] in shadowed_paths]
    mod_errors = [error for error in mod_errors if error not in dependency_shadowed_errors]
    vanilla_errors = [error for error in run.errors if error["file"] not in mod_source_paths]
    error_counts = Counter(str(error["kind"]) for error in mod_errors)
    shadowed_rel = {Path(p).relative_to(root).as_posix() for p in shadowed_paths}
    janino["failures"] = {rel: msg for rel, msg in janino["failures"].items() if rel not in shadowed_rel}
    if janino["status"] == "FAIL" and not janino["failures"]:
        janino["status"] = "PASS"
    return {
        **base,
        "status": "PASS" if not mod_errors and janino["status"] != "FAIL" else "FAIL",
        "janino": janino,
        "files": [str(source.relative_to(root)).replace("\\", "/") for source in sources],
        "errors": mod_errors,
        "error_count": len(mod_errors),
        "error_counts_by_kind": dict(error_counts),
        "javac_returncode": run.returncode,
        # Errors in a jar-shadowed loose script: real evidence the source is stale/RC8-incompatible,
        # but never a launch blocker (see the comment above) - not counted in status/error_count.
        "jar_shadowed_errors": shadowed_errors,
        "shadowed_by_dependency": shadowed,
        "shadowed_file_errors": dependency_shadowed_errors,
        # Should normally be empty: these are RC8's own loose scripts, compiled only so the mod's
        # scripts can resolve symbols from them (see vanilla_loose_scripts()). A non-empty list here
        # is a red flag about the reference --vanilla-core/classpath, not about the mod.
        "vanilla_companion_errors": vanilla_errors,
        "janino_gap_warnings": _janino_gap_warnings(sources, root),
        "janino_note": (
            "PASS reflects javac, not the game's runtime compiler (Janino): javac accepts Java syntax Janino "
            "predates and rejects at load time (generics, lambdas, diamond, try-with-resources, multi-catch, "
            "var). A javac PASS with janino_gap_warnings entries is not proof the flagged file loads cleanly."
        ),
    }
