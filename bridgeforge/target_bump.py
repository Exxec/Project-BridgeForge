"""`target-bump`, `target` and `retarget`: a new game build in one run (ROADMAP-3 item 90, 2026-11-15).

`target-bump NEW_CORE` diffs the API against the current target's core, runs `target-impact` over the archive and the
queue (resumable: its checkpoint lives in `targets/<build>/impact/`), merges an optional `finding-stats` result into a
per-mod catalogue (the scratch script of the 0.98.5a move made permanent), records the registry entry and makes the new
build the target. `retarget` then moves every workspace the delta leaves CLEAN to the new build: `gameVersion`, `+bf.N`,
a revival-report section ending READY_FOR_LIVE_TEST and a MOD_CHANGELOG line (`workspace_tools.bump_version`). It
plans by default and writes only with `--apply`. CLEAN is not live proof, which is what that report status says.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .progress import report
from .safeio import atomic_write_bytes, atomic_write_json, atomic_write_text
from .targets import (STATUSES, TargetError, build_dir, core_build, load_target, record_build, registry, set_target,
                      state_dir)

ACTIVE = ("BREAKS", "RELINK", "REVIEW")


def _mod_key(record: dict) -> str:
    """The name finding-stats uses: the workspace or archive folder (`Done/X/X` and `In operation/X/working` -> X)."""
    return Path(record["path"]).parent.name


def catalogue(impact: dict, stats: dict | None = None) -> list[dict]:
    by_name = {m["workspace"]: m for m in (stats or {}).get("mods", [])}
    rows = []
    for record in impact["records"]:
        scanned = by_name.get(_mod_key(record), {})
        rows.append({"mod": record["mod"], "id": record.get("id"), "version": record.get("version"), "path": record["path"],
                     "delta": record["verdict"], "fixers_only": record.get("fixers_only", False), "next": record.get("next", []),
                     "tier": scanned.get("bucket", "unscanned" if stats else "-"), "blocking": scanned.get("blocking", [])})
    return rows


def render_catalogue(build: str, previous: str | None, rows: list[dict], scanned: bool) -> str:
    deltas, tiers = Counter(r["delta"] for r in rows), Counter(r["tier"] for r in rows)
    blockers = Counter(b for r in rows for b in r["blocking"])
    fixable = [r["mod"] for r in rows if r["delta"] in ACTIVE and r["fixers_only"]]
    lines = [f"# Catalogue: {len(rows)} mods against {build}", "",
             f"Version delta from {previous or 'the previous target'} (`target-impact`)"
             + (", plus the full scan on the new core (`finding-stats --scan`)." if scanned else "; no full scan merged."),
             "Nothing here is live-tested on the new build.", "", "## Version delta", "",
             ", ".join(f"{k} {deltas.get(k, 0)}" for k in (*ACTIVE, "CLEAN")), "",
             f"Gated fixers alone clear {len(fixable)} of {sum(deltas.get(k, 0) for k in ACTIVE)} affected mods."]
    if scanned:
        lines += ["", "## Hardest remaining work per mod (full scan)", "", "| Tier | Mods |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in tiers.most_common()]
        lines += ["", "## Most common blockers", "", "| Finding | Mods |", "|---|---|"]
        lines += [f"| `{k}` | {v} |" for k, v in blockers.most_common(20)]
    lines += ["", "## Affected mods", ""]
    for r in rows:
        if r["delta"] in ACTIVE:
            lines.append(f"### {r['mod']}: {r['delta']}" + (" (gated fixers alone clear it)" if r["fixers_only"] else ""))
            lines += [f"- {step}" for step in r["next"]] + [""]
    lines += ["## All mods", "", "| Mod | Delta | Tier | Blocking findings |", "|---|---|---|---|"]
    lines += [f"| {r['mod']} | {r['delta']} | {r['tier']} | {', '.join(r['blocking'][:4])}{' ...' if len(r['blocking']) > 4 else ''} |" for r in rows]
    return "\n".join(lines) + "\n"


def bump(new_core: Path, roots: list[Path], state: Path, *, old_core: Path | None = None, stats: dict | None = None,
         make_target: bool = True, restart: bool = False, progress=None) -> dict:
    from .api_diff import diff_api_jars
    from .target_impact import CHECKPOINT_NAME, render, target_impact

    previous_target = load_target(state)
    if old_core is None:
        if not previous_target:
            raise TargetError("no current target to diff against; pass --from OLD_CORE.")
        old_core = Path(previous_target["core"])
    previous, build = core_build(old_core), core_build(new_core)
    if previous == build:
        raise TargetError(f"{new_core} is the same build as the old core ({build}).")
    record_build(state, old_core)
    out = build_dir(state, build)
    api = diff_api_jars(old_core, new_core)
    atomic_write_json(out / "api-diff.json", api, indent=2, ensure_ascii=False)
    checkpoint = out / "impact" / CHECKPOINT_NAME
    if restart and checkpoint.is_file():
        checkpoint.unlink()
    impact = target_impact(roots, old_core, new_core, checkpoint=checkpoint, progress=progress)
    atomic_write_json(out / "impact" / "TARGET_IMPACT.json", impact, indent=2, ensure_ascii=False)
    atomic_write_text(out / "impact" / "TARGET_IMPACT.md", render(impact))
    if checkpoint.is_file():
        checkpoint.unlink()
    rows = catalogue(impact, stats)
    atomic_write_json(out / "CATALOGUE.json", rows, indent=2, ensure_ascii=False)
    atomic_write_text(out / "CATALOGUE.md", render_catalogue(build, previous, rows, stats is not None))
    entry = record_build(state, new_core, previous=previous)
    if make_target:
        set_target(state, new_core)
    return {"build": build, "previous": previous, "folder": str(out), "verdicts": impact["verdicts"], "target_set": make_target,
            "api": {**api.get("summary", {}), "parameters_renamed": len(api.get("parameters_renamed", []))}, "status": entry["status"]}


def retarget_plan(impact: dict, build: str) -> list[dict]:
    """One row per mod: a CLEAN workspace not yet on `build` is `retarget`; everything else says why it is skipped."""
    from .scan.scanner import _load_lenient_json_file

    rows = []
    for record in impact["records"]:
        folder = Path(record["path"])
        if folder.name != "working":
            rows.append({"mod": record["mod"], "action": "skip", "why": "not a workspace (archives move with `archive --refresh`)"})
            continue
        if record["verdict"] != "CLEAN":
            rows.append({"mod": record["mod"], "action": "skip", "why": f"{record['verdict']}: fix first (target-impact steps)"})
            continue
        info = _load_lenient_json_file(folder / "mod_info.json") or {}
        if info.get("gameVersion") == build:
            rows.append({"mod": record["mod"], "action": "skip", "why": f"already {build}"})
            continue
        rows.append({"mod": record["mod"], "action": "retarget", "workspace": str(folder.parent), "from": info.get("gameVersion")})
    return rows


def apply_retarget(row: dict, build: str, *, changelog: Path | None = None) -> dict:
    from .fixers.mod_info import _fix_mod_info_game_version_inexact
    from .workspace_tools import bump_version

    working = Path(row["workspace"]) / "working"
    change = _fix_mod_info_game_version_inexact(working, {"target_game_version": build})[0]
    atomic_write_bytes(change.path, change.after)
    note = (f"Retargeted to Starsector {build} (gameVersion {row['from']} -> {build}): `target-impact` found no API, "
            f"linkage or data change affecting this mod. Not yet live-tested on {build}.")
    return bump_version(Path(row["workspace"]), note, changelog=changelog)


def add_parser(subcommands) -> None:
    target = subcommands.add_parser("target", help="show, set or export the current target game build (bridgeforge-state/target.json); "
                                                   "`--vanilla-core @target` on any command resolves to its core")
    actions = target.add_subparsers(dest="target_action", required=True)
    actions.add_parser("show", help="the current target and every recorded build")
    set_cmd = actions.add_parser("set", help="make CORE the target (records its build entry)")
    set_cmd.add_argument("core", type=Path, help="a starsector-core folder")
    set_cmd.add_argument("--status", choices=STATUSES, help="registry status (default: keep, else OBSERVED)")
    export = actions.add_parser("export", help="write game-builds.json (the registry the sister repos pin by hash)")
    export.add_argument("--to", type=Path, required=True, help="file to write")

    bump_cmd = subcommands.add_parser("target-bump", help="move to a new game build in one run: api-diff, target-impact, catalogue, "
                                                          "registry entry, then make it the target (resumable)")
    bump_cmd.add_argument("new_core", type=Path, help="starsector-core of the new build")
    bump_cmd.add_argument("roots", type=Path, nargs="*", help="default <repo>/Done and <repo>/In operation")
    bump_cmd.add_argument("--from", dest="old_core", type=Path, help="old core (default: the current target)")
    bump_cmd.add_argument("--stats", type=Path, help="a FINDING_STATS.json from `finding-stats ... --scan --vanilla-core NEW_CORE` to merge")
    bump_cmd.add_argument("--no-set", action="store_true", help="record the build but keep the current target")
    bump_cmd.add_argument("--restart", action="store_true", help="ignore an interrupted run's checkpoint")
    bump_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")

    retarget = subcommands.add_parser("retarget", help="move every workspace the version delta leaves CLEAN to the target build "
                                                       "(gameVersion, +bf.N, report, mod changelog); plans unless --apply")
    retarget.add_argument("--impact", type=Path, help="TARGET_IMPACT.json (default: the target build's, from target-bump)")
    retarget.add_argument("--apply", action="store_true", help="write the changes")
    retarget.add_argument("--json", action="store_true")


def _run_target(args, state: Path) -> int:
    if args.target_action == "set":
        print(json.dumps(set_target(state, args.core, status=args.status), indent=2))
    elif args.target_action == "export":
        atomic_write_json(args.to, registry(state), indent=2)
        print(f"Written: {args.to}", file=sys.stderr)
    else:
        print(json.dumps(registry(state), indent=2))
    return 0


def _run_bump(args, state: Path) -> int:
    from .substitutes import REPO_ROOT

    stats = json.loads(args.stats.read_text(encoding="utf-8")) if args.stats else None

    def progress(done: int, total: int, label: str, record: dict, seconds: float | None) -> None:
        report(done, total, label, record["verdict"], seconds)

    result = bump(args.new_core, args.roots or [REPO_ROOT / "Done", REPO_ROOT / "In operation"], state, old_core=args.old_core,
                  stats=stats, make_target=not args.no_set, restart=args.restart, progress=None if args.quiet else progress)
    print(json.dumps(result, indent=2))
    print(f"Catalogue: {Path(result['folder']) / 'CATALOGUE.md'}. Next: `bridgeforge retarget` (plan), then --apply.", file=sys.stderr)
    return 0


def _run_retarget(args, state: Path) -> int:
    from .fixers.common import FixerError

    target = load_target(state)
    if not target:
        raise TargetError("no target set; run `bridgeforge target set CORE` or `target-bump`.")
    path = args.impact or build_dir(state, target["build"]) / "impact" / "TARGET_IMPACT.json"
    if not path.is_file():
        raise TargetError(f"{path} not found; run `bridgeforge target-bump` first or pass --impact.")
    rows = retarget_plan(json.loads(path.read_text(encoding="utf-8")), target["build"])
    todo = [r for r in rows if r["action"] == "retarget"]
    if args.apply:
        for index, row in enumerate(todo, 1):
            try:
                row["result"] = apply_retarget(row, target["build"])
            except (ValueError, OSError, FixerError) as exc:
                row["action"], row["why"] = "failed", str(exc)
            report(index, len(todo), row["mod"], row.get("result", {}).get("new") or row["why"], None)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['action']:9} {r['mod']}" + (f"  ({r['why']})" if r.get("why") else f"  {r.get('from')} -> {target['build']}"))
        print(f"{len(todo)} to retarget to {target['build']}" + ("" if args.apply else "; nothing written (pass --apply)."))
    return 1 if any(r["action"] == "failed" for r in rows) else 0


def run_cli(args: argparse.Namespace) -> int:
    from .fixers.common import FixerError

    state = state_dir()
    try:
        if args.command == "target":
            return _run_target(args, state)
        if args.command == "target-bump":
            return _run_bump(args, state)
        return _run_retarget(args, state)
    except (TargetError, FixerError, OSError, json.JSONDecodeError) as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
