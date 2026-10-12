"""Campaign scripting checks: system generation guards, identifier lookups, market conditions, hyperspace coordinates."""
from __future__ import annotations

import json
import re
from .models import ScanResult
from pathlib import Path
from .scan_classfile import NON_MOD_JAR_DIRS, _iter_jar_class_files, _parse_class_file
from .scan_common import CAMPAIGN_ENTITY_CREATION_PATTERN, CAMPAIGN_SYSTEM_CREATION_PATTERN, _relative
from .scan_javatext import _blank_java_comments, _method_body_with_helpers
from .scan_json import _parse_json, _read_csv_rows_lenient


def _declared_spec_ids(folder: Path, pattern: str, key: str) -> dict[str, Path]:
    """Spec id -> file, keyed by the id declared inside each file, which is what Starsector registers.

    Filenames often differ from ids (Nightcross's naai_mare_center.wpn declares naai_mare_deco). The
    filename is only a fallback when a file can't be parsed or declares no id.
    """
    specs: dict[str, Path] = {}
    # Variants load from subfolders too (RC8's own core keeps 356 there, data/variants/anubis/...; Sanguinary
    # Autonomist Defectors' mothership variants live in data/variants/mothership/, 2026-10-05). Hulls and weapons
    # are flat in RC8's core, so they are not searched recursively.
    found = folder.rglob(pattern) if pattern == "*.variant" else folder.glob(pattern)
    for path in sorted(found):
        declared = None
        try:
            data, _ = _parse_json(path.read_text(encoding="utf-8-sig"))
            declared = data.get(key) if isinstance(data, dict) else None
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            pass
        specs[declared.strip() if isinstance(declared, str) and declared.strip() else path.stem] = path
    return specs


def _scan_core_campaign_plugin_reregistered(root: Path, result: ScanResult) -> None:
    """A mod that registers vanilla's CoreCampaignPluginImpl again (Zorg18's ZorgGen, 2026-09-14).

    Vanilla's own SectorGen already calls sector.registerPlugin(new CoreCampaignPluginImpl()) (RC8
    data/scripts/world/SectorGen.java:168). 0.6-era system templates copied that line into mod
    generators, so every new game gains a second core plugin that is kept in the save. A total
    conversion that replaces SectorGen (Vacuum) legitimately registers it and is skipped.
    """
    if result.metadata.get("totalConversion") in (True, "true", "TRUE"):
        return
    hits: list[str] = []
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "SectorGeneratorPlugin" in text:
            continue
        for match in re.finditer(r"\bregisterPlugin\s*\(\s*new\s+(?:[\w.]+\.)?CoreCampaignPluginImpl\s*\(", text):
            hits.append(f"{_relative(root, source)}:{text.count(chr(10), 0, match.start()) + 1}")
    if hits:
        result.add(
            id="core-campaign-plugin-reregistered",
            category="campaign",
            severity="low",
            classification="REVIEW",
            confidence="HIGH",
            explanation="The mod registers vanilla's CoreCampaignPluginImpl, which vanilla's SectorGen already registers (RC8 SectorGen.java:168). Each new game then carries a duplicate core plugin in its save. It is a leftover from 0.6-era system templates; remove the line unless the mod replaces vanilla sector generation.",
            evidence=hits,
        )


_MEMORY_FLAG_CHECK = re.compile(r"getMemory(?:WithoutUpdate)?\s*\(\s*\)\s*\.\s*(?:getBoolean|contains|is)\s*\(")


_PERSISTENT_FLAG_CHECK = re.compile(r"getPersistentData\s*\(\s*\)\s*\.\s*(?:containsKey|get)\s*\(")


def _scan_system_generation_unguarded(root: Path, result: ScanResult) -> None:
    """Star systems created with no "already generated?" guard (Zorg18, 2026-09-14).

    createStarSystem("X") is safe when some code null-checks getStarSystem("X") or checks a memory flag
    around the generator (Flu-X's plugin does the first; Zorg18 r2 both). Unguarded generation reached
    from onGameLoad creates the system again on every load; from onNewGame it relies on being called
    once per sector. Total conversions and SectorGeneratorPlugin replacements build the whole sector and
    are skipped.
    """
    if result.metadata.get("totalConversion") in (True, "true", "TRUE"):
        return
    texts: dict[Path, str] = {}
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            texts[source] = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
    plugins = {path: text for path, text in texts.items() if re.search(r"\bextends\s+BaseModPlugin\b", text)}
    hits: list[str] = []
    worst = "low"
    for source, text in texts.items():
        if "SectorGeneratorPlugin" in text:
            continue
        for match in re.finditer(r'\bcreateStarSystem\s*\(\s*"([^"]+)"', text):
            name = match.group(1)
            names = {name, name.lower(), name.replace(" ", "_").lower()}
            guarded = any(_system_lookup_null_guarded(other, candidate) for other in texts.values() for candidate in names)
            class_name = source.stem
            callers = [path for path, body in plugins.items() if re.search(rf"\b{re.escape(class_name)}\b", body)] or ([source] if source in plugins else [])
            if not guarded:
                guarded = bool(_MEMORY_FLAG_CHECK.search(text)) or any(_MEMORY_FLAG_CHECK.search(plugins[path]) for path in callers if path in plugins)
            if guarded:
                continue
            reached = "unknown"
            # Only a generation call counts: Exigency's onGameLoad calls the static Tasserus.getExiHome(),
            # while `new Tasserus().generate(...)` sits in initExigency(), called from onNewGame.
            # The system class is often generated by the mod's own generator, not the plugin (Junk Pirates:
            # plugin -> JunkPiratesGen -> new Brehinni().generate; 2026-10-01): follow such chains up to the plugin.
            chain = {class_name}
            frontier = [class_name]
            for _ in range(4):
                found = []
                for other_path, other_text in texts.items():
                    other = other_path.stem
                    if other in chain:
                        continue
                    # A qualified `new src.data.scripts.world.Art_Gen()` counts too (KIND-STRANGER Artefact, 2026-10-05).
                    if any(re.search(rf"\bnew\s+(?:[\w.]+\.)?{re.escape(c)}\s*\(|\b{re.escape(c)}\s*\.\s*generate\s*\(", other_text) for c in frontier):
                        chain.add(other)
                        found.append(other)
                frontier = found
                if not found:
                    break
            generates = re.compile("|".join(rf"\bnew\s+(?:[\w.]+\.)?{re.escape(c)}\s*\(|\b{re.escape(c)}\s*\.\s*generate\s*\(" for c in sorted(chain)))
            reachers = [path for path, body in plugins.items() if generates.search(body)] or callers
            # A once-per-save flag in the reaching plugin guards it (ROADMAP 51): SLPC's onGameLoad generates only when
            # getPersistentData() lacks CLASS_MARK, and sets it first (2026-10-05).
            if any(_PERSISTENT_FLAG_CHECK.search(plugins.get(path, "")) or _MEMORY_FLAG_CHECK.search(plugins.get(path, ""))
                   for path in reachers):
                continue
            on_new_game = False
            for path in reachers:
                plugin_text = plugins.get(path, "")
                if generates.search(_method_body_with_helpers(plugin_text, "onGameLoad")):
                    reached = "onGameLoad"
                    worst = "medium"
                    break
                if generates.search(_method_body_with_helpers(plugin_text, "onNewGame")) or generates.search(
                        _method_body_with_helpers(plugin_text, "onNewGameAfterProcGen")):
                    on_new_game = True
            if reached != "onGameLoad" and on_new_game:
                reached = "onNewGame"
            line = text.count("\n", 0, match.start()) + 1
            if reached == "unknown" and not any(
                    re.search(rf"\b{re.escape(source.stem)}\b", other_text) for other_path, other_text in texts.items()
                    if other_path != source):
                # Nothing references the generator (Galaxy Tigers' test/Testo, 2026-10-05): dead code cannot duplicate.
                reached = "never called"
            hits.append(f"{_relative(root, source)}:{line}: {name} (called from {reached})")
    # Generation reached only from onNewGame runs once per sector, as vanilla's own generators do: a note, not
    # work. onGameLoad (duplicates on every load) or a caller not traced stays REVIEW.
    if hits and all(h.endswith(("(called from onNewGame)", "(called from never called)")) for h in hits):
        result.add(
            id="system-generation-unguarded",
            category="campaign",
            severity="low",
            classification="SAFE",
            confidence="MEDIUM",
            explanation="Star systems are created without an 'already exists' guard, but only from onNewGame, which runs once per sector (vanilla's own generators do the same). A note; add a guard only if the mod is added to a running game.",
            evidence=hits,
        )
        hits = []
    if hits:
        result.add(
            id="system-generation-unguarded",
            category="campaign",
            severity=worst,
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="A star system is created with no check that it already exists (no null check on getStarSystem for it, no memory flag). Called from onGameLoad this duplicates the system on every load; from onNewGame it relies on running exactly once per sector. Add a memory-flag or getStarSystem guard.",
            evidence=hits,
        )


def _system_lookup_null_guarded(text: str, system_name: str) -> bool:
    """True when getStarSystem("<name>") is compared with null, inline or through the variable it's assigned to."""
    return _lookup_null_guarded(text, "getStarSystem", system_name)


def _lookup_null_guarded(text: str, method: str, name: str) -> bool:
    """True when <method>("<name>") is compared with null, inline or through the variable it's assigned to.
    Used for getStarSystem and getEntityById: Fantastic Furniture checks getEntityById("gilead") != null before
    using it, and an agent could not clear a finding that had nothing to fix (pilot 4, 2026-09-29)."""
    call = re.escape(method) + r'\s*\(\s*"' + re.escape(name) + r'"\s*\)'
    if re.search(call + r"\s*[!=]=\s*null|null\s*[!=]=\s*[^;]*" + call, text):
        return True
    for variable in re.findall(r"\b([A-Za-z_$][\w$]*)\s*=\s*[^;=]*" + call, text):
        if re.search(rf"\b{re.escape(variable)}\s*[!=]=\s*null\b|\bnull\s*[!=]=\s*{re.escape(variable)}\b", text):
            return True
    return False


def _scan_campaign_identifier_context(root: Path, result: ScanResult) -> None:
    """Attribute literal campaign lookups without assuming a global ID registry.

    A local definition is deterministic evidence. A mod-ID prefix is only a
    useful hint, so it remains explicitly labeled as such instead of becoming a
    compatibility claim.
    """
    mod_id = str(result.metadata.get("id") or "").strip()
    local_systems: set[str] = set()
    local_entities: set[str] = set()
    created_in: dict[str, set[str]] = {}
    entities_in: dict[str, set[str]] = {}
    for source in root.rglob("*.java"):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        systems = set(CAMPAIGN_SYSTEM_CREATION_PATTERN.findall(text))
        entities = set(CAMPAIGN_ENTITY_CREATION_PATTERN.findall(text))
        local_systems |= systems
        local_entities |= entities
        created_in[_relative(root, source)] = systems | entities
        entities_in[_relative(root, source)] = {e.casefold() for e in entities}

    def same_file(finding, identifier: str) -> None:
        # ROADMAP 34.6: the lookup's own file creates the id (Sylphon's Nym, ORA's Joy, Hiver's Kiztac: 7 of 14 hand
        # decisions on 2026-10-04), a generator looking up what it just made. A note, not work.
        # Entity ids match case-insensitively: getEntityById is (RC8-20); Aivon's addPlanet("Atempause") then
        # getEntityById("atempause") resolves (2026-10-05).
        if identifier in created_in.get(finding.file or "", set()) or (
                finding.id == "hard-coded-campaign-entity-reference"
                and identifier.casefold() in entities_in.get(finding.file or "", set())):
            finding.classification = "SAFE"
            finding.evidence.append("created-in-same-file")

    def ownership(identifier: str, defined: set[str]) -> str:
        if identifier in defined:
            return "defined-locally"
        if mod_id and identifier.startswith(f"{mod_id}_"):
            return "likely-mod-local-prefix"
        return "external-or-core-unresolved"

    lookups: list[dict[str, str]] = []
    for finding in result.findings:
        if finding.id == "hard-coded-campaign-system-reference" and finding.evidence:
            identifier = finding.evidence[0]
            state = ownership(identifier, local_systems)
            finding.evidence.append(f"ownership: {state}")
            same_file(finding, identifier)
            lookups.append({"kind": "system", "id": identifier, "ownership": state})
        elif finding.id == "hard-coded-campaign-entity-reference" and finding.evidence:
            identifier = finding.evidence[0]
            state = ownership(identifier, local_entities)
            finding.evidence.append(f"ownership: {state}")
            same_file(finding, identifier)
            lookups.append({"kind": "entity", "id": identifier, "ownership": state})
    result.migration_context["campaign_identifier_context"] = {
        "defined_system_ids": sorted(local_systems),
        "defined_entity_ids": sorted(local_entities),
        "lookups": lookups,
    }


# RC8's Conditions class (0.9a+ colony/economy overhaul) dropped these four 0.8-era market
# "conditions" outright - they are now buildable Industries instead, a materially different API
# (MarketAPI.addIndustry(String) vs. addCondition(String), different mechanics: an industry can be
# damaged/disrupted and often wants an AI core). javap of RC8 starfarer.api.jar confirms Conditions
# has no MILITARY_BASE/ORBITAL_STATION/TRADE_CENTER/HEADQUARTERS. Real, working precedent for this
# exact mapping: Exigency's Avesta.java (`In operation/Exigency/working/src-extracted/.../Avesta.java`)
# already ported HEADQUARTERS->HIGHCOMMAND and TRADE_CENTER->COMMERCE via a second addIndustry list
# alongside addMarketplace's existing conditions list. Found 2026-09-22 auditing Thule-Legacy's
# TLHeimdallSystem.java (ROADMAP P14 item 41); also present, live (not commented out), in
# Tore-Up-Plenty's CorvusScrapyard.java/TUP_Iota.java/TUP_Qat.java.
REMOVED_MARKET_CONDITION_IDS = {
    "MILITARY_BASE": "MILITARYBASE",
    "ORBITAL_STATION": "ORBITALSTATION",
    "TRADE_CENTER": "COMMERCE",
    "HEADQUARTERS": "HIGHCOMMAND",
}


_CONDITIONS_FIELD_REF = re.compile(r"\bConditions\s*\.\s*(" + "|".join(REMOVED_MARKET_CONDITION_IDS) + r")\b")


def _scan_removed_market_condition_ids(root: Path, result: ScanResult) -> None:
    """A loose script references a 0.8-era Conditions id that RC8 moved to Industries (see above)."""
    explanation = (
        "RC8's Conditions class no longer defines this id - the 0.9a+ colony overhaul turned it into "
        "a buildable Industry instead (a different API: MarketAPI.addIndustry(String), not "
        "addCondition(String); an industry can be damaged/disrupted and may want an AI core, unlike a "
        "static condition). Suggested id (real precedent, Exigency's Avesta.java): "
        + ", ".join(f"Conditions.{old}->Industries.{new}" for old, new in REMOVED_MARKET_CONDITION_IDS.items())
        + ". This reference will not compile as a Conditions field (missing-symbol), so it also blocks the "
        "mod's loose scripts from loading."
    )
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        found = sorted({match.group(1) for match in _CONDITIONS_FIELD_REF.finditer(text)})
        if found:
            result.add(
                id="removed-market-condition-id",
                category="scripts",
                severity="high",
                classification="MANUAL",
                confidence="DETERMINISTIC",
                explanation=explanation,
                file=_relative(root, source),
                evidence=[f"condition:{value}" for value in found],
            )


_VARIABLE_LOOKUP_DEREF = re.compile(r"\b(getStarSystem|getEntityById)\s*\(\s*([A-Za-z_]\w*)\s*\)\s*\.\s*\w+\s*\(")


def _scan_unguarded_variable_lookup(root: Path, result: ScanResult) -> None:
    """`getStarSystem(name).x()` / `getEntityById(id).x()` on a variable, with no null check of that call before it in
    the method. A save without the system (a Nexerelin random sector, a total conversion) crashes there: DNEEP's
    setIndustryOnPlanet(SystemName, ...) took vanilla system names and crashed on load in the owner's game
    (NullPointerException from onGameLoad, 2026-10-04). The literal-name checks never saw it."""
    for source in sorted(root.rglob("*.java")):
        parts = source.relative_to(root).parts
        if "disabled_files" in parts or "scratch" in parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for match in _VARIABLE_LOOKUP_DEREF.finditer(text):
            method, var = match.group(1), match.group(2)
            if var in ("this", "super"):
                continue
            window = text[max(0, text.rfind("\n    public ", 0, match.start()), text.rfind("\n\tpublic ", 0, match.start())):match.start()]
            if re.search(rf"{method}\s*\(\s*{re.escape(var)}\s*\)\s*(==|!=)\s*null", window):
                continue
            line = text.count("\n", 0, match.start()) + 1
            result.add(
                id="campaign-lookup-dereferenced-unguarded",
                category="campaign",
                severity="high",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(f"{method}({var}) is used directly (`{match.group(0)}`), with no null check of that lookup earlier "
                             "in the method. A save or sector without that system or entity throws a NullPointerException "
                             "here (DNEEP crashed on load this way in a live game, 2026-10-04)."),
                file=_relative(root, source),
                evidence=[f"line:{line}", f"call:{method}({var})"],
            )


_NEX_SECTOR_MANAGER_IMPORT = re.compile(r"^[ \t]*import\s+exerelin\.campaign\.SectorManager\s*;[ \t]*\r?\n", re.M)


_NEX_CORVUS_CALL = re.compile(r"\bSectorManager\s*\.\s*(?:getManager\s*\(\s*\)\s*\.\s*)?getCorvusMode\s*\(\s*\)")


def _scan_nexerelin_corvus_mode_import(root: Path, result: ScanResult) -> None:
    """A loose script importing Nexerelin's SectorManager only to ask getCorvusMode() (ROADMAP 34.13).

    Janino compiles every loose script at startup, so without Nexerelin the import alone fails (Hiver Swarm,
    2026-10-04), whatever isModEnabled check guards the call. Nexerelin 0.12.2d's new-game entry point
    (ExerelinNewGameSetup.generateStarSystems, javap and its bundled source, 2026-10-04) writes
    `$nex_randomSector` = !corvusMode to sector memory, so the same answer needs no import. A mod that requires
    Nexerelin is skipped: there the import always resolves."""
    raw = result.metadata.get("dependencies") or result.metadata.get("requiredDependencies") or []
    if "nexerelin" in json.dumps(raw).lower():
        return
    for source in sorted((root / "data").rglob("*.java")) if (root / "data").is_dir() else []:
        try:
            text = source.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blank = _blank_java_comments(text, strings=True)
        if not _NEX_SECTOR_MANAGER_IMPORT.search(blank):
            continue
        # A jar class of the same name wins and the loose file is never compiled (Kadur Remnant ships
        # data/scripts/KadurModPlugin.java beside the same class in KadurRemnant.jar; read 2026-10-04).
        package = re.search(r"^\s*package\s+([\w.]+)\s*;", blank, re.M)
        if package and f"{package.group(1)}.{source.stem}" in result.compiled_class_names:
            continue
        calls = len(_NEX_CORVUS_CALL.findall(blank))
        others = len(re.findall(r"\bSectorManager\b", blank)) - calls - 1
        if calls and others == 0 and "exerelin." not in _NEX_SECTOR_MANAGER_IMPORT.sub("", blank):
            result.add(
                id="nexerelin-corvus-mode-import",
                category="scripts",
                severity="critical",
                classification="REVIEW",
                confidence="HIGH",
                explanation=(
                    "This loose script imports Nexerelin's SectorManager only for getCorvusMode(). Janino compiles "
                    "every loose script at startup, so without Nexerelin the import fails to compile. Nexerelin's "
                    "new-game setup writes $nex_randomSector (= !corvusMode) to sector memory, which gives the "
                    "same answer with no import."
                ),
                file=_relative(root, source),
                evidence=[f"calls:{calls}", "import:exerelin.campaign.SectorManager"],
            )


_COORDINATE_NUMBER = r"-?\d+(?:\.\d+)?f?"


_VECTOR_LITERAL_PATTERN = re.compile(
    rf"(?:new\s+Vector2f\s*\(\s*({_COORDINATE_NUMBER})\s*,\s*({_COORDINATE_NUMBER})\s*\))"
    rf"|(?:getLocation\(\)\.set\s*\(\s*({_COORDINATE_NUMBER})\s*,\s*({_COORDINATE_NUMBER})\s*\))"
)


_HYPERSPACE_TOUCH_PATTERN = re.compile(r"getHyperspace\(\)|getLocationInHyperspace|\bwaypoints?\b", re.I)


_TERRAIN_GRID_LITERAL_PATTERN = re.compile(r"(?:[/%]\s*(\d{2,4})\b)|(?:\[\s*(\d{2,4})\s*\])")


def _scan_hardcoded_hyperspace_coordinates(root: Path, result: ScanResult) -> None:
    """A hyperspace-touching class hard-coding >=3 literal coordinate pairs (e.g. a stale pre-rework layout)."""
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blanked = _blank_java_comments(text)
        if not _HYPERSPACE_TOUCH_PATTERN.search(blanked):
            continue
        pairs: list[tuple[int, str, str]] = []
        for match in _VECTOR_LITERAL_PATTERN.finditer(blanked):
            groups = match.groups()
            x = groups[0] if groups[0] is not None else groups[2]
            y = groups[1] if groups[1] is not None else groups[3]
            line = blanked.count("\n", 0, match.start()) + 1
            pairs.append((line, x, y))
        if len(pairs) < 3:
            continue
        evidence = [f"line:{line}:({x},{y})" for line, x, y in pairs[:5]]
        evidence.append(f"total_coordinate_pairs:{len(pairs)}")
        result.add(
            id="hardcoded-hyperspace-coordinates",
            category="content",
            severity="low",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation="This class touches hyperspace (getHyperspace()/getLocationInHyperspace/a waypoint-like list) and hard-codes 3 or more literal Vector2f coordinate pairs. A stale pre-rework layout (e.g. old hyperspace-terrain-era coordinates) can land in the wrong place after a hyperspace rework; verify these coordinates are still sane for the target game version.",
            file=_relative(root, path),
            evidence=evidence,
        )


def _scan_hardcoded_terrain_grid_size(root: Path, result: ScanResult) -> None:
    """Code that indexes/divides a getTiles() terrain grid by a hard-coded literal grid size or mask."""
    for path in root.rglob("*.java"):
        if "disabled_files" in path.relative_to(root).parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        blanked = _blank_java_comments(text)
        if "getTileCenter" in blanked:
            continue  # already fixed to use the grid's own accessor; must not fire
        for match in re.finditer(r"getTiles\(\)", blanked):
            start = max(0, match.start() - 200)
            end = min(len(blanked), match.end() + 200)
            grid_match = _TERRAIN_GRID_LITERAL_PATTERN.search(blanked[start:end])
            if not grid_match:
                continue
            value = grid_match.group(1) or grid_match.group(2)
            line = blanked.count("\n", 0, match.start()) + 1
            result.add(
                id="hardcoded-terrain-grid-size",
                category="content",
                severity="low",
                classification="REVIEW",
                confidence="MEDIUM",
                explanation="Code indexes or divides a getTiles() terrain grid by a hard-coded literal grid size/mask near this call. This breaks if the grid's actual dimensions ever differ from the constant; use the grid's own reported size/center accessor (e.g. getTileCenter) instead of a fixed literal.",
                file=_relative(root, path),
                evidence=[f"line:{line}", f"literal:{value}"],
            )
            break


# RC8-16. Market conditions in 0.8.1a's market_conditions.csv that RC8's no longer defines (diffed 2026-09-28). 0.9 turned most
# into industries (RC8 industries.csv ids noted; None where there is no direct successor). A market that adds one throws
# "Market condition [antimatter_fuel_production] not found", a Fatal at New Game (FlowerGod, FG-SOLO-20260928).
LEGACY_MARKET_CONDITIONS = {
    "antimatter_fuel_production": "fuelprod", "aquaculture": "aquaculture", "autofac_heavy_industry": "heavyindustry",
    "cryosanctum": "cryosanctum", "light_industrial_complex": "lightindustry", "military_base": "militarybase",
    "orbital_burns": None, "orbital_station": "orbitalstation", "ore_complex": "mining", "ore_refining_complex": "refining",
    "organics_complex": "mining", "spaceport": "spaceport", "volatiles_complex": "mining", "volatiles_depot": None,
}


def _scan_legacy_market_conditions(root: Path, result: ScanResult) -> None:
    """Code that adds a pre-0.9 market condition. MarketAPI.addIndustry is absent from 0.8.1a's API (javap, 2026-09-28),
    so a class that calls addCondition with one of these ids and never addIndustry is unported 0.8 market code."""
    own = {(row.get("id") or "").strip() for row in _read_csv_rows_lenient(root / "data" / "campaign" / "market_conditions.csv") or []}
    legacy = {cid for cid in LEGACY_MARKET_CONDITIONS if cid not in own}
    hits: dict[str, set[str]] = {}
    for source in sorted(root.rglob("*.java")):
        parts = source.relative_to(root).parts
        if "disabled_files" in parts or "src-decompiled" in parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "addCondition" not in text or "addIndustry" in text:
            continue
        found = {cid for cid in legacy if f'"{cid}"' in text}
        if found:
            hits[_relative(root, source)] = found
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or "addCondition" not in info.utf8_values or "addIndustry" in info.utf8_values:
            continue
        found = legacy & set(info.string_constants)
        if found:
            hits[f"{_relative(root, jar)}!{member}"] = found
    # aquaculture, cryosanctum and spaceport are RC8 industry ids too, so alone they are ambiguous: a class may pass one
    # to getIndustry/hasIndustry. The 2026-09-28 sweep of 293 working copies flagged seven such classes on "spaceport"
    # alone (Omega-Trauma's among them, live-validated). Only a class with an id RC8 has no industry for counts.
    both = {"aquaculture", "cryosanctum", "spaceport"}
    hits = {where: found for where, found in hits.items() if found - both}
    if not hits:
        return
    ids = sorted(set().union(*hits.values()))
    result.add(
        id="legacy-market-condition",
        category="campaign",
        severity="high",
        classification="MANUAL",
        confidence="HIGH",
        explanation="Code adds market conditions that 0.9 removed (most became industries), and never calls addIndustry, "
                    "which 0.8.1a's API lacked: unported 0.8 market code. RC8 throws \"Market condition [...] not found\" "
                    "when the market is built, a Fatal at New Game. Add the successor industry instead ("
                    + ", ".join(f"{cid} -> {LEGACY_MARKET_CONDITIONS[cid] or 'no direct successor'}" for cid in ids)
                    + "), plus population and a spaceport, which every RC8 market needs.",
        file=sorted(hits)[0],
        evidence=[f"{where}: {', '.join(sorted(found))}" for where, found in sorted(hits.items())][:10],
    )
