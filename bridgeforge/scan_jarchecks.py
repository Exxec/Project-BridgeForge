"""Jar-level checks: linkage, sandbox-forbidden API, bundled library classes, vanilla duplicates, stale bundled source."""
from __future__ import annotations

import json
import re
import zipfile
from .models import ScanResult
from .zipsafe import MAX_CLASS_BYTES, read_limited
from collections import Counter
from pathlib import Path
from .scan_classfile import _ClassFileInfo, _iter_jar_class_files, _loaded_mod_jars, _parse_class_file
from .scan_common import BUNDLED_LIBRARY_PACKAGE_PREFIXES, FORBIDDEN_IO_CLASSES, FORBIDDEN_NIO_FILE_PREFIX, FORBIDDEN_REFLECT_PREFIX, FORBIDDEN_SANDBOX_SOURCE_PATTERN, MAX_JAR_ENTRIES, _relative
from .scan_javatext import _blank_java_comments
from .scan_json import _load_lenient_json_file, _read_csv_rows_lenient


def _scan_jar_linkage(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """jar-linkage-unresolved: a declared jar calls a game method or field RC8 does not have (bridgeforge/linkage.py).
    Too Much Information's beginTable(...)V (RC8 returns UIPanelAPI) is a NoSuchMethodError the first time the tooltip
    draws. Over the 79 live-validated mods in Done/ (2026-09-30) it found only addImageWithText in four, the same
    return-type change on tooltip paths the probe does not open, once jars of the rig's other mods count as
    providers (SEEKER's NGCAddStartingShipsByFleetType is Nexerelin's, squatting a game package)."""
    declared = result.metadata.get("jars")
    if vanilla_core is None or not isinstance(declared, list):
        return
    from .linkage import unresolved_references

    jars = [root / entry for entry in declared if isinstance(entry, str) and (root / entry).is_file()]
    if not jars:
        return
    # Providers: the jars each other rig mod declares, not every jar in its folder (FlowerGod's build/cp held a
    # copy of starfarer.api.jar, which hid every break, 2026-09-30).
    rig_mods = Path(vanilla_core).resolve().parent / "mods"
    others = []
    for info_path in sorted(rig_mods.glob("*/mod_info.json")) if rig_mods.is_dir() else []:
        info = _load_lenient_json_file(info_path) or {}
        if not isinstance(info, dict) or info.get("id") == result.metadata.get("id"):
            continue
        others += [info_path.parent / j for j in info.get("jars") or [] if isinstance(j, str) and (info_path.parent / j).is_file()]
    for entry, problems in unresolved_references(jars, vanilla_core, others).items():
        jar_name, _, member = entry.partition("!")
        jar_rel = next(_relative(root, j) for j in jars if j.name == jar_name)
        relink = all(p.get("return_type_only") for p in problems)
        evidence = [f"{p['owner'].replace('/', '.')}.{p['name']}{p['descriptor'] if p['kind'] != 'class' else ''}"
                    + (f" (RC8: {', '.join(p['candidates'])})" if p.get("candidates") else "") + (" [class missing]" if p["kind"] == "class" else "")
                    for p in problems][:12]
        result.add(
            id="jar-linkage-unresolved",
            category="bytecode",
            severity="high",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=("This class calls game methods whose RC8 signature differs only in return type; it throws NoSuchMethodError "
                         "when that code runs. Recompiling the class against RC8 relinks it with no source change "
                         "(`bridgeforge jar-packets`, then `patch-jar-class`)." if relink else
                         "This class references game classes, methods or fields RC8 does not have (a NoSuchMethodError, "
                         "NoSuchFieldError or NoClassDefFoundError when that code runs). The RC8 candidates are listed; "
                         "port the call, then recompile the class (`bridgeforge jar-packets`, then `patch-jar-class`)."),
            file=f"{jar_rel}!{member}",
            evidence=evidence,
        )


def _scan_jar_interface_methods(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """jar-interface-method-missing: a concrete jar class implements a game interface (or extends an abstract game
    class) without a method RC8 requires: an AbstractMethodError when the game calls it. Polaris Prime, UNGP and
    Wotani (10 on-hit classes) were found only by compiling, 2026-10-01; `bridgeforge port-interfaces` ports the
    known contract changes (onHit's ApplyDamageResultAPI, createCustomDialog's callback, buttonPressed)."""
    declared = result.metadata.get("jars")
    if vanilla_core is None or not isinstance(declared, list):
        return
    from .linkage import missing_interface_methods

    jars = [root / entry for entry in declared if isinstance(entry, str) and (root / entry).is_file()]
    if not jars:
        return
    rig_mods = Path(vanilla_core).resolve().parent / "mods"
    others = []
    for info_path in sorted(rig_mods.glob("*/mod_info.json")) if rig_mods.is_dir() else []:
        info = _load_lenient_json_file(info_path) or {}
        if isinstance(info, dict) and info.get("id") != result.metadata.get("id"):
            others += [info_path.parent / j for j in info.get("jars") or [] if isinstance(j, str) and (info_path.parent / j).is_file()]
    for entry, methods in missing_interface_methods(jars, vanilla_core, others).items():
        jar_name, _, member = entry.partition("!")
        jar_rel = next(_relative(root, j) for j in jars if j.name == jar_name)
        result.add(
            id="jar-interface-method-missing",
            category="bytecode",
            severity="high",
            classification="REVIEW",
            confidence="DETERMINISTIC",
            explanation=("This class implements a game interface or abstract class without a method RC8 requires (an "
                         "AbstractMethodError when the game calls it). Known contract changes are ported by "
                         "`bridgeforge port-interfaces`; others need the method added by hand, then `patch-jar-class`."),
            file=f"{jar_rel}!{member}",
            evidence=[m.replace("/", ".") for m in methods][:8],
        )


def _scan_script_sandbox_forbidden_api(root: Path, result: ScanResult) -> None:
    """RC8's script classloader crashes at runtime the first time a scripted class touches reflection/file I/O."""
    explanation = (
        "RC8's script sandbox classloader throws SecurityException(\"File access and reflection are not allowed "
        "to scripts\") the first time this class is loaded at runtime, because it references java.lang.reflect, "
        "java.nio.file, or a java.io.File-family type. This is lazy (it only surfaces when the class is actually "
        "loaded, which can be mid-combat), so a clean boot does not prove it is safe. Remove the reflection/file-I/O "
        "usage, or move it out of the scripted class, before runtime testing."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        forbidden = sorted(
            name for name in info.referenced_classes
            if name.startswith(FORBIDDEN_REFLECT_PREFIX) or name.startswith(FORBIDDEN_NIO_FILE_PREFIX) or name in FORBIDDEN_IO_CLASSES
        )
        if not forbidden:
            continue
        class_name = (info.this_class or member[:-6]).replace("/", ".")
        result.add(
            id="script-sandbox-forbidden-api",
            category="bytecode",
            severity="critical",
            classification="MANUAL",
            confidence="HIGH",
            explanation=explanation,
            file=_relative(root, jar),
            evidence=[f"class:{class_name}", *[f"forbidden:{name.replace('/', '.')}" for name in forbidden]],
        )

    source_dirs = [root / "data" / "scripts", root / "src"]
    seen_sources: set[Path] = set()
    for source_dir in source_dirs:
        if not source_dir.is_dir():
            continue
        for source in sorted(source_dir.rglob("*.java")):
            if source in seen_sources:
                continue
            seen_sources.add(source)
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                text = source.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Blank comments first (same helper _scan_removed_api_calls uses), so a comment that merely
            # names java.io.File/java.nio.file/java.lang.reflect (to explain the sandbox, or to say they are
            # avoided) doesn't read the same as code that actually references them. Real case: BF Legacy
            # Fleets' own class Javadoc named these APIs to describe what it avoids (2026-09-14).
            matches = sorted(set(FORBIDDEN_SANDBOX_SOURCE_PATTERN.findall(_blank_java_comments(text))))
            if not matches:
                continue
            result.add(
                id="script-sandbox-forbidden-api",
                category="bytecode",
                severity="critical",
                classification="MANUAL",
                confidence="HIGH",
                explanation=explanation,
                file=_relative(root, source),
                evidence=[f"forbidden:{name}" for name in matches[:10]],
            )


def _scan_bundled_library_classes(root: Path, result: ScanResult) -> None:
    """A mod jar can silently absorb another mod/library's compiled classes during a rebuild."""
    for jar in _loaded_mod_jars(root):
        try:
            with zipfile.ZipFile(jar) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_JAR_ENTRIES:
                    continue
                names = [item.filename.replace("\\", "/") for item in entries if item.filename.endswith(".class")]
        except (OSError, zipfile.BadZipFile):
            continue
        counts: Counter[str] = Counter()
        for name in names:
            internal = name[:-6]
            for library, prefixes in BUNDLED_LIBRARY_PACKAGE_PREFIXES.items():
                if any(internal.startswith(prefix) for prefix in prefixes):
                    counts[library] += 1
        for library, count in sorted(counts.items()):
            prefixes = ", ".join(BUNDLED_LIBRARY_PACKAGE_PREFIXES[library])
            result.add(
                id="bundled-library-classes",
                category="dependencies",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=(
                    f"This jar contains {count} compiled class(es) under {library}'s package(s) ({prefixes}). "
                    f"A rebuild that compiles against {library}'s sources found on the classpath can silently "
                    "bundle its classes into this mod's own jar, duplicating them for every player who also has "
                    f"the real {library} installed. Rebuild against {library} as a provided/compile-only "
                    "dependency instead of packaging its classes."
                ),
                file=_relative(root, jar),
                evidence=[f"library:{library}", f"class-count:{count}"],
            )


def _vanilla_api_jar_class_info(vanilla_core: Path) -> dict[str, _ClassFileInfo]:
    classes: dict[str, _ClassFileInfo] = {}
    for jar_name in ("starfarer.api.jar", "starfarer_obf.jar"):
        jar_path = vanilla_core / jar_name
        if not jar_path.is_file():
            continue
        try:
            with zipfile.ZipFile(jar_path) as archive:
                for item in archive.infolist():
                    if not item.filename.endswith(".class"):
                        continue
                    fqn = item.filename.replace("\\", "/")[:-6].replace("/", ".")
                    if fqn in classes:
                        continue
                    try:
                        data = read_limited(archive, item, MAX_CLASS_BYTES)
                    except (OSError, zipfile.BadZipFile, KeyError):
                        continue
                    info = _parse_class_file(data)
                    if info is not None:
                        classes[fqn] = info
        except (OSError, zipfile.BadZipFile):
            continue
    return classes


def _vanilla_loose_script_fqns(vanilla_core: Path) -> set[str]:
    """Every loose vanilla .java source under data/** (not just data/scripts), by path-derived FQN.

    Starsector loads loose scripts from many data/ subdirectories, not only data/scripts (e.g.
    data/shipsystems/scripts/SensorDroneStats.java, referenced by vanilla ship systems). The FQN is
    the path relative to starsector-core with '/' -> '.', minus the .java suffix; when the file
    declares a 'package' line, that is used instead so a mismatched directory layout does not
    produce a false FQN.
    """
    data_root = vanilla_core / "data"
    if not data_root.is_dir():
        return set()
    fqns: set[str] = set()
    for path in data_root.rglob("*.java"):
        relative = path.relative_to(vanilla_core)
        path_fqn = ".".join(relative.with_suffix("").parts)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            fqns.add(path_fqn)
            continue
        package_match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
        if package_match:
            fqns.add(f"{package_match.group(1)}.{path.stem}")
        else:
            fqns.add(path_fqn)
    return fqns


def _scan_vanilla_duplicated_classes(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A mod jar's own copy of a vanilla class replaces the target release's class for every mod loaded after it."""
    if vanilla_core is None:
        return
    vanilla_jar_classes = _vanilla_api_jar_class_info(vanilla_core)
    vanilla_loose_fqns = _vanilla_loose_script_fqns(vanilla_core)
    if not vanilla_jar_classes and not vanilla_loose_fqns:
        return
    for jar, member, data in _iter_jar_class_files(root):
        fqn = member[:-6].replace("/", ".")
        # A mod's own new rulecmd command classes are how rules.csv registers commands; only classes
        # that also exist in vanilla are duplicates, so a brand-new rulecmd class is never flagged here.
        if fqn.startswith("com.fs.starfarer.api.impl.campaign.rulecmd.") and fqn not in vanilla_jar_classes and fqn not in vanilla_loose_fqns:
            continue
        if fqn in vanilla_jar_classes:
            info = _parse_class_file(data)
            if info is None:
                continue
            vanilla_info = vanilla_jar_classes[fqn]
            vanilla_public = {(name, descriptor) for name, descriptor, is_public in vanilla_info.methods if is_public}
            mod_public = {(name, descriptor) for name, descriptor, is_public in info.methods if is_public}
            missing = sorted(f"{name}{descriptor}" for name, descriptor in (vanilla_public - mod_public))
            classification = "MANUAL" if missing else "REVIEW"
            severity = "critical" if missing else "high"
            result.add(
                id="vanilla-class-duplicated-in-jar",
                category="bytecode",
                severity=severity,
                classification=classification,
                confidence="HIGH",
                explanation=(
                    "This mod jar contains its own compiled copy of a vanilla API class, replacing the target "
                    "release's class on the classpath for every mod loaded after it."
                    + (
                        f" The mod's copy is missing {len(missing)} public method(s) the current release's class "
                        "has, so code compiled against the real class fails with NoSuchMethodError at runtime."
                        if missing
                        else " Its public method signatures currently match the target release; confirm this is an "
                        "intentional override rather than a stale copy."
                    )
                ),
                file=_relative(root, jar),
                evidence=[f"class:{fqn}", "vanilla-source:api-jar", *[f"missing-public-method:{m}" for m in missing[:10]]],
            )
        elif fqn in vanilla_loose_fqns:
            result.add(
                id="vanilla-class-duplicated-in-jar",
                category="bytecode",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(
                    "This mod jar contains a compiled class at the same fully-qualified name as a vanilla loose "
                    "script (data/scripts/**/*.java). A compiled class on the classpath takes priority over the "
                    "game's loose script, silently replacing that vanilla script's behavior game-wide, not just "
                    "for this mod."
                ),
                file=_relative(root, jar),
                evidence=[f"class:{fqn}", "vanilla-source:loose-script"],
            )


def _scan_obfuscated_internal_api_use(root: Path, result: ScanResult, vanilla_core: Path | None = None) -> None:
    """com.fs.starfarer classes outside the api package are obfuscated internals renamed each release.

    With RC8's core jars (item 73 F6) each reference is resolved: a class whose every reference exists is reported as
    `obfuscated-internal-api-resolved` (informational, with the count); one with a missing class or member keeps this id and
    names them; references whose hierarchy leaves the core jars stay unverified (this id, nothing claimed)."""
    from .obfuscated_members import classify_internal_references

    core = None
    if vanilla_core is not None:
        from .linkage import core_index

        core = core_index(str(Path(vanilla_core).resolve())) or None
    own = frozenset(name.replace(".", "/") for name in result.compiled_class_names)
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        internal_refs = sorted(
            name.replace("/", ".") for name in info.referenced_classes
            if name.startswith("com/fs/starfarer/") and not name.startswith("com/fs/starfarer/api/")
        )
        if not internal_refs:
            continue
        class_name = (info.this_class or member[:-6]).replace("/", ".")
        verdict = ""
        if core is not None:
            checked = classify_internal_references(data, core, own) or {"missing": [], "unverified": [], "resolved": []}
            # A class named only in a descriptor or cast has no member reference: look it up by name.
            named = [f"class {n}" for n in internal_refs if n.replace(".", "/") not in core and n.replace(".", "/") not in own]
            missing = sorted(set(checked["missing"]) | set(named))
            if not missing and not checked["unverified"]:
                result.add(
                    id="obfuscated-internal-api-resolved", category="bytecode", severity="info", classification="REVIEW", confidence="HIGH",
                    explanation=("Every com.fs.starfarer internal (non-api) class and member this compiled class references exists in RC8's "
                                 "core jars (name and descriptor, read from the class files). Informational: existence is not proof of "
                                 "behaviour."),
                    file=_relative(root, jar), evidence=[f"class:{class_name}", f"resolved:{len(checked['resolved'])}", *[f"internal:{n}" for n in internal_refs[:15]]])
                continue
            verdict = [f"missing:{m}" for m in missing[:15]] + [f"unverified:{u}" for u in checked["unverified"][:5]] + [f"resolved:{len(checked['resolved'])}"]
        result.add(
            id="obfuscated-internal-api-use",
            category="bytecode",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(
                "This compiled class references com.fs.starfarer internal (non-api) classes. Names outside "
                "com.fs.starfarer.api are obfuscated implementation details that get renamed between releases "
                "without notice; verify each reference still resolves against the target release before runtime "
                "testing."
            ),
            file=_relative(root, jar),
            evidence=[f"class:{class_name}", *[f"internal:{name}" for name in internal_refs[:15]], *(verdict or [])],
        )


_REFERENCE_INSTALLS = ("Starsector62", "Starsector7.2", "Starsector8.1", "Starsector9a", "Starsector9.0", "Starsector9.5.1a")


_OLD_VANILLA_CLASSES: dict[str, set[str]] = {}


def _old_vanilla_api_classes(vanilla_core: Path) -> set[str]:
    """Classes any older reference install's starfarer.api.jar shipped (beside RC8's install; CLAUDE.md)."""
    import zipfile

    base = Path(vanilla_core).resolve().parent.parent
    key = str(base)
    if key not in _OLD_VANILLA_CLASSES:
        names: set[str] = set()
        for install in _REFERENCE_INSTALLS:
            jar = base / install / "starsector-core" / "starfarer.api.jar"
            try:
                with zipfile.ZipFile(jar) as archive:
                    names |= {n[:-6] for n in archive.namelist() if n.endswith(".class") and "$" not in n}
            except (OSError, zipfile.BadZipFile):
                continue
        _OLD_VANILLA_CLASSES[key] = names
    return _OLD_VANILLA_CLASSES[key]


def _scan_retired_vanilla_class_copy(root: Path, result: ScanResult, vanilla_core: Path | None) -> None:
    """A mod class in vanilla's own package that an older vanilla shipped and RC8 no longer does (ROADMAP 43).
    Ironclads bundled 0.7.2's SystemBountyEvent unchanged; nothing in the mod started it (0.7's core did), RC8
    replaced it with SystemBountyIntel, so on RC8 it is dead code (2026-10-05). vanilla-class-duplicated-in-jar
    compares only with classes RC8 still has."""
    if vanilla_core is None:
        return
    import zipfile

    old = _old_vanilla_api_classes(vanilla_core)
    if not old:
        return
    try:
        with zipfile.ZipFile(Path(vanilla_core) / "starfarer.api.jar") as archive:
            rc8 = {n[:-6] for n in archive.namelist() if n.endswith(".class")}
    except (OSError, zipfile.BadZipFile):
        return
    for jar in sorted(p for p in root.rglob("*.jar") if "disabled_files" not in p.relative_to(root).parts):
        try:
            with zipfile.ZipFile(jar) as archive:
                names = [n[:-6] for n in archive.namelist() if n.endswith(".class") and "$" not in n]
        except (OSError, zipfile.BadZipFile):
            continue
        for name in names:
            if name.startswith("com/fs/starfarer/api/") and name in old and name not in rc8:
                result.add(
                    id="retired-vanilla-class-copy",
                    category="api",
                    severity="medium",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation=(f"{name.replace('/', '.')} is a copy of a vanilla class an older Starsector shipped "
                                 "and RC8 no longer does. Vanilla's own core started classes like this; on RC8 nothing "
                                 "may, so it is dead code, or it stands in for a system RC8 replaced (Ironclads' "
                                 "SystemBountyEvent: RC8 uses SystemBountyIntel)."),
                    file=f"{_relative(root, jar)}!{name}.class",
                    evidence=[f"class:{name.replace('/', '.')}"],
                )


_SOURCE_ROOTS = ("src", "jars/src", "src/src", "jars/source", "source")


_JAVA_METHOD = re.compile(r"\bpublic\s+(?:static\s+|final\s+|synchronized\s+|abstract\s+)*[\w<>\[\],.?\s]+?\s+(\w+)\s*\(")


def _scan_bundled_source_stale(root: Path, result: ScanResult) -> None:
    """Bundled jar source that does not match the shipped jar (ROADMAP 47). Grytpype & Moriarty's src/ hull mods said
    `implements HullModEffect` where the jar's classes extend BaseHullMod; Tritachyon's src/ had a PeachGarden system
    the jar never shipped (2026-10-05). Source-based findings on such files may describe code that never runs; the jar
    is the truth."""
    jar_classes: dict[str, _ClassFileInfo] = {}
    for _, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and info.this_class and "$" not in info.this_class:
            jar_classes[info.this_class] = info
    if not jar_classes:
        return
    differing, source_only, compared = [], [], 0
    seen: set[Path] = set()
    for rel in _SOURCE_ROOTS:
        base = root / rel
        if not base.is_dir():
            continue
        for source in sorted(base.rglob("*.java")):
            if source in seen or "disabled_files" in source.relative_to(root).parts:
                continue
            seen.add(source)
            try:
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"), strings=True)
            except OSError:
                continue
            package = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.M)
            internal = ((package.group(1).replace(".", "/") + "/") if package else "") + source.stem
            info = jar_classes.get(internal)
            if info is None:
                if re.search(rf"\b(?:class|interface|enum)\s+{re.escape(source.stem)}\b", text):
                    source_only.append(_relative(root, source))
                continue
            compared += 1
            header = re.search(rf"\b(?:class|interface|enum)\s+{re.escape(source.stem)}\b([^{{]*)\{{", text)
            reasons = []
            if header:
                extends = re.search(r"\bextends\s+([\w.]+)", header.group(1))
                source_super = extends.group(1).split(".")[-1] if extends else "Object"
                jar_super = (info.super_class or "java/lang/Object").split("/")[-1]
                if "class" in header.group(0).split(source.stem)[0] and source_super != jar_super:
                    reasons.append(f"extends {source_super} in source, {jar_super} in jar")
            source_methods = set(_JAVA_METHOD.findall(text))
            jar_methods = {name for name, _, public in info.methods if public and not name.startswith(("<", "lambda$", "access$"))}
            # Only methods the jar has and the source lacks: a source-only name is usually an anonymous inner class's
            # method, compiled into a separate $1 class (Exigency's console commands, 2026-10-05).
            missing = sorted(jar_methods - source_methods)
            if missing:
                reasons.append(f"methods only in jar: {', '.join(missing[:3])}")
            if reasons:
                differing.append(f"{_relative(root, source)}: {'; '.join(reasons)}")
    if differing or (source_only and compared):
        result.add(
            id="bundled-source-stale",
            category="source",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(f"The mod's bundled jar source does not match the shipped jar: {len(differing)} of {compared} "
                         f"compared class(es) differ and {len(source_only)} source class(es) are not in any jar. The jar "
                         "is what runs: findings on these source files may describe code that never runs, and a "
                         "source fix must be compiled into the jar (patch-jar-class)."),
            file=None,
            evidence=[f"differ:{len(differing)}", f"source-only:{len(source_only)}", *differing[:4], *[f"not in jar: {s}" for s in source_only[:3]]],
        )


def _scan_rc8_signature_changed(root: Path, result: ScanResult) -> None:
    """Old-form calls with an exact RC8 equivalent (bridgeforge.signature_rewrites; ROADMAP 41, Ironclads 2026-10-04)."""
    from .signature_rewrites import suspects

    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"), strings=True)
        except OSError:
            continue
        for line, rule, _, _ in suspects(text):
            result.add(
                id="rc8-signature-changed",
                category="api",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(f"{rule}(...) uses its pre-RC8 argument list; RC8 has only the changed signature "
                             "(addMarket gained withJunkAndChatter, TileParams/addNebulaFromPNG a name, addCondition "
                             "lost its boolean), so this does not compile on RC8. The fixer writes RC8's exact form."),
                file=_relative(root, source),
                evidence=[f"line:{line}", f"call:{rule}"],
            )


# Vanilla classes that 0.53-0.65 mods import and that 0.98a no longer ships (2026-09-14 batch: Batavia,
# Cobalt Arms, Gekelonians, Independant Mining Faction, Qualljom).
# Vanilla classes that old mods use but the target no longer has. Add an entry only with evidence from
# the target's own starsector-core: its jars AND its loose data/scripts.
# Correction, 2026-09-14: BaseSpawnPoint and corvus.Corvus were listed here as removed, but RC8 still
# ships both as loose scripts (starsector-core/data/scripts/world/BaseSpawnPoint.java, with the same
# constructor and abstract spawnFleet(), and .../corvus/Corvus.java). The earlier evidence had checked
# only the jars.
LEGACY_VANILLA_CLASSES: dict[str, str] = {}


def _load_rc8_vanilla_loose_script_classes() -> frozenset[str]:
    """RC8's loose vanilla scripts (all 116: hull mods, ship systems, missions, world generation).

    The game compiles them at startup, so mods may import them like API classes: Adjusted Sector imports
    data.hullmods.HeavyArmor. The list is read from vanilla_loose_scripts_rc8.json, which was generated
    from RC8's starsector-core, because the import check runs without a vanilla core path.
    """
    try:
        data = json.loads(Path(__file__).with_name("vanilla_loose_scripts_rc8.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    return frozenset(str(name) for name in data.get("classes", []))


VANILLA_LOOSE_SCRIPT_CLASSES = _load_rc8_vanilla_loose_script_classes()


def _console_command_classes(root: Path) -> set[str]:
    """Classes registered in data/console/commands.csv (loaded only by Console Commands)."""
    rows = _read_csv_rows_lenient(root / "data" / "console" / "commands.csv") or []
    return {(row.get("class") or "").strip() for row in rows if (row.get("class") or "").strip()}
