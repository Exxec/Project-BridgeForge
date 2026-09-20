"""Shared Java toolchain support for `compile-check` and `rebuild-jar`.

Three things every javac-backed BridgeForge command needs, factored out so both share one
implementation: JDK discovery (explicit `--jdk` first, then this repo's rig, then JAVA_HOME,
then PATH), classpath assembly (RC8 core + a mod's own jars + its declared dependencies' jars,
found via `substitutes.provider_index`), and a javac runner that parses diagnostics into
structured records instead of leaving callers to grep stderr.

Standard library only. Never writes into a mod's working copy: callers choose the output
directory for compiled classes, always outside the mod tree unless they say otherwise.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .scanner import _load_lenient_json_file
from .substitutes import provider_index

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROVIDER_ROOTS = (REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods")

# A mod's own jar discovery mirrors scanner._loaded_mod_jars (mod_info.json's "jars" list first,
# else every jar outside build-output/disabled dirs) but is reimplemented here rather than
# imported, so this module has no dependency on scanner.py beyond the mandated lenient-JSON reader.
_NON_MOD_JAR_DIRS = {"build", "out", "tmp", "target", "disabled_files"}


class JavaToolchainError(RuntimeError):
    """Raised for a refused or unusable Java toolchain request."""


@dataclass(frozen=True)
class JdkInfo:
    home: Path
    javac: Path
    javap: Path
    jar: Path
    source: str  # "explicit" | "repo-rig" | "JAVA_HOME" | "PATH"


def find_jdk(explicit: Path | None = None, repo_root: Path | None = None) -> JdkInfo | None:
    """Locate a JDK with a working javac. Order: explicit --jdk, this repo's rig, JAVA_HOME, PATH.

    Returns None rather than raising, so callers can report an UNAVAILABLE status instead of a
    crash when no JDK is installed (e.g. on a CI runner with no Java toolchain configured).
    """
    root = Path(repo_root).expanduser().resolve() if repo_root is not None else REPO_ROOT
    candidates: list[tuple[Path, str]] = []
    if explicit is not None:
        candidates.append((Path(explicit), "explicit"))
    rig = root / "In operation" / "_rig"
    if rig.is_dir():
        for entry in sorted(rig.glob("jdk-*")):
            candidates.append((entry, "repo-rig"))
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append((Path(java_home), "JAVA_HOME"))
    which_javac = shutil.which("javac")
    if which_javac:
        candidates.append((Path(which_javac).resolve().parent.parent, "PATH"))
    exe = ".exe" if os.name == "nt" else ""
    for home, source in candidates:
        try:
            home = home.expanduser().resolve()
        except OSError:
            continue
        javac = home / "bin" / f"javac{exe}"
        if javac.is_file():
            return JdkInfo(home=home, javac=javac, javap=home / "bin" / f"javap{exe}", jar=home / "bin" / f"jar{exe}", source=source)
    return None


@dataclass
class ClasspathResult:
    core_jars: list[str] = field(default_factory=list)
    mod_jars: list[str] = field(default_factory=list)
    dependency_jars: dict[str, list[str]] = field(default_factory=dict)  # declared dependency id -> jars found
    dependencies_missing: list[str] = field(default_factory=list)  # declared dependency ids with no provider/no jars
    providers_indexed: int = 0

    def entries(self, exclude: set[str] | None = None) -> list[str]:
        """Classpath entries in order (core, mod, dependencies), de-duplicated, minus `exclude`."""
        ordered = list(self.core_jars) + list(self.mod_jars)
        for jars in self.dependency_jars.values():
            ordered.extend(jars)
        excluded = {str(Path(item).resolve()) for item in (exclude or set())}
        seen: dict[str, None] = {}
        for entry in ordered:
            if str(Path(entry).resolve()) in excluded:
                continue
            seen.setdefault(entry, None)
        return list(seen)

    def classpath(self, exclude: set[str] | None = None) -> str:
        return os.pathsep.join(self.entries(exclude))

    def summary(self) -> dict[str, object]:
        return {
            "core_jar_count": len(self.core_jars),
            "mod_jars": list(self.mod_jars),
            "dependencies_found": {dep: jars for dep, jars in self.dependency_jars.items() if jars},
            "dependencies_missing": list(self.dependencies_missing),
            "providers_indexed": self.providers_indexed,
        }


def _mod_jars(folder: Path) -> list[Path]:
    """Jars one mod folder ships: its own mod_info.json "jars" list, else every jar under it."""
    info_path = folder / "mod_info.json"
    info = _load_lenient_json_file(info_path) if info_path.is_file() else None
    declared = info.get("jars") if isinstance(info, dict) else None
    if isinstance(declared, list):
        jars = [folder / entry for entry in declared if isinstance(entry, str) and (folder / entry).is_file()]
        if jars:
            return sorted(jars)
    return sorted(
        jar for jar in folder.rglob("*.jar")
        if not _NON_MOD_JAR_DIRS.intersection(part.lower() for part in jar.relative_to(folder).parts[:-1])
    )


def declared_dependencies(mod_dir: Path) -> list[str]:
    """Dependency ids from mod_info.json's "dependencies" list (each item a dict with an "id")."""
    info_path = mod_dir / "mod_info.json"
    info = _load_lenient_json_file(info_path) if info_path.is_file() else None
    deps = info.get("dependencies") if isinstance(info, dict) else None
    if not isinstance(deps, list):
        return []
    ids: list[str] = []
    for entry in deps:
        if isinstance(entry, dict) and entry.get("id"):
            ids.append(str(entry["id"]))
        elif isinstance(entry, str) and entry.strip():
            ids.append(entry.strip())
    return ids


def assemble_classpath(mod_dir: Path, vanilla_core: Path | None, provider_roots: list[Path] | None = None) -> ClasspathResult:
    """Every jar in the core folder, the mod's own jars, and each declared dependency's jars.

    Dependency folders are found with `substitutes.provider_index`/its mod_id index, using
    `provider_roots` (default: <repo>/In operation and its rig's mods folder) -- the same default
    `dependency-substitutes` uses. A declared dependency with no matching provider, or a provider
    folder with no jars, is reported in `dependencies_missing` rather than silently dropped.
    """
    mod_dir = Path(mod_dir).expanduser().resolve()
    result = ClasspathResult()
    if vanilla_core is not None:
        core = Path(vanilla_core).expanduser().resolve()
        if not core.is_dir():
            raise JavaToolchainError(f"{core} is not an existing directory; is this a starsector-core path?")
        result.core_jars = sorted(str(jar) for jar in core.glob("*.jar"))
    result.mod_jars = sorted(str(jar) for jar in _mod_jars(mod_dir))
    deps = declared_dependencies(mod_dir)
    if deps:
        roots = [Path(entry) for entry in (provider_roots if provider_roots else DEFAULT_PROVIDER_ROOTS)]
        providers = provider_index(roots, exclude=mod_dir)
        result.providers_indexed = len(providers)
        by_id = {provider.mod_id: provider for provider in providers}
        for dep_id in deps:
            provider = by_id.get(dep_id)
            jars = sorted(str(jar) for jar in _mod_jars(Path(provider.path))) if provider is not None else []
            if jars:
                result.dependency_jars[dep_id] = jars
            else:
                result.dependencies_missing.append(dep_id)
    return result


# --- javac execution and diagnostic parsing -------------------------------------------------

# javac error headers: "<file>.java:<line>: error: <message>". Non-greedy up to ".java" so a
# Windows drive-letter colon ("C:\Users\...\Foo.java:12: error: ...") is not mistaken for the
# line-number separator.
_ERROR_HEADER = re.compile(r"^(?P<file>.*?\.java):(?P<line>\d+): error: (?P<message>.*)$")
# javac can also report diagnostics for sources bundled INSIDE a classpath jar, printed as
# "C:\\...\\II.jar(/data/scripts/Foo.java):12: error: ...". _ERROR_HEADER deliberately does not
# match these (the ")" defeats it), which used to leave `current` pointing at the previous real
# error so every following "symbol:"/"location:" line was appended to its detail list -- one
# genuine error once accumulated 726 spurious entries. `-sourcepath ""` above stops javac
# compiling them at all; this pattern is the guard for any that still appear. They are never
# the mod under test's errors, so they are skipped rather than recorded.
_JAR_EMBEDDED_HEADER = re.compile(r"^.*?\.jar\([^)]*\.java\):\d+: (?:error|warning): ")
# The "symbol:"/"location:" continuation lines javac prints under an error, indented.
_DETAIL_LINE = re.compile(r"^\s+(symbol|location):\s*(.*)$")

# `-sourcepath ""` is load-bearing (ROADMAP P14 item 13): some mods ship .java sources INSIDE
# their jar beside the .class files (Interstellar Imperium's II.jar does). Without an empty
# sourcepath, javac's default source-preference finds those entries on the classpath and tries
# to recompile them, reporting errors for libraries the mod under test never declared. Every
# caller passes its sources explicitly (compile_check and rebuild_jar both rglob the whole
# tree), so nothing relies on implicit source lookup.
DEFAULT_JAVAC_ARGS = (
    "--release", "17", "-proc:none", "-nowarn", "-encoding", "UTF-8", "-Xmaxerrs", "10000", "-sourcepath", "",
)


def _classify_error(message: str) -> str:
    if "cannot find symbol" in message:
        return "missing-symbol"
    if "cannot be applied" in message:
        return "cannot-be-applied"
    if "incompatible types" in message:
        return "incompatible-types"
    return "other"


def parse_javac_errors(stderr: str) -> list[dict[str, object]]:
    """Parse javac's stderr into structured records: file, line, kind, message, detail lines.

    Needs no JDK to run -- it operates purely on captured text, so it can be unit tested with a
    fixture string. Only "error:" lines are recorded; warnings are ignored (-nowarn suppresses
    most, and `compile-check`/`rebuild-jar` only need failures).
    """
    errors: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for line in stderr.splitlines():
        if _JAR_EMBEDDED_HEADER.match(line):
            current = None
            continue
        header = _ERROR_HEADER.match(line)
        if header:
            current = {
                "file": header.group("file"),
                "line": int(header.group("line")),
                "kind": _classify_error(header.group("message")),
                "message": header.group("message").strip(),
                "detail": [],
            }
            errors.append(current)
            continue
        if current is None:
            continue
        detail = _DETAIL_LINE.match(line)
        if detail:
            current["detail"].append(f"{detail.group(1)}: {detail.group(2)}".strip())
    return errors


@dataclass
class JavacRun:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str
    errors: list[dict[str, object]]

    @property
    def success(self) -> bool:
        return self.returncode == 0


def run_javac(javac: Path, classpath: str, sources: list[Path], out_dir: Path, extra_args: list[str] | None = None) -> JavacRun:
    """Compile `sources` with javac, using an @argument file so Windows path spaces/length never bite.

    Applies DEFAULT_JAVAC_ARGS (`--release 17 -proc:none -nowarn -encoding UTF-8 -Xmaxerrs 10000`);
    `extra_args`, if given, are appended after them.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    args = list(DEFAULT_JAVAC_ARGS)
    if extra_args:
        args += list(extra_args)
    if classpath:
        args += ["-cp", classpath]
    args += ["-d", str(out_dir)]
    args += [str(source) for source in sources]
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".javac-args", delete=False) as handle:
        for argument in args:
            handle.write('"' + argument.replace("\\", "\\\\").replace('"', '\\"') + '"\n')
        argfile = Path(handle.name)
    try:
        completed = subprocess.run([str(javac), "@" + str(argfile)], capture_output=True, text=True, check=False)
    finally:
        argfile.unlink(missing_ok=True)
    return JavacRun(
        command=[str(javac), *args],
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        errors=parse_javac_errors(completed.stderr),
    )
