"""Which name table StarsectorPrepatcher's agent will load on a rig, read offline (ROADMAP-3 98.17).

Prepatcher writes its patches against Windows 0.98a-RC8's obfuscated names and carries one table per other build. Its
`GameNamespaceDetector` picks the build by `CombatEngine.getResults()`'s return type: the canonical type itself, or a table
whose row maps the canonical type to that native type. On Windows 0.98.5a-RC9 the stock 0.18.9 agent matched the Linux
0.98.5a-RC8 table (RC9 returns `combat/B/D`, that table's native name). In RC9NC-LIVE4 (2026-11-26) it then rewrote
`campaign.rules.Rules` with a method name RC9 lacks, and the game died at start-up with NoSuchMethodError.

This replays the detection: the tables the detector names (string constants of its class), the getResults match, and the
`getCombatMap()` tie-break when the detector carries one (the rig jar of 98.14 does). Then it checks that the chosen table
describes the core: every class it maps must exist there.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

from bridgeforge.zipsafe import read_class, read_limited

AGENT_RELATIVE = Path("mods") / "StarsectorPrepatcher" / "agent" / "StarsectorPrepatcherAgent.jar"
TABLE_PREFIX = "com/starsector/prepatcher/agent/"
DETECTOR = "com/starsector/prepatcher/namespace/GameNamespaceDetector.class"
ENGINE = "com/fs/starfarer/combat/CombatEngine.class"
CANONICAL_RESULT = "com/fs/starfarer/combat/Object/String"
CANONICAL_COMBAT_MAP = "com/fs/starfarer/combat/A/B"
IDENTITY = "windows-0.98a-RC8"  # the canonical namespace: no table
CORE_JARS = ("starfarer_obf.jar", "fs.common_obf.jar", "fs.sound_obf.jar", "starfarer.api.jar")
SHOWN = 5  # missing class names quoted in a FAIL


def _tables(agent: zipfile.ZipFile) -> tuple[dict[str, dict[str, str]], bool]:
    """({table id: {canonical class: native class}} for the tables the detector names, whether it breaks ties)."""
    detector = read_class(agent, DETECTOR) or b""
    tables: dict[str, dict[str, str]] = {}
    for entry in agent.namelist():
        if not (entry.startswith(TABLE_PREFIX) and entry.endswith(".tsv")):
            continue
        table_id = entry[len(TABLE_PREFIX):-len(".tsv")]
        if table_id.encode("utf-8") not in detector:
            continue  # shipped, but not in the detector's TABLES list
        rows = {}
        for line in read_limited(agent, entry).decode("utf-8", "replace").splitlines():
            if line.startswith("C\t"):
                parts = line.split("\t")
                if len(parts) >= 3:
                    rows[parts[1]] = parts[2]
        tables[table_id] = rows
    return tables, b"getCombatMap" in detector


def _engine_getters(core: Path) -> dict[str, str]:
    """{method name: descriptor} of CombatEngine's no-argument methods (from the core's starfarer_obf.jar)."""
    from bridgeforge.scan.scan_classfile import _parse_class_file

    with zipfile.ZipFile(core / "starfarer_obf.jar") as jar:
        info = _parse_class_file(read_class(jar, ENGINE) or b"")
    if info is None:
        return {}
    return {name: descriptor for name, descriptor, _public in info.methods if descriptor.startswith("()")}


def _core_classes(core: Path) -> set[str]:
    names: set[str] = set()
    for jar_name in CORE_JARS:
        if (core / jar_name).is_file():
            with zipfile.ZipFile(core / jar_name) as jar:
                names |= {entry[:-len(".class")] for entry in jar.namelist() if entry.endswith(".class")}
    return names


def predicted_table(agent_jar: Path, core: Path) -> dict:
    """{"matches": [...], "tie_break": bool, "table": the one the agent will load or None, "missing": [...], "mapped": n}."""
    with zipfile.ZipFile(agent_jar) as agent:
        tables, tie_break = _tables(agent)
    getters = _engine_getters(core)
    result = getters.get("getResults")
    matches = [IDENTITY] if result == f"()L{CANONICAL_RESULT};" else []
    matches += [table_id for table_id, rows in sorted(tables.items()) if rows.get(CANONICAL_RESULT) and result == f"()L{rows[CANONICAL_RESULT]};"]
    if len(matches) > 1 and tie_break:
        combat = getters.get("getCombatMap")
        matches = [table_id for table_id in matches
                   if combat == f"()L{CANONICAL_COMBAT_MAP if table_id == IDENTITY else tables[table_id].get(CANONICAL_COMBAT_MAP)};"]
    chosen = matches[0] if len(matches) == 1 else None
    missing: list[str] = []
    mapped = 0
    if chosen is not None and chosen != IDENTITY:
        classes = _core_classes(core)
        natives = sorted(set(tables[chosen].values()))
        mapped = len(natives)
        missing = [name for name in natives if name not in classes]
    return {"matches": matches, "tie_break": tie_break, "table": chosen, "missing": missing, "mapped": mapped,
            "get_results": result}


def check(runtime_dir: Path) -> dict[str, object]:
    """rig-doctor's `prepatcher_namespace` check: PASS when the agent will load a table that describes the core (or the core is
    the canonical build), FAIL when the table it will load names classes the core lacks, WARN when it matches no table or
    several (it then fails open and the game runs unpatched), SKIPPED without the agent."""
    def result(status: str, detail: str) -> dict[str, object]:
        return {"name": "prepatcher_namespace", "status": status, "detail": detail}

    agent = Path(runtime_dir) / AGENT_RELATIVE
    core = Path(runtime_dir) / "starsector-core"
    if not agent.is_file():
        return result("SKIPPED", "no StarsectorPrepatcher agent jar in the rig")
    if not (core / "starfarer_obf.jar").is_file():
        return result("WARN", "the rig's core has no starfarer_obf.jar to read CombatEngine from")
    try:
        found = predicted_table(agent, core)
    except (OSError, zipfile.BadZipFile, ValueError) as exc:
        return result("WARN", f"could not read the agent or the core: {exc}")
    if found["table"] is None:
        what = "no table" if not found["matches"] else f"{len(found['matches'])} tables ({', '.join(found['matches'])})"
        return result("WARN", f"the agent matches {what} for CombatEngine.getResults() {found['get_results']}: it fails open and the "
                              "game runs unpatched")
    if found["table"] == IDENTITY:
        return result("PASS", "the core is the canonical build (Windows 0.98a-RC8): no table needed")
    if found["missing"]:
        shown = ", ".join(found["missing"][:SHOWN]) + (" ..." if len(found["missing"]) > SHOWN else "")
        return result("FAIL", f"the agent will load table {found['table']}, which names {len(found['missing'])} of its {found['mapped']} "
                              f"classes this core lacks ({shown}): its patches would call members that do not exist (RC9NC-LIVE4 "
                              "died at start-up this way). Install an agent with this build's table (ROADMAP-3 98.14).")
    return result("PASS", f"the agent will load table {found['table']}; all {found['mapped']} classes it maps exist in the core")
