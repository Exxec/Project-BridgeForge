"""Library and dependency checks: usage attribution, undeclared dependencies, mod_info metadata, RevenantLib folding."""
from __future__ import annotations

import json
import re
from ..models import ScanResult
from pathlib import Path
from .scan_classfile import _iter_jar_class_files, _parse_class_file
from .scan_common import BUNDLED_LIBRARY_PACKAGE_PREFIXES, GAME_VERSION_RC_PATTERN, LIBRARY_DEPENDENCY_IDS, LIBRARY_PACKAGES, LIBRARY_PATTERNS, _java_for_major, _relative
from .scan_content import _source_class_index
from .scan_jarchecks import _console_command_classes
from .scan_javatext import _blank_java_comments
from .scan_json import _emit_json_tolerance_findings, _json_encoding_finding, _load_lenient_json_file, _parse_json


def _scan_metadata(root: Path, result: ScanResult) -> None:
    path = root / "mod_info.json"
    if not path.exists():
        result.add(id="missing-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json was not found at the mod root.")
        nested_roots = [child.name for child in root.iterdir() if child.is_dir() and (child / "mod_info.json").is_file()]
        if len(nested_roots) == 1:
            result.add(id="wrapper-directory-layout", category="metadata", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A single nested directory contains mod_info.json. Select that directory after extracting the release archive; Bridgeforge will not implicitly change the input root.", evidence=nested_roots)
        return
    try:
        metadata_text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        _json_encoding_finding(result, "metadata", "mod_info.json", exc)
        return
    except OSError as exc:
        result.add(id="unreadable-mod-info", category="metadata", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=f"mod_info.json could not be read: {exc}", file="mod_info.json")
        return
    try:
        metadata, tolerances = _parse_json(metadata_text)
    except json.JSONDecodeError as exc:
        result.add(id="unverified-mod-info-syntax", category="metadata", severity="high", classification="UNKNOWN", confidence="DETERMINISTIC", explanation=f"A strict JSON parser rejected mod_info.json ({exc}). Metadata could not be trusted for environment inference.", file="mod_info.json")
        return
    if not isinstance(metadata, dict):
        result.add(id="invalid-mod-info", category="metadata", severity="critical", classification="MANUAL", confidence="DETERMINISTIC", explanation="mod_info.json must contain a JSON object.", file="mod_info.json")
        return
    result.metadata = metadata
    result.metadata_parse_mode = "STRICT" if not tolerances else "+".join(sorted(tolerances)).upper()
    _emit_json_tolerance_findings(result, "metadata", "mod_info.json", tolerances)
    game_version = metadata.get("gameVersion") or metadata.get("game_version")
    if game_version:
        result.declared_starsector = str(game_version)
        result.estimated_starsector = str(game_version)
    dependencies = metadata.get("dependencies") or metadata.get("requiredDependencies") or []
    if dependencies:
        result.add(id="declared-dependencies", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="Dependency declarations were found.", file="mod_info.json", evidence=[str(item) for item in dependencies])


def _scan_mod_info_jar_missing(root: Path, result: ScanResult) -> None:
    """Each mod_info.json "jars" entry that doesn't exist under the mod root.

    Xenoargh's EZFaction and AI Overhaul originals both list "jars/LazyLib.jar" (read 2026-09-15:
    In operation/Xenoargh-EZFaction/original and In operation/Xenoargh-AI-Overhaul/original), and
    neither ships it. Starsector is asked to load a jar that isn't there; whether that is a Fatal
    dialog, a silent skip, or something else has not been confirmed in game, so this is reported as
    a launch blocker to verify, not a confirmed crash.
    """
    declared = result.metadata.get("jars")
    if not isinstance(declared, list):
        return
    missing = sorted(
        entry for entry in declared
        if isinstance(entry, str) and entry.strip() and not (root / entry).is_file()
    )
    if missing:
        result.add(
            id="mod-info-jar-missing",
            category="metadata",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="mod_info.json's \"jars\" list names a jar that does not exist under the mod root; Starsector is asked to load it at startup. Treat this as a launch blocker until verified in game.",
            file="mod_info.json",
            evidence=missing,
        )


def _annotate_source_reachability(root: Path, result: ScanResult) -> None:
    """Resolve only unambiguous local class-qualified calls from configured roots."""
    integrity = result.migration_context.get("configured_class_integrity", {})
    entrypoints = set(integrity.get("configured_entrypoint_sources", []))
    source_index = _source_class_index(root)
    by_simple_name: dict[str, set[str]] = {}
    for class_name, file in source_index.items():
        by_simple_name.setdefault(class_name.rsplit(".", 1)[-1], set()).add(file)
    calls: dict[str, list[str]] = {}
    for fact in result.source_facts:
        if fact.get("kind") == "call_edge":
            calls.setdefault(str(fact["file"]), []).append(str(fact["value"]))
    reachable = set(entrypoints)
    pending = list(sorted(entrypoints))
    resolved_edges: list[dict[str, str]] = []
    uncertain_edges = 0
    while pending:
        source = pending.pop()
        for edge in calls.get(source, []):
            _, _, select = edge.partition("->")
            receiver, separator, _ = select.partition(".")
            candidates = by_simple_name.get(receiver, set()) if separator else set()
            if len(candidates) != 1:
                uncertain_edges += 1
                continue
            target = next(iter(candidates))
            resolved_edges.append({"from": source, "to": target, "call": select})
            if target not in reachable:
                reachable.add(target)
                pending.append(target)
    result.migration_context["source_reachability"] = {
        "configured_entrypoint_sources": sorted(entrypoints),
        "reachable_local_sources": sorted(reachable),
        "resolved_local_edges": sorted(resolved_edges, key=lambda item: (item["from"], item["to"], item["call"])),
        "uncertain_call_edge_count": uncertain_edges,
        "limitation": "Only unambiguous local class-qualified calls are followed; unqualified, instance, inherited, reflective, and dependency calls remain unresolved.",
    }
    tracked = {"runtime-placeholder-unsupported-operation", "campaign-spawn-registration-disabled", "missing-custom-ui-button-pressed-callback", "legacy-custom-dialog-delegate-signature"}
    for finding in result.findings:
        if finding.id not in tracked or not finding.file:
            continue
        if finding.file in entrypoints and "reachability: configured-entrypoint" not in finding.evidence:
            finding.evidence.append("reachability: configured-entrypoint")
        elif finding.file in reachable and "reachability: reachable-local-call" not in finding.evidence:
            finding.evidence.append("reachability: reachable-local-call")


def _local_class_names(root: Path) -> set[str]:
    """Classes the mod defines itself, in its loose sources or its jars (dotted names)."""
    names = set(_source_class_index(root))
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and info.this_class:
            names.add(info.this_class.replace("/", "."))
    return names


def _attribute_library_usage(result: ScanResult) -> None:
    dependencies = " ".join(map(str, result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or [])).lower()
    calls = [fact.get("value", "") for fact in result.source_facts if fact.get("kind") == "method_invocation"]
    # The mod's own classes are never a library's, even in a library-looking package.
    local_classes = _local_class_names(Path(result.input_path)) if result.input_path else set()
    for library, prefixes in LIBRARY_PACKAGES.items():
        imports = [item for item in result.imports if item not in local_classes and any(item.startswith(prefix) for prefix in prefixes)]
        simple_names = {item.rsplit(".", 1)[-1] for item in imports if not item.endswith(".*")}
        source_calls = [call for call in calls if call.split(".", 1)[0] in simple_names]
        # "Bundled" means a matching jar actually exists under the mod root, not merely that
        # mod_info.json's "jars" list names one: EZFaction and AI Overhaul (Xenoargh) both declare
        # "jars/LazyLib.jar" without shipping it (read 2026-09-15), which would hide their real,
        # undeclared LazyLib dependency (48 javac errors, found later by compile-check) if a
        # declared-but-absent entry counted as bundled. result.jars is already filtered to existing
        # files by _loaded_mod_jars()/_scan_jars(), but the existence check is repeated explicitly
        # here so this invariant holds even if that upstream filtering ever changes.
        bundled = any(
            LIBRARY_PATTERNS[library].search(str(item.get("path", "")))
            and (Path(result.input_path) / str(item.get("path", ""))).is_file()
            for item in result.jars
        )
        declared = library.lower() in dependencies or library.replace("Lib", "").lower() in dependencies
        bytecode_referenced = library in result.bytecode_library_references
        if declared or bundled or imports:
            result.library_usage.append({"library": library, "declared": declared, "bundled": bundled, "imported": bool(imports), "source_called": bool(source_calls), "bytecode_referenced": bytecode_referenced, "evidence": {"imports": imports, "source_calls": source_calls}})
            # A jar's own bytecode references count too: ClearCommands' jar calls org.lazywizard 42
            # times with no loose source, so revive's undeclared-library-dependency fix declared
            # LazyLib and this check then called it unreferenced (found 2026-09-27, P15 item 14).
            if declared and not bundled and not imports and not bytecode_referenced:
                result.add(id="declared-library-unreferenced", category="dependencies", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation="A declared library has no bundled, import, or source-call evidence. Confirm whether it is required before removing or changing it.", evidence=[library])
            if imports and not declared and not bundled and not bytecode_referenced and _library_import_only(Path(result.input_path), result, [prefix.replace(".", "/") for prefix in prefixes]):
                pass  # an unused import compiled away; reported once as library-import-unused-in-jar
            elif imports and library == "Nexerelin" and _only_nexerelin_custom_starts(Path(result.input_path), prefixes):
                pass  # reported once as optional-library-integration (registered:customStarts.json)
            elif imports and not declared and not bundled:
                result.add(
                    id="source-library-dependency-undeclared",
                    category="dependencies",
                    severity="high",
                    classification="REVIEW",
                    confidence="DETERMINISTIC",
                    explanation=f"Source imports {library}, but mod_info.json does not declare it and no bundled {library} JAR was found. Determine whether the library is mandatory or an optional integration before changing metadata or source.",
                    file="mod_info.json",
                    evidence=[library, *imports],
                )


def _dependency_compatibility_context(result: ScanResult) -> None:
    """Record dependency evidence without guessing API replacements or versions."""
    raw_declared = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    declared: list[dict[str, str | None]] = []
    normalized: set[str] = set()
    for item in raw_declared:
        if isinstance(item, dict):
            dependency_id = str(item.get("id") or "").strip() or None
            dependency_name = str(item.get("name") or "").strip() or None
        else:
            dependency_id = str(item).strip() or None
            dependency_name = None
        declared.append({"id": dependency_id, "name": dependency_name})
        normalized.update(re.sub(r"[^a-z0-9]", "", value.lower()) for value in (dependency_id, dependency_name) if value)
    direct_apis: list[dict[str, object]] = []
    for finding in result.findings:
        # external-mod-api-import-declared (SAFE): the same direct-API-usage evidence, just for a
        # dependency mod_info.json already declares - still real for a consumer reasoning about
        # cross-mod integration, so both ids are harvested here.
        if finding.id not in ("external-mod-api-import", "external-mod-api-import-declared") or not finding.evidence:
            continue
        dependency = finding.evidence[0]
        key = re.sub(r"[^a-z0-9]", "", dependency.lower())
        finding_imports = [item for item in finding.evidence[1:] if not item.startswith("line:")]
        direct_apis.append({"dependency": dependency, "declared": key in normalized, "imports": finding_imports})
    result.migration_context["dependency_compatibility"] = {
        "declared_dependencies": declared,
        "direct_api_dependencies": direct_apis,
        "library_usage": result.library_usage,
        "limitation": "Static evidence does not establish an installed dependency version or API-symbol compatibility.",
    }


def _infer_environment(result: ScanResult) -> None:
    majors = [major for jar in result.jars for major in jar.get("class_file_majors", [])]
    if majors:
        result.estimated_java = _java_for_major(max(majors))
        if max(majors) > 61:
            result.add(id="target-bytecode-exceeds-profile", category="java", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"Detected {_java_for_major(max(majors))} bytecode exceeds target Java {result.target.java}.")
    if result.estimated_starsector == "UNKNOWN":
        result.add(id="version-inference-blocked", category="environment", severity="medium", classification="UNKNOWN", confidence="DETERMINISTIC", explanation="No trustworthy declared Starsector version was available. Do not make confident compatibility or migration claims until metadata or independent target evidence is supplied.")


def _base_game_version(version: str) -> str:
    """'0.98a-RC8' -> '0.98a'. The launcher accepts any RC of the same base version."""
    return re.sub(r"-RC\d+$", "", version.strip(), flags=re.I).lower()


def _version_series(version: str) -> str:
    """'0.98a-RC8' -> '0.98', '0.9.1a' -> '0.9.1', '0.98.x' -> '0.98'."""
    base = _base_game_version(version)
    return re.sub(r"(?:\.x|[a-z]+)$", "", base)


def _scan_mod_info_game_version(result: ScanResult) -> None:
    target_version = result.target.starsector
    declared = result.declared_starsector
    if not target_version or not declared or declared == target_version:
        return
    # A generic target ('0.98.x', the default) used to skip this check entirely, so the 2026-09-14 batch
    # of 0.53a-0.9.1a mods never heard that the launcher would untick every one of them.
    if not GAME_VERSION_RC_PATTERN.match(target_version):
        if not re.fullmatch(r"\d+(?:\.\d+)*\.x", target_version.strip()) or _version_series(declared) == _version_series(target_version):
            return
        target_version = f"{_version_series(target_version)}a"
    # The launcher matches on the BASE version: mods declaring 0.98a-RC5 / 0.98a-RC7 loaded and ran
    # all week in an RC8 rig (LazyLib, LunaLib, Console Commands, MagicLib), so an older RC is fine.
    if _base_game_version(declared) == _base_game_version(target_version):
        return
    result.add(
        id="mod-info-game-version-inexact",
        category="metadata",
        severity="high",
        classification="REVIEW",
        confidence="DETERMINISTIC",
        explanation=f"mod_info.json gameVersion ('{declared}') targets a different base game version than the configured target ({target_version}). The Starsector launcher unchecks a mod whose base version differs. An older release candidate of the same version (e.g. 0.98a-RC5 on RC8) is accepted, so only the base version matters.",
        file="mod_info.json",
        evidence=[f"declared:{declared}", f"target:{target_version}"],
    )


TOOLBOX_ID = "aotd_theory_of_toolbox"


TOOLBOX_FORK_MINIMUM = (1, 0, 14)  # the Scheduler Fork installed 2026-10-10 is 1.0.14-spp13 (docs/AOTD_COMPAT_PLAN.md)


def _version_tuple(text: object) -> tuple[int, ...]:
    """Leading numeric dotted part of a version string: `1.0.14-spp13` -> (1, 0, 14); no digits -> ()."""
    match = re.match(r"\s*v?(\d+(?:\.\d+)*)", str(text or ""))
    return tuple(int(p) for p in match.group(1).split(".")) if match else ()


def toolbox_version_gaps(root: Path, provider_roots: list[Path] | None) -> list[dict]:
    """Declared Toolbox dependency versions below the installed provider, or below the fork's minimum when no
    provider is found. Seats of Power and Vaults of Knowledge declare 1.0.11; the fork is 1.0.14-spp13."""
    info = _load_lenient_json_file(Path(root) / "mod_info.json") if (Path(root) / "mod_info.json").is_file() else None
    declared = [d for d in (info.get("dependencies") if isinstance(info, dict) else None) or [] if isinstance(d, dict) and d.get("id") == TOOLBOX_ID]
    if not declared:
        return []
    installed: tuple[int, ...] = ()
    if provider_roots:
        from ..substitutes import provider_index

        versions = [_version_tuple(p.version) for p in provider_index([Path(e) for e in provider_roots], exclude=Path(root)) if p.mod_id == TOOLBOX_ID]
        installed = max(versions, default=())
    required = installed or TOOLBOX_FORK_MINIMUM
    gaps = []
    for dep in declared:
        wanted = _version_tuple(dep.get("version") if not isinstance(dep.get("version"), dict) else ".".join(str(dep["version"].get(k, 0)) for k in ("major", "minor", "patch")))
        if wanted and wanted < required:
            gaps.append({"declared": ".".join(map(str, wanted)), "required": ".".join(map(str, required)), "source": "installed provider" if installed else "fork minimum"})
    return gaps


def _scan_aotd_toolbox_version(root: Path, result: ScanResult, provider_roots: list[Path] | None) -> None:
    for gap in toolbox_version_gaps(root, provider_roots):
        result.add(
            id="aotd-toolbox-version-below-minimum",
            category="dependencies",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation=(f"mod_info.json asks for Theory of Toolbox {gap['declared']}, below {gap['required']} ({gap['source']}). "
                         "The Scheduler Fork replaces Kaysaar's Toolbox and rewrites the economy refresh path; whether this mod "
                         "was tested against it is unproven. Re-test with the fork before raising the declared version."),
            file="mod_info.json",
            evidence=[f"dependency:{TOOLBOX_ID}", f"declared:{gap['declared']}", f"required:{gap['required']}", f"source:{gap['source']}"],
        )


def _mod_info_declares_dependency(result: ScanResult, dependency_id: str) -> bool:
    dependencies = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    target = dependency_id.strip().lower()
    for item in dependencies:
        if isinstance(item, dict):
            candidates = (str(item.get("id") or ""), str(item.get("name") or ""))
        else:
            candidates = (str(item),)
        if any(candidate.strip().lower() == target for candidate in candidates):
            return True
    return False


def _scan_revenantlib_fold_conflict(result: ScanResult) -> None:
    """MANUAL: mod_info.json declares both revenantlib and an id `dependency_successors.json` records
    as folded into it (`bridgeforge fold`, roadmap P14 item 10; docs/DEPENDENCY_STRATEGY.md).

    Folding keeps the original mod's ids and class names unchanged, so enabling the original mod
    alongside RevenantLib double-registers the same ids and classes. Local imports: fold.py and
    substitutes.py both import this module at load time, so importing either back at module scope
    here would cycle; deferring to call time (after both are fully loaded) avoids that, the same way
    `_scan_compile_check` defers its import of compile_check.
    """
    if not _mod_info_declares_dependency(result, "revenantlib"):
        return
    from ..fold import FOLD_KIND
    from ..substitutes import load_successors

    folded_ids = {
        str(entry.get("match") or "").strip().lower()
        for entry in load_successors()
        if entry.get("kind") == FOLD_KIND and entry.get("match")
    }
    if not folded_ids:
        return
    dependencies = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    conflicts: list[str] = []
    for item in dependencies:
        candidate = str(item.get("id") or "").strip() if isinstance(item, dict) else str(item).strip()
        if candidate and candidate.lower() != "revenantlib" and candidate.lower() in folded_ids:
            conflicts.append(candidate)
    if not conflicts:
        return
    result.add(
        id="revenantlib-fold-conflict",
        category="dependencies",
        severity="high",
        classification="MANUAL",
        confidence="DETERMINISTIC",
        explanation=(
            f"mod_info.json declares both revenantlib and {', '.join(sorted(set(conflicts)))}, which "
            "RevenantLib has folded in with the same ids and class names; enabling both together "
            "double-registers them. Declare only revenantlib."
        ),
        file="mod_info.json",
        evidence=sorted(set(conflicts)),
    )


def _drop_library_findings_judged_elsewhere(result: ScanResult) -> None:
    """source-library-dependency-undeclared says only "source imports it"; undeclared-library-dependency (declare it:
    standing approval) and optional-library-integration (guarded, no dependency) judge the same library with more
    evidence. Where either exists, the source finding is a duplicate that blocked 38 mods on a question already
    answered (owner ruling 2026-09-29: treat it like the existing rule)."""
    judged = {e.split(":", 1)[1] for f in result.findings if f.id in ("undeclared-library-dependency", "optional-library-integration")
              for e in f.evidence if e.startswith("library:")}
    if judged:
        result.findings[:] = [f for f in result.findings
                              if not (f.id == "source-library-dependency-undeclared" and f.evidence and f.evidence[0] in judged)]


def _nexerelin_custom_start_classes(root: Path) -> set[str]:
    """Classes named by "className" in data/config/exerelin/customStarts.json (loaded only by Nexerelin)."""
    data = _load_lenient_json_file(root / "data" / "config" / "exerelin" / "customStarts.json")
    starts = data.get("starts") if isinstance(data, dict) else None
    return {s["className"].strip() for s in starts or [] if isinstance(s, dict) and isinstance(s.get("className"), str) and s["className"].strip()}


def _only_nexerelin_custom_starts(root: Path, prefixes) -> bool:
    """True when every source using these packages is a class registered in customStarts.json."""
    registered = _nexerelin_custom_start_classes(root)
    users = set(_sources_mentioning(root, [prefix.rstrip(".") for prefix in prefixes]).values()) if registered else set()
    return bool(users) and users <= registered


def _sources_mentioning(root: Path, dotted: list[str]) -> dict[str, str]:
    """{relative source path: class name} for .java files that mention any dotted package."""
    found: dict[str, str] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(needle in text for needle in dotted):
            package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
            found[_relative(root, source)] = f"{package.group(1)}.{source.stem}" if package else source.stem
    return found


def _library_import_only(root: Path, result: ScanResult, slash_prefixes: tuple[str, ...] | list[str]) -> list[str]:
    """Source files that mention a library although the shipped jar never references it.

    Returns the mentioning sources when every one of them compiles into a loaded jar class and no loaded
    jar class references the library's packages; otherwise []. Bionic Alteration imports Nexerelin's
    StringHelper but never calls it, so its jar has no exerelin/ reference and it runs without
    Nexerelin: an unused import is not a dependency (2026-09-14).
    """
    if not result.compiled_class_names:
        return []
    dotted = [prefix.replace("/", ".").rstrip(".") for prefix in slash_prefixes]
    mentioning: list[str] = []
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not any(needle in text for needle in dotted):
            continue
        package = re.search(r"(?m)^\s*package\s+([\w.]+)\s*;", text)
        class_name = f"{package.group(1)}.{source.stem}" if package else source.stem
        if class_name not in result.compiled_class_names:
            return []  # a loose or uncompiled source: its import may be live
        mentioning.append(_relative(root, source))
    if not mentioning:
        return []
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is not None and any(ref.startswith(prefix) for ref in info.referenced_classes for prefix in slash_prefixes):
            return []
    return mentioning


# Names a mod probes for with loadClass/Class.forName to detect a library at runtime (the library is then optional).
# Exigency 0.8.01a probes "data.scripts.world.ExerelinGen", Nexerelin's class outside its own package (2026-09-28).
LIBRARY_PROBE_MARKERS = {
    "Nexerelin": ("exerelin", "ExerelinGen"),
    "Console Commands": ("lazywizard.console",),
    "LunaLib": ("lunalib",),
    "MagicLib": ("magiclib", "data.scripts.util.Magic", "org.magiclib"),
    "GraphicsLib": ("dark.shaders", "org.dark."),
    "LazyLib": ("lazywizard.lazylib",),
}


_PRESENCE_PROBE = re.compile(r'\b(?:loadClass|forName)\s*\(\s*"([^"]+)"')


def _library_presence_probed(root: Path, library: str) -> bool:
    """A source file or jar class probes for this library by class name (loadClass/Class.forName)."""
    markers = LIBRARY_PROBE_MARKERS.get(library, ())
    if not markers:
        return False
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(any(m.lower() in name.lower() for m in markers) for name in _PRESENCE_PROBE.findall(text)):
            return True
    for _jar, _member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or not ({"loadClass", "forName"} & set(info.utf8_values)):
            continue
        if any(any(m.lower() in value.lower() for m in markers) and "." in value for value in info.string_constants):
            return True
    return False


def _unguarded_library_users(root: Path, source_hits: list[str], library: str, dependency_id: str) -> list[str]:
    """Source files that use a library with no sign of a guard: no isModEnabled(<id>), no loadClass/forName probe, no catch of
    NoClassDefFoundError/LinkageError/Throwable, and no `if (...)` condition naming the library or its id (a flag the plugin
    set from its own probe). A probe elsewhere in the mod does not protect such a file: Free Stars Union's AicModPlugin probes
    ShaderLib in a try/catch, yet aic_temporalstats built a StandardLight in combat and stopped the game with
    NoClassDefFoundError (GRP3A-20261006)."""
    id_guard = re.compile(r'\bisModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)', re.IGNORECASE)
    catches = re.compile(r"catch\s*\(\s*(?:final\s+)?(?:\w+\s*\|\s*)*(?:NoClassDefFoundError|LinkageError|Throwable|Error)\b")
    names = sorted({re.escape(dependency_id.lower()), re.escape(library.lower().replace(" ", ""))})
    flag = re.compile(r"\bif\s*\(\s*!?\s*[\w.]*(?:" + "|".join(names) + r")", re.IGNORECASE)
    markers = LIBRARY_PROBE_MARKERS.get(library, ())
    unguarded = []
    for relative in source_hits:
        try:
            text = _blank_java_comments((root / relative).read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        probes = any(any(m.lower() in name.lower() for m in markers) for name in _PRESENCE_PROBE.findall(text))
        if not (id_guard.search(text) or probes or catches.search(text) or flag.search(text)):
            unguarded.append(relative)
        elif (not id_guard.search(text) and _MOD_PLUGIN_CLASS.search(text) and not _probe_returns_early(text, markers)
              and _library_call_outside_guard(text, markers, flag)):
            # A probe in the mod plugin does not cover a call outside any guarding block: onApplicationLoad runs at every start.
            # Only the mod plugin: a helper class's call is usually guarded by its caller, which this textual check cannot see
            # (a sweep of 300 workspaces found 3 such false hits in shader and ship system classes, 2026-10-11).
            unguarded.append(relative)
    return unguarded


_GUARD_HEADER = re.compile(r"\b(?:try|catch|synchronized)\b")


_MOD_PLUGIN_CLASS = re.compile(r"\bextends\s+BaseModPlugin\b")


def _probe_returns_early(text: str, markers: tuple[str, ...]) -> bool:
    """`try { loadClass("<library class>") } catch (...) { return; }`: everything after the probe runs only with the library
    (Upgraded Rotary Weapons' URW_modPlugin, 2026-10-11)."""
    for match in re.finditer(r'(?:loadClass|forName)\s*\(\s*"([^"]+)"[^{}]*\}\s*catch\s*\([^)]*\)\s*\{\s*return\s*;', text):
        if any(m.lower() in match.group(1).lower() for m in markers):
            return True
    return False


_IMPORT_LINE = re.compile(r"^\s*import\s+([\w.]+)\.(\w+)\s*;", re.M)


def _library_call_outside_guard(text: str, markers: tuple[str, ...], flag: re.Pattern) -> bool:
    """A direct use of a class the file imports from the library (`ShaderLib.init()`, `new StandardLight(...)`) that is not inside
    a `try` block, a catch, or an `if` whose condition names the library (a flag set from the probe). Neutrino's NCModPlugin
    probed ShaderLib in a static block yet called ShaderLib.init() unguarded in onApplicationLoad, which stopped the game at
    startup without GraphicsLib (SMOKE-neu-20261011). Brace tracking is textual; a guard in a caller is not seen."""
    simple = sorted({m.group(2) for m in _IMPORT_LINE.finditer(text) if any(mk.lower() in (m.group(1) + ".").lower() for mk in markers)})
    if not simple:
        return False
    names = "|".join(re.escape(name) for name in simple)
    usage = re.compile(r"(?<![\w.])(?:" + names + r")\s*\.|\bnew\s+(?:" + names + r")\b")
    stack: list[str] = []
    last_boundary = 0
    for i, ch in enumerate(text):
        if ch == "{":
            stack.append(text[last_boundary:i])
            last_boundary = i + 1
        elif ch == "}":
            if stack:
                stack.pop()
            last_boundary = i + 1
        elif ch == ";":
            statement = text[last_boundary:i]
            if not statement.lstrip().startswith("import") and usage.search(statement):
                if not any(_GUARD_HEADER.search(header) or flag.search(header) for header in stack):
                    return True
            last_boundary = i + 1
    return False


def _fails_fast_through_variable(text: str, dependency_id: str) -> bool:
    """`boolean has = ...isModEnabled("<id>"); ... if (!has) { throw` -- a required library, not an optional one.
    Hiigaran Descendants 2.1 (HiiModPlugin.onApplicationLoad, shaderLib) stopped at startup this way, GRP7B-20261005."""
    for name in re.findall(r'\b(\w+)\s*=\s*[\w.()\s]*isModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)', text, re.IGNORECASE):
        if re.search(r'if\s*\(\s*!\s*' + re.escape(name) + r'\s*\)\s*\{?\s*throw\b', text):
            return True
    return False


def _throws_without_library(text: str, dependency_id: str) -> bool:
    direct = re.compile(r'!\s*[\w.()\s]*isModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)\s*\)\s*\{?\s*throw\b', re.IGNORECASE)
    return bool(direct.search(text)) or _fails_fast_through_variable(text, dependency_id)


def _loads_library_class_or_throws(text: str, library: str) -> bool:
    """`getScriptClassLoader().loadClass("org.lazywizard.lazylib.ModUtils")` in a try whose catch throws: the standard "library is
    required" check. Vayra's Ship Pack 1.2.3 declared no dependencies and stopped at load without LazyLib (REG7-20261012)."""
    needles = [prefix.replace("/", ".").rstrip(".") for prefix in BUNDLED_LIBRARY_PACKAGE_PREFIXES[library] if not prefix.startswith("kotlin")]
    for needle in needles:
        for match in re.finditer(r'loadClass\s*\(\s*"' + re.escape(needle) + r'[\w.$]*"\s*\)', text):
            tail = text[match.end():match.end() + 900]
            if re.match(r"[^{}]*\}\s*catch\s*\([^)]*\)\s*\{[^}]*throw", tail):  # the catch right after the load, not a later one
                return True
    return False


def _scan_library_required_by_throw(root: Path, result: ScanResult) -> None:
    """A plugin that throws when a library is missing needs that library whether or not it reaches the library's
    package: HullMods Expansion's "MagicLib is Required to run this mod" and P9 Colony Group's, neither declared.
    Emits the same finding the fixer reads (no guard evidence, so `fix` declares it)."""
    already = {f.evidence[0] for f in result.findings if f.id == "undeclared-library-dependency" and f.evidence}
    for library, dependency_id in LIBRARY_DEPENDENCY_IDS.items():
        if f"library:{library}" in already or _mod_info_declares_dependency(result, dependency_id):
            continue
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if ("isModEnabled" in text and _throws_without_library(text, dependency_id)) or _loads_library_class_or_throws(text, library):
                result.add(
                    id="undeclared-library-dependency",
                    category="dependencies",
                    severity="high",
                    classification="REVIEW",
                    confidence="HIGH",
                    explanation=f"{_relative(root, source)} throws when {library} is not enabled, so the mod needs {library}, but "
                                "mod_info.json does not declare it; the game's launcher then does not enable it first.",
                    file="mod_info.json",
                    evidence=[f"library:{library}", f"dependency-id:{dependency_id}", "required:throws-without", _relative(root, source)],
                )
                break


def _scan_undeclared_library_dependency(root: Path, result: ScanResult) -> None:
    """Code that reaches a known library's package without mod_info.json declaring that dependency."""
    own_info = _load_lenient_json_file(root / "mod_info.json")
    own_id = str(own_info.get("id", "")).strip().lower() if isinstance(own_info, dict) else ""
    for library, dependency_id in LIBRARY_DEPENDENCY_IDS.items():
        if _mod_info_declares_dependency(result, dependency_id):
            continue
        if own_id and own_id == dependency_id.lower():
            continue  # the mod IS this library: Combat-Misc-Utils (cmutils) was told to depend on itself (2026-10-11)
        prefixes = BUNDLED_LIBRARY_PACKAGE_PREFIXES[library]
        import_only = _library_import_only(root, result, prefixes)
        if import_only:
            result.add(
                id="library-import-unused-in-jar",
                category="dependencies",
                severity="info",
                classification="SAFE",
                confidence="HIGH",
                explanation=f"Source files mention {library}, but they all compile into the shipped jar and no jar class references {library}'s packages (an unused import). The mod runs without {library}; no dependency is needed.",
                file="mod_info.json",
                evidence=[f"library:{library}", *import_only[:5]],
            )
            continue
        # Kotlin is compiled, never a .java import: matching the word "kotlin" in Java text would be noise.
        dotted_needles = [prefix.replace("/", ".").rstrip(".") for prefix in prefixes if not prefix.startswith("kotlin")]
        source_hits: list[str] = []
        guarded = False
        # Optional integration: every referencing source checks isModEnabled("<this library's id>") and none
        # fails fast (throws) when it is missing. RC8 runs with -noverify (CLAUDE.md), so a library class resolves
        # only when code using it runs, which the guard prevents when the library is absent.
        id_guard = re.compile(r'\bisModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)', re.IGNORECASE)
        fail_fast = re.compile(r'!\s*[\w.()\s]*isModEnabled\s*\(\s*"' + re.escape(dependency_id) + r'"\s*\)\s*\)\s*\{?\s*throw\b', re.IGNORECASE)
        every_hit_id_guarded = True
        fails_fast_hit = False
        for source in sorted(root.rglob("*.java")):
            if "disabled_files" in source.relative_to(root).parts:
                continue
            try:
                # Comments are not code: DNEEP was flagged for Nexerelin by a BridgeForge comment naming
                # "a Nexerelin random sector" (2026-10-05).
                text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if not any(needle in text for needle in dotted_needles):
                continue
            source_hits.append(_relative(root, source))
            if re.search(r"\bisModEnabled\s*\(", text):
                guarded = True
            if fail_fast.search(text) or _fails_fast_through_variable(text, dependency_id):
                fails_fast_hit = True
            if not id_guard.search(text) or fail_fast.search(text) or _fails_fast_through_variable(text, dependency_id):
                every_hit_id_guarded = False
        bytecode_hits: list[str] = []
        referencing_classes: set[str] = set()
        if not source_hits:
            for jar, member, data in _iter_jar_class_files(root):
                info = _parse_class_file(data)
                if info is None:
                    continue
                if any(ref.startswith(prefix) for ref in info.referenced_classes for prefix in prefixes):
                    relative_jar = _relative(root, jar)
                    if relative_jar not in bytecode_hits:
                        bytecode_hits.append(relative_jar)
                    if info.this_class:
                        referencing_classes.add(info.this_class.split("$", 1)[0].replace("/", "."))
                # Bytecode-only mods (no source, e.g. Nightcross): a loaded class that calls
                # isModEnabled and carries this mod id as a string literal is the same guard.
                if "isModEnabled" in info.utf8_values and any(value.strip().lower() == dependency_id.lower() for value in info.string_constants):
                    guarded = True
        if not source_hits and not bytecode_hits:
            continue
        if library == "Console Commands":
            # Classes registered in data/console/commands.csv load only through Console Commands, so an
            # addon made of them needs no declared dependency (the source-side console-command-optional rule).
            registered = _console_command_classes(root)
            users = set(_sources_mentioning(root, dotted_needles).values()) if source_hits else referencing_classes
            if registered and users and users <= registered:
                if any(f.id == "console-command-optional" for f in result.findings):
                    continue  # already reported from the source imports
                result.add(id="console-command-optional", category="dependencies", severity="info", classification="SAFE", confidence="HIGH",
                           explanation="Every class that uses Console Commands' API is registered in data/console/commands.csv, which only Console Commands reads, so the classes load only when it is installed. An optional integration; no dependency needed.",
                           evidence=sorted(users)[:10])
                continue
        if library == "Nexerelin":
            # Nexerelin's exerelin.campaign.customstart.CustomStartDefs loads each "className" listed in
            # data/config/exerelin/customStarts.json (ExerelinCore.jar 0.12.2c, 2026-09-28), so classes registered
            # only there load only with Nexerelin (SEEKER 0.6.6's six SKR_*Start classes).
            registered = _nexerelin_custom_start_classes(root)
            users = set(_sources_mentioning(root, dotted_needles).values()) if source_hits else referencing_classes
            if registered and users and users <= registered:
                result.add(id="optional-library-integration", category="dependencies", severity="info", classification="SAFE", confidence="HIGH",
                           explanation="Every class that uses Nexerelin is a custom start registered in data/config/exerelin/customStarts.json, which only Nexerelin reads, so the classes load only when it is installed. An optional integration; no dependency needed.",
                           file="mod_info.json", evidence=[f"library:{library}", f"dependency-id:{dependency_id}", "registered:customStarts.json", *sorted(users)[:5]])
                continue
        probed = _library_presence_probed(root, library)
        unguarded_users = _unguarded_library_users(root, source_hits, library, dependency_id) if probed and not every_hit_id_guarded else []
        if unguarded_users:
            probed = False
        if (source_hits and every_hit_id_guarded) or probed:
            result.add(id="optional-library-integration", category="dependencies", severity="info", classification="SAFE", confidence="MEDIUM",
                       explanation=("The mod probes for " + library + " at runtime (loadClass/Class.forName of its classes) before using it" if probed else f"Every source file that uses {library} checks isModEnabled(\"{dependency_id}\")") + f" and none throws when it is missing: an optional integration. RC8 runs with -noverify, so {library}'s classes are resolved only when that guarded code runs. No dependency needed; the mod works with or without {library}.",
                       file="mod_info.json", evidence=[f"library:{library}", f"dependency-id:{dependency_id}", *source_hits[:5]])
            continue
        # Owner ruling 2026-09-27: an unguarded use of a known, maintained library is fixed by declaring it (the
        # library's own mod id, from LIBRARY_DEPENDENCY_IDS), which is deterministic, so it is REVIEW, not MANUAL,
        # and the fixer is a standing approval in AUTOMATION_POLICY.json. Before: 88 MANUAL findings in 229 mods.
        classification = "REVIEW"
        result.add(
            id="undeclared-library-dependency",
            category="dependencies",
            severity="high",
            classification=classification,
            confidence="HIGH",
            explanation=(
                f"Code references {library}'s package(s) ({', '.join(prefixes)}), but mod_info.json does not "
                f"declare a matching '{dependency_id}' dependency. An undeclared mandatory dependency lets the "
                f"mod load and crash later, the first time it calls {library}."
                + (
                    " An isModEnabled(...) guard was found (in a referencing source file, or in a loaded class "
                    "that checks this mod id), suggesting an optional integration rather than a hard dependency. "
                    "A plugin may also use that check to fail fast when a required library is missing, so confirm."
                    if guarded and not unguarded_users
                    else ""
                )
            ),
            file="mod_info.json",
            evidence=[f"library:{library}", f"dependency-id:{dependency_id}", *(["guard:present"] if guarded and not unguarded_users else []), *(["required:throws-without"] if fails_fast_hit else []), *[f"probe-present-but-unguarded-use:{u}" for u in unguarded_users[:5]], *source_hits[:5], *bytecode_hits[:5]],
        )
