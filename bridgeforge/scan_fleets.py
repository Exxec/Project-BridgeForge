"""Fleet and orbit scripting checks: orbit-period hazards, captain personality, market fleet sources, per-frame market work."""
from __future__ import annotations

import re
from .models import ScanResult
from pathlib import Path
from .scan_classfile import NON_MOD_JAR_DIRS, _iter_jar_class_files, _parse_class_file
from .scan_common import _relative
from .scan_javatext import _blank_java_comments, _brace_body, _call_argument_count, _enclosing_method_span, _extract_call_arguments_text, _split_call_arguments
from .scan_json import _read_csv_rows, _wing_ids_set


# RC8's FleetFactoryV3 multiplies fleet size by the source market's Stats.COMBAT_FLEET_SIZE_MULT.
# A bare Global.getFactory().createMarket(...) has no industries, so the multiplier is 0 and every
# fleet comes out empty and vanishes (live run EX-7: no Exigency fleets in Tasserus, no error).
_FLEET_FACTORY_V3 = "com/fs/starfarer/api/impl/campaign/fleets/FleetFactoryV3"


_FLEET_SIZE_MULT_KEY = "combat_fleet_size_mult"  # value of Stats.COMBAT_FLEET_SIZE_MULT


_SECTOR_API = "com/fs/starfarer/api/campaign/SectorAPI"


def _scan_legacy_event_report(root: Path, result: ScanResult) -> None:
    """SectorAPI.reportEventStage is a documented no-op in 0.98a (live run EX-7b, EXI-EVENT-01).

    Old event plugins put their real effect (reputation changes, rewards) in the
    OnMessageDeliveryScript passed to reportEventStage. RC8 still accepts the call but does nothing,
    so that script never runs: no message, no penalty, no error.
    """
    explanation = (
        "This code calls Global.getSector().reportEventStage(...). In 0.98a that method is deprecated and does "
        "nothing (the old comm-message system was replaced by intel), so any effect placed in its delivery "
        "script never happens, with no error. Exigency's illegal-tech event caught the player but never applied "
        "its reputation penalty this way. Apply the effect directly (e.g. adjustPlayerReputation) and notify via "
        "getCampaignUI().addMessage(...) or an intel item."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or "reportEventStage" not in info.utf8_values or _SECTOR_API not in info.referenced_classes:
            continue
        result.add(id="legacy-event-report-noop", category="campaign", severity="high", classification="MANUAL", confidence="HIGH", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=["call:SectorAPI.reportEventStage"])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        lines = [text.count("\n", 0, match.start()) + 1 for match in re.finditer(r"\.reportEventStage\s*\(", text)]
        if lines:
            result.add(id="legacy-event-report-noop", category="campaign", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"line:{line}" for line in lines])


def _scan_bare_market_fleet_source(root: Path, result: ScanResult) -> None:
    """Flag fleets built from a bare createMarket() source, unless the same tier sets the fleet-size multiplier.

    Jars and source are judged separately: a fix in the source tree does not help a jar that was never
    rebuilt (the game runs the jar), and a fix in the jar does not cover loose scripts.
    """
    jar_callers: list[str] = []
    jar_mitigated = False
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        if _FLEET_SIZE_MULT_KEY in info.string_constants:
            jar_mitigated = True
        if _FLEET_FACTORY_V3 in info.referenced_classes and {"createMarket", "createFleet"} <= info.utf8_values:
            jar_callers.append(f"{_relative(root, jar)}!{member}")
    source_callers: list[str] = []
    source_mitigated = False
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "COMBAT_FLEET_SIZE_MULT" in text or f'"{_FLEET_SIZE_MULT_KEY}"' in text:
            source_mitigated = True
        if re.search(r"\bcreateMarket\s*\(", text) and re.search(r"\bFleetFactoryV3\s*\.\s*createFleet\s*\(", text):
            source_callers.append(_relative(root, source))
    callers = (jar_callers if not jar_mitigated else []) + (source_callers if not source_mitigated else [])
    if callers:
        result.add(
            id="fleet-source-bare-market",
            category="campaign",
            severity="high",
            classification="REVIEW",
            confidence="HEURISTIC",
            explanation=(
                "This code builds fleets with FleetFactoryV3 from a market made by Global.getFactory().createMarket(...). "
                "In 0.98a, fleet size is multiplied by the source market's combat fleet size stat, which is 0 on a bare "
                "market with no industries, so every fleet comes out empty and silently vanishes. Exigency's fleets never "
                "appeared this way. Give the market what vanilla's own fallback gets (Stats.COMBAT_FLEET_SIZE_MULT flat 1, "
                "Stats.FLEET_QUALITY_MOD flat FleetFactoryV3.BASE_QUALITY_WHEN_NO_MARKET), or pass a null source with a "
                "hyperspace location."
            ),
            evidence=sorted(set(callers))[:12],
        )


ORBIT_CALL_ARG_INDICES: dict[str, list[int]] = {
    "addRingBand": [8],
    "addAsteroidBelt": [4, 5],
    "setCircularOrbit": [3],
    "setCircularOrbitPointingDown": [3],
    "setCircularOrbitWithSpin": [3],
}


_ORBIT_CALL_NAME_PATTERN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")


_ZERO_LITERAL_PATTERN = re.compile(r"^-?0+(\.0+)?[fFdD]?$")


_ORBIT_GUARD_PATTERN = re.compile(r"Math\.max\s*\(|isNaN\s*\(|>\s*0\b")


def _looks_like_division(expr: str) -> bool:
    cleaned = re.sub(r'"(?:\\.|[^"\\])*"', '""', expr)
    return bool(re.search(r"(?<!/)/(?!/)", cleaned))


def _classify_orbit_argument(arg_text: str, method_text: str) -> str | None:
    """Classify one orbit-period call argument: 'zero', 'computed-unguarded', or None (no finding)."""
    arg = arg_text.strip()
    if not arg:
        return None
    if _ZERO_LITERAL_PATTERN.match(arg):
        return "zero"
    is_computed = _looks_like_division(arg)
    if not is_computed and re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", arg):
        is_computed = bool(re.search(rf"\b{re.escape(arg)}\s*=(?!=)\s*[^;]*?/[^;]*?;", method_text))
    if not is_computed:
        return None
    if _ORBIT_GUARD_PATTERN.search(method_text):
        return None
    return "computed-unguarded"


def _scan_orbit_period_hazards(root: Path, result: ScanResult) -> None:
    """RC8 crashes at the next save when a ring/belt/orbit is given a zero (or unguarded-computed) period.

    A zero orbit period is infinite angular speed; RingBand and similar orbit objects cannot
    serialize a non-finite number, so the next autosave/save throws
    "RingBand.writeReplace: JSON does not allow non-finite numbers" (or an equivalent crash).
    Real case: Legacy of Arkgneisis's SpawnChampionRing computed `float orbitTime = orbitRadius / 20f;`
    where orbitRadius can be -1 (no jump points) or <= 0 (a cramped system).
    """
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        relative = _relative(root, source)
        for match in _ORBIT_CALL_NAME_PATTERN.finditer(text):
            call_name = match.group(1)
            indices = ORBIT_CALL_ARG_INDICES.get(call_name)
            if indices is None:
                continue
            open_paren = match.end() - 1
            args_text = _extract_call_arguments_text(text, open_paren)
            if args_text is None:
                continue
            args = _split_call_arguments(args_text)
            line_number = text.count("\n", 0, match.start()) + 1
            method_text: str | None = None
            for index in indices:
                if index >= len(args):
                    continue
                arg_text = args[index]
                if method_text is None:
                    start, end = _enclosing_method_span(text, match.start())
                    method_text = text[start:end]
                classification = _classify_orbit_argument(arg_text, method_text)
                if classification == "zero":
                    result.add(
                        id="orbit-period-zero",
                        category="source",
                        severity="critical",
                        classification="MANUAL",
                        confidence="DETERMINISTIC",
                        explanation=(
                            f"This call to {call_name}(...) passes a literal 0 orbit-period. A zero orbit period "
                            "is infinite angular speed; the next save throws "
                            "'RingBand.writeReplace: JSON does not allow non-finite numbers' (or an equivalent "
                            "non-finite-orbit crash) the first time this object is serialized."
                        ),
                        file=relative,
                        evidence=[f"line:{line_number}", f"call:{call_name}", f"arg-index:{index}", f"arg:{arg_text}"],
                    )
                elif classification == "computed-unguarded":
                    result.add(
                        id="orbit-period-computed-unguarded",
                        category="source",
                        severity="medium",
                        classification="REVIEW",
                        confidence="MEDIUM",
                        explanation=(
                            f"This call to {call_name}(...) passes a computed orbit-period with no visible "
                            "Math.max/'> 0'/isNaN guard in the enclosing method. If the underlying value can be "
                            "zero, negative, or NaN, the next save throws a non-finite-number crash "
                            "(RingBand.writeReplace or equivalent). Real case: Legacy of Arkgneisis's "
                            "SpawnChampionRing computed `float orbitTime = orbitRadius / 20f;` where orbitRadius "
                            "can be -1 or <= 0."
                        ),
                        file=relative,
                        evidence=[f"line:{line_number}", f"call:{call_name}", f"arg-index:{index}", f"arg:{arg_text}"],
                    )


def _scan_module_captain_personality_risk(root: Path, result: ScanResult) -> None:
    """RC8's Ship.getPersonality() NPEs for a module/spawned ship whose captain has no personality."""
    ship_data_path = root / "data" / "hulls" / "ship_data.csv"
    for row in _read_csv_rows(ship_data_path) or []:
        hull_id = (row.get("id") or "").strip()
        if not hull_id or hull_id.startswith("#"):
            continue
        hints = (row.get("hints") or "").upper()
        if "SHIP_WITH_MODULES" not in hints:
            continue
        result.add(
            id="module-captain-personality-risk",
            category="hulls",
            severity="medium",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation=(
                "This hull is tagged SHIP_WITH_MODULES. Reported live, pending confirmation: RC8's "
                "Ship.getPersonality() NPEs if a module's captain has no personality, and AI-replacement mods "
                "(e.g. AI Tweaks) construct BasicShipAI for modules without a personality override, crashing in "
                "CombatFleetManager.deployAll. Ensure module/spawned-ship captains get a personality."
            ),
            file=_relative(root, ship_data_path),
            evidence=[f"hull:{hull_id}", "hint:SHIP_WITH_MODULES"],
        )


def _external_memory_keys_harmless(text: str, keys: list[str], mod_id: str) -> bool:
    """Every use of every key is a write (`set`/`unset`: an inert entry without the integration; Kadur's
    `$nex_recentlyCapturedByPlayer`), or a read on a line guarded by `isModEnabled("<mod_id>")` directly or through a
    boolean assigned from it (Hiver's `!haveNexerelin || ...getBoolean("$nex_randomSector")`). ROADMAP 34.17."""
    blank = _blank_java_comments(text)
    guards = set(re.findall(rf'\b(\w+)\s*=\s*[^;]*isModEnabled\s*\(\s*"{re.escape(mod_id)}"\s*\)', blank))
    for key in keys:
        for match in re.finditer(re.escape(f'"{key}"'), blank):
            before = blank[max(0, match.start() - 40):match.start()]
            if re.search(r"\b(?:set|unset)\s*\(\s*$", before):
                continue
            line_start = blank.rfind("\n", 0, match.start()) + 1
            line_end = blank.find("\n", match.end())
            line = blank[line_start:line_end if line_end >= 0 else len(blank)]
            if f'isModEnabled("{mod_id}")' in line.replace(" ", "") or any(re.search(rf"\b{re.escape(g)}\b", line) for g in guards):
                continue
            return False
    return True


_JDK_FOR_PROCGEN: list = []


def _scan_procgen_call_arguments(root: Path, result: ScanResult) -> None:
    """Suspect literal initStar / addPlanet arguments in sources and jar classes (bridgeforge.procgen_args):
    Zorg18's archived build had corona -10000 and a radius-0 planet from a 0.6-to-RC8 port (2026-10-04)."""
    from .procgen_args import jar_suspects, source_suspects

    def add(file: str, where: str, method: str, problems: list[str]) -> None:
        result.add(
            id="procgen-call-argument-suspect",
            category="campaign",
            severity="medium",
            classification="REVIEW",
            confidence="HIGH",
            explanation=(f"{method}() gets {', '.join(problems)}. RC8's signatures are initStar(id, type, radius, corona, ...) "
                         "and addPlanet(id, focus, name, type, angle, radius, orbitRadius, orbitDays); a 0.6-era call "
                         "ported by position shifts its numbers into the wrong slots (Zorg18: corona -10000, a radius-0 "
                         "planet orbiting at 100, 2026-10-04)."),
            file=file,
            evidence=[where, f"call:{method}", *problems],
        )

    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "initStar" not in text and "addPlanet" not in text:
            continue
        for line, method, problems in source_suspects(text):
            add(_relative(root, source), f"line:{line}", method, problems)
    jars = [p for p in root.rglob("*.jar") if "disabled_files" not in p.relative_to(root).parts]
    if not jars:
        return
    if not _JDK_FOR_PROCGEN:
        from .java_toolchain import find_jdk

        _JDK_FOR_PROCGEN.append(find_jdk())
    jdk = _JDK_FOR_PROCGEN[0]
    if jdk is None:
        return
    for jar in jars:
        for class_name, method_name, method, problems in jar_suspects(jar, jdk.javap):
            add(f"{_relative(root, jar)}!{class_name}", f"method:{method_name}", method, problems)


def _scan_temporary_market_fleet_source(root: Path, result: ScanResult) -> None:
    """A class that creates a market, builds a fleet from it and removes it again (Exigency, Arkgneisis,
    Omega-Trauma). RC8's FleetFactoryV3 does this itself when FleetParamsV3.source is null: it picks the nearest
    market to locInHyper, or builds an internal stand-in that never enters the economy (FleetFactoryV3.java, 2026-10-04).
    The mod's own removeMarket runs through the economy, which AoTD Theory of Toolbox turns into a full structural
    refresh per fleet."""
    import zipfile

    hits: list[tuple[str, str]] = []
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "createMarket(" in text and "removeMarket(" in text and "FleetParamsV3" in text:
            hits.append((_relative(root, source), "source"))
    for jar in sorted(p for p in root.rglob("*.jar") if "disabled_files" not in p.relative_to(root).parts):
        try:
            with zipfile.ZipFile(jar) as archive:
                for name in archive.namelist():
                    if name.endswith(".class"):
                        data = archive.read(name)
                        # A class that also calls addMarket may remove a market it registered (Omega-Trauma's
                        # IIRT_Omega_Invasion removes a planet's real market; 2026-10-04): not this pattern.
                        if (b"createMarket" in data and b"removeMarket" in data and b"FleetParamsV3" in data
                                and b"addMarket" not in data):
                            hits.append((f"{_relative(root, jar)}!{name}", "jar"))
        except (OSError, zipfile.BadZipFile):
            continue
    for file, where in hits:
        result.add(
            id="temporary-market-fleet-source",
            category="compatibility",
            severity="low",
            classification="REVIEW",
            confidence="MEDIUM",
            explanation=("Creates a market to build a fleet from and removes it again. RC8's FleetFactoryV3 does this "
                         "itself when FleetParamsV3.source is null (nearest market to locInHyper, or an internal "
                         "stand-in outside the economy); the mod's removeMarket instead mutates the economy, which AoTD "
                         "Theory of Toolbox turns into a full refresh per fleet."),
            file=file,
            evidence=[f"found:{where}", "calls:createMarket+removeMarket+FleetParamsV3"],
        )


_ADVANCE_RE = re.compile(r"\bvoid\s+advance\s*\(\s*(?:final\s+)?float\s+\w+\s*\)\s*\{")


_MARKET_WORK_RE = re.compile(r"getMarketsCopy\s*\(|\.reapplyIndustries\s*\(|\.reapplyConditions\s*\(")


_TIMER_GUARD_RE = re.compile(r"IntervalUtil|intervalElapsed|interval|timer|elapsed|cooldown|lastRun|lastCheck|daysSince", re.I)


def _scan_per_frame_market_work(root: Path, result: ScanResult) -> None:
    """An EveryFrameScript.advance() that walks the whole economy or re-applies industries/conditions with no
    timer guard runs that work every frame. The Toolbox fork's changelog records ~50 vs ~90 FPS after a refresh
    redesign (docs/AOTD_COMPAT_PLAN.md), so economy refresh cost is the known sensitivity. Source only, REVIEW:
    the guard test is textual and a guard kept in another method is not seen."""
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "EveryFrameScript" not in text:
            continue
        for match in _ADVANCE_RE.finditer(text):
            body = _brace_body(text, match.end() - 1)
            work = _MARKET_WORK_RE.search(body)
            if work and not _TIMER_GUARD_RE.search(body):
                result.add(
                    id="per-frame-market-work",
                    category="performance",
                    severity="low",
                    classification="REVIEW",
                    confidence="LOW",
                    explanation=("advance() of an EveryFrameScript calls " + work.group(0).rstrip("( ").lstrip(".") + " with no timer or "
                                 "interval in the method body, so the economy is walked or refreshed every frame. Put the work behind "
                                 "an IntervalUtil. Not yet measured against the Toolbox fork."),
                    file=_relative(root, source),
                    evidence=["found:source", f"call:{work.group(0).rstrip('( ').lstrip('.')}", "guard:none-in-advance"],
                )


_SPAWN_SHIP_CALL_PATTERN = re.compile(r"\b(spawnShipOrWing|spawnFleetMember)\s*\(\s*\"([^\"]+)\"")


def _scan_spawned_ship_captain_personality_risk(root: Path, result: ScanResult) -> None:
    """A ship (not wing) spawned directly via spawnShipOrWing/spawnFleetMember gets an AI captain with no personality."""
    wing_ids = _wing_ids_set(root / "data" / "hulls" / "wing_data.csv")
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        relative = _relative(root, source)
        for match in _SPAWN_SHIP_CALL_PATTERN.finditer(text):
            call_name, spawned_id = match.group(1), match.group(2)
            if spawned_id.endswith("_wing") or spawned_id in wing_ids:
                continue
            # The overload with a captain (5 args) is how RC8's ChiralFigmentStats spawns ships: guarded (34.14).
            if call_name == "spawnShipOrWing" and _call_argument_count(_blank_java_comments(text, strings=True), match.start()) == 5:
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            result.add(
                id="spawned-ship-captain-personality-risk",
                category="source",
                severity="low",
                classification="REVIEW",
                confidence="MEDIUM",
                explanation=(
                    f"This {call_name}(...) call spawns '{spawned_id}', which resolves as a ship variant rather "
                    "than a fighter wing (it is not in wing_data.csv and does not end in '_wing'). RC8's "
                    "Ship.getPersonality() NPEs if the spawned ship's captain has no personality; real case: "
                    "SEEKER hullmods spawn ART_*_hulk* debris ships on death this way."
                ),
                file=relative,
                evidence=[f"line:{line_number}", f"call:{call_name}", f"spawned:{spawned_id}"],
            )
