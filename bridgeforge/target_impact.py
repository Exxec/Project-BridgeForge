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


def mod_impact(folder: Path, old_core: Path, new_core: Path, provider_jars: list[Path]) -> dict:
    """What breaks on `new_core` that did not on `old_core`, for one mod folder."""
    from .linkage import missing_interface_methods, unresolved_references

    info = _mod_info(folder) or {}
    jars = _declared_jars(folder, info)
    linkage, interfaces = [], []
    if jars:
        before = _linkage_keys(unresolved_references(jars, old_core, provider_jars))
        after = _linkage_keys(unresolved_references(jars, new_core, provider_jars))
        linkage = [after[key] for key in sorted(after.keys() - before.keys())]
        old_missing = missing_interface_methods(jars, old_core, provider_jars)
        for entry, methods in sorted(missing_interface_methods(jars, new_core, provider_jars).items()):
            new_only = sorted(set(methods) - set(old_missing.get(entry, [])))
            if new_only:
                interfaces.append({"class": entry, "methods": new_only})
    sources = sorted(_source_hits(folder, new_core) - _source_hits(folder, old_core))
    data = data_hits(folder, old_core, new_core)
    if interfaces or sources or any(not p.get("return_type_only") for p in linkage):
        verdict = "BREAKS"
    elif linkage:
        verdict = "RELINK"
    elif data:
        verdict = "REVIEW"
    else:
        verdict = "CLEAN"
    return {"id": info.get("id"), "version": info.get("version"), "path": str(folder), "verdict": verdict,
            "linkage": linkage, "interfaces": interfaces, "data": data,
            "sources": [{"file": f, "line": line, "call": rule} for f, line, rule in sources]}


def _member(problem: dict) -> str:
    return f"{problem['owner'].replace('/', '.')}.{problem['name']}{problem['descriptor'] if problem['kind'] != 'class' else ''}"


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
    lines += [f"| `{e['member']}` | {len(e['mods'])} | {', '.join(e['mods'][:8])}{' ...' if len(e['mods']) > 8 else ''} |" for e in result["by_member"]]
    lines += ["", "## Mods that break or need a relink", ""]
    for r in result["records"]:
        if r["verdict"] == "CLEAN":
            continue
        lines.append(f"### {r['mod']} ({r['id']} {r['version']}): {r['verdict']}")
        lines += [f"- jar `{p['class']}` calls `{_member(p)}`" + (f" (new core: {', '.join(p['candidates'])})" if p.get("candidates") else "")
                  + (" [return type only]" if p.get("return_type_only") else "") for p in r["linkage"]]
        lines += [f"- jar `{i['class']}` lacks {', '.join('`' + m.replace('/', '.') + '`' for m in i['methods'])}" for i in r["interfaces"]]
        lines += [f"- source `{s['file']}:{s['line']}` uses the old `{s['call']}(...)` (fixer: `rc8-signature-changed` with the new core)" for s in r["sources"]]
        lines += [f"- {d['kind']}: `{d['detail']}`" for d in r.get("data", [])]
        lines.append("")
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
