"""94.G2 slice 19: what a carrier must hold for the game to load it, beyond the anchors its genes define.

P2's and P3's carriers passed static isolation and were then Fatal at load (P2B-CAR-20261122, P3B-CAR-20261122): their hulls
use a hull style only the donor's `data/config/hull_styles.json` defines. With the styles added by hand, P3's carrier went on to
a missing cover image the style names (DIAG-P3-STYLES-20261123). RC8_BEHAVIOUR RC8-49: a hull's `style` must be defined, in the
core's file or a mod's merged into it, and every file a style names must exist, or the game is Fatal at load.

`load_gaps` lists every such gap at once, where the game shows only the first. A style's files are its string values that name
an image or sound file: vanilla RC7's styles name them under thirteen keys (`slotCover*`, `dHullOverlay*`, `damageDecal*`,
`fluxVent*`), all `.png` (read 2026-11-23). A `.skin` may set `style` too (vanilla's `brawler_tritachyon` and
`buffalo_tritachyon` do), so skins are read as well. A style or file a declared dependency's folder holds counts as present:
the game merges that mod's files too (review of slice 19).
"""
from __future__ import annotations

from pathlib import Path

HULL_STYLES = "data/config/hull_styles.json"
_FILE_SUFFIXES = (".png", ".jpg", ".jpeg", ".ogg", ".wav")


def _styles(root: Path | None, gaps: list[dict] | None = None, label: str = "") -> dict:
    """{style id: its definition} of a folder's `data/config/hull_styles.json` (empty when there is none). An unreadable file
    is a gap of its own when `gaps` is given, so it is not taken for undefined styles."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    if root is None or not (Path(root) / HULL_STYLES).is_file():
        return {}
    data = _load_lenient_json_file(Path(root) / HULL_STYLES)
    if isinstance(data, dict):
        return data
    if gaps is not None:
        gaps.append({"finding": "hull-styles-unreadable", "file": HULL_STYLES, "where": label})
    return {}


def files_named(definition: object) -> list[str]:
    """The image and sound files a style definition names, as paths relative to a mod or the core (a leading `/` dropped)."""
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and value.strip().lower().endswith(_FILE_SUFFIXES):
            found.add(value.strip().replace("\\", "/").lstrip("/"))

    walk(definition)
    return sorted(found)


def _held(relative: str, roots: list[Path]) -> bool:
    if ".." in relative.split("/"):
        return False  # never looked up outside its folder
    return any((root / relative).is_file() for root in roots)


def load_gaps(carrier: Path, vanilla_core: Path, dependencies: list[Path] | None = None) -> list[dict]:
    """[{finding, file, ...}]: each hull or skin whose `style` neither the carrier, a declared dependency's folder nor the core
    defines (`hull-style-undefined`); each file a style the carrier defines names that none of them holds
    (`hull-style-file-missing`); and each hull, skin or styles file that cannot be read (`hull-file-unreadable`,
    `hull-styles-unreadable`)."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    carrier = Path(carrier)
    others = [Path(d) for d in dependencies or []] + [Path(vanilla_core)]
    gaps: list[dict] = []
    own = _styles(carrier, gaps, "carrier")
    known = dict(own)
    for root in others:
        known.update({k: v for k, v in _styles(root).items() if k not in known})
    hulls = carrier / "data" / "hulls"
    for path in sorted([*hulls.rglob("*.ship"), *hulls.rglob("*.skin")]) if hulls.is_dir() else []:
        data = _load_lenient_json_file(path)
        relative = path.relative_to(carrier).as_posix()
        if not isinstance(data, dict):
            gaps.append({"finding": "hull-file-unreadable", "file": relative})
            continue
        style = data.get("style")
        if isinstance(style, str) and style.strip() and style not in known:
            gaps.append({"finding": "hull-style-undefined", "file": relative, "style": style})
    for name in sorted(own):
        for relative in files_named(own[name]):
            if not _held(relative, [carrier, *others]):
                gaps.append({"finding": "hull-style-file-missing", "file": HULL_STYLES, "style": name, "path": relative})
    return gaps


def dependency_folders(provider_roots: list[Path], mod_ids: list[str]) -> list[Path]:
    """The folders under `provider_roots` (mods/ folders) whose mod_info id is one of `mod_ids`."""
    from bridgeforge.mod_files import read_mod_info

    wanted, found = set(mod_ids), []
    for root in provider_roots:
        for folder in sorted(Path(root).iterdir()) if Path(root).is_dir() else []:
            info = read_mod_info(folder) if folder.is_dir() else None
            if isinstance(info, dict) and info.get("id") in wanted:
                found.append(folder)
    return found


__all__ = ["HULL_STYLES", "dependency_folders", "files_named", "load_gaps"]
