"""How vanilla migrated its own calls between two game builds (ROADMAP-3 item 91, owner 2026-11-15).

Fractal Softworks moved their own code across every API change, and the API source (`starfarer.api.zip`, beside
`starfarer.api.jar`) of both builds ships with the game. For each changed member (a method `api-diff` lists as removed, or
a same-signature parameter rename), this lists vanilla's call sites in the old and the new source, pairs them by file and
counts what the new code passes in the new argument positions. It then checks each gated fixer rule
(`signature_rewrites.TARGET_RULES`) against that: a rule whose constant vanilla also passes is backed by the game's own
migration; one that differs is not wrong (vanilla often has a real object to hand where a mod passes a neutral default), but
its evidence should say why. Read-only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

from .procgen_args import _arguments
from .zipsafe import read_limited

_COMMENTS = re.compile(r"/\*.*?\*/|//[^\n]*", re.S)


class VanillaMigrationError(Exception):
    pass


def _blank(match: re.Match) -> str:
    return re.sub(r"[^\n]", " ", match.group(0))  # keeps offsets and line numbers


def _sources(zip_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(zip_path) as archive:
        return {info.filename: _COMMENTS.sub(_blank, read_limited(archive, info).decode("utf-8", "replace"))
                for info in archive.infolist() if info.filename.endswith(".java")}


def _pattern(simple_class: str, name: str) -> re.Pattern:
    if name == "<init>":
        return re.compile(rf"\bnew\s+(?:[\w.]+\.)?{re.escape(simple_class)}\s*\(")
    return re.compile(rf"(?<![\w$]){re.escape(name)}\s*\(")


def _is_declaration(text: str, start: int) -> bool:
    before = text[max(0, start - 200):start].rstrip()
    if before.endswith((".", "new")) or re.search(r"\b(?:return|else|throw)$", before):
        return False
    return bool(re.search(r"[\w>\]]$", before))


def call_sites(sources: dict[str, str], simple_class: str, name: str) -> dict[str, list[dict]]:
    """{file: [{"line", "args"}]} for calls (not declarations) of `name` (or `new SimpleClass(`)."""
    pattern, found = _pattern(simple_class, name), {}
    for file, text in sources.items():
        if (simple_class if name == "<init>" else name) not in text:
            continue
        for match in pattern.finditer(text):
            if name != "<init>" and _is_declaration(text, match.start()):
                continue
            args = _arguments(text, match.end() - 1)
            if args is None:
                continue
            args = [] if args == [""] or (len(args) == 1 and not args[0].strip()) else [" ".join(a.split()) for a in args]
            found.setdefault(file, []).append({"line": text.count("\n", 0, match.start()) + 1, "args": args})
    return found


def changed_members(api: dict) -> list[dict]:
    members = []
    for owner, entry in sorted(api.get("changed_classes", {}).items()):
        for removed in entry.get("methods_removed", []):
            members.append({"class": owner, "name": removed["name"], "old": removed["signature"],
                            "new": removed.get("same_name_in_class", []), "kind": "removed"})
    for rename in api.get("parameters_renamed", []):
        members.append({"class": rename["class"], "name": rename["method"], "old": f"{rename['method']}({', '.join(rename['types'])})",
                        "new": [", ".join(f"{r['old']} -> {r['new']}" for r in rename["renamed"])], "kind": "meaning"})
    return members


def _rule_forms(name: str) -> list[dict]:
    from .signature_rewrites import TARGET_RULES

    forms = []
    for rule in TARGET_RULES:
        if rule[0] != name:
            continue
        old_args = [f"a{i}" for i in range(rule[2])]
        forms.append({"old_arity": rule[2], "new_args": [" ".join(a.split()) for a in rule[4](old_args)]})
    return forms


def _summary(member: dict, old_sites: dict, new_sites: dict) -> dict:
    old_arity = {len(c["args"]) for calls in old_sites.values() for c in calls}
    new_calls = [c for calls in new_sites.values() for c in calls]
    passed: dict[int, Counter] = {}
    for call in new_calls:
        if len(call["args"]) not in old_arity:  # the new form: count what goes where the old form had nothing
            for position in range(min(old_arity, default=0), len(call["args"])):
                passed.setdefault(position, Counter())[call["args"][position]] += 1
    rules = []
    for form in _rule_forms(member["name"].replace("<init>", member["class"].rsplit(".", 1)[-1])):
        checks = []
        for position in range(form["old_arity"], len(form["new_args"])):
            ours, theirs = form["new_args"][position], passed.get(position, Counter())
            checks.append({"position": position, "rule_passes": ours, "vanilla_passes": dict(theirs.most_common(5)),
                           "backed": ours in theirs})
        rules.append({"old_arity": form["old_arity"], "checks": checks,
                      "verdict": "BACKED" if checks and all(c["backed"] for c in checks) else ("NO_VANILLA_CALLS" if not passed else "DIFFERS")})
    paired = sorted(old_sites.keys() & new_sites.keys())
    return {**member, "old_sites": sum(map(len, old_sites.values())), "new_sites": len(new_calls),
            "files_changed": [{"file": f, "old": [c["args"] for c in old_sites[f]], "new": [c["args"] for c in new_sites[f]]}
                              for f in paired if [c["args"] for c in old_sites[f]] != [c["args"] for c in new_sites[f]]][:12],
            "new_argument_values": {str(p): dict(c.most_common(8)) for p, c in sorted(passed.items())}, "rules": rules}


def vanilla_migration(old_core: Path, new_core: Path, api: dict | None = None) -> dict:
    from .api_diff import diff_api_jars
    from .api_sources import source_zip_beside

    zips = [source_zip_beside(Path(core)) for core in (old_core, new_core)]
    if not all(zips):
        raise VanillaMigrationError("both cores need starfarer.api.zip (the API source the game ships) beside starfarer.api.jar.")
    api = api or diff_api_jars(old_core, new_core)
    old_src, new_src = _sources(zips[0]), _sources(zips[1])
    results = []
    for member in changed_members(api):
        simple = member["class"].rsplit(".", 1)[-1]
        results.append(_summary(member, call_sites(old_src, simple, member["name"]), call_sites(new_src, simple, member["name"])))
    verdicts = Counter(rule["verdict"] for r in results for rule in r["rules"])
    return {"schema_version": 1, "mode": "VANILLA_MIGRATION", "old_core": str(old_core), "new_core": str(new_core),
            "members": results, "rule_verdicts": dict(verdicts),
            "note": "Call sites found by text in the API source bundles; the obfuscated core is not searched. A DIFFERS rule "
                    "is not wrong by that alone: vanilla often passes a real object where a neutral default keeps old behaviour."}


def render(result: dict) -> str:
    lines = ["# How vanilla migrated its own calls", "", f"Old: `{result['old_core']}`", f"New: `{result['new_core']}`", "",
             "Fixer rules against vanilla's own migration: " + (", ".join(f"{k} {v}" for k, v in sorted(result["rule_verdicts"].items())) or "no rule applies"),
             "", result["note"], ""]
    for m in result["members"]:
        lines.append(f"## `{m['class']}.{m['old']}` ({m['kind']})")
        lines.append(f"Now: {', '.join(m['new']) or 'gone'}. Vanilla call sites: {m['old_sites']} old, {m['new_sites']} new.")
        for position, values in m["new_argument_values"].items():
            lines.append(f"- new argument {position}: " + ", ".join(f"`{v}` x{n}" for v, n in values.items()))
        for rule in m["rules"]:
            lines.append(f"- fixer rule from {rule['old_arity']} argument(s): **{rule['verdict']}** "
                         + "; ".join(f"position {c['position']} passes `{c['rule_passes']}`" for c in rule["checks"]))
        lines += [f"- `{f['file']}`: {f['old']} -> {f['new']}" for f in m["files_changed"][:5]]
        lines.append("")
    return "\n".join(lines) + "\n"


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("vanilla-migration", help="how vanilla's own API source moved across each changed member between two "
                                                              "builds, and whether each gated fixer rule passes what vanilla passes (read-only)")
    command.add_argument("old_core", type=Path, help="older starsector-core (with starfarer.api.zip)")
    command.add_argument("new_core", type=Path, help="newer starsector-core; `@target` works")
    command.add_argument("--write", type=Path, help="write VANILLA_MIGRATION.json and .md into DIR")
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    from .api_diff import ApiDiffError
    from .safeio import atomic_write_json, atomic_write_text

    try:
        result = vanilla_migration(args.old_core, args.new_core)
    except (VanillaMigrationError, ApiDiffError, OSError, zipfile.BadZipFile) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.write:
        atomic_write_json(args.write / "VANILLA_MIGRATION.json", result, indent=2, ensure_ascii=False)
        atomic_write_text(args.write / "VANILLA_MIGRATION.md", render(result))
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result), end="")
    return 0
