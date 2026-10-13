"""Combat-state checks: hullmod instance state, hulk death repeats, weapon effect static state, saved market refs."""
from __future__ import annotations

import re
from .models import ScanResult
from pathlib import Path
from .scan_classfile import NON_MOD_JAR_DIRS, _ClassFileInfo, _instance_fields_written_outside_constructors, _iter_jar_class_files, _parse_class_file
from .scan_common import _relative
from .scan_javatext import _blank_java_comments


# Plugins Starsector instantiates once PER WEAPON (or per projectile); a static field is shared by
# every copy in the battle. Live run SK13-1: SEEKER's ART_thrusterRotation kept `static ShipAPI ship`,
# so Vector-cruiser debris spawned mid-battle overwrote it and a living cruiser's flame weapon read a
# ship with no system -> NPE -> Fatal dialog.
PER_WEAPON_PLUGIN_INTERFACES = {
    "com/fs/starfarer/api/combat/EveryFrameWeaponEffectPlugin",
    "com/fs/starfarer/api/combat/EveryFrameWeaponEffectPluginWithAdvanceAfter",
    "com/fs/starfarer/api/combat/OnFireEffectPlugin",
    "com/fs/starfarer/api/combat/OnHitEffectPlugin",
    "com/fs/starfarer/api/combat/WeaponEffectPluginWithInit",
}


COMBAT_STATE_TYPES = ("ShipAPI", "WeaponAPI", "ShipEngineControllerAPI", "ShipSystemAPI", "MissileAPI", "DamagingProjectileAPI", "BeamAPI")


_COMBAT_STATE_DESCRIPTORS = {f"Lcom/fs/starfarer/api/combat/{name};" for name in COMBAT_STATE_TYPES}


_SOURCE_STATIC_STATE = re.compile(r"\bstatic\s+(?!final\b)(?:(?:private|protected|public|volatile|transient)\s+)*(" + "|".join(COMBAT_STATE_TYPES) + r")\s+(\w+)\s*[;=]")


_HULLMOD_BASES = {"com/fs/starfarer/api/combat/BaseHullMod"}


# Whitespace inside a declaration is [ \t], not \s: \s crossed lines and backtracked for 13 s on AI War's
# AIW_Forcefield.java (2026-09-30). A multi-line initializer is still matched by [^;]*.
_SOURCE_HULLMOD_FIELD = re.compile(r"^[ \t]*(?:private|protected|public)?[ \t]*(?!static\b)(?!final\b)(?:transient[ \t]+|volatile[ \t]+)*([A-Za-z_][\w.<>\[\], ]*?)[ \t]+(\w+)[ \t]*(?:=[^;]*)?;", re.MULTILINE)


def _looks_like_constant(name: str) -> bool:
    """UPPER_SNAKE fields are constants by convention even when not declared final (never mutated)."""
    return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", name))


_HULK_SPAWN_CALLS = frozenset({"spawnShipOrWing", "spawnProjectile"})


_HULK_IF = re.compile(r"if\s*\(\s*(?P<var>\w+)\s*\.\s*isHulk\s*\(\s*\)\s*\)\s*\{")


HULK_DEATH_GUARD_KEY_SUFFIX = "_deathDone"


def _hulk_block_spawns(text: str, start: int) -> bool:
    """The brace block opened at `start` (just after its '{') calls a spawn method, directly or through a method of the same class."""
    depth, i = 1, start
    while i < len(text) and depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    block = text[start:i]
    if any(re.search(r"\b" + name + r"\s*\(", block) for name in _HULK_SPAWN_CALLS):
        return True
    for called in set(re.findall(r"\b(?:this\s*\.\s*)?([A-Za-z_]\w*)\s*\(", block)):
        body = re.search(r"\b(?:void|boolean|int|float)\s+" + re.escape(called) + r"\s*\([^)]*\)\s*\{", text)
        if body and any(re.search(r"\b" + name + r"\s*\(", text[body.end():body.end() + 6000]) for name in _HULK_SPAWN_CALLS):
            return True
    return False


def hulk_death_effect_sites(text: str) -> list[str]:
    """Wreck checks in a hull mod source that spawn ships or projectiles with no once-per-ship guard: the variable names."""
    if "advanceInCombat" not in text:
        return []
    found = []
    for match in _HULK_IF.finditer(text):
        if _hulk_block_spawns(text, match.end()):
            found.append(match["var"])
    return found


def _scan_hulk_death_effect_repeats(root: Path, result: ScanResult) -> None:
    """A hull mod whose advanceInCombat spawns wreck debris under `if (ship.isHulk())` with no once-per-ship guard. RC8 keeps calling
    a hull mod for a wreck every frame, so the death effect repeats every frame: one SEEKER Bone-Breaker kill grew the field to 2,388
    hulks and 8 s frames (RC8-27, DUEL9-20261011). The fix is a once-per-ship flag in ship.getCustomData(), which SEEKER's
    Organic Hull already had and Liquid Skin and Phased Mainframe did not."""
    explanation = ("This hull mod spawns ships or projectiles when its ship is a wreck (isHulk), with no once-per-ship guard. RC8 keeps "
                   "running a hull mod for a wreck every frame, so the death effect repeats every frame and the wrecks it spawns pile up "
                   "until the game crawls (RC8-27: one SEEKER Bone-Breaker kill made 2,388 hulks and 8-second frames). Run the effect "
                   "once per ship with a flag in ship.getCustomData().")
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        sites = hulk_death_effect_sites(text)
        if sites:
            result.add(id="hulk-death-effect-repeats", category="scripts", severity="high", classification="REVIEW", confidence="HIGH",
                       explanation=explanation, file=_relative(root, source), evidence=[f"wreck-check:{v}.isHulk()" for v in sites])
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or "isHulk" not in info.utf8_values or "advanceInCombat" not in info.utf8_values:
            continue
        if not (_HULK_SPAWN_CALLS & set(info.utf8_values)) or {"setCustomData", "getCustomData"} & set(info.utf8_values):
            continue
        result.add(id="hulk-death-effect-repeats", category="scripts", severity="high", classification="REVIEW", confidence="MEDIUM",
                   explanation=explanation + " Compiled class: decompile it, add the guard, then patch-jar-class.",
                   file=f"{_relative(root, jar)}!{member}", evidence=[f"class:{info.this_class}", "calls:" + ",".join(sorted(_HULK_SPAWN_CALLS & set(info.utf8_values)))])


def _scan_saved_object_holds_market_ref(root: Path, result: ScanResult) -> None:
    """A class stored in a memory/customData or registered as a listener or script that keeps a MarketAPI, SectorEntityToken, PlanetAPI
    or CampaignFleetAPI in a non-transient field (the Station Augments save-cycle pattern, ROADMAP 60g(4); see saved_object_scan)."""
    from .saved_object_scan import saved_object_findings

    sources: dict[str, str] = {}
    for source in sorted(root.rglob("*.java")):
        relative = _relative(root, source)
        if "disabled_files" in Path(relative).parts:
            continue
        try:
            sources[relative] = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"), strings=True)
        except OSError:
            continue
    for hit in saved_object_findings(sources):
        result.add(
            id="saved-object-holds-market-ref", category="scripts", severity="medium", classification="REVIEW", confidence="MEDIUM",
            explanation=(f"{hit['class']} is {hit['how']}, so the game saves it with every non-transient field, and it keeps "
                         f"{', '.join(hit['fields'])}. A saved object that holds a market, planet, entity or fleet ties the save graph to that "
                         "entity; with a memory that holds the planet back it becomes a reference cycle, and a Modpack 6.3 save with Station "
                         "Augments failed to load after c212 (NullPointerException in PlanetConditionMarket.readResolve, RC8-31; `save-doctor "
                         "--cycles` finds the cycle in a save). Safe fix pattern: clear the field in beforeGameSave, restore it in "
                         "afterGameSave/onGameSaveFailed, and re-link it in onGameLoad. Do NOT mark an already-saved field transient: RC8's "
                         "XStream throws UnknownFieldException on a saved element whose field is no longer readable, so existing saves would "
                         "break (RC8-32, bytecode only)."),
            file=hit["file"], evidence=[f"class:{hit['class']}", f"saved:{hit['how']}", *[f"field:{field}" for field in hit["fields"]]])


def _scan_hullmod_instance_state(root: Path, result: ScanResult) -> None:
    """Hull mods are single shared instances: mutable instance fields leak state between ships (SEEKER-DEATH-01).

    Starsector creates ONE object per hull mod spec and calls advanceInCombat(ship, ...) for every
    ship that has it, so a non-static, non-final field is shared across all of those ships. SEEKER's
    ART_organicHull kept runOnce/RADIUS/timers that way, and re-ran its death effect every frame
    on a wreck. REVIEW: constants stored in non-final fields are harmless; per-ship state belongs in
    ship.getCustomData().
    """
    explanation = (
        "This hull mod keeps changeable instance fields. Starsector shares ONE hull mod object across every "
        "ship with it, so per-ship state (timers, 'runOnce' flags, cached radius) leaks between ships and is "
        "never reset per ship. SEEKER's ART_organicHull did this and also re-ran its death effect every frame "
        "on a wreck, spawning debris until the game crawled. Keep per-ship state in ship.getCustomData()."
    )
    # A field written only in <init> is set once per object (configuration), not per-ship state. Writes are
    # collected across every jar class, because a subclass writing an inherited field names itself as the owner
    # (RogueSynth, 2026-09-27: RS_BaseVariantHullmod's 11 flagged fields are all constructor-only).
    classes: list[tuple[Path, str, _ClassFileInfo]] = []
    writes: set[tuple[str, str]] = set()
    walk_failed = False
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None:
            continue
        found = _instance_fields_written_outside_constructors(data)
        if found is None:
            walk_failed = True
        else:
            writes |= found
        classes.append((jar, member, info))
    supers = {info.this_class: info.super_class for _jar, _member, info in classes}

    def descends_from(name: str, ancestor: str) -> bool:
        for _ in range(20):
            if name == ancestor:
                return True
            name = supers.get(name, "")
            if not name:
                return False
        return False

    # Grouped by owner: one hierarchy walk per owning class, not per write (AI War took 29 s here, 2026-09-30).
    names_by_owner: dict[str, set[str]] = {}
    for owner, name in writes:
        names_by_owner.setdefault(owner, set()).add(name)
    for jar, member, info in classes:
        if info.super_class not in _HULLMOD_BASES:
            continue
        written_names = {name for owner, names in names_by_owner.items() if descends_from(owner, info.this_class) for name in names}
        mutable = sorted(
            name for name, descriptor, is_static, is_final in info.fields
            if not is_static and not is_final and not _looks_like_constant(name) and not descriptor.startswith("Ljava/util/")
            and (walk_failed or name in written_names)
        )
        if mutable:
            result.add(id="hullmod-instance-state", category="scripts", severity="medium", classification="REVIEW", confidence="DETERMINISTIC", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=[f"field:{name}" for name in mutable[:12]])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        class_match = re.search(r"\bclass\s+\w+\s+extends\s+BaseHullMod\b[^{]*\{", text)
        if not class_match:
            continue
        # Only fields declared at class-body depth 1 (not locals inside methods).
        body = text[class_match.end():]
        depth, top_level = 1, []
        for line in body.splitlines():
            if depth == 1:
                top_level.append(line)
            depth += line.count("{") - line.count("}")
            if depth <= 0:
                break
        mutable = sorted({
            match.group(2) for match in _SOURCE_HULLMOD_FIELD.finditer("\n".join(top_level))
            if "(" not in match.group(0)
            and not re.search(r"\b(static|final|return|package|import)\b", match.group(0))
            and not _looks_like_constant(match.group(2))
            and not re.search(r"\b(Map|HashMap|List|ArrayList|Set|HashSet|Collection|WeakHashMap)\b", match.group(1))
        })
        # Only a field some method writes is shared state; one set at its declaration and only read is a constant
        # in all but name (2026-09-30: 86 source packets, many of them tuning values or fields of commented-out code).
        # Only primitive and String fields are dropped this way: an array or object can change through its contents
        # without the field being assigned (Kingdom of Terra's KT_Biter fills `skull[0]` per ship through a setup call).
        declarations = "\n".join(top_level)
        # And only private ones: a public, protected or package field can be written from another class
        # (More Planetary Conditions' `public float hybridMult`).
        field_types = {m.group(2): m.group(1).strip() for m in _SOURCE_HULLMOD_FIELD.finditer(declarations)
                       if re.match(r"\s*private\b", m.group(0))}
        value_types = {"boolean", "byte", "char", "short", "int", "long", "float", "double", "String",
                       "Boolean", "Byte", "Character", "Short", "Integer", "Long", "Float", "Double"}

        def written(name: str) -> bool:
            if field_types.get(name) not in value_types:
                return True
            n = re.escape(name)
            writes = len(re.findall(rf"(?<![\w.])(?:this\.)?{n}\s*(?:[+\-*/%&|^]|<<|>>)?=(?!=)|(?<![\w.])(?:this\.)?{n}\s*(?:\+\+|--)|(?:\+\+|--)\s*(?:this\.)?{n}\b", body))
            initialised = 1 if re.search(rf"[\w>\]]\s+{n}\s*=(?!=)", declarations) else 0
            return writes > initialised

        mutable = [name for name in mutable if written(name)]
        if mutable:
            result.add(id="hullmod-instance-state", category="scripts", severity="medium", classification="REVIEW", confidence="HEURISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"field:{name}" for name in mutable[:12]])


def _scan_rules_firebest_populate_options(root: Path, result: ScanResult) -> None:
    """`FireBest PopulateOptions` rebuilds a menu from ONE rule, dropping vanilla's options (live bug VAC-DIALOG-01).

    PopulateOptions is fired by many rules that each add options (trade, comm directory, Leave...).
    Vanilla's rules.csv uses `FireAll PopulateOptions` 462 times and `FireBest` never. Vacuum's
    recreated station options used FireBest after "take bounty", so only one rule ran and the player
    was left in the dialog with no Leave option.
    """
    rules = root / "data" / "campaign" / "rules.csv"
    if not rules.is_file():
        return
    try:
        text = rules.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return
    lines = [text.count("\n", 0, match.start()) + 1 for match in re.finditer(r"\bFireBest\s+PopulateOptions\b", text)]
    if lines:
        result.add(
            id="rules-firebest-populate-options",
            category="rules",
            severity="high",
            classification="MANUAL",
            confidence="DETERMINISTIC",
            explanation="rules.csv fires PopulateOptions with FireBest, which runs only the single best-scoring rule. Menus are built by many PopulateOptions rules together (trade, comm directory, Leave...), so the player can be left in a dialog with no way out. Vanilla uses FireAll PopulateOptions everywhere (462 times, FireBest never); use FireAll.",
            file=_relative(root, rules),
            evidence=[f"line:{line}" for line in lines],
        )


def _scan_weapon_effect_static_state(root: Path, result: ScanResult) -> None:
    explanation = (
        "This weapon-effect plugin keeps combat state (a ship, weapon, engine controller, system or "
        "projectile) in a static field. Starsector creates one plugin per weapon, so a static field is "
        "shared by every copy in the battle: the last one to initialise overwrites it for all of them. "
        "SEEKER's ART_thrusterRotation did this, and a ship spawned mid-battle made another ship's weapon "
        "read a ship with no system, which crashed the game with a Fatal dialog. Make the field an instance "
        "field, and null-check getSystem()."
    )
    for jar, member, data in _iter_jar_class_files(root):
        info = _parse_class_file(data)
        if info is None or not PER_WEAPON_PLUGIN_INTERFACES.intersection(info.interfaces):
            continue
        shared = sorted(f"{name}:{descriptor.rsplit('/', 1)[-1].rstrip(';')}" for name, descriptor, is_static, is_final in info.fields if is_static and not is_final and descriptor in _COMBAT_STATE_DESCRIPTORS)
        if shared:
            result.add(id="weapon-effect-static-combat-state", category="scripts", severity="high", classification="MANUAL", confidence="DETERMINISTIC", explanation=explanation, file=f"{_relative(root, jar)}!{member}", evidence=[f"static:{item}" for item in shared])
    for source in sorted(root.rglob("*.java")):
        if any(part in NON_MOD_JAR_DIRS or part.startswith("src-decompiled") for part in source.relative_to(root).parts):
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not re.search(r"\bimplements\b[^{]*\b(EveryFrameWeaponEffectPlugin|OnFireEffectPlugin|OnHitEffectPlugin|WeaponEffectPluginWithInit)\b", text):
            continue
        shared = sorted(f"{match.group(2)}:{match.group(1)}" for match in _SOURCE_STATIC_STATE.finditer(text))
        if shared:
            result.add(id="weapon-effect-static-combat-state", category="scripts", severity="high", classification="MANUAL", confidence="HEURISTIC", explanation=explanation, file=_relative(root, source), evidence=[f"static:{item}" for item in shared])


# A ship in a market's stock (or any fleet data that belongs to no fleet) has getFleetData().getFleet() == null, and RC8 calls a hull mod's
# advanceInCampaign for such members when it syncs the stock (opening a market sorts it). Epta Consortium's AI-core refunder hull mods
# read `member.getFleetData().getFleet().equals(...)` there and crashed on opening a market (crash report 2026-10-13; the stack ran
# FleetData.sort -> syncIfNeeded -> advanceInCampaign).
_FLEET_DEREFERENCE = re.compile(r"getFleetData\(\)\s*\.\s*getFleet\(\)\s*\.\s*\w+")
_FLEET_NULL_CHECK = re.compile(r"getFleet\(\)\s*(?:!=|==)\s*null|getFleetData\(\)\s*(?:!=|==)\s*null|\.getFleet\(\)\s*(?:!=|==)")


def unguarded_fleet_dereference_lines(body: str) -> list[int]:
    """1-based line numbers (within `body`) of `getFleetData().getFleet().x` calls with no null check on the fleet or its data before them."""
    lines = []
    for match in _FLEET_DEREFERENCE.finditer(body):
        if not _FLEET_NULL_CHECK.search(body[:match.start()]):
            lines.append(body.count("\n", 0, match.start()) + 1)
    return lines


def _scan_hullmod_fleet_dereference(root: Path, result: ScanResult) -> None:
    """A hull mod's advanceInCampaign that calls a method on `member.getFleetData().getFleet()` without a null check crashes when RC8 runs it
    for a ship in a market's stock (REVIEW; add `getFleetData() != null && getFleet() != null &&`)."""
    for source in sorted(root.rglob("*.java")):
        if "disabled_files" in source.relative_to(root).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if "advanceInCampaign" not in text or not re.search(r"\bextends\s+BaseHullMod\b|\bimplements\s+HullModEffect\b", text):
            continue
        from .scan_javatext import _method_body

        body = _method_body(text, "advanceInCampaign")
        lines = unguarded_fleet_dereference_lines(body)
        if lines:
            result.add(id="hullmod-fleet-dereference-unguarded", category="scripts", severity="high", classification="REVIEW", confidence="HIGH",
                       explanation="advanceInCampaign calls a method on member.getFleetData().getFleet() with no null check. A ship in a market's stock has "
                                   "no fleet, and RC8 runs the hull mod for it when the stock is synced, so opening a market throws a NullPointerException. "
                                   "Guard it: getFleetData() != null && getFleetData().getFleet() != null && ...",
                       file=_relative(root, source), evidence=[f"line-in-advanceInCampaign:{n}" for n in lines])
