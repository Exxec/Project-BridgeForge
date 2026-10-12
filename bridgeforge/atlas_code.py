"""Mod Atlas phases 2-3: facts from a mod's code (loose .java under data/ and loaded jars).

Loose Java is read with comments blanked (the scanner's helper) and call-site regexes. Jars are read through their
class-file constant pools (`atlas_classfile`), so no javap is needed. A string literal in code is only ever REVIEW: it
may be dead code. Literals that are not at a recognised call site are returned separately and resolved against the
known ids once every mod is indexed (`atlas.resolve_references`).
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import NamedTuple

from .atlas_classfile import ACC_STATIC, ACC_TRANSIENT, ClassFormatError, ClassInfo, parse_class
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
REGISTER_METHODS = {"addListener", "addTransientListener", "addScript", "addTransientScript", "addPlugin"}


class CodeResult(NamedTuple):
    facts: list[Fact]
    literals: list[tuple[str, int, str, str]]  # (file, line, value, ctx: call names seen in the same class)


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
            facts.append(Fact(kind, "<dynamic>", action, rel, line, f"method={method} non-literal argument: {(other or '').strip()}", "UNKNOWN"))
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


def _loose_class_facts(text: str, rel: str, stem: str, scripts: set[str]) -> list[Fact]:
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
    if roles & SAVED_BASES or stem in scripts:
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
    facts, literals = [], []
    for path, text in texts.items():
        rel = path.relative_to(root).as_posix()
        facts += _call_facts(text, rel)
        facts += [Fact("hook", _simple(m.group(2)), "registers", rel, _line_of(text, m.start()), f"{m.group(1)}(new {m.group(2)})", "REVIEW")
                  for m in _REGISTER_RE.finditer(text)]
        facts += _loose_class_facts(text, rel, path.stem, scripts)
        seen = set()
        for match in LITERAL_RE.finditer(text):
            if match.group(1) not in seen:
                seen.add(match.group(1))
                literals.append((rel, _line_of(text, match.start()), match.group(1), ""))
    return CodeResult(facts, literals)


# ---------------------------------------------------------------- jars

def _jar_class_facts(info: ClassInfo, rel: str, digest: str) -> list[Fact]:
    fqcn = info.name.replace("/", ".")
    roles = {_simple(info.super_name)} | {_simple(name) for name in info.interfaces}
    facts = []
    if "$" not in info.name:
        facts.append(Fact("class", fqcn, "defines", rel, 0, f"jar sha={digest}", "SAFE"))
    facts += [Fact("hook", fqcn, "registers", rel, 0, f"declares {role}", "REVIEW") for role in sorted(roles) if _is_role_hook(role)]
    called = sorted(info.called_methods & REGISTER_METHODS)
    if called:
        facts.append(Fact("hook", fqcn, "registers", rel, 0, f"jar: calls {', '.join(called)} (class-level)", "REVIEW"))
    if roles & CAMPAIGN_PLUGIN_ROLES:
        priorities = info.field_refs & PICK_PRIORITIES
        priority = next(iter(priorities)) if len(priorities) == 1 else "?"
        facts += [Fact("campaign-pick", name, "registers", rel, 0, f"{fqcn} priority={priority}", "REVIEW")
                  for name in info.methods if re.match(r"pick[A-Z]", name)]
    if roles & SAVED_BASES:
        for name, descriptor, flags in info.fields:
            if descriptor in HEAVY_DESCRIPTORS and not flags & (ACC_STATIC | ACC_TRANSIENT):
                facts.append(Fact("saved-field", f"{fqcn}.{name}", "persists", rel, 0,
                                  f"{HEAVY_DESCRIPTORS[descriptor]} held by a saved script/plugin ({'/'.join(sorted(roles & SAVED_BASES))})", "REVIEW"))
    if "getConditions" in info.called_methods and info.called_methods & set(_MUTATORS):
        facts.append(Fact("collection", "market.conditions", "mutates", rel, 0,
                          "jar: getConditions and a clear/sort call in one class (co-occurrence, weaker than a call site)", "REVIEW"))
    return facts


def _jar_literals(info: ClassInfo, rel: str) -> list[tuple[str, int, str, str]]:
    ctx = ",".join(sorted(info.called_methods & CALLS.keys()))
    return [(rel, 0, value, ctx) for value in sorted({s for s in info.strings if ID_LIKE.match(s)})]


def extract_jar(root: Path, jar: Path) -> CodeResult:
    jar_rel = jar.relative_to(root).as_posix()
    facts: list[Fact] = []
    literals: list[tuple[str, int, str, str]] = []
    try:
        with zipfile.ZipFile(jar) as archive:
            names = [n for n in archive.namelist() if n.endswith(".class")]
            if len(names) > MAX_JAR_ENTRIES:
                return CodeResult([Fact("jar", jar_rel, "unreadable", jar_rel, 0, "too many entries", "UNKNOWN")], [])
            for name in names:
                try:
                    data = archive.read(name)
                    info = parse_class(data)
                except (ClassFormatError, zipfile.BadZipFile, OSError, RuntimeError, EOFError):
                    continue
                rel = f"{jar_rel}!{name}"
                facts += _jar_class_facts(info, rel, _digest(data))
                literals += _jar_literals(info, rel)
    except (zipfile.BadZipFile, OSError) as exc:
        return CodeResult([Fact("jar", jar_rel, "unreadable", jar_rel, 0, f"{type(exc).__name__}: {exc}", "UNKNOWN")], [])
    return CodeResult(facts, literals)


def extract_code(root: Path, with_jars: bool = True) -> CodeResult:
    result = extract_loose_java(root)
    facts, literals = list(result.facts), list(result.literals)
    for jar in _loaded_mod_jars(root) if with_jars else []:
        part = extract_jar(root, jar)
        facts += part.facts
        literals += part.literals
    return CodeResult(facts, literals)
