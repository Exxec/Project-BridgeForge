from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator, NamedTuple
from xml.etree import ElementTree as ET

"""Shared streaming helpers for save-format tooling (roadmap P3b, modules A/E/I/L).

## Two files, two reading strategies

Every save directory holds a `descriptor.xml` (a few hundred lines: character
name, save date, game version, and the **mod list with versions**) and a
`campaign.xml` (the ~10 MB XStream-serialized campaign object graph).
`descriptor.xml` is small enough to parse as a full DOM with `ElementTree`
without violating the "no full-DOM loads" rule, which exists for the ~10 MB
`campaign.xml` -- that one is only ever read with the streaming line scanner
below, one line at a time, never loaded whole.

## How Starsector records the enabled mod list (verified on real descriptors)

`descriptor.xml` has two mod-list sections:
  - `<allModsEverEnabled><EnabledModData z="N"><spec z="M">...</spec>...`:
    one `spec` per mod ever enabled on this save, each carrying `id`, `name`,
    `versionInfo` (a `major`/`minor`/`patch`/`string` block; `string` is the
    dotted display version, e.g. `"0.7.2"`), `gameVersion` (the RC the mod
    declares), `dirName`, `path`, `jars`, and `dependencies`.
  - `<enabledMods><EnabledModData z="N"><spec ref="M"></spec>...`: the
    *currently* enabled subset, each an XStream back-reference (`ref=`) to a
    `spec`'s `z=` id in `allModsEverEnabled` rather than a repeated block.
This module resolves those `ref=` links itself (`ElementTree` has no notion
of XStream's `z`/`ref` graph reuse) and returns both the full "ever enabled"
list and the resolved "currently enabled" list.

Confirmed on `In operation/_rig/saves/save_FourthAnderson_*`:
Exigency's `spec` shows `id=exigency`, `name=Exigency`,
`versionInfo/string=0.7.2`, `gameVersion/string=0.98a-RC8`,
`dirName=Exigency`; `enabledMods` resolves via `ref=` back to that same
`z=` id.

## Streaming `campaign.xml`

Starsector's XStream writer emits one tag (or one open+text+close leaf) per
line -- confirmed by inspecting `save_FourthAnderson_*/campaign.xml` and
`save_TrangThisbe_*/campaign.xml` directly. `iter_elements` relies on that
convention: a line-by-line `readline()` scan (never the whole file in
memory) that tracks an ancestor-tag stack, matches leaf `<tag attrs>text</tag>`
pairs into a single `Element` (with `.text` set), and yields every other
open tag as an `Element` with `.text is None` (its scalar children, if any,
follow as later elements at `depth + 1`). A `PeekableElements` wrapper adds
one-element lookahead so callers (see `save_inspect.read_scalar_record`) can
tell when a tracked object's own scope has ended without needing explicit
close-tag events.
"""


class SaveReadError(ValueError):
    """Raised when a save directory/file or descriptor.xml cannot be resolved or parsed."""


def resolve_save_dir(save: Path | str) -> Path:
    """Resolve a save argument (its directory, or a campaign.xml/descriptor.xml inside it)."""
    path = Path(save).expanduser().resolve()
    if path.is_dir():
        return path
    if path.is_file():
        return path.parent
    raise SaveReadError(f"{path} does not exist.")


def campaign_xml_path(save: Path | str) -> Path:
    # An explicit campaign.xml* file (notably campaign.xml.bak, the previous save) is used as given;
    # mapping it back to its folder made `save-diff campaign.xml campaign.xml.bak` compare a file
    # with itself (PRB-2, 2026-09-13).
    explicit = Path(save).expanduser().resolve()
    if explicit.is_file() and explicit.name.startswith("campaign.xml"):
        return explicit
    save_dir = resolve_save_dir(save)
    campaign = save_dir / "campaign.xml"
    if not campaign.is_file():
        raise SaveReadError(f"{save_dir} has no campaign.xml.")
    return campaign


def descriptor_xml_path(save: Path | str) -> Path:
    save_dir = resolve_save_dir(save)
    descriptor = save_dir / "descriptor.xml"
    if not descriptor.is_file():
        raise SaveReadError(f"{save_dir} has no descriptor.xml.")
    return descriptor


_BF_NAME_SUFFIX = re.compile(r"\[BF\s+r(\d+)\]\s*$")
_BF_VERSION_SUFFIX = re.compile(r"\+bf\.(\d+)\s*$")


def parse_build_tag(name: str | None, version: str | None) -> dict[str, object]:
    """Extract our `[BF rN]` name suffix and/or `+bf.N` version suffix, per `build_tag.py`.

    Both may be present, absent, or (rarely, if a release stripped one) disagree; both are
    reported rather than collapsed, so callers can decide. `build` is the higher of the two
    when both are present (a build only ever increases), else whichever is present, else None.
    """
    name_match = _BF_NAME_SUFFIX.search(name) if name else None
    version_match = _BF_VERSION_SUFFIX.search(version) if version else None
    name_build = int(name_match.group(1)) if name_match else None
    version_build = int(version_match.group(1)) if version_match else None
    if name_build is not None and version_build is not None:
        build = max(name_build, version_build)
    else:
        build = name_build if name_build is not None else version_build
    return {
        "name_build": name_build,
        "version_build": version_build,
        "build": build,
        "tagged": build is not None,
    }


def _text(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    child = el.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _parse_spec(spec: ET.Element) -> dict[str, object]:
    mod_id = _text(spec, "id")
    name = _text(spec, "name")
    dir_name = _text(spec, "dirName")
    dir_path = _text(spec, "path")
    version_info = spec.find("versionInfo")
    version = _text(version_info, "string") if version_info is not None else None
    if not version and version_info is not None:
        parts = [
            piece
            for piece in (_text(version_info, "major"), _text(version_info, "minor"), _text(version_info, "patch"))
            if piece
        ]
        version = ".".join(parts) if parts else None
    game_version_el = spec.find("gameVersion")
    game_version = _text(game_version_el, "string") if game_version_el is not None else None
    return {
        "id": mod_id,
        "name": name,
        "dir_name": dir_name,
        "path": dir_path,
        "version": version,
        "game_version": game_version,
        "build_tag": parse_build_tag(name, version),
    }


def parse_descriptor(save: Path | str) -> dict[str, object]:
    """Parse `descriptor.xml`: save identity plus the mod list, with versions and build tags.

    `descriptor.xml` is small; this is the one place in this module that uses a full-DOM parse
    (see module docstring). Returns `all_mods_ever_enabled` (every `spec` ever recorded) and
    `enabled_mods` (the `ref=`-resolved subset actually enabled for this save).
    """
    descriptor = descriptor_xml_path(save)
    try:
        root = ET.parse(descriptor).getroot()
    except ET.ParseError as exc:
        raise SaveReadError(f"{descriptor} is not well-formed XML: {exc}") from exc

    specs_by_z: dict[str, dict[str, object]] = {}
    all_mods_el = root.find("allModsEverEnabled")
    if all_mods_el is not None:
        for entry in all_mods_el.findall("EnabledModData"):
            spec = entry.find("spec")
            if spec is None:
                continue
            z = spec.get("z")
            info = _parse_spec(spec)
            if z:
                specs_by_z[z] = info

    enabled_mods: list[dict[str, object]] = []
    enabled_el = root.find("enabledMods")
    if enabled_el is not None:
        for entry in enabled_el.findall("EnabledModData"):
            spec = entry.find("spec")
            if spec is None:
                continue
            ref = spec.get("ref")
            if ref and ref in specs_by_z:
                enabled_mods.append(specs_by_z[ref])

    return {
        "save_dir": str(resolve_save_dir(save)),
        "character_name": _text(root, "characterName"),
        "save_date": _text(root, "saveDate"),
        "game_version": _text(root, "gameVersion"),
        "all_mods_ever_enabled": list(specs_by_z.values()),
        "enabled_mods": enabled_mods,
    }


class Element(NamedTuple):
    tag: str
    attrs: dict[str, str]
    text: str | None
    path: tuple[str, ...]


_TAG_PATTERN = re.compile(
    r"<(/?)([A-Za-z_][\w.\-]*)((?:\s+[\w:.\-]+=\"[^\"]*\")*)\s*(/?)>"
)
_ATTR_PATTERN = re.compile(r'([\w:.\-]+)="([^"]*)"')


def iter_elements(campaign_xml: Path | str) -> Iterator[Element]:
    """Stream `campaign.xml` one line at a time, yielding an `Element` per tag.

    Never loads the file into memory at once. Relies on Starsector's XStream writer emitting
    one tag (or one open+text+close leaf pair) per line -- see module docstring for where this
    was confirmed. A leaf line like `<loitering>true</loitering>` yields one `Element` with
    `.text == "true"`; a structural line like `<ExipiratedAvestaMovement z="891">` yields an
    `Element` with `.text is None`, and its scalar children follow as later elements one level
    deeper in `.path`.
    """
    campaign_xml = Path(campaign_xml)
    stack: list[str] = []
    with campaign_xml.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            matches = list(_TAG_PATTERN.finditer(line))
            skip_next = False
            for index, match in enumerate(matches):
                if skip_next:
                    skip_next = False
                    continue
                closing, name, attrs_str, self_closing = match.groups()
                if closing:
                    if stack and stack[-1] == name:
                        stack.pop()
                    continue
                attrs = dict(_ATTR_PATTERN.findall(attrs_str))
                if self_closing:
                    yield Element(name, attrs, None, tuple(stack) + (name,))
                    continue
                text = None
                if index + 1 < len(matches):
                    next_closing, next_name = matches[index + 1].group(1), matches[index + 1].group(2)
                    if next_closing and next_name == name:
                        text = line[match.end():matches[index + 1].start()]
                        skip_next = True
                path = tuple(stack) + (name,)
                if text is None:
                    stack.append(name)
                yield Element(name, attrs, text, path)


class PeekableElements:
    """One-element lookahead over `iter_elements`, so a consumer can tell when a tracked
    object's scope has ended (its next sibling/ancestor appears) without explicit close events.
    """

    def __init__(self, source: Iterator[Element]):
        self._source = iter(source)
        self._buffered: Element | None = None
        self._has_buffered = False

    def peek(self) -> Element | None:
        if not self._has_buffered:
            self._buffered = next(self._source, None)
            self._has_buffered = True
        return self._buffered

    def __next__(self) -> Element:
        if self._has_buffered:
            self._has_buffered = False
            value = self._buffered
            self._buffered = None
            if value is None:
                raise StopIteration
            return value
        value = next(self._source, None)
        if value is None:
            raise StopIteration
        return value

    def __iter__(self) -> "PeekableElements":
        return self

    def close(self) -> None:
        """Close the underlying generator (and its file handle) without draining it.

        Needed on Windows when a caller stops consuming early (e.g. a diff that only reads a
        tracked object's own scope): a generator otherwise keeps its `with open(...)` frame
        alive, and its file locked, until garbage collection happens to run.
        """
        close = getattr(self._source, "close", None)
        if close is not None:
            close()


def open_campaign_stream(save: Path | str) -> PeekableElements:
    return PeekableElements(iter_elements(campaign_xml_path(save)))


def coerce_scalar(text: str) -> object:
    """Best-effort text -> int/float/bool, else the original string."""
    if text == "true":
        return True
    if text == "false":
        return False
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        pass
    return text


def read_scalar_record(stream: PeekableElements, start_depth: int) -> dict[str, object]:
    """Consume a tracked element's immediate-child scalar fields until its scope ends.

    Call right after receiving the tracked start `Element` (whose `len(path) == start_depth`).
    Only depth `start_depth + 1` fields are recorded (e.g. `ExipiratedAvestaMovement`'s
    `waypoint`/`progress`/`loitering`/`loiterTime`/`burnLevel`/`miningFleetQuota`); deeper
    nested structures (e.g. its `WAYPOINTS` list) are consumed to keep the stream in sync but
    not expanded into the record. A leaf child with no text but a `ref=`/`cl=` attribute (an
    XStream back-reference or resolved-type marker) is recorded under `field@ref`/`field@cl` so
    entity links are visible without dereferencing them.
    """
    record: dict[str, object] = {}
    while True:
        nxt = stream.peek()
        if nxt is None or len(nxt.path) <= start_depth:
            break
        element = next(stream)
        if len(element.path) != start_depth + 1:
            continue
        # Attribute-only leaves (an XStream `ref=`/`cl=` back-reference, e.g.
        # `<entity cl="CCEnt" ref="99"></entity>`) take priority over their -- always empty or
        # absent -- text, so the reference is recorded rather than a blank string.
        if element.attrs.get("ref"):
            record[f"{element.tag}@ref"] = element.attrs["ref"]
        elif element.attrs.get("cl"):
            record.setdefault(f"{element.tag}@cl", element.attrs["cl"])
        elif element.text is not None:
            record[element.tag] = coerce_scalar(element.text)
    return record
