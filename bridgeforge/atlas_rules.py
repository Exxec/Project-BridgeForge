"""Mod Atlas conflict rules, replacement profiles and forecasts (ROADMAP item 67).

Every rule works on the facts of a load set (some mods plus vanilla) and yields `Finding`s at SAFE/REVIEW/MANUAL/UNKNOWN.
Nothing here edits a mod: a finding names both sides, the files and lines, and the evidence.
"""
from __future__ import annotations

import difflib
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from typing import NamedTuple

from .atlas import VANILLA_ID, latest_mods
from .atlas_data import DATA_KINDS

CRASH, SILENT, COSMETIC = "crash-class", "silent-behaviour", "cosmetic"
CATEGORY_ORDER = {CRASH: 0, SILENT: 1, COSMETIC: 2}
MISSING_KINDS = {"industry", "condition", "commodity", "faction", "special_item", "hullmod", "weapon", "wing", "hull", "system", "skill", "ability", "submarket"}
CLOSE_ID_CUTOFF = 0.6
MAX_SIDE_FACTS = 5
MAX_NAMED_IDS = 8
LEVEL_ORDER = {"MANUAL": 0, "REVIEW": 1, "UNKNOWN": 2, "SAFE": 3}


class AFact(NamedTuple):
    mod: str
    kind: str
    id: str
    action: str
    file: str
    line: int
    evidence: str
    confidence: str


@dataclass
class Finding:
    rule: str
    level: str
    category: str
    summary: str
    mods: list[str]
    sides: list[dict] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"rule": self.rule, "level": self.level, "category": self.category, "summary": self.summary,
                "mods": self.mods, "ids": self.ids, "sides": self.sides}


@dataclass
class Profile:
    """What one mod removes, replaces, overrides or mutates (owner decision 3, 2026-10-11)."""
    mod: str
    replaced: dict[tuple[str, str], dict] = field(default_factory=dict)  # (kind, id) -> {"by": set, "facts": [AFact], "how": str}
    overrides: list[AFact] = field(default_factory=list)
    mutates: dict[str, list[AFact]] = field(default_factory=dict)  # shared collection / id -> facts

    def as_dict(self) -> dict:
        return {
            "replaced": [{"kind": k, "id": i, "by": sorted(v["by"]), "how": v["how"], "at": _where(v["facts"][0])}
                         for (k, i), v in sorted(self.replaced.items())],
            "overrides": [{"kind": f.kind, "id": f.id, "at": _where(f)} for f in self.overrides],
            "mutates": {key: [_where(f) for f in facts[:MAX_SIDE_FACTS]] for key, facts in sorted(self.mutates.items())},
        }


def _where(fact: AFact) -> str:
    return f"{fact.file}:{fact.line}" if fact.line else fact.file


def _side(fact: AFact) -> dict:
    return {"mod": fact.mod, "kind": fact.kind, "id": fact.id, "action": fact.action, "file": fact.file,
            "line": fact.line, "evidence": fact.evidence, "confidence": fact.confidence}


def _sides(facts: list[AFact]) -> list[dict]:
    return [_side(f) for f in facts[:MAX_SIDE_FACTS]]


# ---------------------------------------------------------------- loading

def load_facts(conn: sqlite3.Connection, mods: list[dict]) -> list[AFact]:
    rows: list[AFact] = []
    for mod in mods:
        for r in conn.execute("SELECT kind, id, action, file, line, evidence, confidence FROM facts WHERE mod = ? AND version = ?",
                              (mod["id"], mod["version"])):
            rows.append(AFact(mod["id"], *tuple(r)))
    return rows


def with_vanilla(conn: sqlite3.Connection, mods: list[dict]) -> list[dict]:
    vanilla = [m for m in latest_mods(conn) if m["id"] == VANILLA_ID]
    return [m for m in mods if m["id"] != VANILLA_ID] + vanilla


# ---------------------------------------------------------------- profiles

def _method(fact: AFact) -> str:
    match = re.search(r"method=(\w+)|co-occurrence with (\w+)", fact.evidence)
    return (match.group(1) or match.group(2)) if match else ""


def build_profile(mod: str, facts: list[AFact]) -> Profile:
    profile = Profile(mod)
    removed: dict[tuple[str, str], list[AFact]] = defaultdict(list)
    added: dict[str, set[str]] = defaultdict(set)
    added_in: dict[tuple[str, str], set[str]] = defaultdict(set)  # (kind, file/class) -> ids added there
    for fact in (f for f in facts if f.mod == mod):
        if fact.confidence == "UNKNOWN" or fact.evidence.startswith("prefix-resolved"):
            continue  # guesses (unscanned class, id built from a prefix) never decide what a mod replaces
        method = _method(fact)
        if fact.action == "replaces":
            entry = profile.replaced.setdefault((fact.kind, fact.id), {"by": set(), "facts": [], "how": "csv upgrade/downgrade chain"})
            entry["by"].add(fact.evidence.split()[0])
            entry["facts"].append(fact)
        elif fact.action == "overrides":
            profile.overrides.append(fact)
        elif fact.action == "mutates" and fact.kind == "collection":
            profile.mutates.setdefault(fact.id, []).append(fact)
        elif fact.action == "mutates" and method.startswith("remove"):
            removed[(fact.kind, fact.id)].append(fact)
        elif fact.action == "mutates" and method.startswith("add"):
            added[fact.kind].add(fact.id)
            added_in[(fact.kind, fact.file)].add(fact.id)
    for (kind, ident), source in removed.items():
        if ident in added.get(kind, set()):
            # removed and added back: a reorder (AoTD's condition reshuffle), not a replacement
            profile.mutates.setdefault(f"{kind}:{ident}", []).extend(source)
            continue
        # A replacement is a removal with an addition in the same class or file. Counting every id the mod adds anywhere made
        # AoTD's terraforming inserter (removeCondition("cold"), etc.) "replace" cold/hot/very_cold for DNEEP (2026-10-11);
        # a bare removal is a shared mutation, reported by ATLAS-MUTATE-SHARED, not a replacement.
        by: set[str] = set()
        for fact in source:
            by |= added_in.get((kind, fact.file), set())
        by -= {key[1] for key in removed if key[0] == kind}
        if not by:
            profile.mutates.setdefault(f"{kind}:{ident}", []).extend(source)
            continue
        entry = profile.replaced.setdefault((kind, ident), {"by": set(), "facts": [], "how": "remove+add in code"})
        entry["by"] |= by
        entry["facts"] += source
    return profile


# ---------------------------------------------------------------- rules

def _distinct_mods(facts: list[AFact]) -> set[str]:
    return {f.mod for f in facts}


def _sig(fact: AFact) -> str:
    match = re.search(r"sig=(\w+)", fact.evidence)
    return match.group(1) if match else fact.evidence


def rule_dup_define(facts: list[AFact], folders: dict[str, str]) -> list[Finding]:
    groups: dict[tuple[str, str], list[AFact]] = defaultdict(list)
    for f in facts:
        if f.mod != VANILLA_ID and f.action in ("defines", "overrides") and f.kind in DATA_KINDS and f.kind != "rule":
            groups[(f.kind, f.id)].append(f)
    out = []
    for (kind, ident), group in sorted(groups.items()):
        if len(_distinct_mods(group)) < 2:
            continue
        differ = len({_sig(f) for f in group}) > 1
        level = "MANUAL" if kind in ("hull", "weapon") and differ else "REVIEW"
        winner = max(_distinct_mods(group), key=lambda m: folders.get(m, m).lower())
        out.append(Finding("ATLAS-DUP-DEFINE", level, SILENT, f"{kind} '{ident}' is defined by {len(_distinct_mods(group))} mods"
                           f"{' with different rows' if differ else ''}; load order is alphabetical by folder, so '{winner}' likely wins",
                           sorted(_distinct_mods(group)), _sides(group), [ident]))
    return out


def rule_settings_override(facts: list[AFact]) -> list[Finding]:
    groups: dict[str, list[AFact]] = defaultdict(list)
    for f in facts:
        if f.kind == "setting" and f.mod != VANILLA_ID and not f.evidence.startswith(("dict:", "list:")):
            groups[f.id].append(f)
    return [Finding("ATLAS-SETTINGS-OVERRIDE", "REVIEW", COSMETIC,
                    f"settings.json key '{key}' is set to different values: " + ", ".join(f"{f.mod}={f.evidence}" for f in group),
                    sorted(_distinct_mods(group)), _sides(group), [key])
            for key, group in sorted(groups.items()) if len(_distinct_mods(group)) > 1 and len({f.evidence for f in group}) > 1]


def _rule_parts(fact: AFact) -> tuple[str, str]:
    match = re.match(r"trigger=(.*?) \| conditions=(.*?) \| sig=", fact.evidence)
    return (match.group(1).strip(), re.sub(r"\s+", "", match.group(2))) if match else ("", "")


def rule_rules_clash(facts: list[AFact]) -> list[Finding]:
    groups: dict[tuple[str, str], list[AFact]] = defaultdict(list)
    for f in facts:
        if f.kind == "rule" and f.mod != VANILLA_ID:
            trigger, conditions = _rule_parts(f)
            if trigger and conditions:
                groups[(trigger, conditions)].append(f)
    return [Finding("ATLAS-RULES-CLASH", "REVIEW", COSMETIC,
                    f"rules.csv trigger '{trigger}' with the same conditions has different content in {len(_distinct_mods(group))} mods",
                    sorted(_distinct_mods(group)), _sides(group), [f.id for f in group[:MAX_SIDE_FACTS]])
            for (trigger, _), group in sorted(groups.items()) if len(_distinct_mods(group)) > 1 and len({_sig(f) for f in group}) > 1]


def rule_reads_replaced(facts: list[AFact], profiles: dict[str, Profile]) -> list[Finding]:
    readers: dict[tuple[str, str], list[AFact]] = defaultdict(list)
    for f in facts:
        if f.action in ("reads", "references", "mutates") and f.id != "<dynamic>" and f.mod != VANILLA_ID:
            if f.action == "mutates" and "method=add" in f.evidence:
                # Creating an industry/condition/submarket (addIndustry("farming") at generation, which AoTD expects) is not a use of
                # an existing one: only lookups and removals break when another mod has replaced it. The AoTD sweep of 338 mods
                # flagged 80 mods that "use" an AoTD-replaced industry, nearly all through addIndustry (2026-10-12).
                continue
            readers[(f.kind, f.id)].append(f)
    out = []
    for replacer, profile in sorted(profiles.items()):
        for (kind, ident), info in sorted(profile.replaced.items()):
            for reader in sorted({f.mod for f in readers.get((kind, ident), []) if f.mod != replacer}):
                theirs = [f for f in readers[(kind, ident)] if f.mod == reader]
                ordered = sorted(info["by"])
                by = (", ".join(ordered[:MAX_NAMED_IDS]) + (f" (+{len(ordered) - MAX_NAMED_IDS} more)" if len(ordered) > MAX_NAMED_IDS else "")) or "nothing (removed)"
                # A call site (getIndustry, hasIndustry, removeIndustry ...) is a use: REVIEW. A string equal to the id somewhere in a jar's
                # constant pool is only a mention (javac inlines Industries.FARMING as "farming" into every jar that names it): UNKNOWN.
                # The AoTD sweep of 338 mods: 57 mods only mentioned "farming" this way, about a dozen called getIndustry/hasIndustry.
                used = any(f.action != "references" for f in theirs)
                out.append(Finding("ATLAS-READS-REPLACED", "REVIEW" if used else "UNKNOWN", SILENT,
                                   f"{reader} {'uses' if used else 'mentions'} {kind} '{ident}' ({_where(theirs[0])}); {replacer} replaces or removes it ({info['how']}); replacing ids: {by}",
                                   [reader, replacer], _sides(theirs) + _sides(info["facts"]), [ident, *sorted(info["by"])]))
    return out


def rule_reads_missing(facts: list[AFact]) -> list[Finding]:
    if not any(f.mod == VANILLA_ID for f in facts):
        return []
    defined = {(f.kind, f.id) for f in facts if f.action in ("defines", "overrides", "patches")}
    defined_ids: dict[str, list[str]] = defaultdict(list)
    for kind, ident in sorted(defined):
        defined_ids[kind].append(ident)
    out = []
    for f in facts:
        literal_call = f.evidence.startswith("method=") and " via " not in f.evidence
        method = _method(f)
        if (f.action == "reads" or method.startswith("add")) and f.kind in MISSING_KINDS and literal_call and f.id != "<dynamic>" \
                and (f.kind, f.id) not in defined:
            close = difflib.get_close_matches(f.id.lower(), [i.lower() for i in defined_ids[f.kind]], n=1, cutoff=CLOSE_ID_CUTOFF)
            closest = next((i for i in defined_ids[f.kind] if close and i.lower() == close[0]), "")
            hint = f"; closest id a provider does define: '{closest}' (a renamed id?)" if closest else ""
            out.append(Finding("ATLAS-READS-MISSING", "REVIEW", CRASH,
                               f"{f.mod} uses {f.kind} '{f.id}' ({_where(f)}) but no mod in this set and not vanilla defines it "
                               f"(often an optional soft dependency){hint}", [f.mod], [_side(f)], [f.id, *([closest] if closest else [])]))
    return out


def rule_mutate_shared(facts: list[AFact]) -> list[Finding]:
    groups: dict[tuple[str, str], list[AFact]] = defaultdict(list)
    for f in facts:
        if f.action == "mutates" and f.mod != VANILLA_ID and f.id != "<dynamic>":
            groups[(f.kind, f.id)].append(f)
    return [Finding("ATLAS-MUTATE-SHARED", "REVIEW", SILENT,
                    f"{len(_distinct_mods(group))} mods mutate the same {'collection' if kind == 'collection' else kind} '{ident}'",
                    sorted(_distinct_mods(group)), _sides(group), [ident])
            for (kind, ident), group in sorted(groups.items()) if len(_distinct_mods(group)) > 1]


def rule_pick_priority(facts: list[AFact]) -> list[Finding]:
    groups: dict[str, list[AFact]] = defaultdict(list)
    for f in facts:
        if f.kind == "campaign-pick" and f.mod != VANILLA_ID:
            groups[f.id].append(f)
    out = []
    for pick, group in sorted(groups.items()):
        priorities = {f.evidence.rsplit("priority=", 1)[-1] for f in group}
        if len(_distinct_mods(group)) > 1 and (len(priorities) == 1 or "?" in priorities):
            out.append(Finding("ATLAS-PICK-PRIORITY", "REVIEW", SILENT,
                               f"{len(_distinct_mods(group))} CampaignPlugins define {pick} at priority {'/'.join(sorted(priorities))}",
                               sorted(_distinct_mods(group)), _sides(group), [pick]))
    return out


def rule_shadow_class(facts: list[AFact]) -> list[Finding]:
    groups: dict[str, list[AFact]] = defaultdict(list)
    for f in facts:
        if f.kind == "class" and f.action == "defines" and f.mod != VANILLA_ID:
            groups[f.id].append(f)
    out = []
    for fqcn, group in sorted(groups.items()):
        if len(group) < 2 or len({_sig(f) for f in group}) < 2:
            continue
        across = len(_distinct_mods(group)) > 1
        out.append(Finding("ATLAS-SHADOW-CLASS", "MANUAL" if across else "REVIEW", CRASH,
                           f"class {fqcn} exists in {len(group)} places with different content" + ("" if across else " (jar beats loose script inside one mod)"),
                           sorted(_distinct_mods(group)), _sides(group), [fqcn]))
    return out


def rule_save_holds_heavy(facts: list[AFact]) -> list[Finding]:
    return [Finding("ATLAS-SAVE-HOLDS-HEAVY", "REVIEW", CRASH,
                    f"{f.mod}: saved class field {f.id.rsplit('.', 1)[0].rsplit('.', 1)[-1]}.{f.id.rsplit('.', 1)[-1]} ({_where(f)}) "
                    f"holds a heavy campaign object ({f.evidence}); a save cycle through it can crash on load",
                    [f.mod], [_side(f)], [f.id]) for f in facts if f.kind == "saved-field" and f.mod != VANILLA_ID]


def analyze(conn: sqlite3.Connection, mods: list[dict]) -> tuple[list[Finding], dict[str, Profile]]:
    scope = with_vanilla(conn, mods)
    facts = load_facts(conn, scope)
    folders = {m["id"]: m["folder"] for m in scope}
    profiles = {m["id"]: build_profile(m["id"], facts) for m in scope if m["id"] != VANILLA_ID}
    findings = [*rule_shadow_class(facts), *rule_dup_define(facts, folders), *rule_settings_override(facts),
                *rule_rules_clash(facts), *rule_reads_replaced(facts, profiles), *rule_reads_missing(facts),
                *rule_mutate_shared(facts), *rule_pick_priority(facts), *rule_save_holds_heavy(facts)]
    return sorted(findings, key=lambda f: (CATEGORY_ORDER[f.category], LEVEL_ORDER[f.level], f.rule, f.summary)), profiles


# ---------------------------------------------------------------- forecast

def forecast(conn: sqlite3.Connection, subjects: list[dict], against: list[dict] | None = None) -> dict:
    """Run every rule over `subjects` (plus `against`, a family treated as one set) and vanilla. With `against`, keep the
    findings that join a subject to the family, plus single-mod findings about a subject."""
    family = [m for m in (against or []) if m["id"] not in {s["id"] for s in subjects}]
    findings, profiles = analyze(conn, subjects + family)
    names, family_ids = {s["id"] for s in subjects}, {m["id"] for m in family}
    kept = []
    for finding in findings:
        mods = set(finding.mods)
        if len(mods) == 1:
            keep = mods <= names
        elif against is not None:
            keep = bool(mods & names) and bool(mods & family_ids)
        else:
            keep = bool(mods & names)
        if keep:
            kept.append(finding)
    from .atlas_runtime import confirmed_by_runtime, runtime_findings  # lazy: atlas_runtime imports this module

    kept += runtime_findings(conn, subjects)
    confirmed_by_runtime(kept)
    verdicts = {s["id"]: _verdict(conn, s, kept) for s in subjects}
    return {"subjects": [s["id"] for s in subjects], "against": sorted(family_ids), "findings": kept,
            "verdicts": verdicts, "profiles": {m: profiles[m] for m in profiles if m in names}}


def _verdict(conn: sqlite3.Connection, mod: dict, findings: list[Finding]) -> dict:
    mine = [f for f in findings if mod["id"] in f.mods]
    dynamic = conn.execute("SELECT COUNT(*) FROM facts WHERE mod = ? AND version = ? AND id = '<dynamic>'",
                           (mod["id"], mod["version"])).fetchone()[0]
    if any(f.level == "MANUAL" for f in mine):
        status = "NEEDS PATCH (MANUAL findings)"
    elif any(f.level == "REVIEW" for f in mine):
        status = "REVIEW"
    elif any(f.level == "UNKNOWN" for f in mine):
        status = "UNKNOWN (string mentions of ids another mod replaces; no call site found)"
    elif mine:
        status = "no open findings (fixed history only)"
    elif dynamic:
        status = "UNKNOWN (non-literal id lookups the static scan cannot resolve)"
    else:
        status = "no static conflicts found"
    return {"status": status, "findings": len(mine), "dynamic_lookups": dynamic}
