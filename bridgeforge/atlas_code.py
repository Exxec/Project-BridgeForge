"""Mod Atlas phases 2-3: facts from a mod's code (loose .java under data/ and loaded jars).

Loose Java is read with comments blanked (the scanner's helper) and call-site regexes. Jars are read through their
class-file constant pools (`atlas_classfile`), so no javap is needed. A string literal in code is only ever REVIEW: it
may be dead code. Literals that are not at a recognised call site are returned separately and resolved against the
known ids once every mod is indexed (`atlas.resolve_references`).
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import NamedTuple

from .atlas_data import Fact
from .scanner import _blank_java_comments, _loaded_mod_jars

MAX_JAR_ENTRIES = 200_000
MAX_DYNAMIC_PER_FILE = 20
LITERAL_RE = re.compile(r'"([A-Za-z][A-Za-z0-9_]{2,60})"')
ID_LIKE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,60}$")

# method name -> (kind of id passed, action)
CALLS: dict[str, tuple[str, str]] = {
    "getIndustry": ("industry", "reads"), "hasIndustry": ("industry", "reads"), "getIndustrySpec": ("industry", "reads"),
    "addIndustry": ("industry", "mutates"), "removeIndustry": ("industry", "mutates"),
    "hasCondition": ("condition", "reads"), "getCondition": ("condition", "reads"),
    "getMarketConditionSpec": ("condition", "reads"),
    "addCondition": ("condition", "mutates"), "removeCondition": ("condition", "mutates"),
    "getCommodityData": ("commodity", "reads"), "getCommoditySpec": ("commodity", "reads"),
    "getFaction": ("faction", "reads"), "getHullSpec": ("hull", "reads"), "getWeaponSpec": ("weapon", "reads"),
    "getSpecialItemSpec": ("special_item", "reads"), "getHullModSpec": ("hullmod", "reads"),
    "getFighterWingSpec": ("wing", "reads"), "getShipSystemSpec": ("system", "reads"),
    "getSkillSpec": ("skill", "reads"), "getAbilitySpec": ("ability", "reads"), "getVariant": ("variant", "reads"),
    "hasSubmarket": ("submarket", "reads"), "getSubmarket": ("submarket", "reads"),
    "addSubmarket": ("submarket", "mutates"), "removeSubmarket": ("submarket", "mutates"),
    "hasAbility": ("ability", "reads"), "addAbility": ("ability", "mutates"), "removeAbility": ("ability", "mutates"),
}
# Starsector id constants: Industries.FARMING == "farming" (lower-cased name; REVIEW)
CONSTANT_CLASSES = ("Industries", "Conditions", "Commodities", "Factions", "Submarkets", "Abilities", "HullMods", "Skills", "Items")
_CALL_RE = re.compile(
    r"\b(" + "|".join(CALLS) + r")\s*\(\s*(?:\"([^\"\\\n]*)\"(?=\s*[,)])|(" +"|".join(CONSTANT_CLASSES) + r")\.([A-Z][A-Z0-9_]*)\b|([^,)\n]{1,40}))")
_COLLECTIONS = (("getConditions", "market.conditions"), ("getIndustries", "market.industries"))
_MUTATORS = ("clear", "sort", "reverse", "shuffle", "swap", "removeAll", "retainAll")
_COLLECTION_RE = re.compile(
    r"\b(getConditions|getIndustries)\s*\(\s*\)\s*\.\s*(" + "|".join(_MUTATORS) + r")\s*\("
    r"|\bCollections\s*\.\s*(sort|reverse|shuffle|swap)\s*\(\s*[\w.()\s]*?\b(getConditions|getIndustries)\s*\(")
_REGISTER_RE = re.compile(r"\b(addListener|addTransientListener|addScript|addTransientScript|addPlugin)\s*\(\s*new\s+([\w.]+)")
_PERSISTENT_REGISTER = {"addListener", "addScript"}
_PACKAGE_RE = re.compile(r"^\s*package\s+([\w.]+)\s*;", re.MULTILINE)
_HEAVY = ("MarketAPI", "SectorEntityToken", "CampaignFleetAPI")
_FIELD_RE = re.compile(
    r"^([ \t]*)((?:(?:private|protected|public|static|final|transient|volatile)\s+)*)"
    r"(?:(?:List|ArrayList|Set|HashSet|Map|HashMap)\s*<[^;=(){}]*?)?\b(" + "|".join(_HEAVY) + r")\b[^;=(){}]*?\s(\w+)\s*(?:=|;)",
    re.MULTILINE)
_PICK_RE = re.compile(r"\b(?:public|protected)\s+[\w<>?,\s.\[\]]+?\s+(pick[A-Z]\w*)\s*\(")
_PRIORITY_RE = re.compile(r"\bPickPriority\s*\.\s*([A-Z_]+)")
HEAVY_DESCRIPTORS = {
    "Lcom/fs/starfarer/api/campaign/econ/MarketAPI;": "MarketAPI",
    "Lcom/fs/starfarer/api/campaign/SectorEntityToken;": "SectorEntityToken",
    "Lcom/fs/starfarer/api/campaign/CampaignFleetAPI;": "CampaignFleetAPI",
}
PICK_PRIORITIES = {"HIGHEST", "MOD_SPECIFIC", "MOD_SET", "MOD_GENERAL", "CORE_SPECIFIC", "CORE_SET", "CORE_GENERAL", "LOWEST"}
SAVED_BASES = {"EveryFrameScript", "EveryFrameScriptWithCleanup", "BaseIntelPlugin"}
HOOK_ROLES = {"BaseModPlugin", "EveryFrameScript", "EveryFrameScriptWithCleanup", "CampaignPlugin", "BaseCampaignPlugin"}
CAMPAIGN_PLUGIN_ROLES = {"CampaignPlugin", "BaseCampaignPlugin"}


class CodeResult(NamedTuple):
    facts: list[Fact]
    literals: list[tuple[str, int, str, str]]  # (file, line, value, ctx: call names, only when a class's bytecode could not be scanned)
    constants: dict  # (simple class name, field name) -> String constant value, for resolving `getIndustry(Cls.X)`


def _digest(data: bytes | str) -> str:
    raw = data.encode("utf-8", "replace") if isinstance(data, str) else data
    return hashlib.sha1(raw).hexdigest()[:10]


def _simple(name: str) -> str:
    return re.split(r"[./$]", name.strip())[-1] if name.strip() else ""


def _is_role_hook(role: str) -> bool:
    return role in HOOK_ROLES or role.endswith("Listener")


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------- loose java

_PREFIX_RE = re.compile(r'\s*"([A-Za-z0-9_]{1,40})"\s*\+')
_CONSTREF_RE = re.compile(r"\s*(?:([A-Za-z_]\w*)\s*\.\s*)?([A-Z][A-Z0-9_]*)\s*")
_STRING_CONSTANT_RE = re.compile(r'\b(?:static\s+final|final\s+static)\s+String\s+(\w+)\s*=\s*"([^"\\\n]*)"')
_EVIDENCE_PREFIX = re.compile(r"prefix=(\S+)")
_EVIDENCE_CONSTREF = re.compile(r"constref=(\w*)\.(\w+)")


def _dynamic_fact(kind: str, action: str, rel: str, line: int, method: str, argument: str, prefix: str = "", constref: str = "") -> Fact:
    """An id the static scan cannot read; `prefix=` (67f) and `constref=` (67b) let later passes resolve it."""
    note = f"method={method} non-literal argument: {argument.strip()}"
    note += f" prefix={prefix}" if prefix else ""
    note += f" constref={constref}" if constref else ""
    return Fact(kind, "<dynamic>", action, rel, line, note, "UNKNOWN")


def _loose_dynamic(kind: str, action: str, rel: str, line: int, method: str, other: str) -> Fact:
    prefix = _PREFIX_RE.match(other)
    constref = _CONSTREF_RE.fullmatch(other)
    ref = f"{constref.group(1) or Path(rel).stem}.{constref.group(2)}" if constref else ""
    return _dynamic_fact(kind, action, rel, line, method, other, prefix.group(1) if prefix else "", ref)


def resolve_constants(facts: list[Fact], constants: dict) -> list[Fact]:
    """Replace `<dynamic>` facts that name a mod-defined String constant (`Cls.X`) by the literal it holds (67b)."""
    out = []
    for fact in facts:
        ref = _EVIDENCE_CONSTREF.search(fact.evidence) if fact.id == "<dynamic>" else None
        value = constants.get((ref.group(1), ref.group(2))) if ref else None
        if value is None:
            out.append(fact)
            continue
        method = re.match(r"method=(\w+)", fact.evidence).group(1)
        out.append(Fact(fact.kind, value, fact.action, fact.file, fact.line,
                        f"method={method} constant {ref.group(1)}.{ref.group(2)} = \"{value}\" (mod-defined)", "REVIEW"))
    return out


def _call_facts(text: str, rel: str) -> list[Fact]:
    facts, dynamic = [], 0
    for match in _CALL_RE.finditer(text):
        method, literal, const_class, const_name, other = match.groups()
        kind, action = CALLS[method]
        line = _line_of(text, match.start())
        if literal is not None:
            facts.append(Fact(kind, literal, action, rel, line, f"method={method}", "REVIEW"))
        elif const_class:
            facts.append(Fact(kind, const_name.lower(), action, rel, line,
                              f"method={method} via {const_class}.{const_name} (id lower-cased from the constant name)", "REVIEW"))
        elif dynamic < MAX_DYNAMIC_PER_FILE:
            dynamic += 1
            facts.append(_loose_dynamic(kind, action, rel, line, method, other or ""))
    for match in _COLLECTION_RE.finditer(text):
        getter = match.group(1) or match.group(4)
        ident = dict(_COLLECTIONS)[getter]
        how = f"{getter}().{match.group(2)}()" if match.group(1) else f"Collections.{match.group(3)}({getter}())"
        facts.append(Fact("collection", ident, "mutates", rel, _line_of(text, match.start()), how, "REVIEW"))
    return facts


def _class_header(text: str, stem: str) -> tuple[int, set[str]] | None:
    match = re.search(r"\b(?:class|interface|enum)\s+" + re.escape(stem) + r"\b([^{]*)\{", text)
    if not match:
        return None
    header = re.sub(r"<[^<>]*>", "", match.group(1))
    roles = {_simple(token) for token in re.split(r"[\s,]+", header) if token and token not in ("extends", "implements")}
    return _line_of(text, match.start()), roles


def _loose_class_facts(text: str, rel: str, stem: str, scripts: set[str], transient: frozenset[str] = frozenset()) -> list[Fact]:
    header = _class_header(text, stem)
    package = _PACKAGE_RE.search(text)
    if not header:
        return []
    line, roles = header
    fqcn = (package.group(1) + "." if package else "") + stem
    facts = [Fact("class", fqcn, "defines", rel, line, f"loose sha={_digest(text)}", "SAFE")]
    facts += [Fact("hook", fqcn, "registers", rel, line, f"declares {role}", "REVIEW") for role in sorted(roles) if _is_role_hook(role)]
    if roles & CAMPAIGN_PLUGIN_ROLES:
        priorities = set(_PRIORITY_RE.findall(text)) & PICK_PRIORITIES
        priority = next(iter(priorities)) if len(priorities) == 1 else "?"
        facts += [Fact("campaign-pick", pick, "registers", rel, _line_of(text, m.start()), f"{fqcn} priority={priority}", "REVIEW")
                  for m in _PICK_RE.finditer(text) for pick in [m.group(1)]]
    if (roles & SAVED_BASES and stem not in transient) or stem in scripts:  # addTransientScript(new X) is not saved (67e)
        for match in _FIELD_RE.finditer(text):
            indent, modifiers, type_name, field_name = match.groups()
            if "static" in modifiers or "transient" in modifiers:
                continue
            is_field = bool(re.search(r"private|protected|public", modifiers)) or len(indent.replace("\t", "    ")) <= 4
            if not is_field:
                continue  # a local variable inside a method
            facts.append(Fact("saved-field", f"{fqcn}.{field_name}", "persists", rel, _line_of(text, match.start()),
                              f"{type_name} held by a saved script/plugin ({'/'.join(sorted(roles & SAVED_BASES)) or 'added with addScript'})",
                              "REVIEW"))
    return facts


def extract_loose_java(root: Path) -> CodeResult:
    data_dir = root / "data"
    files = sorted(data_dir.rglob("*.java")) if data_dir.is_dir() else []
    texts: dict[Path, str] = {}
    for path in files:
        try:
            texts[path] = _blank_java_comments(path.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            continue
    scripts = {_simple(m.group(2)) for text in texts.values() for m in _REGISTER_RE.finditer(text)
               if m.group(1) in _PERSISTENT_REGISTER}
    transient = frozenset(_simple(m.group(2)) for text in texts.values() for m in _REGISTER_RE.finditer(text)
                          if m.group(1) not in _PERSISTENT_REGISTER) - scripts
    constants = {(path.stem, m.group(1)): m.group(2) for path, text in texts.items() for m in _STRING_CONSTANT_RE.finditer(text)}
    facts, literals = [], []
    for path, text in texts.items():
        rel = path.relative_to(root).as_posix()
        facts += _call_facts(text, rel)
        facts += [Fact("hook", _simple(m.group(2)), "registers", rel, _line_of(text, m.start()), f"{m.group(1)}(new {m.group(2)})", "REVIEW")
                  for m in _REGISTER_RE.finditer(text)]
        facts += _loose_class_facts(text, rel, path.stem, scripts, transient)
        seen = set()
        for match in LITERAL_RE.finditer(text):
            if match.group(1) not in seen:
                seen.add(match.group(1))
                literals.append((rel, _line_of(text, match.start()), match.group(1), ""))
    return CodeResult(facts, literals, constants)


def extract_code(root: Path, with_jars: bool = True) -> CodeResult:
    """Loose java plus loaded jars; mod-defined String constants from both resolve `getIndustry(Cls.X)` call sites (67b)."""
    from .atlas_jar import extract_jar  # imported late: atlas_jar builds on this module

    result = extract_loose_java(root)
    facts, literals, constants = list(result.facts), list(result.literals), dict(result.constants)
    for jar in _loaded_mod_jars(root) if with_jars else []:
        part = extract_jar(root, jar)
        facts += part.facts
        literals += part.literals
        constants.update(part.constants)
    return CodeResult(resolve_constants(facts, constants), literals, constants)
