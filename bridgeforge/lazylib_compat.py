from __future__ import annotations

from pathlib import Path

DRAWABLE = {"LazyFont.DrawableString", "org.lazywizard.lazylib.ui.LazyFont.DrawableString"}
FONT = {"LazyFont", "org.lazywizard.lazylib.ui.LazyFont"}
REMOVED = {"appendText": "append", "setColor": "setBaseColor", "getColor": "getBaseColor", "checkRebuild": "triggerRebuildIfNeeded"}


def scan_lazylib_compat(root: Path, result) -> None:
    """Emit only AST/type-proven LazyLib 2.6–3.0 compatibility findings."""
    types = {}
    for fact in result.source_facts:
        if fact["kind"] == "variable_declaration" and "\x1f" in fact["value"]:
            declared, name = fact["value"].split("\x1f", 1)
            types[(fact["file"], name)] = declared
    imports = {(fact["file"], fact["value"]) for fact in result.source_facts if fact["kind"] == "import"}
    for fact in result.source_facts:
        if fact["kind"] != "method_invocation" or "." not in fact["value"]:
            continue
        receiver, method = fact["value"].rsplit(".", 1)
        declared = types.get((fact["file"], receiver))
        if method in REMOVED and declared in DRAWABLE:
            result.add(id=f"lazylib-drawable-string-{method}", category="lazylib-compatibility", severity="high", classification="REVIEW", confidence="DETERMINISTIC", explanation=f"AST/type evidence identifies {receiver} as LazyFont.DrawableString. LazyLib 3.0 removes {method}(); the release-noted candidate is {REMOVED[method]}(). This is a blocked evidence-contract candidate, not an executable rule.", file=fact["file"], evidence=[f"{declared} {receiver}", fact["value"], f"candidate: {REMOVED[method]}"])
        elif method == "drawText" and declared in FONT:
            result.add(id="lazylib-lazy-font-draw-text", category="lazylib-compatibility", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="AST/type evidence identifies a LazyFont receiver. LazyLib 3.0 removes drawText(); its createText() replacement requires lifecycle/draw/dispose decisions, so no source rewrite is proposed.", file=fact["file"], evidence=[f"{declared} {receiver}", fact["value"]])
    for file, imported in imports:
        if imported == "org.lazywizard.lazylib.campaign.orbits.KeplerOrbit":
            result.add(id="lazylib-kepler-orbit-removed", category="lazylib-compatibility", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation="KeplerOrbit is removed in LazyLib 3.0 with no documented replacement. Preserve intent through manual design and runtime validation; no migration is inferred.", file=file, evidence=[imported])
    for version_file in root.rglob("lazylib.version"):
        value = version_file.read_text(encoding="utf-8", errors="replace").strip()
        if value:
            result.add(id="lazylib-version-evidence", category="dependencies", severity="info", classification="SAFE", confidence="DETERMINISTIC", explanation="A local LazyLib version marker was found; it is evidence for dependency review, not permission to rewrite source.", file=version_file.relative_to(root).as_posix(), evidence=[value])
    jar_paths = [str(item.get("path", "")) for item in result.jars]
    if any("lazylib" in path.lower() for path in jar_paths) and any("kotlin" in path.lower() or "coroutines" in path.lower() for path in jar_paths):
        result.add(id="lazylib-3-internal-runtime-layout", category="dependencies", severity="high", classification="REVIEW", confidence="HIGH", explanation="LazyLib and Kotlin/coroutine runtime JARs are bundled together. LazyLib 3.0 keeps its internal runtime JARs under jars/internal; confirm that this mod does not declare or redistribute them as direct mod dependencies. This is packaging/dependency review only, never a source rewrite.", evidence=["LazyLib + Kotlin/coroutine runtime JAR evidence"])
