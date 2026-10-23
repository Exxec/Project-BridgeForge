from __future__ import annotations
import re
from pathlib import Path
from ..scanner import LEGACY_PERSONALITY_IDS, _blank_java_comments, _SOURCE_SET_PERSONALITY
from .common import FileChange, FixerError, _decode, _encode, _findings_of, _relative_path


# ---------------------------------------------------------------------------
# Fixer: rules-firebest-populate-options
# ---------------------------------------------------------------------------

_FIREBEST_POPULATE_OPTIONS_PATTERN = re.compile(r"\bFireBest(\s+)PopulateOptions\b")


def _fix_rules_firebest_populate_options(root: Path, options: dict) -> list[FileChange]:
    """FireBest PopulateOptions -> FireAll PopulateOptions in rules.csv (live bug VAC-DIALOG-01).

    FireBest runs only the single best-scoring rule; PopulateOptions menus are built by many rules
    together (trade, comm directory, Leave...), so FireBest leaves the player in a dialog with no way
    out. Vanilla's own rules.csv uses FireAll PopulateOptions everywhere (462 times) and FireBest never,
    so the rewrite is a literal keyword swap - same column, same surrounding whitespace.
    """
    path = root / "data" / "campaign" / "rules.csv"
    if not path.is_file():
        raise FixerError(f"No rules.csv found at {path}.")
    raw = path.read_bytes()
    text, had_bom = _decode(raw)
    new_text, count = _FIREBEST_POPULATE_OPTIONS_PATTERN.subn(r"FireAll\1PopulateOptions", text)
    if count == 0:
        raise FixerError(f"{path} has no 'FireBest PopulateOptions' to fix.")
    return [FileChange(path=path, before=raw, after=_encode(new_text, had_bom))]


# ---------------------------------------------------------------------------
# Fixer: personality-id-unknown (loose scripts only)
# ---------------------------------------------------------------------------


def _fix_personality_id_unknown(root: Path, options: dict) -> list[FileChange]:
    """cowardly/suicidal/fearless -> timid/reckless/reckless in setPersonality(...) (loose scripts only).

    RC8 dropped these 0.6-era personality ids (bridgeforge.scanner.LEGACY_PERSONALITY_IDS); an unknown
    id leaves the officer's personality null and Ship.getPersonality() NPEs on deploy - a Fatal dialog on
    the first affected ship (live run SK13-1d, SEEKER's missions). The mapping is the same one-to-one
    table the scanner's own finding explanation already suggests. A jar's bundled source needs the jar
    rebuilt, so a match found only there is refused rather than silently skipped.
    """

    files = sorted({f.file for f in _findings_of(root, options, "personality-id-unknown") if f.file})
    loose = [rel for rel in files if "!" not in rel]
    if not loose:
        detail = f" (jar sources need a rebuild: {', '.join(files[:5])})" if files else ""
        raise FixerError(f"No loose script has an unknown legacy personality id{detail}.")

    def _rewrite(match: re.Match) -> str:
        new = LEGACY_PERSONALITY_IDS.get(match.group(1))
        return f'setPersonality("{new}")' if new else match.group(0)

    changes: list[FileChange] = []
    for rel in loose:
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text = _SOURCE_SET_PERSONALITY.sub(_rewrite, text)
        if new_text != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("The flagged loose scripts could not be rewritten mechanically; fix them by hand.")
    return changes


# ---------------------------------------------------------------------------
# Fixer: nexerelin-corvus-mode-import (ROADMAP 34.13)
# ---------------------------------------------------------------------------


def _fix_nexerelin_corvus_mode_import(root: Path, options: dict) -> list[FileChange]:
    """SectorManager[.getManager()].getCorvusMode() -> (!Global.getSector().getMemoryWithoutUpdate()
    .getBoolean("$nex_randomSector")) and the Nexerelin import dropped (done by hand for Hiver Swarm, 2026-10-04;
    evidence in scanner._scan_nexerelin_corvus_mode_import). Without Nexerelin the key is absent and getBoolean
    returns false, i.e. "Corvus mode", which is the vanilla sector."""
    from ..scanner import _NEX_CORVUS_CALL, _NEX_SECTOR_MANAGER_IMPORT

    replacement = '(!Global.getSector().getMemoryWithoutUpdate().getBoolean("$nex_randomSector"))'
    changes: list[FileChange] = []
    for rel in sorted({f.file for f in _findings_of(root, options, "nexerelin-corvus-mode-import") if f.file}):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        new_text = _NEX_CORVUS_CALL.sub(lambda _m: replacement, _NEX_SECTOR_MANAGER_IMPORT.sub("", text, count=1))
        if "import com.fs.starfarer.api.Global;" not in new_text and "import com.fs.starfarer.api.*;" not in new_text:
            package = re.search(r"^package [\w.]+;\s*\n", new_text, re.M)
            at = package.end() if package else 0
            new_text = new_text[:at] + "import com.fs.starfarer.api.Global;\n" + new_text[at:]
        if new_text != text:
            changes.append(FileChange(path=path, before=raw, after=_encode(new_text, had_bom)))
    if not changes:
        raise FixerError("No loose script imports Nexerelin's SectorManager only for getCorvusMode().")
    return changes


# ---------------------------------------------------------------------------
# Fixer: campaign-lookup-dereferenced-unguarded (2026-10-04)
# ---------------------------------------------------------------------------

_VOID_METHOD_HEADER = re.compile(r"\bvoid\s+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{\s*$")


def _fix_lookup_dereferenced_unguarded(root: Path, options: dict) -> list[FileChange]:
    """Guard `getStarSystem(name).x()` / `getEntityById(id).x()` with `if (lookup == null) { return; }` when the
    statement is the first one in a void method (DNEEP's setIndustryOnPlanet, fixed by hand 2026-10-04): the early
    return skips only what would have thrown. Any other shape (inside a loop, after other statements, in a method that
    returns a value) is refused and left for a person. Loose scripts only."""

    lines_by_file: dict[str, set[int]] = {}
    for finding in _findings_of(root, options, "campaign-lookup-dereferenced-unguarded"):
        if finding.file and not finding.file.replace("\\", "/").startswith(("jars/", "src/")) and "!" not in finding.file:
            lines_by_file.setdefault(finding.file, set()).update(int(e.split(":", 1)[1]) for e in finding.evidence if e.startswith("line:"))
    changes, refused = [], []
    for rel, wanted in sorted(lines_by_file.items()):
        path = root / rel
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        eol = "\r\n" if "\r\n" in text else "\n"
        # splitlines counts line breaks as the scanner's universal-newline read does (a lone CR included)
        lines = text.splitlines(keepends=True)
        blank = _blank_java_comments(text).splitlines(keepends=True)
        inserts = []
        for number in sorted(wanted):
            index = number - 1
            call = re.search(r"\b(getStarSystem|getEntityById)\s*\(\s*([A-Za-z_]\w*)\s*\)", blank[index])
            previous = index - 1
            while previous >= 0 and not blank[previous].strip():
                previous -= 1
            if not call or previous < 0 or not _VOID_METHOD_HEADER.search(blank[previous]):
                refused.append(f"{rel}:{number}")
                continue
            receiver = re.search(r"([\w.()]*?)\b" + call.group(1) + r"\s*\(", lines[index])
            prefix = receiver.group(1) if receiver else ""
            indent = re.match(r"[ \t]*", lines[index]).group(0)
            inserts.append((index, [f"{indent}// BridgeForge: a missing system or entity (random sector, total conversion) is skipped.{eol}",
                                    f"{indent}if ({prefix}{call.group(1)}({call.group(2)}) == null) {{{eol}",
                                    f"{indent}    return;{eol}", f"{indent}}}{eol}"]))
        for index, block in sorted(inserts, reverse=True):
            lines[index:index] = block
        if inserts:
            changes.append(FileChange(path=path, before=raw, after=_encode("".join(lines), had_bom)))
    if not changes:
        raise FixerError("No unguarded lookup is the first statement of a void method" + (f" (refused: {', '.join(refused[:5])})" if refused else "."))
    return changes


# ---------------------------------------------------------------------------
# Fixer: temporary-market-fleet-source (ROADMAP 34.38, 2026-10-04)
# ---------------------------------------------------------------------------

_TEMP_MARKET = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*Global\s*\.\s*getFactory\s*\(\s*\)\s*\.\s*createMarket\s*\(")
_REMOVE_MARKET_LINE = re.compile(r"^([ \t]*)Global\s*\.\s*getSector\s*\(\s*\)\s*\.\s*getEconomy\s*\(\s*\)\s*\.\s*removeMarket\s*\(\s*([A-Za-z_]\w*)\s*\)\s*;[ \t]*(\r?\n?)$")


def _temporary_market_sources(root: Path, options: dict) -> list[Path]:
    """Source files for the findings: a loose script as is; a jar class through the mod's bundled source
    (jars/src/ or src/, matched by package path), which patch-jar-class then compiles into the jar."""
    paths: list[Path] = []
    for finding in _findings_of(root, options, "temporary-market-fleet-source"):
        file = (finding.file or "").replace("\\", "/")
        if "!" in file:
            class_path = file.split("!", 1)[1].split("$", 1)[0].removesuffix(".class") + ".java"
            candidates = [root / base / class_path for base in ("jars/src", "src")]
            found = next((c for c in candidates if c.is_file()), None)
            if found is None:
                raise FixerError(f"{file}: no bundled source for this class (jars/src/ or src/); decompile it first")
            paths.append(found)
        elif file:
            paths.append(root / file)
    return sorted(set(paths))


def _fix_temporary_market_fleet_source(root: Path, options: dict) -> list[FileChange]:
    """Drop `Global.getSector().getEconomy().removeMarket(m);` where `m` came from `createMarket(...)` in the same
    file and is never `addMarket`-ed: the market never entered the economy, so vanilla only removes it from a list it is
    not in and marks the location cache stale (ReachEconomy.removeMarket, javap 2026-10-04; RC8-22), and
    the fleet still builds from the same market (same quality and size). AoTD Theory of Toolbox's economy turns each
    such call into a structural refresh (AoTDEconomy.removeMarket, 2026-10-04). A market that is also added, or a
    removeMarket not alone on its line, is refused."""

    changes, refused = [], []
    for path in _temporary_market_sources(root, options):
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        blank = _blank_java_comments(text)
        created = set(_TEMP_MARKET.findall(blank))
        lines = text.splitlines(keepends=True)
        blank_lines = blank.splitlines(keepends=True)
        changed = False
        for index, line in enumerate(blank_lines):
            match = _REMOVE_MARKET_LINE.match(line)
            if not match:
                continue
            name = match.group(2)
            if name not in created or re.search(r"\baddMarket\s*\(\s*" + re.escape(name) + r"\b", blank):
                refused.append(f"{_relative_path(root, path)}:{index + 1}")
                continue
            eol = match.group(3) or ""
            lines[index] = (f"{match.group(1)}// BridgeForge: removeMarket({name}) dropped; {name} never entered the economy, "
                            f"so vanilla only removed it from a list it was not in and marked a cache stale (RC8-22).{eol}")
            changed = True
        if changed:
            changes.append(FileChange(path=path, before=raw, after=_encode("".join(lines), had_bom)))
    if not changes:
        raise FixerError("No removeMarket of a never-added temporary market found" + (f" (refused: {', '.join(refused[:5])})" if refused else "."))
    return changes


def _fix_campaign_lookup_guard(root: Path, options: dict, finding_id: str) -> list[FileChange]:
    """Guard an unguarded `getStarSystem("X")` / `getEntityById("X")` in a void method: right after the declaration
    that takes the result, `if (v == null) { log a warning; return; }`. Done by hand for Pegasus Belt Council,
    Vayra's Sector and First Persean Empire (2026-09-29/30): a generator that assumes a vanilla system or entity
    exists NPEs at New Game in a total conversion or random sector.

    Applied only where the edit cannot change anything else: a one-line local declaration directly in a void
    method's body (not in a loop, lambda or inner block), so the early return skips only the rest of that method,
    which would have thrown on the null. Every other shape is refused and stays with an agent."""

    method = "getStarSystem" if finding_id == "hard-coded-campaign-system-reference" else "getEntityById"
    names_by_file: dict[str, set[str]] = {}
    for finding in _findings_of(root, options, finding_id):
        if finding.file and finding.evidence and "null-guarded" not in finding.evidence and "created-in-same-file" not in finding.evidence:
            names_by_file.setdefault(finding.file, set()).add(finding.evidence[0])
    changes, refused = [], []
    for relative, names in sorted(names_by_file.items()):
        path = root / relative
        # A jar's source tree is not what runs: an edit there changes nothing until the jar is rebuilt, so it is a jar
        # packet for patch-jar-class (21 of 33 first-run edits were jar sources, 2026-09-30).
        if not path.is_file() or path.suffix != ".java" or relative.replace("\\", "/").startswith(("src/", "jars/", "jar/")):  # any source under jars/ (Free Stars Union: jars/FSU_source_from_Procyon/)
            refused.append(relative)
            continue
        raw = path.read_bytes()
        text, had_bom = _decode(raw)
        newline = "\r\n" if "\r\n" in text else "\n"
        # Split the real and the comment-blanked text on the same boundaries: the blanker turns "\r" into a space, so
        # on a CRLF file split(newline) gave the blanked text ONE line and the guard went in at line 1, inside a doc
        # comment, once per revive round (Scy Nation's SCY_outposts, five times, 2026-09-30). Mixed endings: refuse.
        if newline == "\r\n" and text.count("\n") != text.count("\r\n"):
            refused.append(f"{relative} (mixed line endings)")
            continue
        lines = text.split(newline)
        blank = _blank_java_comments(text.replace("\r\n", "\n")).split("\n")
        if len(blank) != len(lines):
            refused.append(f"{relative} (line split mismatch)")
            continue
        cls = re.search(r"\bclass\s+(\w+)", _blank_java_comments(text))
        inserts: list[tuple[int, str]] = []
        for name in sorted(names):
            call = re.escape(method) + r'\s*\(\s*"' + re.escape(name) + r'"\s*\)'
            hits = [i for i, line in enumerate(blank) if re.search(call, line)]
            placed = False
            for i in hits:
                decl = re.match(r"^(\s*)(?:final\s+)?[\w.]+(?:<[\w.,\s<>?]*>)?\s+(\w+)\s*=\s*[^;]*" + call + r"\s*;\s*$", blank[i])
                if not decl or cls is None:
                    continue
                # Brace depth from the enclosing method's opening brace must be exactly 1.
                depth, start = 0, None
                for j in range(i - 1, -1, -1):
                    depth += blank[j].count("}") - blank[j].count("{")
                    if depth < 0:
                        start = j
                        break
                if start is None or depth != -1 or not re.search(r"\bvoid\s+\w+\s*\([^)]*\)\s*(?:throws[^{]*)?\{\s*$", blank[start]):
                    continue
                if "->" in blank[start]:
                    continue
                indent, variable = decl.group(1), decl.group(2)
                if i + 1 < len(lines) and f"if ({variable} == null)" in lines[i + 1]:
                    continue  # already guarded right here: never insert twice
                what = "star system" if method == "getStarSystem" else "entity"
                inserts.append((i + 1, newline.join([
                    f"{indent}if ({variable} == null) {{ // BridgeForge: guard a missing {what} (a total conversion or random sector)",
                    f'{indent}    com.fs.starfarer.api.Global.getLogger({cls.group(1)}.class).warn("{what} \\"{name}\\" not found, skipping the rest of this generator");',
                    f"{indent}    return;",
                    f"{indent}}}"])))
                placed = True
            if not placed:
                refused.append(f"{relative} ({name})")
        if inserts:
            for index, block in sorted(inserts, reverse=True):
                lines.insert(index, block)
            changes.append(FileChange(path=path, before=raw, after=_encode(newline.join(lines), had_bom)))
    if refused and not changes:
        raise FixerError(f"{finding_id}: no lookup is a one-line declaration directly in a void method; left for an agent: " + ", ".join(refused))
    return changes
