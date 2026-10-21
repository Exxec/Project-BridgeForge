"""Atlas census, library part (ROADMAP-3 81.4): which libraries each mod calls into, by package prefix. STATIC.

Rows (area `lib`): kind = library name, symbol = dotted class or member, count = classes/files that reference it. A class
the mod defines itself is never a library call, so a mod that bundles a library under its own name hides its own use of it.
Declared dependency versions come from `mod_info.json` (`census_deps`), read by `atlas_census_report.libraries`.
"""
from __future__ import annotations

from .atlas_census import ClassRefs, LooseFile, Tally, member_symbol, qualified_uses

KNOWN_LIBRARIES = (  # (internal-name prefix, library)
    ("org/lazywizard/", "LazyLib"),
    ("org/magiclib/", "MagicLib"),
    ("data/scripts/util/Magic", "MagicLib"),
    ("org/dark/shaders/", "GraphicsLib"),
    ("exerelin/", "Nexerelin"),
    ("lunalib/", "LunaLib"),
)
# the JDK, the game's own bundled runtime and its API are not "libraries" a mod depends on
ENGINE_PREFIXES = ("java/", "javax/", "sun/", "jdk/", "com/sun/", "kotlin/", "kotlinx/", "org/lwjgl/", "org/apache/", "org/json/",
                   "org/codehaus/", "org/w3c/", "org/xml/", "org/newdawn/", "org/objectweb/", "paulscode/", "com/thoughtworks/",
                   "com/jcraft/", "com/fs/", "scala/", "groovy/", "[")
PACKAGE_DEPTH = 2
DATA_SCRIPTS_DEPTH = 3
DECLARED_ID_LIBRARY = {"lw_lazylib": "LazyLib", "magiclib": "MagicLib", "shaderlib": "GraphicsLib", "nexerelin": "Nexerelin",
                       "lunalib": "LunaLib"}


def library_of(internal: str) -> str | None:
    """Library name for an internal class name, or None for the engine/JDK. Unknown packages are named by prefix."""
    if not internal or internal.startswith(ENGINE_PREFIXES):
        return None
    for prefix, library in KNOWN_LIBRARIES:
        if internal.startswith(prefix):
            return library
    parts = internal.split("/")
    if len(parts) < 2:
        return None  # default package: the mod's own
    depth = DATA_SCRIPTS_DEPTH if internal.startswith("data/scripts/") else PACKAGE_DEPTH
    return "pkg:" + ".".join(parts[:depth] if len(parts) > depth else parts[:-1])


def libs_from_jar(classes: list[ClassRefs], tally: Tally) -> None:
    own = {entry.name for entry in classes}
    own_outer = {name.split("$", 1)[0] for name in own}
    for entry in classes:
        for ref in entry.refs:
            if ref.owner in own or ref.owner.split("$", 1)[0] in own_outer or ref.name in ("<init>", "<clinit>"):
                continue
            library = library_of(ref.owner)
            if library:
                tally.add("lib", library, member_symbol(ref), entry.rel)


def libs_from_loose(files: list[LooseFile], tally: Tally) -> None:
    own = {f"{item.package}.{item.rel.rsplit('/', 1)[-1].removesuffix('.java')}" for item in files}
    for item in files:
        for simple, full in item.imports.items():
            library = library_of(full.replace(".", "/"))
            if not library or full in own:
                continue
            tally.add("lib", library, full, item.rel)
            for kind, name in qualified_uses(item, simple):
                tally.add("lib", library, f"{full}.{name}", item.rel)
