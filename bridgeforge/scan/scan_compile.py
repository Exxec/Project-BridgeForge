"""Loose-script Janino risk, dependency version conflicts and the compile-check scan."""
from __future__ import annotations

import re
from ..models import ScanResult
from pathlib import Path
from .scan_classfile import _dependency_jar_class_names, mod_jar_class_names
from .scan_common import _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _load_lenient_json_file


LOOSE_SCRIPT_JANINO_PATTERNS = (
    ("typed-for-each", re.compile(r"\bfor\s*\(\s*(?:final\s+)?(?!Object\b)([A-Za-z_][\w.]*(?:\s*<[^>;]*>)?(?:\s*\[\s*\])*)\s+\w+\s*:(?!:)")),
    ("diamond", re.compile(r"\bnew\s+[A-Za-z_][\w.]*\s*<\s*>")),
    ("lambda", re.compile(r"(?:\)|\b[A-Za-z_]\w*)\s*->")),
)


def _version_major_of(version) -> str:
    if isinstance(version, dict):
        return str(version.get("major", "")).strip()
    return str(version or "").strip().split(".")[0]


def dependency_version_major_conflicts(root: Path, provider_roots: list[Path] | None) -> list[dict]:
    """Declared dependencies whose version has another major than every provider with that id (RC8-23: the launcher
    drops the mod without a log line; zzz Bingus Sustem wanted IndEvo 3.0.c and US 0.43 against 4.1.b and 3.0.3).
    A provider with the same major counts as a match, so a mods folder holding several versions does not flag."""
    from ..substitutes import provider_index

    if not provider_roots:
        return []
    info = _load_lenient_json_file(Path(root) / "mod_info.json")
    declared = [d for d in (info.get("dependencies") if isinstance(info, dict) else None) or [] if isinstance(d, dict) and d.get("id")]
    if not declared:
        return []
    by_id: dict[str, list] = {}
    for provider in provider_index([Path(entry) for entry in provider_roots], exclude=Path(root)):
        by_id.setdefault(provider.mod_id, []).append(provider)
    conflicts = []
    for dep in declared:
        wanted = _version_major_of(dep.get("version"))
        providers = by_id.get(dep["id"])
        if not wanted or not providers:
            continue
        majors = {_version_major_of(p.version) for p in providers if p.version}
        if majors and wanted not in majors:
            conflicts.append({"id": dep["id"], "declared": dep.get("version"), "provider": sorted(p.version for p in providers if p.version)[-1]})
    return conflicts


def _scan_dependency_version_major(root: Path, result: ScanResult, provider_roots: list[Path] | None) -> None:
    for conflict in dependency_version_major_conflicts(root, provider_roots):
        result.add(
            id="dependency-version-major-mismatch",
            category="dependencies",
            severity="high",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=f"mod_info.json asks for {conflict['id']} {conflict['declared']}, but the provider available is "
                        f"{conflict['provider']}: another major version. RC8's launcher then disables this mod at startup without a "
                        "log line (RC8-23). If the mod was tested against the available provider, `fix` sets the declared version to it.",
            file="mod_info.json",
            evidence=[f"dependency:{conflict['id']}", f"declared:{conflict['declared']}", f"provider:{conflict['provider']}"],
        )


def _scan_loose_script_janino_risk(root: Path, result: ScanResult, provider_roots: list[Path] | None = None) -> None:
    """Loose .java under data/ is compiled at runtime by Janino, which ignores generics (live bug PRB-MISSION-02).

    A for-each over a generic collection (element typed as Object -> String), a diamond or a lambda is a
    Fatal dialog before the main menu. Vanilla's 116 loose scripts use none of these; they iterate with
    raw iterators and explicit casts. REVIEW, not MANUAL: a for-each over an array does compile.

    A loose script whose class is also in a loaded jar is never compiled: the game loads the jar class
    and logs "already loaded (perhaps from jar file) ... skipping compilation". Mirfak Parcel Service
    ships both, so those are reported once as shadowed instead of as Janino risks.

    ROADMAP P14 item 12 (found 2026-09-20 on Maelstrom Interstellar Imperium Unofficial Expansion,
    escalation E8): the same classloader-sharing rule applies across mods too - a script that
    overrides a *declared dependency's* jar-compiled class is shadowed exactly the same way, but the
    mod's own jars aren't the only jar that can supply the class. `dependency_classes` extends the
    same detection to every declared dependency's provider jars.
    """
    jar_classes = mod_jar_class_names(root)
    dependency_classes = _dependency_jar_class_names(root, provider_roots)
    shadowed: list[str] = []
    dependency_shadowed: dict[str, str] = {}  # relative path -> shadowing dependency's name
    for source in sorted((root / "data").rglob("*.java")) if (root / "data").is_dir() else []:
        class_name = ".".join(source.relative_to(root).with_suffix("").parts)
        if class_name in jar_classes:
            shadowed.append(_relative(root, source))
            continue
        if class_name in dependency_classes:
            dependency_shadowed[_relative(root, source)] = dependency_classes[class_name]
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        evidence: list[str] = []
        for kind, pattern in LOOSE_SCRIPT_JANINO_PATTERNS:
            for match in pattern.finditer(text):
                evidence.append(f"line:{text.count(chr(10), 0, match.start()) + 1}:{kind}")
        if evidence:
            result.add(
                id="loose-script-janino-risk",
                category="scripts",
                severity="high",
                classification="REVIEW",
                confidence="HEURISTIC",
                explanation="This loose script is compiled at runtime by the game's Janino compiler, which ignores generics and predates lambdas. A for-each over a generic collection (the element reads as Object), a diamond <> or a lambda fails to compile, and the game shows a Fatal dialog before the main menu. Rewrite it the way vanilla loose scripts are written: a raw Iterator with explicit casts. A for-each over an array is fine.",
                file=_relative(root, source),
                evidence=sorted(set(evidence), key=lambda item: int(item.split(":")[1]))[:20],
            )
    if shadowed:
        result.add(
            id="loose-script-shadowed-by-jar",
            category="scripts",
            severity="info",
            classification="SAFE",
            confidence="HIGH",
            explanation="These loose scripts have the same class name as a class in the mod's loaded jar. The game loads the jar class and skips compiling the loose copy (starsector.log: 'already loaded (perhaps from jar file) ... skipping compilation'), so their Janino risks don't apply and edits to them have no effect. Change the jar (or its source) instead.",
            evidence=[f"count:{len(shadowed)}", *shadowed[:10]],
        )
    for path, provider_name in sorted(dependency_shadowed.items()):
        result.add(
            id="loose-script-shadowed-by-dependency-jar",
            category="dependencies",
            severity="high",
            classification="MANUAL",
            confidence="HIGH",
            explanation=f"This loose script has the same class name as a compiled class already in the declared dependency {provider_name}'s own jar. All mod jars share one classloader, so the game loads {provider_name}'s class first and skips compiling this override (starsector.log: 'already loaded (perhaps from jar file) ... skipping compilation') - the override silently has no effect. Either patch {provider_name}'s jar (or its source, if you can rebuild it) instead, or drop this loose copy.",
            file=path,
            evidence=[f"shadowed by: {provider_name}"],
        )


def _format_compile_error(error: dict[str, object]) -> str:
    detail = error.get("detail") or []
    symbol = next((str(item).split(":", 1)[1].strip() for item in detail if str(item).startswith("symbol:")), None)
    text = f"line {error.get('line')}: {error.get('message')}"
    return f"{text} (symbol: {symbol})" if symbol else text


def _scan_compile_check(root: Path, result: ScanResult, vanilla_core: Path | None, provider_roots: list[Path] | None = None) -> None:
    """Opt-in (`scan --compile-check`): javac-compile the mod's loose scripts against RC8.

    Off by default so a plain scan stays fast and hermetic; `bridgeforge.compile_check` does the
    actual compile (see its module docstring for the Janino caveat). Real cases (2026-09-15):
    Renis-Imperium, AI-War, Argamede-Union and EZFaction were each marked ready by every other
    check and failed only this one.

    `provider_roots` (ROADMAP P14 item 29, found during item 23's full corpus recheck 2026-09-21):
    without it, a mod with a declared dependency (LazyLib, MagicLib, a base mod) gets misleading
    missing-symbol errors here, because `compile_loose_scripts` otherwise defaults to
    `DEFAULT_PROVIDER_ROOTS` (`<repo>/In operation` and its rig's mods) rather than whatever the
    caller actually wants searched - a mod whose declared dependency lives outside that default
    (e.g. a base mod only in the real Starsector install's own `mods/` folder, as
    `Maelstrom-Interstellar-Imperium-Unofficial-Expansion` does) got a false FAIL under the plain
    default. Passing `None` keeps that same default; a caller that knows a wider provider set should
    supply it explicitly.
    """
    if vanilla_core is None:
        result.add(
            id="loose-script-compile-unavailable",
            category="build",
            severity="medium",
            classification="UNKNOWN",
            confidence="DETERMINISTIC",
            explanation="--compile-check was requested but no --vanilla-core was given, so loose scripts could not be compiled against RC8's API.",
        )
        return
    from ..compile_check import compile_loose_scripts  # local: avoids a scanner<->compile_check<->java_toolchain import cycle

    outcome = compile_loose_scripts(root, vanilla_core=vanilla_core, provider_roots=provider_roots)
    if outcome["status"] == "UNAVAILABLE":
        result.add(
            id="loose-script-compile-unavailable",
            category="build",
            severity="medium",
            classification="UNKNOWN",
            confidence="DETERMINISTIC",
            explanation=str(outcome.get("reason") or "No JDK was available to compile-check this mod's loose scripts."),
        )
        return
    for entry in outcome.get("shadowed_by_dependency") or []:
        result.add(
            id="loose-script-shadowed-by-dependency-jar",
            category="scripts",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation=f"A declared dependency ({entry['dependency']}) already compiles this class into its jar. All mod jars share one classloader, so the game loads the dependency's class and never compiles this loose file: whatever this file changes has no effect in game. Port the change another way (a differently named class the mod registers itself) or drop the file.",
            file=str(entry["file"]),
            evidence=[f"class:{entry['class']}", f"supplied by:{entry['supplied_by']}"],
        )
    _apply_janino_outcome(root, result, outcome.get("janino") or {})
    if not outcome.get("errors"):
        return
    errors_by_file: dict[str, list[dict[str, object]]] = {}
    for error in outcome["errors"]:
        errors_by_file.setdefault(str(error["file"]), []).append(error)
    for file_path, errors in sorted(errors_by_file.items()):
        try:
            rel = _relative(root, Path(file_path))
        except ValueError:
            # javac echoes paths as given; an alias of root (Windows 8.3 name, symlink) only matches once resolved.
            try:
                rel = _relative(root, Path(file_path).resolve())
            except ValueError:
                rel = file_path
        evidence = [_format_compile_error(error) for error in errors[:5]]
        if len(errors) > 5:
            evidence.append(f"... {len(errors) - 5} more")
        result.add(
            id="loose-script-compile-error",
            category="build",
            severity="critical",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation=f"javac rejects this loose script against RC8 ({len(errors)} error(s)); the game's own class loader would fail the same way at startup.",
            file=rel,
            evidence=evidence,
        )


def _apply_janino_outcome(root: Path, result: ScanResult, janino: dict) -> None:
    """Replace the `loose-script-janino-risk` guess with RC8's own Janino (ROADMAP P15 item 22.1).

    Evidence (2026-09-27, compile_check.janino_compile on RC8's janino.jar 2.7.8): a typed for-each
    over `List<String>` whose element calls a String method compiles; a lambda fails ("Unexpected
    token"), and so does calling a method on a generic-typed value (`e.getValue().size()` on a
    `Map.Entry<String, List<String>>`: "A method named size is not declared"), because Janino erases
    generics to Object. Yunru's Unpack Blueprints' original, flagged for 9 typed loops, compiles.
    So a file Janino accepted drops its risk finding, and a file it rejected gets a MANUAL error.
    """
    if janino.get("status") not in ("PASS", "FAIL"):
        return
    failures = janino.get("failures") or {}
    checked_ok = set()
    if janino.get("checked"):
        risky = {f.file for f in result.findings if f.id == "loose-script-janino-risk"}
        checked_ok = {path for path in risky if path not in failures}
    result.findings[:] = [f for f in result.findings if not (f.id == "loose-script-janino-risk" and f.file in checked_ok)]
    for rel, message in sorted(failures.items()):
        result.add(
            id="loose-script-janino-compile-error",
            category="build",
            severity="critical",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="RC8's own runtime compiler (Janino 2.7.8, run offline on the game's janino.jar) rejects this loose script, so the game shows a Fatal dialog before the main menu. javac accepts it. Janino erases generics to Object and has no lambdas: cast values whose type comes from generics before calling their methods, and replace lambdas with anonymous classes.",
            file=rel,
            evidence=[message[:400]],
        )
