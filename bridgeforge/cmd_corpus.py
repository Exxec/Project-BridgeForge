"""Corpus-index, content-diff, dependency and vendoring commands (ROADMAP 70 H2.1)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def add_parser(subcommands) -> None:
    corpus_recheck_cmd = subcommands.add_parser("corpus-recheck", help="re-scan every mod with real revival work recorded (ROADMAP P14 item 32): finding counts, compile signal and declared status in one roll-up")
    corpus_recheck_cmd.add_argument("--repo-root", type=Path, default=Path("."), help="repo root holding In operation/ (default: cwd)")
    corpus_recheck_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core; without it, most checks return UNKNOWN and no compile signal is produced")
    corpus_recheck_cmd.add_argument("--write-markdown", type=Path, help="also write a roll-up table to this path")
    corpus_recheck_cmd.add_argument("--include-intake", action="store_true", help="also include mods with a working/ copy but no REVIVAL_REPORT.md yet (ROADMAP P14 item 8: the Ironclads intake queue)")
    corpus_recheck_cmd.add_argument("--restart", action="store_true", help="ignore an interrupted run's In operation/CORPUS_RECHECK.partial.jsonl and rescan everything")
    corpus_recheck_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    corpus_recheck_cmd.add_argument("--json", action="store_true")
    sibling_cmd = subcommands.add_parser("sibling-assets", help="fill missing sprites and description rows from sibling mods of the same pack, only when every copy is byte-identical (ROADMAP 60c); dry run unless --apply; copies are recorded for audit-explain --auto")
    sibling_cmd.add_argument("workspace", type=Path, help="a workspace folder (In operation/<Mod>)")
    sibling_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so vanilla files are not reported missing")
    sibling_cmd.add_argument("--siblings", type=Path, nargs="*", help="mod roots to search instead of the other workspaces beside this one")
    sibling_cmd.add_argument("--apply", action="store_true", help="write the copies (default: report only)")
    sibling_cmd.add_argument("--json", action="store_true")
    corpus_index_cmd = subcommands.add_parser("corpus-index", help="index a large mod archive once (inside .zip files too) and search it like grep in milliseconds; reports what it could not read so \"no hits\" means something")
    corpus_index_sub = corpus_index_cmd.add_subparsers(dest="corpus_index_command", required=True)
    corpus_build_cmd = corpus_index_sub.add_parser("build", help="index (or refresh) every file under ROOT; unchanged files are skipped on re-runs")
    corpus_build_cmd.add_argument("root", type=Path, help="folder to index, e.g. Downloads")
    corpus_build_cmd.add_argument("--db", type=Path, default=Path("bridgeforge-state") / "corpus-index.sqlite", help="index file (default: bridgeforge-state/corpus-index.sqlite)")
    corpus_build_cmd.add_argument("--max-bytes", type=int, default=4 * 1024 * 1024, help="skip (and report) text files larger than this")
    corpus_build_cmd.add_argument("--quiet", action="store_true", help="no per-file progress lines on stderr")
    corpus_build_cmd.add_argument("--json", action="store_true")
    corpus_search_cmd = corpus_index_sub.add_parser("search", help="find files whose content (3+ characters, case-insensitive) or path contains TEXT")
    corpus_search_cmd.add_argument("text")
    corpus_search_cmd.add_argument("--db", type=Path, default=Path("bridgeforge-state") / "corpus-index.sqlite")
    corpus_search_cmd.add_argument("--names", action="store_true", help="match file paths only")
    corpus_search_cmd.add_argument("--limit", type=int, default=50)
    corpus_search_cmd.add_argument("--json", action="store_true")
    content_diff_cmd = subcommands.add_parser("content-diff", help="list hull/variant/weapon/wing/hullmod/shipsystem ids an older install defined that RC8 no longer does, with same-named RC8 candidates; feed the catalogue to `scan --removed-content`")
    content_diff_cmd.add_argument("reference_core", type=Path, help="starsector-core of the older install (read-only)")
    content_diff_cmd.add_argument("vanilla_core", type=Path, help="RC8 starsector-core (read-only)")
    content_diff_cmd.add_argument("--output", type=Path, help="write the JSON catalogue here")
    content_diff_cmd.add_argument("--json", action="store_true")
    verify_shadow_cmd = subcommands.add_parser("verify-shadow", help="does a jar set really compile the class a loose script defines? Parses class files (never a path check); use before dropping or editing a script as 'jar-shadowed'")
    verify_shadow_cmd.add_argument("scripts", type=Path, nargs="+", help="loose .java file(s)")
    verify_shadow_cmd.add_argument("--against", type=Path, action="append", required=True, help="a jar, a mod folder (its declared jars) or any folder (every jar under it, e.g. starsector-core); repeatable")
    verify_shadow_cmd.add_argument("--json", action="store_true")
    diff_data_cmd = subcommands.add_parser("diff-data", help="compare two Starsector data files (JSON dialect or CSV) by value: key/row/column order, comments and formatting never count; exit 1 when they differ")
    diff_data_cmd.add_argument("a", type=Path, help="first file (e.g. the mod's copy)")
    diff_data_cmd.add_argument("b", type=Path, help="second file (e.g. vanilla's or a reference install's)")
    diff_data_cmd.add_argument("--json", action="store_true")
    rebuild_ref_cmd = subcommands.add_parser("rebuild-from-reference", help="port a mod's edited copies of vanilla files (.ship/.wpn/.variant/.skin/.system) to RC8: three-way merge of the reference install's vanilla file, the mod's copy and RC8's file; RC8's changes kept, only the mod's edits applied, overlaps reported as conflicts")
    rebuild_ref_cmd.add_argument("mod", type=Path, help="mod folder (holding data/)")
    rebuild_ref_cmd.add_argument("--reference-core", type=Path, required=True, help="starsector-core of the install the mod was made for (read-only)")
    rebuild_ref_cmd.add_argument("--vanilla-core", type=Path, required=True, help="RC8 starsector-core (read-only)")
    rebuild_ref_cmd.add_argument("--class", dest="file_classes", action="append", help="limit to one file class, e.g. --class wpn; repeatable (default: all), so a large mod can be rebuilt in reviewable stages")
    rebuild_ref_cmd.add_argument("--output", type=Path, help="write MERGED files here, mirroring data/ paths (never into the mod or either core)")
    rebuild_ref_cmd.add_argument("--json", action="store_true")
    subs_cmd = subcommands.add_parser("dependency-substitutes", help="rank visible mods that could replace a missing or discontinued dependency (EXACT / PARTIAL / NONE) and recommend SWAP, REVIVE_DEPENDENCY, STRIP_FROM_MOD or ESCALATE")
    subs_cmd.add_argument("mod", type=Path, help="mod working copy")
    subs_cmd.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search; repeatable (default: <repo>/In operation and its rig's mods)")
    subs_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so vanilla content isn't counted as missing")
    subs_cmd.add_argument("--policy", type=Path, help="licence policy JSON (default: bundled release_policy.json); flags a REVIVE_DEPENDENCY recommendation as local-only when its licence doesn't allow redistribution")
    subs_cmd.add_argument("--write", action="store_true", help="also record the result in <workspace>/reports/dependencies.json, which `board` shows")
    subs_cmd.add_argument("--provider-index", type=Path, help="saved `provider-index build` output: also consider mods it lists that are not visible live")
    provider_index_cmd = subcommands.add_parser("provider-index", help="save what every visible mod defines (hull mods, weapons, wings, hulls, classes, with game and mod version) as a corpus artefact, so provider lookups work without the mods installed")
    provider_index_sub = provider_index_cmd.add_subparsers(dest="provider_index_command", required=True)
    provider_index_build = provider_index_sub.add_parser("build", help="index the --providers folders")
    provider_index_build.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree; repeatable (default: <repo>/In operation and its rig's mods)")
    provider_index_build.add_argument("--output", type=Path, default=Path("bridgeforge-state") / "provider-index.json")
    graph_cmd = subcommands.add_parser("dependency-graph", help="across every queued workspace, which non-current mods need reviving and how many queued mods each would unblock (revival order)")
    graph_cmd.add_argument("--queue", type=Path, help="folder of workspaces (<name>/working); default <repo>/In operation")
    graph_cmd.add_argument("--providers", type=Path, action="append", default=[], help="as for dependency-substitutes; repeatable")
    graph_cmd.add_argument("--vanilla-core", type=Path)
    graph_cmd.add_argument("--provider-index", type=Path)
    graph_cmd.add_argument("--write", action="store_true", help="write <queue>/DEPENDENCY_GRAPH.json and .md, and each mod's reports/dependencies.json, all of which `board` shows")
    graph_cmd.add_argument("--restart", action="store_true", help="with --write: ignore an earlier interrupted run's <queue>/DEPENDENCY_GRAPH.partial.jsonl")
    graph_cmd.add_argument("--quiet", action="store_true", help="no per-mod progress lines on stderr")
    graph_cmd.add_argument("--json", action="store_true")
    subs_cmd.add_argument("--json", action="store_true")
    stats_cmd = subcommands.add_parser("finding-stats", help="count findings across workspaces by automation tier: how many mods could be revived unattended, and which finding ids to automate next (roadmap P15 item 1)")
    stats_cmd.add_argument("roots", type=Path, nargs="*", help="queue folders or single workspaces; default <repo>/In operation")
    stats_cmd.add_argument("--scan", action="store_true", help="scan each <ws>/working afresh instead of reading its latest stored scan")
    stats_cmd.add_argument("--rescan-stale", action="store_true", help="scan afresh only the workspaces whose stored scan is stale (a fixer backup, the escalation ledger, an explain record or the Done/ archive note is newer); keep the stored result for the rest")
    stats_cmd.add_argument("--done", type=Path, help="the Done/ folder whose ARCHIVE_NOTE.md files count for staleness (default <repo>/Done)")
    stats_cmd.add_argument("--vanilla-core", type=Path, help="with --scan or --rescan-stale: also compile-check loose scripts")
    stats_cmd.add_argument("--write", type=Path, metavar="DIR", help="write FINDING_STATS.json and FINDING_STATS.md into DIR; with --scan, each workspace's result is also appended to DIR/FINDING_STATS.partial.jsonl as it finishes, so an interrupted run resumes")
    stats_cmd.add_argument("--restart", action="store_true", help="with --write: ignore an earlier run's FINDING_STATS.partial.jsonl and scan everything again")
    stats_cmd.add_argument("--promotion", type=Path, metavar="DIR", help="also write DIR/PROMOTION_CANDIDATES.md: for each id in the 'write a fixer' list, the verified agent edits grouped by shape, with a before/after example (roadmap item 73 A4)")
    stats_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    stats_cmd.add_argument("--json", action="store_true")
    sup_cmd = subcommands.add_parser("supersession", help="find queued mods whose author has released a newer version (in the real install's mods/ or a modpack); read-only")
    sup_cmd.add_argument("queue", type=Path, help="the queue folder (In operation)")
    sup_cmd.add_argument("--against", type=Path, action="append", default=[], metavar="DIR", help="a folder of mods to compare with; repeatable")
    sup_cmd.add_argument("--corpus-index", type=Path, help="also compare with every mod_info.json a corpus-index database lists (the Downloads archive)")
    sup_cmd.add_argument("--quiet", action="store_true", help="no per-workspace progress lines on stderr")
    sup_cmd.add_argument("--json", action="store_true")
    vendor_copy_cmd = subcommands.add_parser("vendor-copy", help="copy a piece of a provider mod into another mod instead of reviving or depending on the whole provider (ROADMAP P14 item 4): one hullmod by id, or with --plan everything a vendor-plan lists (P15 item 7)")
    vendor_copy_cmd.add_argument("kind", nargs="?", choices=["hullmod"], help="only 'hullmod' is supported without --plan (see the command's own help for why)")
    vendor_copy_cmd.add_argument("id", nargs="?", help="the hullmod id to vendor")
    vendor_copy_cmd.add_argument("from_provider", nargs="?", type=Path, help="the mod folder to copy from")
    vendor_copy_cmd.add_argument("to_mod", nargs="?", type=Path, help="the mod folder to copy into")
    vendor_copy_cmd.add_argument("--plan", type=Path, help="a `vendor-plan --json` file: copy its whole closure (files and CSV rows), re-checked against the provider; any kind vendor-plan traces")
    vendor_copy_cmd.add_argument("--to", type=Path, help="with --plan: the mod folder or workspace to copy into")
    vendor_copy_cmd.add_argument("--allow-partial", action="store_true", help="with --plan: copy even though the plan has MISSING/SUSPECT entries or compiled-only classes (they are reported, not copied)")
    vendor_copy_cmd.add_argument("--policy", type=Path, help="licence policy JSON (default: bundled release_policy.json)")
    vendor_copy_cmd.add_argument("--apply", action="store_true", help="actually write the files (default: dry-run plan only)")
    vendor_copy_cmd.add_argument("--json", action="store_true")
    vendor_cmd = subcommands.add_parser("vendor-plan", help="trace the closure of one piece of an abandoned mod (hull mod, weapon, wing, hull, variant, ship system) for folding into RevenantLib: files to include, SUSPECT files that mention it but nothing references, what is missing, licence; copies nothing")
    vendor_cmd.add_argument("provider", type=Path, help="the mod that defines the piece (mod folder or workspace)")
    vendor_cmd.add_argument("--id", dest="ids", action="append", required=True, help="kind:id, e.g. hullmod:shields_formshield; repeatable")
    vendor_cmd.add_argument("--target", type=Path, help="RevenantLib folder or workspace, to report ids it already has and file collisions (default: <repo>/In operation/RevenantLib when present)")
    vendor_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core, so references vanilla provides are not traced")
    vendor_cmd.add_argument("--json", action="store_true")
    revival_report_draft_cmd = subcommands.add_parser("revival-report-draft", help="draft REVIVAL_REPORT.md/REVIVAL_PLAN.md from real scan+compile evidence for a mod with 0 MANUAL findings and a clean compile (ROADMAP P14 item 35); refuses otherwise")
    revival_report_draft_cmd.add_argument("mod", type=Path, help="mod working copy")
    revival_report_draft_cmd.add_argument("--vanilla-core", type=Path, help="read-only starsector-core; required to establish a compile signal")
    revival_report_draft_cmd.add_argument("--providers", type=Path, action="append", default=[], help="mods folder, mod folder or In operation tree to search for a declared dependency; repeatable")
    revival_report_draft_cmd.add_argument("--apply", action="store_true", help="write reports/REVIVAL_REPORT.md and REVIVAL_PLAN.md (default: print the draft only)")
    revival_report_draft_cmd.add_argument("--force", action="store_true", help="with --apply, overwrite an existing report/plan")
    revival_report_draft_cmd.add_argument("--json", action="store_true")


def run_cli(args: argparse.Namespace) -> int:
    if args.command == "dependency-substitutes":
        from .substitutes import REPO_ROOT, dependency_substitutes
        roots = args.providers or [REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods"]
        result = dependency_substitutes(args.mod, roots, vanilla_core=args.vanilla_core, policy_path=args.policy, index_path=args.provider_index)
        if args.write:
            from .substitutes import write_dependency_report
            try:
                print(f"Recorded: {write_dependency_report(result, args.mod)}", file=sys.stderr)
            except ValueError as exc:
                print(f"bridgeforge: {exc}", file=sys.stderr)
                return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print(f"{result['mod_id']}: {result['strategy']} ({result['providers_indexed']} mods searched)")
        print(f"  {result['reason']}")
        for kind, ids in result["needed"].items():
            print(f"  needs {kind}: {', '.join(ids[:8])}{' ...' if len(ids) > 8 else ''}")
        if result["declared_dependencies_missing"]:
            print(f"  declared but not found: {', '.join(result['declared_dependencies_missing'])}")
        if result.get("total_conversions_excluded"):
            print(f"  not usable as providers (total conversions): {', '.join(result['total_conversions_excluded'])}")
        for item in result["provider_set"]:
            state = item.get("workspace")
            where = f"; workspace {state['workspace']}: {state['status'] or 'no revival report'}, {state['manual_findings'] if state['manual_findings'] is not None else '?'} MANUAL" if state else ""
            print(f"  provides {', '.join(item['covers'])}: {item['name']} ({item['game_version'] or 'no version'}{where})")
        if result["uncovered"]:
            print(f"  in no visible mod: {', '.join(result['uncovered'])}")
        for entry in result["successors"]:
            print(f"  known successor for {entry['match']}: {entry['successor']} [{entry.get('evidence', '')}]")
        for note in result.get("licence_notes") or []:
            print(f"  LICENCE: {note}")
        return 0
    if args.command == "provider-index":
        from .substitutes import REPO_ROOT, provider_index, save_provider_index
        roots = args.providers or [REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods"]
        summary = save_provider_index(provider_index(roots), args.output, roots)
        print(f"Provider index: {summary['providers']} mods, {summary['ids']} ids -> {summary['output']}")
        return 0
    if args.command == "supersession":
        from .supersession import find_superseded
        result = find_superseded(args.queue, args.against, quiet=args.quiet, corpus_index=args.corpus_index)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        for record in result["mods"]:
            if record["verdict"] in ("SUPERSEDED", "SAME_RELEASE", "NEWER_ELSEWHERE", "NEWER_DIFFERENT"):
                ref = record["reference"]
                renamed = f" [named '{ref['name']}' there]" if ref.get("name") and ref["name"].strip().lower() != record["name"].strip().lower() else ""
                print(f"{record['verdict']:16} {record['workspace']}: ours {record['version']}, theirs {ref['version']} ({ref['game_version'] or 'no gameVersion'}) at {ref['path']}{renamed}")
                if record["verdict"] == "NEWER_DIFFERENT":
                    print(f"                 {record['note']}")
        print("Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(result["counts"].items())))
        print(f"Written: {result['result_path']}")
        return 0
    if args.command == "finding-stats":
        from .finding_stats import CHECKPOINT_NAME, FindingStatsError, finding_stats, render
        from .substitutes import REPO_ROOT
        checkpoint = args.write / CHECKPOINT_NAME if args.write and (args.scan or args.rescan_stale) else None
        if checkpoint and args.restart and checkpoint.is_file():
            checkpoint.unlink()

        def progress(done: int, total: int, record: dict, seconds: float, resumed: bool) -> None:
            if "unscanned" in record:
                detail = f"not scanned ({record['unscanned']})"
            else:
                detail = f"{sum(record['tiers'].values())} finding(s), bucket {record['bucket']}"
                if record["blocking"]:
                    detail += f", blocked by {', '.join(record['blocking'][:3])}" + (" ..." if len(record["blocking"]) > 3 else "")
            print(f"[{done}/{total}] {record['workspace']}: {detail}" + (" (from checkpoint)" if resumed else f" ({seconds:.1f}s)"), file=sys.stderr, flush=True)

        try:
            stats = finding_stats(args.roots or [REPO_ROOT / "In operation"], scan=args.scan, vanilla_core=args.vanilla_core,
                                  rescan_stale=args.rescan_stale, done_root=args.done or REPO_ROOT / "Done", checkpoint=checkpoint, progress=None if args.quiet else progress)
        except (FindingStatsError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if checkpoint and checkpoint.is_file():
            checkpoint.unlink()  # the run finished; FINDING_STATS.json now holds every record
        if args.promotion:
            from .finding_stats import discover_workspaces
            from .promotion import write_candidates
            workspaces = {w.name: w for w in discover_workspaces(args.roots or [REPO_ROOT / "In operation"])}
            print(f"Written: {write_candidates(args.promotion, stats['promote_to_fixer'], workspaces)}", file=sys.stderr)
        if args.write:
            args.write.mkdir(parents=True, exist_ok=True)
            from .finding_stats import delta, render_delta
            previous_path = args.write / "FINDING_STATS.json"
            try:
                previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else None
            except (OSError, json.JSONDecodeError):
                previous = None  # an unreadable earlier run just means no comparison
            if previous is not None:
                previous_path.replace(args.write / "FINDING_STATS.previous.json")
            previous_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            (args.write / "FINDING_STATS.md").write_text(render(stats) + (render_delta(delta(previous, stats)) if previous else ""), encoding="utf-8")
            print(f"Written: {args.write / 'FINDING_STATS.md'}", file=sys.stderr)
        print(json.dumps(stats, indent=2, ensure_ascii=False) if args.json else render(stats), end="\n" if args.json else "")
        return 0
    if args.command == "dependency-graph":
        from .substitutes import REPO_ROOT, dependency_graph
        queue = args.queue or REPO_ROOT / "In operation"
        roots = args.providers or [REPO_ROOT / "In operation", REPO_ROOT / "In operation" / "_rig" / "mods"]
        try:
            from .progress import report as print_progress
            checkpoint = Path(queue) / "DEPENDENCY_GRAPH.partial.jsonl" if args.write else None
            if checkpoint and args.restart and checkpoint.is_file():
                checkpoint.unlink()

            def graph_progress(done: int, total: int, name: str, report: dict, seconds: float | None) -> None:
                needs = [item["mod_id"] for item in report["provider_set"] if not item["targets_0.98a"]]
                print_progress(done, total, name, f"{report['strategy']}" + (f", needs {', '.join(needs)}" if needs else "")
                               + (f", {len(report['uncovered'])} unprovided" if report["uncovered"] else ""), seconds)

            result = dependency_graph(queue, roots, vanilla_core=args.vanilla_core, index_path=args.provider_index, write_reports=args.write,
                                      checkpoint=checkpoint, progress=None if args.quiet else graph_progress)
            if args.write:
                from .substitutes import write_dependency_graph
                for written in write_dependency_graph(result, queue):
                    print(f"Written: {written}", file=sys.stderr)
                if checkpoint.is_file():
                    checkpoint.unlink()
        except (ValueError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        print(f"{result['queued_mods']} queued mod(s) in {result['queue']}")
        for rank_number, entry in enumerate(result["revival_order"], 1):
            state = entry.get("workspace") or {}
            licence = (entry.get("licence") or {}).get("decision")
            print(f"{rank_number}. revive {entry['name']} ({entry['game_version'] or 'no version'}"
                  + (f", workspace {state['workspace']}: {state.get('manual_findings')} MANUAL" if state else ", not a workspace here")
                  + (f", licence {licence}" if licence else "") + f"): unblocks {len(entry['unblocks'])}: {', '.join(entry['unblocks'])}")
        for entry in result["unprovided"]:
            print(f"   {entry['workspace']}: no provider for {', '.join(entry['ids'][:6])}{' ...' if len(entry['ids']) > 6 else ''}")
        return 0
    if args.command == "corpus-recheck":
        from .corpus_recheck import corpus_recheck, render_markdown
        from .progress import report as print_progress
        checkpoint = args.repo_root.expanduser().resolve() / "In operation" / "CORPUS_RECHECK.partial.jsonl"
        if args.restart and checkpoint.is_file():
            checkpoint.unlink()

        def recheck_progress(done: int, total: int, mod: dict, seconds: float | None) -> None:
            detail = f"ERROR {mod['error']}" if "error" in mod else ", ".join(f"{count} {name}" for name, count in sorted(mod["by_classification"].items())) or "no findings"
            print_progress(done, total, mod["mod"], detail, seconds)

        result = corpus_recheck(args.repo_root, args.vanilla_core, require_report=not args.include_intake,
                                checkpoint=checkpoint if checkpoint.parent.is_dir() else None,
                                progress=None if args.quiet else recheck_progress)
        if checkpoint.is_file():
            checkpoint.unlink()  # the run finished
        if args.write_markdown:
            args.write_markdown.parent.mkdir(parents=True, exist_ok=True)
            args.write_markdown.write_text(render_markdown(result), encoding="utf-8")
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{result['status']}: {result['mod_count']} mod(s) with real revival work recorded")
            if result["regressions"]:
                print(f"  REGRESSION: {', '.join(result['regressions'])}")
            for mod in result["mods"]:
                if "error" in mod:
                    print(f"  ERROR {mod['mod']}: {mod['error']}")
                    continue
                manual = mod["by_classification"].get("MANUAL", 0)
                if manual:
                    print(f"  {mod['mod']}: {manual} MANUAL ({', '.join(mod['manual_ids'])})")
            if args.write_markdown:
                print(f"Roll-up written: {args.write_markdown}")
        return 1 if result["status"] == "REGRESSION" else 0
    if args.command == "sibling-assets":
        from .sibling_assets import SiblingAssetsError, fix_sibling_assets
        try:
            result = fix_sibling_assets(args.workspace, args.vanilla_core, apply=args.apply, roots=args.siblings or None)
        except (SiblingAssetsError, OSError, ValueError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            verb = "copied" if args.apply else "would copy"
            print(f"Searched {result['siblings_searched']} sibling root(s): {verb} {len(result['files'])} file(s) and {len(result['rows'])} description row(s).")
            for label in ("files_refused", "files_unresolved", "rows_refused", "rows_unresolved"):
                for item in result[label]:
                    print(f"  {label.replace('_', ' ')}: {item.get('path') or item.get('id')}: {item['reason']}")
        return 0
    if args.command == "vendor-copy" and args.plan is not None:
        from .vendor_plan import VendorPlanError, copy_plan
        if args.to is None or any(value is not None for value in (args.kind, args.id, args.from_provider, args.to_mod)):
            print("bridgeforge: with --plan, give only --to (the mod to copy into), no positional arguments", file=sys.stderr)
            return 2
        try:
            result = copy_plan(json.loads(args.plan.read_text(encoding="utf-8")), args.to, apply=args.apply,
                               allow_partial=args.allow_partial, policy_path=args.policy)
        except (VendorPlanError, OSError, json.JSONDecodeError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"{result['status']}" + (f": {result['reason']}" if result.get("reason") else ""))
            for label in ("files", "skipped_identical", "conflicts", "stale", "left_out"):
                for item in result.get(label) or []:
                    print(f"  {label.replace('_', ' ')}: {item}")
            for table, ids in (result.get("rows") or {}).items():
                print(f"  rows: {table} [{', '.join(ids)}]")
            for item in result.get("provenance") or []:
                print(f"  sha256 {item['sha256']}  {item['path']}")
            if result.get("must_stay_local_only"):
                print(f"  LICENCE: {result['licence_note']}")
        return 0 if result["status"] in ("PLANNED", "APPLIED") else 1
    if args.command == "vendor-copy":
        from .strip_plan import vendor_copy
        if None in (args.kind, args.id, args.from_provider, args.to_mod):
            print("bridgeforge: vendor-copy needs KIND ID FROM_PROVIDER TO_MOD, or --plan FILE --to DIR", file=sys.stderr)
            return 2
        result = vendor_copy(args.kind, args.id, args.from_provider, args.to_mod, args.policy, args.apply)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"{result['status']}" + (f": {result['reason']}" if result.get("reason") else ""))
            if result.get("files"):
                print(f"  files: {', '.join(result['files'])}")
            if result.get("note"):
                print(f"  note: {result['note']}")
            if result.get("must_stay_local_only"):
                print(f"  LICENCE: {result['licence_note']}")
        return 0 if result["status"] in ("PLANNED", "APPLIED") else 1
    if args.command == "revival-report-draft":
        from .revival_report_draft import draft_revival_report, write_revival_report_draft
        providers = args.providers or None
        if args.apply:
            result = write_revival_report_draft(args.mod, args.vanilla_core, providers, args.force)
        else:
            result = draft_revival_report(args.mod, args.vanilla_core, providers)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(result["status"])
            if result["status"] == "BLOCKED":
                for reason in result["blocking"]:
                    print(f"  {reason}")
            elif result["status"] == "REFUSED":
                print(f"  {result['reason']}")
                for path in result["existing"]:
                    print(f"  exists: {path}")
            elif result["status"] == "WRITTEN":
                print(f"  {result['report_path']}")
                print(f"  {result['plan_path']}")
            elif result["status"] == "OK":
                print(result["report_text"])
                print(result["plan_text"])
        return 0 if result["status"] in ("OK", "WRITTEN") else 1
    if args.command == "diff-data":
        from .data_diff import DataDiffError, diff_data
        try:
            result = diff_data(args.a, args.b)
        except DataDiffError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["identical"]:
                print(f"IDENTICAL ({result['kind']}): no value differences")
            for change in result["changes"]:
                if change["change"] == "added":
                    print(f"+ {change['path']}: {json.dumps(change['b'], ensure_ascii=False)}")
                elif change["change"] == "removed":
                    print(f"- {change['path']}: {json.dumps(change['a'], ensure_ascii=False)}")
                elif change["change"] == "reordered":
                    print(f"^ {change['path']}: same values, other order: {json.dumps(change['a'], ensure_ascii=False)} -> {json.dumps(change['b'], ensure_ascii=False)}")
                else:
                    print(f"~ {change['path']}: {json.dumps(change['a'], ensure_ascii=False)} -> {json.dumps(change['b'], ensure_ascii=False)}")
        return 0 if result["identical"] else 1
    if args.command == "rebuild-from-reference":
        from .rebuild_reference import RebuildReferenceError, rebuild_from_reference
        try:
            result = rebuild_from_reference(args.mod, args.reference_core, args.vanilla_core, args.file_classes, args.output)
        except (RebuildReferenceError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            counts = ", ".join(f"{status} {count}" for status, count in sorted(result["counts"].items())) or "no shadowed files"
            print(f"REBUILD_FROM_REFERENCE ({', '.join(result['file_classes'])}): {counts}")
            for entry in result["files"]:
                if entry["status"] == "CONFLICT":
                    print(f"  CONFLICT {entry['file']}: " + "; ".join(c["path"] for c in entry["conflicts"][:5])
                          + (f" (+{len(entry['conflicts']) - 5} more)" if len(entry["conflicts"]) > 5 else ""))
                elif entry["status"] == "UNPARSEABLE":
                    print(f"  UNPARSEABLE {entry['file']}")
            for name in result["vanilla_removed_in_rc8"]:
                print(f"  vanilla removed in RC8 (now the mod's own content): {name}")
            if result["output"]:
                print(f"MERGED files written under: {result['output']}")
        return 1 if result["counts"].get("CONFLICT") or result["counts"].get("UNPARSEABLE") else 0
    if args.command == "corpus-index":
        from .corpus_index import CorpusIndexError, build_index, search_index
        try:
            if args.corpus_index_command == "build":
                def corpus_progress(done: int, total: int, source: str, status: str, seconds: float) -> None:
                    if status == "indexed":
                        print(f"[{done}/{total}] indexed {source} ({seconds:.1f}s)", file=sys.stderr, flush=True)
                    elif done % 500 == 0 or done == total:
                        print(f"[{done}/{total}] ... unchanged files skipped", file=sys.stderr, flush=True)

                result = build_index(args.root, args.db, args.max_bytes, progress=None if args.quiet else corpus_progress)
            else:
                result = search_index(args.db, args.text, args.limit, args.names)
        except CorpusIndexError as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if args.corpus_index_command == "build" or result["content_hits"] or result["name_hits"] else 1
        if args.corpus_index_command == "build":
            print(f"Indexed {result['root']} -> {result['db']}: {result['reindexed']} read, {result['unchanged']} unchanged, {result['forgotten']} gone")
        else:
            for hit in result["content_hits"]:
                print(f"{hit['location']} ({hit['line_count']} matching line(s))")
                for line in hit["lines"]:
                    print(f"    {line}")
            for name in result["name_hits"]:
                print(f"name: {name}")
            if not result["content_hits"] and not result["name_hits"]:
                print(f"No hits for {args.text!r}.")
            if len(result["content_hits"]) >= result["limit"] or len(result["name_hits"]) >= result["limit"]:
                print(f"(stopped at --limit {result['limit']})")
        not_searched = ", ".join(f"{count} {reason}" for reason, count in result["not_searched"].items())
        print(f"Coverage: {result['text_files_searched']} text files searched, {result['files_listed']} files listed by name"
              + (f"; NOT searched: {not_searched}" if not_searched else "; nothing skipped"))
        return 0 if args.corpus_index_command == "build" or result["content_hits"] or result["name_hits"] else 1
    if args.command == "content-diff":
        from .content_diff import ContentDiffError, diff_content
        try:
            result = diff_content(args.reference_core, args.vanilla_core)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except (ContentDiffError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for kind, count in result["counts"].items():
                print(f"{kind}: {count['reference']} -> {count['rc8']} ({count['removed']} removed, {count['added']} added)")
            for kind, entries in result["removed"].items():
                for entry in entries[:30]:
                    leads = entry["same_name_in_rc8"]
                    print(f"  - {kind}:{entry['id']}" + (f" ({entry['name']})" if entry.get("name") else "") + (f" -> same name in RC8: {', '.join(leads)}" if leads else ""))
                if len(entries) > 30:
                    print(f"  ... {len(entries) - 30} more {kind} ids (see --output/--json)")
            if args.output:
                print(f"Written: {args.output}")
        return 0
    if args.command == "verify-shadow":
        from .verify_shadow import VerifyShadowError, verify_shadow
        try:
            result = verify_shadow(args.scripts, args.against)
        except (VerifyShadowError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            for entry in result["results"]:
                print(f"{entry['status']}: {entry['script']} (class {entry['class']}, from {entry['class_from']})")
                for owner in entry["supplied_by"]:
                    print(f"    supplied by {owner}")
            print(f"Checked {result['classes_checked']} classes in {result['jars_checked']} jar(s).")
            for problem in result["unreadable_jars"]:
                print(f"  NOT checked: {problem}")
        return 0
    if args.command == "vendor-plan":
        from .substitutes import REPO_ROOT
        from .vendor_plan import VendorPlanError, dumps, render, vendor_plan
        target = args.target
        if target is None and (REPO_ROOT / "In operation" / "RevenantLib").is_dir():
            target = REPO_ROOT / "In operation" / "RevenantLib"
        try:
            plan = vendor_plan(args.provider, args.ids, target=target, vanilla_core=args.vanilla_core)
        except (VendorPlanError, OSError) as exc:
            print(f"bridgeforge: {exc}", file=sys.stderr)
            return 2
        print(dumps(plan) if args.json else render(plan))
        return 0
    return 2
