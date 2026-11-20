"""94.G2 slice 9: the donor's files that still name what a gene provides, as graded dependents with a load condition.

LOBSTER-SUB-20261120 (Test1, 2026-11-20) removed Scrapyard Armories' whole lobster ship (`variant:sa_lobster_royal`) and was
Fatal at load: five files still named the variant, and the static subtraction proof had located none of them. vendor-plan
already listed all five as suspects of the gene ("mentions a closure id but nothing in the closure references this file");
the proof only never used them. This turns those suspects, and the dependents the scanner located, into dependents with:

- `grade`: `reference` when the file's loader is evidenced, else `mention` (a description, a comment, a file nothing loads);
- `loaded`, from evidence only:
  - `always`: the core has the same path (`data/world/factions/default_ship_roles.json`, `data/config/title_screen_variants.csv`),
    or it is a spec under a folder the game scans (`SPEC_FOLDERS`, the ones vendor-plan indexes: a `.ship` under `data/hulls`,
    a `.variant` anywhere under `data/variants`);
  - `on mission start`: a `data/missions/<name>/MissionDefinition.java`, as the core's own missions are (CLAUDE.md: a
    mission naming a missing variant is Fatal when that mission starts, not at New Game);
  - `with <mod id>`: a jar of a provider mod (under `--provider-root`) names the path as a string literal, exactly, as a
    concatenation template (`data/config/exerelinFactionConfig/\\x01.json`, Nexerelin's NexFactionConfig) or as a folder
    (`data/config/modFiles/magicBounty_variants/`). MagicLib's MagicBountyLoader names
    `data/config/modFiles/magicBounty_data.json` (measured 2026-11-20 on MagicLib 1.6.1 and Nexerelin 0.12.2d);
  - `unknown` otherwise.

A dependent never fails subtraction (G2, 2026-11-19); `loaded` is what a boot half needs to tell BLOCKED_BY_DEPENDENT from an
unexplained Fatal: a dependent explains a Fatal only when its condition held in that run (advisor 2026-11-20). Only direct
dependents: a dependent's own dependents are not followed.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

ALWAYS, ON_MISSION, UNKNOWN = "always", "on mission start", "unknown"
_MISSION = re.compile(r"^data/missions/[^/]+/MissionDefinition\.java$")
_PLACEHOLDER = "\x01"  # the slot javac's string concatenation (makeConcatWithConstants) leaves in a recipe


# The folders whose specs the game finds by scanning, with the suffix it reads there: vendor-plan's `_Index` walks the same
# ones (data/weapons .wpn and .proj, data/hulls .ship and .skin, data/variants .variant, data/shipsystems .system), and its
# closure has stood on them through every live run. Anywhere else only the exact path the core has shows a loader: a core
# folder holding `settings.json` does not make `data/config/x.json` loaded (review 2026-11-20).
SPEC_FOLDERS = (("data/weapons/", ".wpn"), ("data/weapons/", ".proj"), ("data/hulls/", ".ship"), ("data/hulls/", ".skin"),
                ("data/variants/", ".variant"), ("data/shipsystems/", ".system"))


def _core_loads(vanilla_core: Path | None, relative: str) -> bool:
    """True when vanilla's own loader reads `relative`: the core has that very path, or it is a spec under a scanned folder."""
    if any(relative.startswith(folder) and relative.endswith(suffix) for folder, suffix in SPEC_FOLDERS):
        return True
    return vanilla_core is not None and (Path(vanilla_core) / relative).is_file()


@lru_cache(maxsize=8)
def _provider_paths(provider_roots: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """((literal, mod id), ...) for every string literal starting with `data/` in the loaded jars of the provider mods."""
    from bridgeforge.atlas.atlas_classfile import ClassFormatError, parse_class
    from bridgeforge.mod_files import read_mod_info
    from bridgeforge.scan.scan_classfile import _loaded_mod_jars, iter_class_files_in_jars

    found = set()
    for root in provider_roots:
        for folder in sorted(p for p in Path(root).iterdir() if p.is_dir()) if Path(root).is_dir() else []:
            info = read_mod_info(folder) or {}
            mod_id = info.get("id") if isinstance(info.get("id"), str) else None
            if not mod_id:
                continue
            try:
                classes = list(iter_class_files_in_jars(_loaded_mod_jars(folder)))
            except OSError:
                continue  # an unreadable provider folder shows no loader
            for _jar, _member, data in classes:
                try:
                    strings = parse_class(data).strings
                except ClassFormatError:
                    continue
                found.update((s, mod_id) for s in strings if s.startswith("data/"))
    return tuple(sorted(found))


def literal_matches(literal: str, path: str) -> bool:
    """`path` is what a loader naming `literal` reads: the same path, a concatenation template, or a folder it lists."""
    if _PLACEHOLDER in literal:
        # A template names a loader only when its folder is fixed and its file name keeps a fixed part (`\x01.json`):
        # `"data/config/" + name` would name every config file (review 2026-11-20).
        directory, _, name = literal.rpartition("/")
        if _PLACEHOLDER in directory or directory.count("/") < 2 or not name.replace(_PLACEHOLDER, ""):
            return False
        pattern = "".join("[^/]+" if part == _PLACEHOLDER else re.escape(part) for part in re.split(f"({_PLACEHOLDER})", literal))
        return re.fullmatch(pattern, path) is not None
    # A folder literal names the files directly in it, and only a specific folder: AshLib's bare `data/` and MagicLib's
    # `data/config/` matched every config file (measured 2026-11-20), so a folder needs three segments.
    folder = literal.endswith("/") and literal.count("/") >= 3 and path.rsplit("/", 1)[0] + "/" == literal
    return path == literal or folder


def load_condition(relative: str, vanilla_core: Path | None, provider_roots: list[Path]) -> str:
    if _MISSION.match(relative):
        return ON_MISSION
    if _core_loads(vanilla_core, relative):
        return ALWAYS
    mods = sorted({mod for literal, mod in _provider_paths(tuple(str(p) for p in provider_roots)) if literal_matches(literal, relative)})
    return f"with {', '.join(mods)}" if mods else UNKNOWN


def _named(text: str, ident: str) -> bool:
    return re.search(rf"(?<![\w$]){re.escape(ident)}(?![\w$])", text) is not None


def graded(gene: dict, located: list[dict], vanilla_core: Path | None, provider_roots: list[Path], root: Path | None = None) -> list[dict]:
    """The subtraction proof's dependents: those the scanner located plus the gene's mention suspects, each with grade and
    loaded. A `(not located)` dependent goes when a reference was found for the same provided id. With the donor `root`, a suspect
    file is read again and a provided id counts only as a whole token: vendor-plan's mentions are substrings, so
    `sa_lobster` was found inside `sa_lobster_royal` (2026-11-20)."""
    provided: dict[str, list[str]] = {}
    for anchor in gene["provides"]:
        provided.setdefault(anchor.split(":", 1)[1], []).append(anchor)  # one id may be provided as two kinds
    rows: dict[tuple[str, str], dict] = {}
    for dependent in located:
        rows[(dependent["from"], dependent["to"])] = dict(dependent)
    for suspect in gene["unknowns"]["suspects"]:
        path = suspect.get("path") or ""
        if "!" in path or "#" in path or not Path(path).suffix:
            continue  # a jar class or a settings key mentioning an id is judged elsewhere
        idents = [i for i in suspect.get("mentions") or [] if i in provided]
        if root is not None and (Path(root) / path).is_file():
            text = (Path(root) / path).read_text(encoding="utf-8", errors="replace")
            idents = [i for i in idents if _named(text, i)]
        for ident in idents:
            for anchor in provided[ident]:
                rows.setdefault((path, anchor), {"from": path, "to": anchor})
    result = []
    for (source, to), row in sorted(rows.items()):
        loaded = UNKNOWN if source == "(not located)" else load_condition(source, vanilla_core, provider_roots)
        result.append({**row, "grade": "mention" if loaded == UNKNOWN else "reference", "loaded": loaded})
    # A `(not located)` row yields only to a located reference: a mere mention elsewhere does not explain it (review 2026-11-20).
    referenced = {row["to"] for row in result if row["grade"] == "reference"}
    return [row for row in result if not (row["from"] == "(not located)" and row["to"] in referenced)]


__all__ = ["ALWAYS", "ON_MISSION", "SPEC_FOLDERS", "UNKNOWN", "graded", "literal_matches", "load_condition"]
