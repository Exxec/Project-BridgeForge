from __future__ import annotations

import re
import zipfile
from pathlib import Path

from .jar_audit import _is_jar_zip, _resolve_jar_classes
from .build_tag import BuildTagError, _find_mod_info
from .scanner import _load_lenient_json_file, _loaded_mod_jars

"""Save/build class-reference compatibility check (roadmap P3b-B).

## How Starsector's saves (XStream campaign.xml) name mod classes

`campaign.xml` is an XStream-serialized object graph. A class shows up in one
of two places, and in more than one *form* depending on whether the mod (or
vanilla) registered a short XStream alias for it:

1. **Element tag names.** A field's *declared* runtime value is written as an
   element whose tag is the class's name. Observed real forms (Exigency,
   `Legacy of Arkgneisis` classes, vanilla `WormholeManager`):
   - Simple class name, when the mod registered an alias equal to its own
     simple name (very common; e.g. `<ExipiratedAvestaMovement z="889">` for
     `data.scripts.world.exipirated.ExipiratedAvestaMovement`).
   - **Outer+inner concatenation with no separator**, when the mod aliased an
     inner class that way (e.g. `<ExipiratedAvestaMovementWaypoint>` for the
     inner class `ExipiratedAvestaMovement$Waypoint`).
   - The **dotted fully-qualified name**, with `$` escaped as `_-` (because
     `$` is not a valid XML NCName tag character to XStream's tag encoder,
     but `.` and `-` are), when nothing is aliased. Confirmed on a real save:
     vanilla's own `com.fs.starfarer.api.impl.campaign.shared.WormholeManager$WormholeData`
     appears as the tag
     `<com.fs.starfarer.api.impl.campaign.shared.WormholeManager_-WormholeData>`.

2. **`cl="..."` attributes.** When a field's *actual* runtime type differs
   from its *declared* type (the common XStream "resolve polymorphism"
   case — e.g. a `List` field holding a `Market` instance, or an interface
   field holding a specific plugin implementation), XStream instead keeps the
   declared-type element tag and adds a `cl="..."` attribute naming the real
   class. Confirmed real forms:
   - A short vanilla alias for vanilla types the game itself aliased
     (`cl="Sstm"`, `cl="Plnt"`, `cl="CCEnt"`, `cl="COrbt"`, ...). These are
     cryptic and collide across totally unrelated vanilla classes, so they
     must never be treated as belonging to a mod. There is no general way to
     decode them without a curated alias table, so this module never invents
     package/class attribution from a short alias alone.
   - The mod's own simple name, when aliased that way
     (`cl="ExipiratedAvestaSubmarketPlugin"`).
   - The dotted FQN **with a literal `$`** (attribute values are ordinary
     XML character data, so `$` needs no escaping there, unlike in a tag
     name) for anything unaliased — confirmed on real vanilla and LunaLib
     classes: `cl="com.fs.starfarer.api.impl.campaign.missions.hub.BaseHubMission$Abandon"`,
     `cl="com.fs.starfarer.campaign.util.CollectionView$1"` (an anonymous
     class), `cl="lunalib.backend.scripts.LunaCampaignRendererEntity"`.

So a mod class's possible save aliases are, precisely:
  - the dotted FQN with `$` literal (`pkg.Outer$Inner`) — matches a `cl=`
    attribute value or (after `_-` substitution) a tag name
  - the same FQN with `$` replaced by `_-` — matches a tag name
  - the bare simple name of the outermost class — matches either form, when
    the mod aliased that way
  - the outer+inner simple-name concatenation (all `$`-separated simple
    names joined with no separator) — matches either form, when the mod
    aliased an inner class that way
Anonymous inner classes (`Outer$1`, `Outer$2`, ...) only get the two FQN
forms: a numeric "simple name" is not a legal identifier to concatenate.

## Attribution: telling "this mod's class" from vanilla noise

Because short vanilla aliases are indistinguishable from arbitrary strings
without a curated table, this module never guesses that a short/cryptic
token belongs to a mod. A save reference is attributed to the mod under test
only when:
  - it exactly matches one of the mod's own computed aliases (above) — this
    resolves whether the class the save needs is present in the build being
    checked, or
  - it is a dotted FQN (or its `_-`-escaped tag form) whose package prefix
    matches a package the mod's *surviving* classes still occupy — this is
    how a class the build **removed entirely** (so it has no aliases of its
    own left to match) is still caught, via its still-present siblings'
    shared package.
Anything else -- a short alias, or a dotted/simple candidate whose package
can't be tied to the mod (and, when `vanilla_core` is supplied, isn't
resolvable as vanilla either) -- is reported under `limitations`, never
silently claimed as a pass or a failure.
"""


_TAG_PATTERN = re.compile(
    r"<(/?)([A-Za-z_][\w.\-]*)((?:\s+[\w:.\-]+=\"[^\"]*\")*)\s*(/?)>"
)
_CL_ATTR_PATTERN = re.compile(r'\bcl="([^"]*)"')

# A bare (non-dotted) token is only worth considering as a class name if it
# looks like a Java simple class name: starts uppercase, and is not an
# ALL-CAPS field name like "WAYPOINTS" (real save data uses those for map/
# list field tags; no vanilla or mod class is ever referenced that way).
_PLAUSIBLE_SIMPLE_NAME = re.compile(r"^[A-Z][A-Za-z0-9_]*$")


def _looks_like_bare_class_name(token: str) -> bool:
    return bool(_PLAUSIBLE_SIMPLE_NAME.match(token)) and not token.isupper()


def _aliases_for_class(dotted_dollar: str) -> set[str]:
    """All save-alias forms a class's dotted-with-`$` name can appear as."""
    aliases = {dotted_dollar}
    if "$" in dotted_dollar:
        aliases.add(dotted_dollar.replace("$", "_-"))
    parts = dotted_dollar.split("$")
    first_simple = parts[0].rsplit(".", 1)[-1]
    simple_parts = [first_simple, *parts[1:]]
    if not any(part.isdigit() for part in simple_parts):
        if len(simple_parts) == 1:
            # Top-level class: its own bare simple name is a legitimate alias.
            aliases.add(simple_parts[0])
        else:
            # Nested class: only the outer+inner concatenation names *this*
            # class. The bare outer name alone names the outer class, not
            # this one, and must not be added here (it would make the outer
            # class's alias falsely ambiguous with every one of its inner
            # classes).
            aliases.add("".join(simple_parts))
    return aliases


def _package_of(dotted_dollar: str) -> str:
    base = dotted_dollar.split("$", 1)[0]
    return base.rsplit(".", 1)[0] if "." in base else ""


class SaveCompatError(ValueError):
    """Raised when a save or mod/jar path cannot be resolved for this check."""


def _entry_names(jar_path: Path) -> dict[str, Path]:
    """Map each class entry in one jar/zip-containing-jar to that jar's path.

    Only entry *names* are needed for save-compat (unlike jar-audit, which
    also diffs bytecode), so the common case -- a real jar -- lists
    zip-member names without reading any class bytes. `_resolve_jar_classes`
    (which does read bytes) is reused only for the rarer "a .zip archive
    containing a .jar" release-package shape it already knows how to unwrap.
    """
    try:
        if not zipfile.is_zipfile(jar_path):
            return {}
        with zipfile.ZipFile(jar_path) as archive:
            if _is_jar_zip(archive):
                return {
                    info.filename.replace("\\", "/"): jar_path
                    for info in archive.infolist()
                    if not info.is_dir() and info.filename.lower().endswith(".class")
                }
        entries = _resolve_jar_classes(jar_path, None, "jar")
    except (ValueError, zipfile.BadZipFile, OSError):
        return {}
    return {name: jar_path for name in entries}


def _class_index(source: Path) -> dict[str, Path]:
    """internal class entry name (e.g. 'pkg/Outer$Inner.class') -> jar it was found in.

    `source` may be a mod directory (its loaded jars, per `_loaded_mod_jars`)
    or a single jar file / a .zip archive containing one.
    """
    source = Path(source).expanduser().resolve()
    if not source.exists():
        raise SaveCompatError(f"{source} does not exist.")
    entries: dict[str, Path] = {}
    if source.is_dir():
        for jar in _loaded_mod_jars(source):
            entries.update(_entry_names(jar))
    else:
        entries.update(_entry_names(source))
    return entries


def _dotted(entry_name: str) -> str:
    """'pkg/Outer$Inner.class' -> 'pkg.Outer$Inner'."""
    posix = entry_name.replace("\\", "/")
    if posix.lower().endswith(".class"):
        posix = posix[: -len(".class")]
    return posix.replace("/", ".")


class ModClassIndex:
    """Alias index for one mod build, built from its loaded jars."""

    def __init__(self, source: Path):
        self.source = Path(source).expanduser().resolve()
        self.entries = _class_index(self.source)
        self.canonical: set[str] = {_dotted(name) for name in self.entries}
        self.alias_to_classes: dict[str, set[str]] = {}
        self.packages: set[str] = set()
        for canonical in self.canonical:
            package = _package_of(canonical)
            if package:
                self.packages.add(package)
            for alias in _aliases_for_class(canonical):
                self.alias_to_classes.setdefault(alias, set()).add(canonical)

    @property
    def is_empty(self) -> bool:
        return not self.canonical

    def resolve(self, token: str) -> set[str] | None:
        return self.alias_to_classes.get(token)

    def owns_package(self, package: str) -> bool:
        return package in self.packages


def _mod_id(mod_dir: Path) -> str | None:
    try:
        mod_info_path = _find_mod_info(mod_dir)
    except BuildTagError:
        return None
    data = _load_lenient_json_file(mod_info_path)
    if isinstance(data, dict):
        value = data.get("id")
        if isinstance(value, str):
            return value
    return None


def _build_tag_display(mod_dir: Path) -> str | None:
    try:
        mod_info_path = _find_mod_info(mod_dir)
    except BuildTagError:
        return None
    data = _load_lenient_json_file(mod_info_path)
    if isinstance(data, dict):
        name = data.get("name")
        if isinstance(name, str):
            return name
    return None


def _resolve_save_path(save_path: Path) -> Path:
    save_path = Path(save_path).expanduser().resolve()
    if save_path.is_dir():
        campaign = save_path / "campaign.xml"
        if not campaign.is_file():
            raise SaveCompatError(f"{save_path} has no campaign.xml.")
        return campaign
    if not save_path.is_file():
        raise SaveCompatError(f"{save_path} is not an existing save directory or campaign.xml file.")
    return save_path


class _StreamState:
    __slots__ = ("stack", "line_no")

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.line_no = 0


def _sample_path(state: _StreamState, tag: str) -> str:
    ancestors = state.stack[-5:]
    return "/" + "/".join([*ancestors, tag])


def _scan_save_tokens(campaign_xml: Path):
    """Stream campaign.xml line-by-line, yielding (token, is_cl_attr, sample_path) for each candidate.

    Never loads the whole ~10MB file into memory at once; a plain per-line
    readline() scan is enough because the game's XStream writer emits one
    tag (or one open+text+close leaf) per line.
    """
    state = _StreamState()
    with campaign_xml.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            state.line_no += 1
            for match in _TAG_PATTERN.finditer(line):
                closing, name, attrs, self_closing = match.groups()
                if closing:
                    if state.stack and state.stack[-1] == name:
                        state.stack.pop()
                    continue
                yield name, False, _sample_path(state, name)
                for cl_match in _CL_ATTR_PATTERN.finditer(attrs):
                    yield cl_match.group(1), True, _sample_path(state, name)
                if not self_closing:
                    state.stack.append(name)


def _vanilla_lookup(vanilla_core: Path | None) -> ModClassIndex | None:
    if vanilla_core is None:
        return None
    try:
        return ModClassIndex(vanilla_core)
    except SaveCompatError:
        return None


def check_save_compat(save_path: Path, mod_dir: Path, *, vanilla_core: Path | None = None) -> dict:
    """Check whether a save's referenced classes for `mod_dir`'s mod are present in its loaded jars.

    Returns a dict with `status` (LOADS / WILL_FAIL / UNKNOWN), `referenced`,
    `missing`, `ambiguous`, `mod_id`, `build_tag`, and `limitations`. See the
    module docstring for exactly how save class references are decoded and
    attributed.
    """
    campaign_xml = _resolve_save_path(save_path)
    mod_dir = Path(mod_dir).expanduser().resolve()
    index = ModClassIndex(mod_dir)
    vanilla_index = _vanilla_lookup(vanilla_core)

    referenced: dict[str, dict[str, object]] = {}
    missing: dict[str, dict[str, object]] = {}
    ambiguous: dict[str, list[str]] = {}
    limitations: dict[str, dict[str, object]] = {}

    for token, _is_cl, sample_path in _scan_save_tokens(campaign_xml):
        classes = index.resolve(token)
        if classes:
            if len(classes) > 1:
                ambiguous.setdefault(token, sorted(classes))
            for class_name in classes:
                entry = referenced.setdefault(class_name, {"occurrences": 0, "aliases": set(), "sample_path": sample_path})
                entry["occurrences"] += 1
                entry["aliases"].add(token)
            continue

        if "." in token or "_-" in token:
            package = _package_of(token.replace("_-", "$"))
            if index.owns_package(package):
                entry = missing.setdefault(token, {"occurrences": 0, "sample_path": sample_path})
                entry["occurrences"] += 1
                continue
            if vanilla_index is not None and vanilla_index.owns_package(package):
                continue
            entry = limitations.setdefault(token, {"reason": "unattributed dotted reference", "occurrences": 0, "sample_path": sample_path})
            entry["occurrences"] += 1
            continue

        if not _looks_like_bare_class_name(token):
            continue
        if vanilla_index is not None:
            if vanilla_index.resolve(token):
                continue
            entry = limitations.setdefault(token, {"reason": "unattributed non-vanilla simple name", "occurrences": 0, "sample_path": sample_path})
            entry["occurrences"] += 1
        else:
            entry = limitations.setdefault(token, {"reason": "unattributed simple name (no vanilla_core to rule out vanilla)", "occurrences": 0, "sample_path": sample_path})
            entry["occurrences"] += 1

    if missing:
        status = "WILL_FAIL"
    elif referenced:
        status = "LOADS"
    else:
        status = "UNKNOWN"

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_COMPAT",
        "save": str(campaign_xml),
        "mod_dir": str(mod_dir),
        "mod_id": _mod_id(mod_dir),
        "build_tag": _build_tag_display(mod_dir),
        "status": status,
        "referenced": {
            "count": len(referenced),
            "classes": [
                {
                    "class": name,
                    "occurrences": entry["occurrences"],
                    "aliases": sorted(entry["aliases"]),
                }
                for name, entry in sorted(referenced.items())
            ],
        },
        "missing": [
            {
                "reference": token,
                "occurrences": entry["occurrences"],
                "sample_path": entry["sample_path"],
            }
            for token, entry in sorted(missing.items())
        ],
        "ambiguous": [
            {"alias": alias, "classes": classes}
            for alias, classes in sorted(ambiguous.items())
        ],
        "limitations": [
            {
                "reference": token,
                "reason": entry["reason"],
                "occurrences": entry["occurrences"],
                "sample_path": entry["sample_path"],
            }
            for token, entry in sorted(limitations.items())
        ],
    }


def compare_builds(save_path: Path, old_jar_or_mod: Path, new_jar_or_mod: Path) -> dict:
    """Which classes a save references that exist in `old_jar_or_mod` but not `new_jar_or_mod`.

    Pairs with `jar-audit`'s removed-class list: this narrows that list down
    to only the classes a *specific save* actually needs.
    """
    campaign_xml = _resolve_save_path(save_path)
    old_index = ModClassIndex(old_jar_or_mod)
    new_index = ModClassIndex(new_jar_or_mod)

    referenced_old: dict[str, dict[str, object]] = {}
    for token, _is_cl, sample_path in _scan_save_tokens(campaign_xml):
        classes = old_index.resolve(token)
        if not classes:
            continue
        for class_name in classes:
            entry = referenced_old.setdefault(class_name, {"occurrences": 0, "aliases": set(), "sample_path": sample_path})
            entry["occurrences"] += 1
            entry["aliases"].add(token)

    dropped = sorted(name for name in referenced_old if name not in new_index.canonical)

    return {
        "schema_version": 1,
        "mode": "READ_ONLY_SAVE_COMPAT_COMPARE",
        "save": str(campaign_xml),
        "old": str(Path(old_jar_or_mod).expanduser().resolve()),
        "new": str(Path(new_jar_or_mod).expanduser().resolve()),
        "referenced_in_old": {
            "count": len(referenced_old),
            "classes": [
                {"class": name, "occurrences": entry["occurrences"], "aliases": sorted(entry["aliases"])}
                for name, entry in sorted(referenced_old.items())
            ],
        },
        "dropped_in_new": dropped,
        "status": "WILL_FAIL" if dropped else "LOADS",
    }
