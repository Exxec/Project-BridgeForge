"""`bridgeforge target-impact OLD_CORE NEW_CORE`: which mods a new game version breaks, and why (2026-11-15).

Starsector 0.98.5a-RC3 arrived after every revival had been validated on 0.98a-RC8. A full `scan` of each mod against
the new core answers "what is wrong with this mod" (minutes per mod: 1054 s for AI-War); this answers the narrower
question a version bump asks: what is wrong on the new core that was not wrong on the old one. Per mod, from the same
deterministic checks the scanner uses, each run against both cores and differenced:

- jar linkage (`linkage.unresolved_references`): game members a jar calls that the new core lacks. A change of return
  type alone is a RELINK (recompile the class, no source change: `patch-jar-class`).
- interface contracts (`linkage.missing_interface_methods`): game interfaces or abstract classes that gained a method a
  mod class does not implement, an AbstractMethodError when the game calls it (RevenantLib's `dl_DroneAPI implements
  ShipAPI`, six methods short on 0.98.5a).
- loose sources (`signature_rewrites.TARGET_RULES`): old call forms the new core dropped and the `rc8-signature-changed`
  fixer rewrites, gated on each core's own API jar.

Read-only on every mod and both cores. Providers for linkage are the jars of each mod's declared dependencies among the
mods found, so a library's classes are not reported as missing. Long-running: one progress line per mod, a resumable
checkpoint (house rule 2026-09-27).
"""
from __future__ import annotations

import argparse
import csv
import re
import json
import sys
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

from .progress import Checkpoint, report
from .scan.scan_json import _load_lenient_json_file

SCHEMA_VERSION = 1
VERDICTS = ("BREAKS", "RELINK", "REVIEW", "CLEAN")
# Listed, but no REVIEW verdict on their own: Ironclads replaces ship_data.csv, wing_data.csv and weapon_data.csv lacking
# 13 to 17 of RC8's columns each (tags, rarity, tech/manufacturer, ...) and was LIVE_VALIDATED on RC8, so the loader reads a
# missing column as blank (2026-11-15). A fixer adding blank columns would change nothing.
# `vanilla-now-provides` is a lead for retiring a workaround (item 91), not a defect.
INFORMATIONAL = {"replace-lacks-new-columns", "vanilla-now-provides"}
CHECKPOINT_NAME = "TARGET_IMPACT.partial.jsonl"
_SKIP_DIRS = {"original", "workspace", "scratch", "reports", "_previous", "disabled_files"}


class TargetImpactError(ValueError):
    """A core or root that does not exist."""


def _mod_info(folder: Path) -> dict | None:
    info = _load_lenient_json_file(folder / "mod_info.json") if (folder / "mod_info.json").is_file() else None
    return info if isinstance(info, dict) else None


def _mod_folder(candidate: Path) -> Path | None:
    """The mod folder a root's child stands for: itself, a workspace's `working/`, or a `Done/<Mod>/<Mod>/` copy."""
    if _mod_info(candidate) is not None:
        return candidate
    if _mod_info(candidate / "working") is not None:
        return candidate / "working"
    for child in sorted(p for p in candidate.iterdir() if p.is_dir() and p.name not in _SKIP_DIRS and not p.name.startswith("_")):
        if _mod_info(child) is not None:
            return child
    return None


def discover_mods(roots: list[Path]) -> list[tuple[str, Path]]:
    """(label, mod folder) for each child of each root that holds a mod; labels are `<root name>/<child name>`."""
    found: list[tuple[str, Path]] = []
    for root in roots:
        root = Path(root).expanduser().resolve()
        if not root.is_dir():
            raise TargetImpactError(f"{root} is not a directory.")
        if _mod_info(root) is not None:
            found.append((root.name, root))
            continue
        for child in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")):
            folder = _mod_folder(child)
            if folder is not None:
                found.append((f"{root.name}/{child.name}", folder))
    return found


def _declared_jars(folder: Path, info: dict) -> list[Path]:
    return [folder / j for j in info.get("jars") or [] if isinstance(j, str) and (folder / j).is_file()]


def _dependency_ids(info: dict) -> list[str]:
    ids = []
    for entry in info.get("dependencies") or []:
        if isinstance(entry, dict) and entry.get("id"):
            ids.append(str(entry["id"]))
    return ids


def _linkage_keys(problems: dict[str, list[dict]]) -> dict[tuple, dict]:
    return {(entry, p["kind"], p["owner"], p["name"], p["descriptor"]): {**p, "class": entry}
            for entry, items in problems.items() for p in items}


def _source_hits(folder: Path, core: Path) -> set[tuple[str, int, str]]:
    from .scan.scan_javatext import _blank_java_comments
    from .signature_rewrites import suspects

    hits = set()
    for source in sorted(folder.rglob("*.java")):
        if "disabled_files" in source.relative_to(folder).parts:
            continue
        try:
            text = _blank_java_comments(source.read_text(encoding="utf-8", errors="replace"), strings=True)
        except OSError:
            continue
        for line, rule, _, _ in suspects(text, core):
            hits.add((source.relative_to(folder).as_posix(), line, rule))
    return hits


_SETTINGS_READ = re.compile(r"getSettings\s*\(\s*\)\s*\.\s*get(?:Float|Int|Integer|Boolean|String|Color|JSONObject|JSONArray|Long|Double)\s*\(\s*\"([\w.]+)\"")


@lru_cache(maxsize=4)
def _core_data(core: str) -> dict:
    """Vanilla rule ids, CSV headers and settings keys of one core, read once per run."""
    root = Path(core) / "data"
    headers = {}
    for path in sorted(root.rglob("*.csv")):
        try:
            with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
                headers[path.relative_to(root.parent).as_posix()] = next(csv.reader(handle), [])
        except OSError:
            continue
    rules: set[str] = set()
    for path in [root / "campaign" / "rules.csv", *sorted((root / "campaign" / "rules").glob("*.csv"))]:
        rules |= _csv_column(path, "id")
    settings = _load_lenient_json_file(root / "config" / "settings.json") if (root / "config" / "settings.json").is_file() else None
    return {"headers": headers, "rules": rules, "settings": set(settings) if isinstance(settings, dict) else set()}


def _csv_column(path: Path, column: str) -> set[str]:
    if not path.is_file():
        return set()
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        return {(row.get(column) or "").strip() for row in csv.DictReader(handle) if (row.get(column) or "").strip()}


def data_hits(folder: Path, old_core: Path, new_core: Path) -> list[dict]:
    """Data a newer core treats differently (REVIEW: not proven to crash): vanilla rule ids the mod overrides that the new
    core removed (the row now adds a rule instead of replacing one), CSVs the mod replaces whole that lack the new core's
    added columns, and settings keys the mod's code reads that the new core removed and the mod does not define."""
    old, new = _core_data(str(old_core)), _core_data(str(new_core))
    hits = []
    removed_rules = old["rules"] - new["rules"]
    for rid in sorted(_csv_column(folder / "data" / "campaign" / "rules.csv", "id") & removed_rules):
        hits.append({"kind": "rule-override-orphaned", "detail": rid})
    info = _mod_info(folder) or {}
    for rel in info.get("replace") or []:
        if not isinstance(rel, str) or not rel.endswith(".csv") or not (folder / rel).is_file():
            continue
        added = [c for c in new["headers"].get(rel, []) if c and c not in old["headers"].get(rel, [])]
        with (folder / rel).open(encoding="utf-8-sig", errors="replace", newline="") as handle:
            mine = next(csv.reader(handle), [])
        lacking = [c for c in added if c not in mine]
        if lacking:
            hits.append({"kind": "replace-lacks-new-columns", "detail": f"{rel}: {', '.join(lacking)}"})
    gone = old["settings"] - new["settings"]
    if gone:
        own = _load_lenient_json_file(folder / "data" / "config" / "settings.json") if (folder / "data" / "config" / "settings.json").is_file() else None
        own_keys = set(own) if isinstance(own, dict) else set()
        read: set[str] = set()
        for source in folder.rglob("*.java"):
            try:
                read |= set(_SETTINGS_READ.findall(source.read_text(encoding="utf-8", errors="replace")))
            except OSError:
                continue
        hits += [{"kind": "settings-key-removed", "detail": key} for key in sorted((read & gone) - own_keys)]
    return hits


def _descriptor_arity(descriptor: str) -> int:
    count, pos = 0, 1
    while descriptor[pos] != ")":
        while descriptor[pos] == "[":
            pos += 1
        pos = descriptor.index(";", pos) + 1 if descriptor[pos] == "L" else pos + 1
        count += 1
    return count


def meaning_hits(folder: Path, old_core: Path, new_core: Path, jars: list[Path]) -> list[dict]:
    """Calls to a game method whose descriptor survived but a parameter was renamed (`api_sources`; 0.98.5a's
    getOfficerSalary boolean, mercenary -> checkIfInPopulatedSystem). Jar references match owner, name and arity; source
    calls match name and arity in a file that names the class. REVIEW: a rename can be cosmetic."""
    from .api_sources import parameter_renames, source_zip_beside
    from .linkage import jar_classes
    from .procgen_args import _arguments

    old_zip, new_zip = source_zip_beside(old_core), source_zip_beside(new_core)
    renames = parameter_renames(str(old_zip), str(new_zip)) if old_zip and new_zip else ()
    if not renames:
        return []
    from .api_sources import render_rename

    hits: list[dict] = []
    refs = set()
    for jar in jars:
        for info in jar_classes(jar).values():
            refs |= {(owner, name, _descriptor_arity(desc)) for kind, owner, name, desc in info.refs if kind == "method" and desc.startswith("(")}
    texts = []
    for source in folder.rglob("*.java"):
        try:
            texts.append((source, source.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    for record in renames:
        owner, simple, arity = record["class"].replace(".", "/"), record["class"].rsplit(".", 1)[-1], len(record["types"])
        found = (owner, record["method"], arity) in refs
        call = re.compile(rf"\b{re.escape(record['method'])}\s*\(")
        for source, text in texts if not found else []:
            if simple not in text:
                continue
            for match in call.finditer(text):
                args = _arguments(text, match.end() - 1)
                if args is not None and len([a for a in args if a.strip()]) == arity:
                    found = True
                    break
            if found:
                break
        if found:
            hits.append({"kind": "parameter-meaning-changed", "detail": render_rename(record)})
    return hits


def mod_impact(folder: Path, old_core: Path, new_core: Path, provider_jars: list[Path]) -> dict:
    """What breaks on `new_core` that did not on `old_core`, for one mod folder."""
    from .linkage import missing_interface_methods, unresolved_references
    from .target_delta import id_collisions, now_provides, touches

    info = _mod_info(folder) or {}
    jars = _declared_jars(folder, info)
    linkage, interfaces, resolved = [], [], []
    if jars:
        before = _linkage_keys(unresolved_references(jars, old_core, provider_jars))
        after = _linkage_keys(unresolved_references(jars, new_core, provider_jars))
        linkage = [after[key] for key in sorted(after.keys() - before.keys())]
        resolved = sorted({_member(before[key]) for key in before.keys() - after.keys()})  # the new core supplies them
        old_missing = missing_interface_methods(jars, old_core, provider_jars)
        for entry, methods in sorted(missing_interface_methods(jars, new_core, provider_jars).items()):
            new_only = sorted(set(methods) - set(old_missing.get(entry, [])))
            if new_only:
                interfaces.append({"class": entry, "methods": new_only})
    sources = sorted(_source_hits(folder, new_core) - _source_hits(folder, old_core))
    data = (data_hits(folder, old_core, new_core) + meaning_hits(folder, old_core, new_core, jars)
            + id_collisions(folder, old_core, new_core) + now_provides(folder, old_core, new_core))
    if interfaces or sources or any(not p.get("return_type_only") for p in linkage):
        verdict = "BREAKS"
    elif linkage:
        verdict = "RELINK"
    elif any(d["kind"] not in INFORMATIONAL for d in data):
        verdict = "REVIEW"
    else:
        verdict = "CLEAN"
    record = {"id": info.get("id"), "version": info.get("version"), "path": str(folder), "verdict": verdict,
              "linkage": linkage, "interfaces": interfaces, "data": data,
              "sources": [{"file": f, "line": line, "call": rule} for f, line, rule in sources],
              "touches": touches(folder, jars, old_core, new_core), "resolved_on_new": resolved}
    record["next"], record["fixers_only"] = worklist(folder, record, new_core) if verdict != "CLEAN" else ([], False)
    return record


def _workspace_for(folder: Path) -> tuple[list[str], Path]:
    """(steps that give the mod a workspace, the mod folder the fix steps act on). A queue workspace acts on its `working/`. A
    `Done/<Mod>/<Mod>` copy is restored first (`restore-from-done` makes `In operation/<Mod>`): `retarget` refuses archives,
    which move with `archive --refresh` after a live run (ROADMAP-3 item 95.13). Any other mod folder is acted on in place."""
    folder = Path(folder)
    if folder.name == "working":
        return [], folder
    if folder.parent.name == folder.name and folder.parent.parent.name == "Done":
        # The queue beside this Done/, named explicitly: restore-from-done's default is the package's own queue (review 2026-11-17).
        queue = folder.parent.parent.parent / "In operation"
        working = queue / folder.name / "working"
        if working.is_dir():  # `archive` copies, so the workspace the archive came from may still be in the queue
            return [f"the queue already holds {working.parent}: the steps below fix it (if it changed since this archive, "
                    "`done-audit` shows the archive STALE)"], working
        return [f'bridgeforge restore-from-done "{folder.parent}" --queue "{queue}"'], working
    return [], folder


def worklist(folder: Path, record: dict, new_core: Path) -> tuple[list[str], bool]:
    """The next steps for one mod, most mechanical first, and whether the gated fixers alone would clear it (ROADMAP-3
    item 89): fixers for dropped call forms in sources and jars and for forwarding classes, `relink` for return-type-only
    changes (recompiles the class from its shipped or decompiled source, unedited; ROADMAP-3 item 95.13), a hand port for
    everything else. An archived mod is restored to a workspace first."""
    from .jar_call_rewrites import matching_rule

    setup, target = _workspace_for(folder)
    fix = 'bridgeforge fix "{folder}" --finding {fid} --vanilla-core "{core}" --apply'
    steps: list[str] = []
    fixers_only = True
    if record["sources"]:
        steps.append(fix.format(folder=target, fid="rc8-signature-changed", core=new_core))
    by_rule = [p for p in record["linkage"] if p["kind"] == "method" and matching_rule(p["owner"], p["name"], p["descriptor"], new_core)]
    if by_rule:
        steps.append(fix.format(folder=target, fid="jar-call-signature-changed", core=new_core))
    relinks = [p for p in record["linkage"] if p.get("return_type_only") and p not in by_rule]
    if relinks:
        if target.name == "working":
            steps.append(f'bridgeforge relink "{target.parent}" --vanilla-core "{new_core}" --apply')
        else:  # `relink` works on a workspace; a loose mod folder needs intake first, or the jar route by hand
            steps.append(f'relink {len(relinks)} call(s): bridgeforge jar-packets, then patch-jar-class --vanilla-core "{new_core}"')
        fixers_only = False
    hand = [p for p in record["linkage"] if p not in by_rule and p not in relinks]
    if hand:
        steps.append("hand port: " + ", ".join(sorted({_member(p) for p in hand}))[:300])
        fixers_only = False
    if record["interfaces"]:
        from .forwarding_methods import missing_forwards
        from .linkage import core_index

        core = core_index(str(Path(new_core).resolve()))
        texts = (s.read_text(encoding="utf-8", errors="replace") for s in folder.rglob("*.java"))
        if any("implements" in text and missing_forwards(text, core) for text in texts):
            steps.append(fix.format(folder=target, fid="forwarding-class-method-missing", core=new_core) + ", then patch-jar-class")
        else:
            steps.append("hand: implement " + ", ".join(m.replace("/", ".") for i in record["interfaces"] for m in i["methods"])[:300])
        fixers_only = False  # the jar is rebuilt from the edited source with patch-jar-class
    for d in record.get("data", []):
        if d["kind"] not in INFORMATIONAL:
            steps.append(f"review {d['kind']}: {d['detail']}")
            fixers_only = False
    return (setup + steps if steps else steps), fixers_only and bool(steps)


def _member(problem: dict) -> str:
    return f"{problem['owner'].replace('/', '.')}.{problem['name']}{problem['descriptor'] if problem['kind'] != 'class' else ''}"


# One Station Augments descriptor named an obfuscated class hundreds of characters long (2026-11-17 catalogue, ROADMAP-3 item
# 95.12(i)): the markdown shortens member names, the JSON keeps them whole.
MEMBER_TEXT_LIMIT = 160


def _short(text: str, limit: int = MEMBER_TEXT_LIMIT) -> str:
    return text if len(text) <= limit else f"{text[:limit - 1]}… ({len(text)} chars)"


def target_impact(roots: list[Path], old_core: Path, new_core: Path, *, checkpoint: Path | None = None, progress=None) -> dict:
    """`progress(done, total, label, record, seconds_or_None)` after each mod."""
    old_core, new_core = Path(old_core).expanduser().resolve(), Path(new_core).expanduser().resolve()
    for core in (old_core, new_core):
        if not (core / "starfarer.api.jar").is_file():
            raise TargetImpactError(f"{core} is not a starsector-core folder (no starfarer.api.jar).")
    mods = discover_mods(roots)
    by_id: dict[str, Path] = {}
    for _, folder in mods:
        mod_id = (_mod_info(folder) or {}).get("id")
        if isinstance(mod_id, str):
            by_id.setdefault(mod_id, folder)
    header = {"checkpoint": SCHEMA_VERSION, "old_core": str(old_core), "new_core": str(new_core),
              "roots": [str(Path(r).expanduser().resolve()) for r in roots]}
    records = []
    with Checkpoint(checkpoint, header) as saved:
        for index, (label, folder) in enumerate(mods, 1):
            started = time.monotonic()
            record = saved.get(label)
            resumed = record is not None
            if record is None:
                info = _mod_info(folder) or {}
                providers = [jar for dep in _dependency_ids(info) if dep in by_id for jar in _declared_jars(by_id[dep], _mod_info(by_id[dep]) or {})]
                record = {"mod": label, **mod_impact(folder, old_core, new_core, providers)}
                saved.add(label, record)
            if progress:
                progress(index, len(mods), label, record, None if resumed else time.monotonic() - started)
            records.append(record)
    verdicts = Counter(r["verdict"] for r in records)
    members: dict[str, set[str]] = {}
    for r in records:
        for p in r["linkage"]:
            members.setdefault(_member(p), set()).add(r["mod"])
        for item in r["interfaces"]:
            for method in item["methods"]:
                members.setdefault(f"implement {method.replace('/', '.')}", set()).add(r["mod"])
        for s in r["sources"]:
            members.setdefault(f"source {s['call']}(...)", set()).add(r["mod"])
        for d in r.get("data", []):
            members.setdefault(f"{d['kind']} {d['detail'].split(':')[0]}", set()).add(r["mod"])
    return {"schema_version": SCHEMA_VERSION, "mode": "TARGET_IMPACT", "old_core": str(old_core), "new_core": str(new_core),
            "mods": len(records), "verdicts": {v: verdicts.get(v, 0) for v in VERDICTS},
            "by_member": sorted(({"member": m, "mods": sorted(names)} for m, names in members.items()), key=lambda e: (-len(e["mods"]), e["member"])),
            "records": records,
            "note": "Only what differs between the two cores. CLEAN means none of these checks changed, not that the mod "
                    "works on the new version: content, settings and behaviour changes need the scan and a live test."}


def render(result: dict) -> str:
    v = result["verdicts"]
    lines = [f"# Target impact: {result['mods']} mods", "", f"Old core: `{result['old_core']}`", f"New core: `{result['new_core']}`", "",
             f"BREAKS {v['BREAKS']}, RELINK {v['RELINK']} (recompile only), REVIEW {v.get('REVIEW', 0)} (data the new core treats differently), CLEAN {v['CLEAN']}", "", result["note"], "",
             "## By game member", "", "| Member | Mods | Which |", "|---|---|---|"]
    lines += [f"| `{_short(e['member'])}` | {len(e['mods'])} | {', '.join(e['mods'][:8])}{' ...' if len(e['mods']) > 8 else ''} |" for e in result["by_member"]]
    lines += ["", "## Mods that break or need a relink", ""]
    for r in result["records"]:
        if r["verdict"] == "CLEAN":
            continue
        lines.append(f"### {r['mod']} ({r['id']} {r['version']}): {r['verdict']}")
        lines += [f"- jar `{p['class']}` calls `{_short(_member(p))}`"
                  + (f" (new core: {', '.join(_short(c) for c in p['candidates'])})" if p.get("candidates") else "")
                  + (" [return type only]" if p.get("return_type_only") else "") for p in r["linkage"]]
        lines += [f"- jar `{i['class']}` lacks {', '.join('`' + _short(m.replace('/', '.')) + '`' for m in i['methods'])}" for i in r["interfaces"]]
        lines += [f"- source `{s['file']}:{s['line']}` uses the old `{s['call']}(...)` (fixer: `rc8-signature-changed` with the new core)" for s in r["sources"]]
        lines += [f"- {d['kind']}: `{d['detail']}`" for d in r.get("data", [])]
        if r.get("resolved_on_new"):
            lines.append(f"- resolves on the new core only: {', '.join('`' + m + '`' for m in r['resolved_on_new'][:6])}")
        if r.get("next"):
            lines.append("- Next" + (" (fixers alone clear it)" if r.get("fixers_only") else "") + ":")
            lines += [f"  {n}. `{step}`" if step.startswith("bridgeforge ") else f"  {n}. {step}" for n, step in enumerate(r["next"], 1)]
        lines.append("")
    plan = [r for r in result["records"] if r["verdict"] != "CLEAN"]
    if plan:
        cleared = [r["mod"] for r in plan if r.get("fixers_only")]
        lines += ["## Worklist", "", f"{len(cleared)} of {len(plan)} mods need only the gated fixers: {', '.join(cleared) or 'none'}.",
                  "The rest need a relink, a hand port or a review (steps above). After fixing, run `target-impact` again; then a "
                  "live run on the new version.", ""]
    return "\n".join(lines) + "\n"


def add_parser(subcommands) -> None:
    command = subcommands.add_parser("target-impact", help="which mods a newer game version breaks: jar linkage, interface contracts and dropped call forms "
                                                           "that fail on NEW_CORE but not OLD_CORE (read-only)")
    command.add_argument("old_core", type=Path, help="starsector-core the mods were validated on (e.g. 0.98a-RC8)")
    command.add_argument("new_core", type=Path, help="starsector-core of the newer version")
    command.add_argument("roots", type=Path, nargs="*", help="Done/ archives, queue folders or single mods; default <repo>/Done and <repo>/In operation")
    command.add_argument("--write", type=Path, help="write TARGET_IMPACT.json and TARGET_IMPACT.md into DIR; a checkpoint there lets an interrupted run resume")
    command.add_argument("--restart", action="store_true", help="with --write: ignore an earlier run's checkpoint")
    command.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    command.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    from .safeio import atomic_write_json, atomic_write_text
    from .substitutes import REPO_ROOT

    roots = args.roots or [REPO_ROOT / "Done", REPO_ROOT / "In operation"]
    checkpoint = args.write / CHECKPOINT_NAME if args.write else None
    if checkpoint and args.restart and checkpoint.is_file():
        checkpoint.unlink()

    def progress(done: int, total: int, label: str, record: dict, seconds: float | None) -> None:
        detail = record["verdict"]
        if record["verdict"] != "CLEAN":
            detail += f" ({len(record['linkage'])} linkage, {len(record['interfaces'])} interface, {len(record['sources'])} source, {len(record.get('data', []))} data)"
        report(done, total, label, detail, seconds)

    try:
        result = target_impact(roots, args.old_core, args.new_core, checkpoint=checkpoint, progress=None if args.quiet else progress)
    except (TargetImpactError, OSError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    if args.write:
        atomic_write_json(args.write / "TARGET_IMPACT.json", result, indent=2, ensure_ascii=False)
        atomic_write_text(args.write / "TARGET_IMPACT.md", render(result))
        if checkpoint and checkpoint.is_file():
            checkpoint.unlink()  # the full result is written
        print(f"Written: {args.write / 'TARGET_IMPACT.md'}", file=sys.stderr)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result), end="")
    return 0
