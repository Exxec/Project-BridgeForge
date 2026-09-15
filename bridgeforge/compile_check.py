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

import re
import tempfile
from collections import Counter
from pathlib import Path

from .java_toolchain import assemble_classpath, find_jdk, run_javac

SCHEMA_VERSION = 1

# Cheap (regex, not a parser), comment-blanked signs of Java 8+ syntax Janino predates/rejects:
# a lambda, a method reference, the diamond operator, try-with-resources, multi-catch, `var`.
# False positives/negatives are expected; this is a warning, not a verdict.
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

    mod_source_paths = {str(source) for source in sources}
    mod_errors = [error for error in run.errors if error["file"] in mod_source_paths]
    vanilla_errors = [error for error in run.errors if error["file"] not in mod_source_paths]
    error_counts = Counter(str(error["kind"]) for error in mod_errors)
    return {
        **base,
        "status": "PASS" if not mod_errors else "FAIL",
        "files": [str(source.relative_to(root)).replace("\\", "/") for source in sources],
        "errors": mod_errors,
        "error_count": len(mod_errors),
        "error_counts_by_kind": dict(error_counts),
        "javac_returncode": run.returncode,
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
