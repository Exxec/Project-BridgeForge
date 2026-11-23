"""94.G2 slice 19: what a carrier must hold for the game to load it, beyond the anchors its genes define.

P2's and P3's carriers passed static isolation and were then Fatal at load (P2B-CAR-20261122, P3B-CAR-20261122): their hulls
use a hull style only the donor's `data/config/hull_styles.json` defines. With the styles added by hand, P3's carrier went on to
a missing cover image the style names (DIAG-P3-STYLES-20261123). RC8_BEHAVIOUR RC8-49: a hull's `style` must be defined, in the
core's file or a mod's merged into it, and every file a style names must exist, or the game is Fatal at load.

`load_gaps` lists every such gap at once, where the game shows only the first. A style's files are its string values that name
an image or sound file: vanilla RC7's styles name them under thirteen keys (`slotCover*`, `dHullOverlay*`, `damageDecal*`,
`fluxVent*`), all `.png` (read 2026-11-23). A `.skin` may set `style` too (vanilla's `brawler_tritachyon` and
`buffalo_tritachyon` do), so skins are read as well.
"""
from __future__ import annotations

from pathlib import Path

HULL_STYLES = "data/config/hull_styles.json"
_FILE_SUFFIXES = (".png", ".jpg", ".jpeg", ".ogg", ".wav")


def _styles(root: Path | None) -> dict:
    """{style id: its definition} of a folder's `data/config/hull_styles.json` (empty when there is none)."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    if root is None or not (Path(root) / HULL_STYLES).is_file():
        return {}
    data = _load_lenient_json_file(Path(root) / HULL_STYLES)
    return data if isinstance(data, dict) else {}


def files_named(definition: object) -> list[str]:
    """The image and sound files a style definition names, as paths relative to a mod or the core."""
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, str) and "/" in value and value.lower().endswith(_FILE_SUFFIXES):
            found.add(value.strip().replace("\\", "/"))

    walk(definition)
    return sorted(found)


def load_gaps(carrier: Path, vanilla_core: Path | None) -> list[dict]:
    """[{finding, file, style, path?}]: each hull or skin whose `style` neither the carrier nor the core defines
    (`hull-style-undefined`), and each file a style the carrier defines names that neither holds (`hull-style-file-missing`)."""
    from bridgeforge.scan.scanner import _load_lenient_json_file

    carrier = Path(carrier)
    core = Path(vanilla_core) if vanilla_core else None
    own, core_styles = _styles(carrier), _styles(core)
    gaps: list[dict] = []
    hulls = carrier / "data" / "hulls"
    for path in sorted([*hulls.rglob("*.ship"), *hulls.rglob("*.skin")]) if hulls.is_dir() else []:
        data = _load_lenient_json_file(path)
        style = data.get("style") if isinstance(data, dict) else None
        if isinstance(style, str) and style.strip() and style not in own and style not in core_styles:
            gaps.append({"finding": "hull-style-undefined", "file": path.relative_to(carrier).as_posix(), "style": style})
    for name in sorted(own):
        for relative in files_named(own[name]):
            if not (carrier / relative).is_file() and not (core is not None and (core / relative).is_file()):
                gaps.append({"finding": "hull-style-file-missing", "file": HULL_STYLES, "style": name, "path": relative})
    return gaps


__all__ = ["HULL_STYLES", "files_named", "load_gaps"]
