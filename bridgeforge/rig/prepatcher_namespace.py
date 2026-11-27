"""Which name table StarsectorPrepatcher's agent will load on a rig, read offline (ROADMAP-3 98.17).

Prepatcher writes its patches against Windows 0.98a-RC8's obfuscated names and carries one table per other build. Its
`GameNamespaceDetector` picks the build by `CombatEngine.getResults()`'s return type: the canonical type itself, or a table
whose row maps the canonical type to that native type. On Windows 0.98.5a-RC9 the stock 0.18.9 agent matched the Linux
0.98.5a-RC8 table (RC9 returns `combat/B/D`, that table's native name). In RC9NC-LIVE4 (2026-11-26) it then rewrote
`campaign.rules.Rules` with a method name RC9 lacks, and the game died at start-up with NoSuchMethodError.

This replays the detection: the tables the detector lists (the table ids among its class's string constants; in both real
jars they are exactly the shipped tables plus the canonical id), the getResults match, and the `getCombatMap()` tie-break when
the detector carries one (the rig jar of 98.14 does). Where the real detector throws, the replay says so: a listed table the
jar lacks, a listed table with no getResults row, a tied table with no getCombatMap row, or a CombatEngine with two
no-argument methods of one name (review, 2026-11-27; the agent then fails open and the game runs unpatched). Then it checks
that the chosen table describes the core: every class it maps must exist there. It checks class names only, not the
members the table also maps; between the real tables and cores that is enough to tell the right table from a wrong one.

It reads the agent jar at its usual place in the rig, not the `-javaagent` a launcher names.
"""
from __future__ import annotations

import re
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
TABLE_ID = re.compile(r"(?:windows|linux|mac|macos)-[0-9][0-9A-Za-z.]*-RC[0-9]+")
CORE_JARS = ("starfarer_obf.jar", "fs.common_obf.jar", "fs.sound_obf.jar", "starfarer.api.jar")
SHOWN = 5  # missing class names quoted in a FAIL


class AgentUnreadable(ValueError):
    """The agent jar has no detector this replay can read."""


def _detector(agent: zipfile.ZipFile) -> tuple[set[str], bool]:
    """(the table ids the detector lists, whether it breaks ties with getCombatMap)."""
    from bridgeforge.scan.scan_classfile import _parse_class_file

    if DETECTOR not in agent.namelist():
        raise AgentUnreadable(f"the agent jar has no {DETECTOR}")
    info = _parse_class_file(read_class(agent, DETECTOR) or b"")
    if info is None:
        raise AgentUnreadable(f"{DETECTOR} is not a readable class file")
    listed = {text for text in info.string_constants if TABLE_ID.fullmatch(text)} - {IDENTITY}
    return listed, "getCombatMap" in info.utf8_values


def _rows(text: str) -> dict[str, str]:
    """A table's class rows. As the agent reads them: the native name is the rest of the line, and the first row wins."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        if line.startswith("C\t"):
            parts = line.split("\t", 2)
            if len(parts) == 3:
                rows.setdefault(parts[1], parts[2])
    return rows


def _tables(agent: zipfile.ZipFile) -> tuple[dict[str, dict[str, str]], list[str], bool]:
    """({table id: {canonical class: native class}} for the listed tables the jar ships, the listed ids it lacks, tie-break)."""
    listed, tie_break = _detector(agent)
    names = set(agent.namelist())
    tables, absent = {}, []
    for table_id in sorted(listed):
        entry = f"{TABLE_PREFIX}{table_id}.tsv"
        if entry not in names:
            absent.append(table_id)
            continue
        tables[table_id] = _rows(read_limited(agent, entry).decode("utf-8", "replace"))
    return tables, absent, tie_break


def _engine_getters(core: Path) -> dict[str, list[str]]:
    """{method name: [descriptor, ...]} of CombatEngine's no-argument methods (from the core's starfarer_obf.jar)."""
    from bridgeforge.scan.scan_classfile import _parse_class_file

    with zipfile.ZipFile(core / "starfarer_obf.jar") as jar:
        info = _parse_class_file(read_class(jar, ENGINE) or b"") if ENGINE in jar.namelist() else None
    getters: dict[str, list[str]] = {}
    for name, descriptor, _public in info.methods if info is not None else []:
        if descriptor.startswith("()"):
            getters.setdefault(name, []).append(descriptor)
    return getters


def _core_classes(core: Path, skipped: list[str]) -> set[str]:
    """The core jars' class names, through the shared jar walker (0.25 s on RC9's 6559 classes). An entry it could not read
    is named in `skipped`: its class may still exist, so a FAIL says so."""
    from bridgeforge.scan.scan_classfile import iter_class_files_in_jars

    jars = [core / jar_name for jar_name in CORE_JARS if (core / jar_name).is_file()]
    return {member.removesuffix(".class") for _jar, member, _data in iter_class_files_in_jars(jars, skipped, skipped_entries=skipped)}


def _throws(tables: dict[str, dict[str, str]], absent: list[str], getters: dict[str, list[str]]) -> str | None:
    """Why the real detector throws before it matches anything, or None."""
    if absent:
        return f"it lists table(s) {', '.join(absent)} that the agent jar lacks"
    unmatched = [table_id for table_id, rows in sorted(tables.items()) if CANONICAL_RESULT not in rows]
    if unmatched:
        return f"table(s) {', '.join(unmatched)} have no row for {CANONICAL_RESULT}"
    doubled = [name for name in ("getResults", "getCombatMap") if len(getters.get(name, [])) > 1]
    if doubled:
        return f"CombatEngine has more than one no-argument {' and '.join(doubled)}"
    return None


def predicted_table(agent_jar: Path, core: Path) -> dict:
    """{"matches", "tie_break", "table" (the one the agent will load, or None), "missing", "mapped", "get_results", "throws"}."""
    with zipfile.ZipFile(agent_jar) as agent:
        tables, absent, tie_break = _tables(agent)
    getters = _engine_getters(core)
    result = (getters.get("getResults") or [None])[0]
    found = {"matches": [], "tie_break": tie_break, "table": None, "missing": [], "mapped": 0, "get_results": result,
             "throws": _throws(tables, absent, getters), "unread": []}
    if found["throws"]:
        return found
    matches = [IDENTITY] if result == f"()L{CANONICAL_RESULT};" else []
    matches += [table_id for table_id, rows in sorted(tables.items()) if result == f"()L{rows[CANONICAL_RESULT]};"]
    if len(matches) > 1 and tie_break:
        lacking = [table_id for table_id in matches if table_id != IDENTITY and CANONICAL_COMBAT_MAP not in tables[table_id]]
        if lacking:
            found.update(matches=matches, throws=f"tied table(s) {', '.join(lacking)} have no row for {CANONICAL_COMBAT_MAP}")
            return found
        combat = (getters.get("getCombatMap") or [None])[0]
        matches = [table_id for table_id in matches
                   if combat == f"()L{CANONICAL_COMBAT_MAP if table_id == IDENTITY else tables[table_id][CANONICAL_COMBAT_MAP]};"]
    found["matches"] = matches
    found["table"] = matches[0] if len(matches) == 1 else None
    if found["table"] is not None and found["table"] != IDENTITY:
        classes = _core_classes(core, found["unread"])
        natives = sorted(set(tables[found["table"]].values()))
        found["mapped"] = len(natives)
        found["missing"] = [name for name in natives if name not in classes]
    return found


def check(runtime_dir: Path) -> dict[str, object]:
    """rig-doctor's `prepatcher_namespace` check: PASS when the agent will load a table whose classes all exist in the core (or
    the core is the canonical build), FAIL when the table it will load names classes the core lacks, WARN when its detector
    throws or matches no table or several (the agent then fails open and the game runs unpatched), SKIPPED without the agent."""
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
    except (OSError, zipfile.BadZipFile, ValueError, KeyError) as exc:  # AgentUnreadable is a ValueError
        return result("WARN", f"could not read the agent or the core: {exc}")
    if found["throws"]:
        return result("WARN", f"the agent's detector would throw: {found['throws']}. The agent then fails open and the game runs "
                              "unpatched")
    if found["table"] is None:
        what = "no table" if not found["matches"] else f"{len(found['matches'])} tables ({', '.join(found['matches'])})"
        return result("WARN", f"the agent matches {what} for CombatEngine.getResults() {found['get_results']}: it fails open and the "
                              "game runs unpatched")
    if found["table"] == IDENTITY:
        return result("PASS", "the core is the canonical build (Windows 0.98a-RC8): no table needed")
    if found["missing"]:
        shown = ", ".join(found["missing"][:SHOWN]) + (" ..." if len(found["missing"]) > SHOWN else "")
        unread = (f" ({len(found['unread'])} core jar or class entries could not be read, so some of these may exist)"
                  if found["unread"] else "")
        return result("FAIL", f"the agent will load table {found['table']}, which names {len(found['missing'])} of its {found['mapped']} "
                              f"classes this core lacks ({shown}){unread}: it is another build's table, so its patches would target "
                              "the wrong classes and members (RC9NC-LIVE4 died at start-up this way). Install an agent with this "
                              "build's table (ROADMAP-3 98.14).")
    return result("PASS", f"the agent will load table {found['table']}; all {found['mapped']} classes it maps exist in the core "
                          "(the members it maps are not checked)")
