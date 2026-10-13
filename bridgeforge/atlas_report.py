"""Mod Atlas output: text, JSON and local self-contained HTML for `atlas show / id / forecast`, plus the CLI entry point.

HTML is plain files with inline CSS and no external URLs (owner decision 2, 2026-10-11: a local file, no web hosting).
"""
from __future__ import annotations

import html
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

from .atlas import (DEFAULT_DB, ORIGINAL_SUFFIX, AtlasError, build_atlas, connect, default_roots, group_mods, latest_mods,
                    original_roots, resolve_mods)
from .atlas_rules import AFact, build_profile, forecast, load_facts

DEFAULT_LIMIT = 25
CSS = ("body{font-family:system-ui,sans-serif;margin:24px auto;max-width:1100px;padding:0 16px;color:#1b1b1b;background:#fff}"
       "table{border-collapse:collapse;width:100%;margin:8px 0 20px}td,th{border:1px solid #ccc;padding:4px 8px;text-align:left;"
       "font-size:13px;vertical-align:top}th{background:#f1f1f1}code{font-size:12px}.MANUAL{color:#a00}.REVIEW{color:#a60}"
       ".UNKNOWN{color:#555}.SAFE{color:#080}")


# ---------------------------------------------------------------- data shapes

def show_data(conn: sqlite3.Connection, mods: list[dict]) -> list[dict]:
    out = []
    for mod in mods:
        facts = load_facts(conn, [mod])
        groups: dict[str, list[dict]] = defaultdict(list)
        for f in facts:
            groups[f"{f.kind} {f.action}"].append({"id": f.id, "at": f.file + (f":{f.line}" if f.line else ""),
                                                   "evidence": f.evidence, "confidence": f.confidence})
        out.append({"mod": mod, "fact_count": len(facts), "groups": dict(sorted(groups.items())),
                    "profile": build_profile(mod["id"], facts).as_dict()})
    return out


def id_data(conn: sqlite3.Connection, ident: str) -> dict:
    rows = conn.execute("SELECT mod, version, kind, action, file, line, evidence, confidence FROM facts WHERE id = ? "
                        "ORDER BY mod, kind, action, file, line", (ident,)).fetchall()
    latest = {m["id"]: m["version"] for m in latest_mods(conn)}
    by_mod: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if latest.get(r["mod"]) == r["version"]:
            by_mod[r["mod"]].append({k: r[k] for k in ("kind", "action", "file", "line", "evidence", "confidence")})
    return {"id": ident, "mods": dict(by_mod)}


def diff_data(conn: sqlite3.Connection, mod: dict) -> dict:
    """Facts only in the working copy, and only in the `+original` copy, of one mod (67c)."""
    originals = [r["version"] for r in conn.execute("SELECT version FROM mods WHERE id = ? AND version LIKE ?",
                                                     (mod["id"], "%" + ORIGINAL_SUFFIX))]
    if not originals:
        raise AtlasError(f"{mod['id']} has no '{ORIGINAL_SUFFIX}' copy indexed; run `atlas build --include-originals`")
    original = {"id": mod["id"], "version": sorted(originals)[0]}

    def keyed(source: dict) -> dict[tuple, AFact]:
        return {(f.kind, f.id, f.action): f for f in load_facts(conn, [source]) if f.id != "<dynamic>"}

    working, before = keyed(mod), keyed(original)

    def rows(only: dict, other: dict) -> list[dict]:
        return [{"kind": k[0], "id": k[1], "action": k[2], "at": _where_of(f), "evidence": f.evidence, "confidence": f.confidence}
                for k, f in sorted(only.items()) if k not in other]

    return {"mod": mod["id"], "working": mod["version"], "original": original["version"],
            "only_working": rows(working, before), "only_original": rows(before, working)}


def _where_of(fact: AFact) -> str:
    return f"{fact.file}:{fact.line}" if fact.line else fact.file


def diff_text(data: dict, limit: int) -> str:
    lines = [f"{data['mod']}: working {data['working']} vs original {data['original']}"]
    for key, title in (("only_working", "only in the working copy (added or fixed)"), ("only_original", "only in the original (removed or changed)")):
        lines.append(f"  {title}: {len(data[key])}")
        lines += [f"    {r['kind']} {r['action']} {r['id']}  {r['at']}  ({r['confidence']})" for r in data[key][:limit]]
        if len(data[key]) > limit:
            lines.append(f"    ... {len(data[key]) - limit} more (raise --limit, or use --json)")
    return "\n".join(lines)


def forecast_data(result: dict) -> dict:
    return {"subjects": result["subjects"], "against": result["against"],
            "verdicts": result["verdicts"], "findings": [f.as_dict() for f in result["findings"]],
            "profiles": {m: p.as_dict() for m, p in result["profiles"].items()}}


# ---------------------------------------------------------------- text

def show_text(data: list[dict], limit: int) -> str:
    lines: list[str] = []
    for entry in data:
        mod = entry["mod"]
        lines.append(f"{mod['name']} ({mod['id']} {mod['version']}) - {entry['fact_count']} fact(s)\n  {mod['path']}")
        for group, items in entry["groups"].items():
            lines.append(f"  [{group}] {len(items)}")
            lines += [f"    {i['id']}  {i['at']}  {i['evidence']}  ({i['confidence']})" for i in items[:limit]]
            if len(items) > limit:
                lines.append(f"    ... {len(items) - limit} more (raise --limit, or use --json)")
        lines.append("  replacement profile:")
        lines += _profile_lines(entry["profile"])
    return "\n".join(lines)


def _profile_lines(profile: dict) -> list[str]:
    lines = [f"    replaces/removes {r['kind']} '{r['id']}' -> {', '.join(r['by']) or 'nothing'} ({r['how']}; {r['at']})"
             for r in profile["replaced"]]
    lines += [f"    overrides {o['kind']} '{o['id']}' ({o['at']})" for o in profile["overrides"][:DEFAULT_LIMIT]]
    lines += [f"    mutates shared '{key}' ({', '.join(where)})" for key, where in profile["mutates"].items()]
    return lines or ["    (none)"]


def id_text(data: dict) -> str:
    if not data["mods"]:
        return f"No indexed mod touches '{data['id']}'."
    lines = [f"'{data['id']}' is touched by {len(data['mods'])} mod(s):"]
    for mod, rows in data["mods"].items():
        lines.append(f"  {mod}")
        lines += [f"    {r['kind']} {r['action']}  {r['file']}{':' + str(r['line']) if r['line'] else ''}  {r['evidence']}  ({r['confidence']})"
                  for r in rows]
    return "\n".join(lines)


def top_pairs(findings: list[dict], top: int) -> list[dict]:
    """Findings grouped by the mods they involve (a pair, or one mod), ranked: crash-class before silent, MANUAL before REVIEW, then by
    how many findings the group holds. SAFE findings (fixed history) are not ranked. A pack forecast has hundreds of findings; this is
    the list to read first."""
    from .atlas_rules import CATEGORY_ORDER, LEVEL_ORDER

    groups: dict[tuple[str, ...], dict] = {}
    for finding in findings:
        if finding["level"] == "SAFE":
            continue
        key = tuple(sorted(finding["mods"]))
        group = groups.setdefault(key, {"mods": list(key), "count": 0, "category": finding["category"], "level": finding["level"],
                                        "rules": set(), "example": finding["summary"]})
        group["count"] += 1
        group["rules"].add(finding["rule"])
        worse = (CATEGORY_ORDER[finding["category"]], LEVEL_ORDER[finding["level"]]) < (CATEGORY_ORDER[group["category"]], LEVEL_ORDER[group["level"]])
        if worse:
            group["category"], group["level"], group["example"] = finding["category"], finding["level"], finding["summary"]
    ranked = sorted(groups.values(), key=lambda g: (CATEGORY_ORDER[g["category"]], LEVEL_ORDER[g["level"]], -g["count"], g["mods"]))
    return [{**g, "rules": sorted(g["rules"])} for g in ranked[:top]]


def forecast_text(data: dict) -> str:
    many = len(data["subjects"]) > 12  # a modpack: name the count, list only the mods with something to say
    names = f"{len(data['subjects'])} mod(s)" if many else ", ".join(data["subjects"])
    lines = [f"Forecast for {names}" + (f" against {len(data['against'])} mod(s): {', '.join(data['against'])}" if data["against"] else "")]
    for mod, verdict in data["verdicts"].items():
        if many and not verdict["findings"]:
            continue
        lines.append(f"  {mod}: {verdict['status']} ({verdict['findings']} finding(s))")
    if many:
        clean = sum(1 for v in data["verdicts"].values() if not v["findings"])
        lines.append(f"  ({clean} mod(s) with no static finding not listed)")
    if data.get("pack_missing"):
        lines.append(f"  not in the atlas, not checked: {len(data['pack_missing'])} mod id(s)")
    if data.get("top_pairs"):
        lines.append(f"\nHighest-impact groups ({len(data['top_pairs'])} shown of {len(data['findings'])} finding(s); --top N, or --json for everything):")
        for pair in data["top_pairs"]:
            lines.append(f"  {' + '.join(pair['mods'])}: {pair['count']} finding(s), worst {pair['category']} {pair['level']} [{', '.join(pair['rules'])}]")
            lines.append(f"      e.g. {pair['example'][:170]}")
        return "\n".join(lines)
    for finding in data["findings"]:
        lines.append(f"\n[{finding['level']}] {finding['rule']} ({finding['category']}): {finding['summary']}")
        for side in finding["sides"]:
            where = side["file"] + (f":{side['line']}" if side["line"] else "")
            lines.append(f"    {side['mod']}: {side['kind']} {side['action']} {side['id']} at {where} - {side['evidence']} ({side['confidence']})")
    if not data["findings"]:
        lines.append("\nNo findings.")
    return "\n".join(lines)


# ---------------------------------------------------------------- html

def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><tr>{head}</tr>{body}</table>"


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><h1>{html.escape(title)}</h1>{body}</body></html>")


def show_html(entry: dict) -> str:
    esc = html.escape
    body = f"<p><code>{esc(entry['mod']['path'])}</code> - {entry['fact_count']} fact(s)</p><h2>Replacement profile</h2><pre>{esc(chr(10).join(_profile_lines(entry['profile'])))}</pre>"
    for group, items in entry["groups"].items():
        rows = [[esc(i["id"]), esc(i["at"]), esc(i["evidence"]), f"<span class=\"{i['confidence']}\">{i['confidence']}</span>"] for i in items]
        body += f"<h2>{esc(group)} ({len(items)})</h2>" + _table(["id", "at", "evidence", "confidence"], rows)
    return _page(f"{entry['mod']['name']} {entry['mod']['version']}", body)


def id_html(data: dict) -> str:
    rows = [[html.escape(mod), html.escape(r["kind"]), html.escape(r["action"]), html.escape(r["file"] + (f":{r['line']}" if r["line"] else "")),
             html.escape(r["evidence"]), r["confidence"]] for mod, items in data["mods"].items() for r in items]
    return _page(f"Id {data['id']}", _table(["mod", "kind", "action", "at", "evidence", "confidence"], rows))


def forecast_html(data: dict) -> str:
    esc = html.escape
    body = _table(["mod", "verdict", "findings"], [[esc(m), esc(v["status"]), str(v["findings"])] for m, v in data["verdicts"].items()])
    for f in data["findings"]:
        rows = [[esc(s["mod"]), esc(f"{s['kind']} {s['action']} {s['id']}"), esc(s["file"] + (f":{s['line']}" if s["line"] else "")), esc(s["evidence"])]
                for s in f["sides"]]
        body += (f"<h3><span class=\"{f['level']}\">{f['level']}</span> {esc(f['rule'])} <small>({esc(f['category'])})</small></h3>"
                 f"<p>{esc(f['summary'])}</p>" + _table(["mod", "fact", "at", "evidence"], rows))
    return _page("Atlas forecast: " + ", ".join(data["subjects"]), body or "<p>No findings.</p>")


def write_html(folder: Path, name: str, content: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (re.sub(r"[^A-Za-z0-9._-]+", "_", name) + ".html")
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------- CLI

def _emit(args, data, text: str) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if args.json else text)


def run_cli(args) -> int:
    conn = None
    try:
        if args.atlas_command in ("outcome", "precision"):
            from . import atlas_predictions as predictions

            if args.atlas_command == "outcome":
                entry = predictions.record(args.rule, args.mod, args.ident, args.outcome, args.run, args.note, other=args.other)
                print(f"Recorded: {entry['rule']} {entry['mod']}/{entry['id']} {entry['outcome']} by {entry['run']}")
                return 0
            table = predictions.precision(predictions.load())
            if args.json:
                print(json.dumps(table, indent=2))
            else:
                for rule, row in sorted(table.items()):
                    rate = "no decided cases" if row["hit_rate"] is None else f"{row['hit_rate']:.0%} held"
                    print(f"  {rule}: {row['confirmed']} confirmed, {row['refuted']} refuted, {row['inconclusive']} inconclusive ({rate})")
                if not table:
                    print("No outcomes recorded yet (atlas outcome ...).")
            return 0
        if args.atlas_command == "build":
            base = args.base or Path.cwd()
            roots = args.roots or default_roots(base)
            originals = original_roots(base) if args.include_originals else []
            stats = build_atlas([Path(r) for r in roots], args.db, args.quiet, originals)
            _emit(args, stats, "Atlas built: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
            return 0
        conn = connect(args.db)
        if args.atlas_command == "show":
            data = show_data(conn, resolve_mods(conn, [args.mod]))
            _emit(args, data, show_text(data, args.limit))
            if args.html:
                for entry in data:
                    print("wrote", write_html(args.html, "mod_" + entry["mod"]["id"], show_html(entry)), file=sys.stderr)
        elif args.atlas_command == "diff":
            data = [diff_data(conn, mod) for mod in resolve_mods(conn, [args.mod])]
            _emit(args, data, "\n".join(diff_text(d, args.limit) for d in data))
        elif args.atlas_command == "id":
            data = id_data(conn, args.id)
            _emit(args, data, id_text(data))
            if args.html:
                print("wrote", write_html(args.html, "id_" + args.id, id_html(data)), file=sys.stderr)
        elif args.atlas_command == "runtime":
            from .atlas_runtime import ingest

            stats = ingest(conn, args.logs)
            _emit(args, stats, f"Read {stats['lines']} probe line(s) from {stats['logs']} log(s): {', '.join(stats['tests'])}")
        elif args.atlas_command == "sweep":
            from .atlas_sweep import sweep, sweep_text
            checkpoint = args.db.with_name(f"sweep-{args.group}.partial.jsonl")
            data = sweep(conn, args.group, checkpoint, args.quiet, args.limit)
            _emit(args, data, sweep_text(data))
        else:
            if args.pack:
                from .atlas_sweep import read_pack

                subjects, missing = read_pack(conn, args.pack)
                if not subjects:
                    raise AtlasError(f"none of the pack's mods is indexed ({len(missing)} id(s) missing)")
                if missing:
                    print(f"bridgeforge: {len(missing)} of the pack's mod id(s) are not in the atlas and were not checked: "
                          + ", ".join(missing[:25]) + (" ..." if len(missing) > 25 else ""), file=sys.stderr)
            elif args.mods:
                subjects, missing = resolve_mods(conn, args.mods), []
            else:
                raise AtlasError("forecast needs mod names or --pack FILE")
            against = group_mods(conn, args.against) if args.against else None
            if args.against and not against:
                raise AtlasError(f"no indexed mod belongs to group {args.against!r}")
            from .atlas_predictions import load as load_predictions

            data = forecast_data(forecast(conn, subjects, against, predictions=load_predictions()))
            data["pack_missing"] = missing
            if args.pack or len(subjects) > 12:  # a pack: rank the findings instead of listing hundreds
                data["top_pairs"] = top_pairs(data["findings"], args.top)
            _emit(args, data, forecast_text(data))
            if args.html:
                print("wrote", write_html(args.html, "forecast_" + "_".join(data["subjects"]), forecast_html(data)), file=sys.stderr)
        return 0
    except AtlasError as exc:
        print(f"bridgeforge: {exc}", file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()


def add_parser(subcommands) -> None:
    atlas = subcommands.add_parser("atlas", help="Mod Atlas: index what every mod defines, reads, mutates and hooks, then forecast conflicts between mods (docs/MOD_ATLAS_PLAN.md)")
    sub = atlas.add_subparsers(dest="atlas_command", required=True)
    build = sub.add_parser("build", help="index mod folders into a SQLite atlas (default roots: Done/, In operation/*/working, the rig's mods and its vanilla starsector-core); a mod is re-read only when its files change")
    build.add_argument("roots", nargs="*", type=Path, help="folders holding mods (a folder with mod_info.json is a mod; a starsector-core folder is indexed as 'vanilla')")
    build.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    build.add_argument("--include-originals", action="store_true", help="also index each `In operation/*/original/` copy as version '<v>+original', so `atlas diff MOD` can compare before and after")
    build.add_argument("--base", type=Path, help="project folder holding Done/ and In operation/ (default: the current folder)")
    build.add_argument("--json", action="store_true")
    diff = sub.add_parser("diff", help="facts only in a mod's working copy and facts only in its '+original' copy (needs `atlas build --include-originals`)")
    diff.add_argument("mod", help="mod id, name, folder, acronym or part of one")
    diff.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="facts shown per side (text only)")
    diff.add_argument("--json", action="store_true")
    show = sub.add_parser("show", help="everything one mod adds, changes, reads and hooks, plus its replacement profile")
    show.add_argument("mod", help="mod id, name, folder, acronym (DNEEP) or part of one")
    show.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="facts shown per kind/action group (text only)")
    ident = sub.add_parser("id", help="every mod that touches an id, and how")
    ident.add_argument("id")
    fore = sub.add_parser("forecast", help="run every conflict rule over these mods plus vanilla; --against GROUP checks them against a whole mod family (aotd)")
    fore.add_argument("mods", nargs="*", metavar="MOD")
    fore.add_argument("--against", metavar="GROUP", help="a family treated as one set, e.g. aotd (id starts with aotd or name says Ashes of the Domain)")
    fore.add_argument("--pack", type=Path, metavar="FILE", help="an enabled_mods.json (or a list of mod ids): forecast the whole pack as one load set; ids the atlas does not hold are listed")
    fore.add_argument("--top", type=int, default=15, help="with --pack: how many highest-impact mod groups to show (default 15)")
    outcome = sub.add_parser("outcome", help="record what a live run showed about a forecast finding (confirmed, refuted, inconclusive) in docs/atlas_predictions.json; needs the run id and a note")
    outcome.add_argument("rule", help="e.g. ATLAS-READS-REPLACED")
    outcome.add_argument("--mod", required=True, help="the mod the finding is about")
    outcome.add_argument("--other", help="the other mod involved, when the finding names two")
    outcome.add_argument("--id", required=True, dest="ident", help="the content id the finding names (an industry, condition, class ...)")
    outcome.add_argument("--outcome", required=True, choices=("confirmed", "refuted", "inconclusive"))
    outcome.add_argument("--run", required=True, help="the live test id that showed it")
    outcome.add_argument("--note", required=True, help="what was seen")
    precision = sub.add_parser("precision", help="how often each rule's predictions held when they were live-tested (docs/atlas_predictions.json)")
    precision.add_argument("--json", action="store_true")
    runtime = sub.add_parser("runtime", help="read probe-group test logs (BF-PROBE lines) into the atlas: live market-supply FAILs then show in forecasts as ATLAS-RUNTIME-SUPPLY and confirm static findings")
    runtime.add_argument("logs", nargs="+", type=Path, help="<rig>/logs/<TESTID>.stdout.log files")
    runtime.add_argument("--json", action="store_true")
    sweeper = sub.add_parser("sweep", help="forecast every indexed mod against a family (aotd) one by one; one progress line per mod and a checkpoint")
    sweeper.add_argument("group", nargs="?", default="aotd", help="the family (default aotd)")
    sweeper.add_argument("--limit", type=int, help="only the first N mods")
    sweeper.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    sweeper.add_argument("--json", action="store_true")
    for command in (show, ident, fore):
        command.add_argument("--json", action="store_true")
        command.add_argument("--html", type=Path, metavar="DIR", help="also write plain self-contained HTML files into DIR")
    for command in (build, show, diff, ident, fore, runtime, sweeper):  # outcome and precision read the ledger, not the atlas
        command.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"atlas file (default: {DEFAULT_DB.as_posix()})")
